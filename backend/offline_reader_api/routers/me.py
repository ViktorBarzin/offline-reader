"""/api/me: who the PWA is talking to, so it can name the Person to Rybbit (ADR-0007)."""

from fastapi import APIRouter, Depends, Request

from offline_reader_api.auth import current_username, person_id
from offline_reader_api.schemas import MeOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
async def me(request: Request, username: str = Depends(current_username)) -> MeOut:
    """The signed-in username and their Person id (Authentik ``uid``), when known."""
    return MeOut(username=username, person_id=person_id(request.scope))
