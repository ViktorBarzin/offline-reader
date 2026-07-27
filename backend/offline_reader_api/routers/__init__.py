"""The /api router tree. Every route requires the Authentik identity."""

from fastapi import APIRouter

from offline_reader_api.routers import captures

api_router = APIRouter()
api_router.include_router(captures.router)
