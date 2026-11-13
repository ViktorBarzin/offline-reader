"""/api/signin: where the PWA's "Sign in" link goes when the SSO session has lapsed.

The link must leave the app shell, because the service worker answers every
other navigation from its precache and the browser would never reach Authentik.
It sits under /api, which the worker always sends to the network and which
forward-auth gates. A request that reaches this route therefore carries a fresh
session, and the route only sends the browser back to the app.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from offline_reader_api.auth import current_username

router = APIRouter(prefix="/signin", tags=["signin"])


@router.get("", include_in_schema=False)
async def signin(_username: str = Depends(current_username)) -> RedirectResponse:
    return RedirectResponse("/", status_code=302)
