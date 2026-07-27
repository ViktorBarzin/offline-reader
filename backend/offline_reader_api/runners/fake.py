"""FakeRunner — a deterministic, cluster-free CaptureRunner for dev and tests.

``start`` writes a small fixture Capture (two self-contained Pages + a
single-file-style ``session.json``) to the PVC layout, then reports ``crawling``.
``poll`` reports the current fixture state; tests drive terminal transitions via
:meth:`complete` / :meth:`fail`. Because it writes real files in the real
layout, the manifest builder and the Page-serving routes exercise the true code
path with no cluster.
"""

import json
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from offline_reader_api import storage
from offline_reader_api.config import Settings
from offline_reader_api.models import Capture
from offline_reader_api.runner import CaptureProgress

_PAGE_TEMPLATE = (
    "<!-- Page saved with SingleFile url: {url} -->\n"
    "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<title>{title}</title></head>\n"
    "<body><h1>{title}</h1><p>Captured fixture page.</p>{links}</body></html>\n"
)


@dataclass
class _FakeJob:
    status: str = "crawling"
    error: str | None = None


@dataclass
class FakeRunner:
    """In-memory job table + on-disk fixture output."""

    settings: Settings
    jobs: dict[str, _FakeJob] = field(default_factory=dict)

    def start(self, capture: Capture) -> str:
        self._write_fixture(capture)
        self.jobs[capture.id] = _FakeJob(status="crawling")
        return f"fake-job-{capture.id[:12]}"

    def poll(self, capture: Capture) -> CaptureProgress:
        job = self.jobs.get(capture.id)
        if job is None:
            return CaptureProgress(status="queued", page_count=0, size_bytes=0)
        # Dev convenience (FAKE_AUTO_COMPLETE): finish on the first poll so a local
        # run without a cluster reaches `done`. Off by default; tests drive complete().
        if job.status == "crawling" and self.settings.fake_auto_complete:
            job.status = "done"
        count, size = storage.count_pages(storage.pages_dir(self.settings.data_dir, capture.id))
        return CaptureProgress(
            status=job.status, page_count=count, size_bytes=size, error=job.error
        )

    def cancel(self, capture: Capture) -> None:
        self.jobs.pop(capture.id, None)

    # --- test / dev hooks: drive the canned progression -----------------------
    def complete(self, cid: str) -> None:
        """Mark a fake crawl finished (Pages are already on disk from ``start``)."""
        self.jobs.setdefault(cid, _FakeJob()).status = "done"

    def fail(self, cid: str, error: str = "fake capture failed") -> None:
        job = self.jobs.setdefault(cid, _FakeJob())
        job.status = "failed"
        job.error = error

    # --- fixture writing ------------------------------------------------------
    def _write_fixture(self, capture: Capture) -> None:
        data_dir = self.settings.data_dir
        cid = capture.id
        root = capture.root_url
        host = urlparse(root).netloc or "capture"
        base = root if root.endswith("/") else root + "/"
        child = urljoin(base, "page-2")

        pages = storage.pages_dir(data_dir, cid)
        pages.mkdir(parents=True, exist_ok=True)
        (pages / "index.html").write_text(
            _PAGE_TEMPLATE.format(
                url=root,
                title=f"{host} — Home",
                links=f'<a href="{child}">Page Two</a>',
            ),
            encoding="utf-8",
        )
        (pages / "page-2.html").write_text(
            _PAGE_TEMPLATE.format(url=child, title="Page Two", links=""),
            encoding="utf-8",
        )
        session = [
            {
                "url": root,
                "originalUrl": root,
                "filename": "index.html",
                "depth": 0,
                "status": "processed",
            },
            {
                "url": child,
                "originalUrl": child,
                "filename": "page-2.html",
                "depth": 1,
                "status": "processed",
            },
        ]
        (storage.capture_dir(data_dir, cid) / "session.json").write_text(
            json.dumps(session), encoding="utf-8"
        )
