"""Identity: trust Authentik's forward-auth header on /api routes.

Traefik + Authentik (``auth = "required"`` in the ingress) gate every request in
production, so the backend's only job is to read ``X-Authentik-Username``.
/api requests without it are rejected with 401; the ``DEV_USER`` env var is the
dev/test fallback (never set in production).
"""

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from offline_reader_api.config import USERNAME_HEADER, get_settings
from offline_reader_api.errors import error_response


class AuthentikUserMiddleware(BaseHTTPMiddleware):
    """Reject /api requests without an identity; stash the username on ``request.state``."""

    async def dispatch(
        self, request: StarletteRequest, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        # /api/ingest does its own token auth (INGEST_TOKEN) and must be
        # reachable with no Authentik SSO header — exempt it from the check.
        if path == "/api/ingest":
            return await call_next(request)
        if path == "/api" or path.startswith("/api/"):
            username = request.headers.get(USERNAME_HEADER) or get_settings().dev_user
            if not username:
                return error_response(401, "unauthorized", f"missing {USERNAME_HEADER} header")
            request.state.username = username
        return await call_next(request)


def current_username(request: Request) -> str:
    """Dependency: the authenticated username (set by :class:`AuthentikUserMiddleware`)."""
    username: str | None = getattr(request.state, "username", None)
    if username is None:
        # Defence in depth — only reachable if a route outside /api uses this dependency.
        raise HTTPException(status_code=401, detail=f"missing {USERNAME_HEADER} header")
    return username
