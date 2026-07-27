"""Persistent state: one row per Capture (the unit of the Library).

The row is the source of truth for the Library; the captured Pages + manifest
live on the PVC beside it (``captures/<id>/``). A TTL-reaped Job loses live
progress detail but the row and the Pages persist (ADR-0002).
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from offline_reader_api.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Capture(Base):
    """A saved website — one root URL crawled into self-contained Pages."""

    __tablename__ = "captures"

    # uuid4 hex — also the directory name under ``captures/``.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    root_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    # One of page | prefix | host | domain (see schemas.ScopeType).
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    # One of queued | crawling | done | failed (see schemas.CaptureStatus).
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The runner's handle for the in-flight crawl (a K8s Job name); None until started.
    job_name: Mapped[str | None] = mapped_column(String(253), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
