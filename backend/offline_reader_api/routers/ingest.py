"""/api/ingest — token-authed capture creation for the iOS Shortcut (no SSO).

Unlike the rest of /api (gated by Authentik forward-auth), this endpoint is
reachable without the ``X-Authentik-Username`` header — ``AuthentikUserMiddleware``
exempts the exact path ``/api/ingest`` — because it authenticates a shared secret
(``INGEST_TOKEN``) instead, presented as ``?token=`` or the ``X-Ingest-Token``
header. On success it creates a Capture via the same ``CaptureService.create``
path as ``POST /api/captures``.
"""

import secrets

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from offline_reader_api.config import get_settings
from offline_reader_api.deps import get_service, get_session
from offline_reader_api.errors import ApiError
from offline_reader_api.schemas import CaptureOut, IngestCreate
from offline_reader_api.service import CaptureService

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=CaptureOut, status_code=201)
async def ingest_capture(
    body: IngestCreate,
    token: str | None = Query(default=None),
    x_ingest_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    service: CaptureService = Depends(get_service),
) -> CaptureOut:
    """Create a Capture from a shared URL, authenticated by ``INGEST_TOKEN``.

    503 when no ``INGEST_TOKEN`` is configured (feature disabled); 401 when the
    presented token is missing or wrong (constant-time compare).
    """
    expected = get_settings().ingest_token
    if not expected:
        raise ApiError(503, "ingest_disabled", "ingest disabled: no INGEST_TOKEN configured")
    presented = token or x_ingest_token
    if not presented or not secrets.compare_digest(presented, expected):
        raise ApiError(401, "unauthorized", "invalid or missing ingest token")
    capture = await service.create(session, body)
    return CaptureOut.model_validate(capture)
