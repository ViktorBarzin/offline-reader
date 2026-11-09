"""Identity: trust Authentik's forward-auth header on /api routes.

Traefik + Authentik (``auth = "required"`` in the ingress) gate every request in
production, so the backend's only job is to read ``X-Authentik-Username``.
/api requests without it are rejected with 401; the ``DEV_USER`` env var is the
dev/test fallback (never set in production).

The same forward-auth sets ``X-Authentik-Uid``, the user's Authentik hashed user
id: the Person id the telemetry standard names people by (ADR-0007). Traefik
overwrites both headers on every gated route, so neither can be forged there.
``/api/ingest`` is the one route outside the gate, so a uid on it is ignored.
"""

from collections.abc import MutableMapping

from fastapi import HTTPException, Request
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response

from offline_reader_api.config import PERSON_HEADER, USERNAME_HEADER, get_settings
from offline_reader_api.errors import error_response

#: The one /api route that does its own token auth instead of Authentik's.
INGEST_PATH = "/api/ingest"


def person_id(scope: MutableMapping[str, object]) -> str | None:
    """The Person id (Authentik ``uid``) a request comes from, or None.

    For ``EnduserMiddleware`` and ``GET /api/me``. None outside HTTP, on
    ``/api/ingest`` (not behind forward-auth) and when the header is absent,
    as it is with the ``DEV_USER`` fallback.
    """
    if scope.get("type") not in ("http", "websocket") or scope.get("path") == INGEST_PATH:
        return None
    value = Headers(scope=scope).get(PERSON_HEADER, "").strip()
    return value or None


class AuthentikUserMiddleware(BaseHTTPMiddleware):
    """Reject /api requests without an identity; stash the username on ``request.state``."""

    async def dispatch(
        self, request: StarletteRequest, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        # /api/ingest does its own token auth (INGEST_TOKEN) and must be
        # reachable with no Authentik SSO header — exempt it from the check.
        if path == INGEST_PATH:
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
