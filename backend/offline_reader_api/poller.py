"""Optional background poller: advances in-flight Captures without a client GET.

Enabled when ``CAPTURE_POLL_INTERVAL_SECONDS > 0``. The PWA also polls GET
/captures/{id}, which advances state too, so this is a belt-and-braces backstop
(and the hook for a future finish-notification). Disabled (0) by default and in
tests for deterministic, lock-free SQLite behaviour.
"""

import logging

import anyio
from fastapi import FastAPI
from sqlalchemy import select

from offline_reader_api.models import Capture
from offline_reader_api.service import CaptureService

logger = logging.getLogger(__name__)


async def poll_loop(app: FastAPI, interval: float) -> None:
    """Every *interval* seconds, advance every queued/crawling Capture once."""
    while True:
        await anyio.sleep(interval)
        try:
            service: CaptureService = app.state.capture_service
            async with app.state.session_factory() as session:
                result = await session.execute(
                    select(Capture).where(Capture.status.in_(["queued", "crawling"]))
                )
                for capture in list(result.scalars().all()):
                    await service.advance(session, capture)
        except Exception:  # a poll error must never kill the loop
            logger.exception("capture poller iteration failed")
