"""Pydantic models for the API contract. The PWA and this backend build against
exactly these shapes. All routes live under /api behind Authentik identity."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The Scope decides which pages a Crawl includes (CONTEXT.md): page = just the
# root; prefix = the root URL's path prefix (default); host = same host; domain
# = the registrable domain.
ScopeType = Literal["page", "prefix", "host", "domain"]

# queued (row created) -> crawling (Job running) -> done | failed (terminal).
CaptureStatus = Literal["queued", "crawling", "done", "failed"]


class CaptureCreate(BaseModel):
    """POST /api/captures request body."""

    url: str
    scope_type: ScopeType = "prefix"
    max_pages: int = Field(default=1000, ge=1, le=100_000)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def _require_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("url must be an absolute http(s) URL")
        return value


class IngestCreate(CaptureCreate):
    """POST /api/ingest request body — the token-authed iOS-Shortcut path.

    Same shape and validation as :class:`CaptureCreate` (notably the http(s) URL
    check), but ``scope_type`` defaults to ``page``: a shared link is usually a
    single article, so capture exactly what was shared rather than crawling a
    prefix.
    """

    scope_type: ScopeType = "page"


class CaptureOut(BaseModel):
    """A Capture as served by the API (summary and detail are the same shape)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    root_url: str
    title: str
    scope_type: str
    max_pages: int
    status: str
    page_count: int
    size_bytes: int
    job_name: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class ManifestPage(BaseModel):
    """One Page in a Capture's manifest."""

    # Stable slug: sha1(original url)[:12] — the id in the pages/{page_id} route.
    id: str
    url: str
    title: str
    # Filename within ``captures/<cid>/pages/``.
    file: str
    depth: int


class Manifest(BaseModel):
    """``captures/<cid>/manifest.json`` — the reader's table of contents."""

    cid: str
    root_url: str
    title: str
    scope_type: str
    created_at: str
    pages: list[ManifestPage]
