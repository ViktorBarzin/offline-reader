"""App factory: /healthz + /metrics + /api/* + (when built) the SvelteKit PWA —
one same-origin image (the tripit/tasks pattern)."""

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from offline_reader_api import __version__, db
from offline_reader_api.auth import AuthentikUserMiddleware
from offline_reader_api.config import get_settings
from offline_reader_api.errors import install_error_handlers
from offline_reader_api.logging_setup import configure_logging
from offline_reader_api.poller import poll_loop
from offline_reader_api.routers import api_router
from offline_reader_api.routers.ingest import router as ingest_router
from offline_reader_api.runner import build_runner
from offline_reader_api.service import CaptureService

# backend/offline_reader_api/app.py -> repo root -> frontend/build (adapter-static).
FRONTEND_BUILD_DIR = Path(__file__).resolve().parents[2] / "frontend" / "build"


class _SpaStaticFiles(StaticFiles):
    """Static files for the SvelteKit PWA, falling back to index.html.

    A client-side route (e.g. /library/abc) has no backing file and must serve
    index.html so the SPA router takes over. A genuinely missing *asset* (a path
    whose final segment has a file extension) still 404s, so the browser never
    loads HTML where it expects JS/CSS.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not Path(path).suffix and self.directory is not None:
                index = Path(self.directory) / "index.html"
                if index.is_file():
                    return FileResponse(index)
            raise


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the DB + capture runner for the app's lifetime; create the SQLite
    schema in-process (no migration tool). Optionally start the poller."""
    settings = get_settings()
    os.makedirs(settings.captures_dir, exist_ok=True)
    engine = db.create_engine(settings.db_dsn)
    if engine.dialect.name == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
    app.state.settings = settings
    app.state.db_engine = engine
    app.state.session_factory = db.create_session_factory(engine)
    runner = build_runner(settings)
    app.state.capture_runner = runner
    app.state.capture_service = CaptureService(settings, runner)

    poller_task: asyncio.Task[None] | None = None
    if settings.poll_interval_seconds > 0:
        poller_task = asyncio.create_task(poll_loop(app, settings.poll_interval_seconds))
    try:
        yield
    finally:
        if poller_task is not None:
            poller_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poller_task
        await engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI app: /healthz, /metrics, /api/*, and the PWA at /.

    Docs/schema live UNDER /api so the forward-auth-gated ingress covers them —
    the public root ("/") is the PWA, and root-level /docs would leak the schema.
    """
    configure_logging()
    app = FastAPI(
        title="offline-reader",
        version=__version__,
        lifespan=_lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(AuthentikUserMiddleware)
    install_error_handlers(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    app.include_router(api_router, prefix="/api")
    # Wired separately (not under the identity-gated api_router): /api/ingest
    # authenticates a token, not the Authentik SSO header (see routers/ingest.py).
    app.include_router(ingest_router, prefix="/api")

    # Serve the built PWA when present — absent in dev (vite proxies to us) and
    # in backend-only test runs. Mounted LAST so /api, /healthz, /metrics win.
    if FRONTEND_BUILD_DIR.is_dir():
        app.mount("/", _SpaStaticFiles(directory=FRONTEND_BUILD_DIR, html=True), name="spa")

    return app


app = create_app()
