"""FastAPI dependencies: the DB session and the process-wide CaptureService."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from offline_reader_api.service import CaptureService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_service(request: Request) -> CaptureService:
    service: CaptureService = request.app.state.capture_service
    return service
