"""Capture service: create / list / advance / delete / refresh, plus manifest
and Page resolution. Owns the SQLite row and its on-PVC directory together.

Runner calls (start/poll/cancel) and filesystem work run on a worker thread so
the event loop is never blocked. Status advances two ways: on GET of a capture
(``advance``) and, if enabled, by the background poller — both idempotent.
"""

import json
import logging
import uuid
from pathlib import Path

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from offline_reader_api import manifest as manifest_mod
from offline_reader_api import storage
from offline_reader_api.config import Settings
from offline_reader_api.models import Capture
from offline_reader_api.runner import CaptureRunner
from offline_reader_api.schemas import CaptureCreate, Manifest

logger = logging.getLogger(__name__)

_TERMINAL = {"done", "failed"}


class CaptureService:
    """Orchestrates Captures over a :class:`CaptureRunner` and the PVC store."""

    def __init__(self, settings: Settings, runner: CaptureRunner) -> None:
        self.settings = settings
        self.runner = runner

    async def create(self, session: AsyncSession, req: CaptureCreate) -> Capture:
        """Create a queued Capture, then start its crawl (-> crawling)."""
        capture = Capture(
            id=uuid.uuid4().hex,
            root_url=req.url,
            title=req.url,
            scope_type=req.scope_type,
            max_pages=req.max_pages,
            status="queued",
            page_count=0,
            size_bytes=0,
        )
        session.add(capture)
        await session.commit()
        await self._start(session, capture)
        return capture

    async def get(self, session: AsyncSession, cid: str) -> Capture | None:
        return await session.get(Capture, cid)

    async def list_all(self, session: AsyncSession) -> list[Capture]:
        result = await session.execute(select(Capture).order_by(Capture.created_at.desc()))
        return list(result.scalars().all())

    async def advance(self, session: AsyncSession, capture: Capture) -> Capture:
        """Refresh a queued/crawling Capture's status from the runner. On done,
        build the manifest and record final page_count/size; terminal is sticky."""
        if capture.status in _TERMINAL:
            return capture
        progress = await anyio.to_thread.run_sync(self.runner.poll, capture)
        capture.page_count = progress.page_count
        capture.size_bytes = progress.size_bytes
        if progress.status == "done":
            manifest = await anyio.to_thread.run_sync(self._build_manifest, capture)
            capture.title = manifest.title
            capture.status = "done"
            capture.error = None
        elif progress.status == "failed":
            capture.status = "failed"
            capture.error = progress.error or "capture failed"
        else:
            capture.status = "crawling"
        await session.commit()
        return capture

    async def delete(self, session: AsyncSession, capture: Capture) -> None:
        """Cancel the crawl (best effort), delete the files, drop the row."""
        await anyio.to_thread.run_sync(self._cancel_quietly, capture)
        await anyio.to_thread.run_sync(storage.remove_capture, self.settings.data_dir, capture.id)
        await session.delete(capture)
        await session.commit()

    async def refresh(self, session: AsyncSession, capture: Capture) -> Capture:
        """Re-crawl and replace: cancel + wipe old Pages, reset to queued, restart."""
        await anyio.to_thread.run_sync(self._cancel_quietly, capture)
        await anyio.to_thread.run_sync(storage.remove_capture, self.settings.data_dir, capture.id)
        capture.status = "queued"
        capture.page_count = 0
        capture.size_bytes = 0
        capture.error = None
        capture.job_name = None
        await session.commit()
        await self._start(session, capture)
        return capture

    # --- manifest / page resolution ------------------------------------------
    def manifest_file(self, cid: str) -> Path:
        return storage.capture_dir(self.settings.data_dir, cid) / "manifest.json"

    def page_file(self, cid: str, page_id: str) -> Path | None:
        """The on-disk Page for a manifest ``page_id`` (None if unknown/missing)."""
        manifest_path = self.manifest_file(cid)
        if not manifest_path.is_file():
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        for page in data.get("pages", []):
            if page.get("id") == page_id:
                candidate = storage.pages_dir(self.settings.data_dir, cid) / page["file"]
                return candidate if candidate.is_file() else None
        return None

    # --- internals ------------------------------------------------------------
    async def _start(self, session: AsyncSession, capture: Capture) -> None:
        try:
            job_name = await anyio.to_thread.run_sync(self.runner.start, capture)
            capture.status = "crawling"
            capture.job_name = job_name
            capture.error = None
        except Exception as exc:  # surface any runner failure as a failed Capture
            logger.exception("failed to start capture", extra={"capture_id": capture.id})
            capture.status = "failed"
            capture.error = f"failed to start capture: {exc}"
        await session.commit()

    def _build_manifest(self, capture: Capture) -> Manifest:
        return manifest_mod.build_manifest(
            storage.capture_dir(self.settings.data_dir, capture.id),
            cid=capture.id,
            root_url=capture.root_url,
            title=capture.title,
            scope_type=capture.scope_type,
            created_at=capture.created_at.isoformat(),
        )

    def _cancel_quietly(self, capture: Capture) -> None:
        try:
            self.runner.cancel(capture)
        except Exception:  # cancellation is best-effort
            logger.warning("failed to cancel capture", extra={"capture_id": capture.id})
