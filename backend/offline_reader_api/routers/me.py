"""/api/me: who the PWA is talking to, so it can name the Person to Rybbit (ADR-0007)."""

from fastapi import APIRouter, Depends, Request

from offline_reader_api import __version__, product_events
from offline_reader_api.auth import current_username, person_id
from offline_reader_api.schemas import BrowserTelemetryOut, MeOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
async def me(request: Request, username: str = Depends(current_username)) -> MeOut:
    """The signed-in username, their Person id (Authentik ``uid``) when known, and
    the Write key the PWA's own events go with while events are on."""
    write_key = product_events.browser_write_key()
    telemetry = BrowserTelemetryOut(write_key=write_key, release=__version__) if write_key else None
    return MeOut(username=username, person_id=person_id(request.scope), telemetry=telemetry)
