"""The /api router tree. Every route requires the Authentik identity."""

from fastapi import APIRouter

from offline_reader_api.routers import captures, me, signin

api_router = APIRouter()
api_router.include_router(captures.router)
api_router.include_router(me.router)
api_router.include_router(signin.router)
