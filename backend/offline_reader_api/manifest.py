"""Build ``manifest.json`` from a finished crawl — pure and unit-tested.

The manifest is the reader's table of contents: one entry per captured Page,
each with a stable id (``sha1(url)[:12]``), its original url, its ``<title>``,
its filename, and its crawl depth, ordered by depth then url.

Input is single-file-cli's ``--crawl-save-session`` file: a JSON array of task
objects carrying ``url`` / ``originalUrl`` / ``filename`` / ``depth`` / ``status``.
If the session is missing or unusable we fall back to scanning ``pages/*.html``
and reading the URL from single-file's ``url:`` header comment — so a manifest
is always buildable from whatever Pages landed (partial captures included).
"""

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from offline_reader_api.schemas import Manifest, ManifestPage

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# single-file writes a header comment: "<!-- Page saved with SingleFile url: <url> ... -->".
_SINGLEFILE_URL_RE = re.compile(r"\burl:\s*(\S+)")


def page_id(url: str) -> str:
    """Stable slug for a Page: first 12 hex chars of sha1(url)."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _extract_title(page_html: str) -> str | None:
    match = _TITLE_RE.search(page_html)
    if match is None:
        return None
    title = html.unescape(match.group(1)).strip()
    return title or None


def _extract_singlefile_url(page_html: str) -> str | None:
    head = page_html[:4096]
    match = _SINGLEFILE_URL_RE.search(head)
    return match.group(1) if match else None


def _session_path(capture_dir: Path) -> Path | None:
    """single-file writes the session into the output dir; we keep it at the
    Capture root, but tolerate either location."""
    for candidate in (capture_dir / "session.json", capture_dir / "pages" / "session.json"):
        if candidate.is_file():
            return candidate
    return None


def _load_session_entries(capture_dir: Path) -> list[tuple[str, str, int]]:
    """Return ``(url, filename, depth)`` per crawled Page from the session file."""
    path = _session_path(capture_dir)
    if path is None:
        return []
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return []
    items: Any
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        # Be tolerant of an object wrapper around the task list.
        items = next(
            (raw[k] for k in ("tasks", "pages", "entries") if isinstance(raw.get(k), list)),
            [],
        )
    else:
        items = []
    entries: list[tuple[str, str, int]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if not filename:
            continue  # still processing / never saved
        url = item.get("url") or item.get("originalUrl") or ""
        depth_raw = item.get("depth", 0)
        depth = depth_raw if isinstance(depth_raw, int) else 0
        entries.append((str(url), Path(str(filename)).name, depth))
    return entries


def _scan_pages(pages: Path) -> list[tuple[str, str, int]]:
    """Fallback: derive entries straight from the Page files on disk."""
    entries: list[tuple[str, str, int]] = []
    if not pages.is_dir():
        return entries
    for file in sorted(pages.glob("*.html")):
        page_html = file.read_text(encoding="utf-8", errors="replace")
        url = _extract_singlefile_url(page_html) or file.name
        entries.append((url, file.name, 0))
    return entries


def _pick_capture_title(pages: list[ManifestPage], root_url: str, fallback: str) -> str:
    """The Capture's title = the root Page's title (matched loosely on url),
    else the shallowest Page's, else the caller's fallback."""
    roots = {root_url, root_url.rstrip("/"), root_url.rstrip("/") + "/"}
    for page in pages:
        if page.url in roots and page.title and page.title != page.url:
            return page.title
    for page in pages:  # pages are already sorted by (depth, url)
        if page.title and page.title != page.url:
            return page.title
    return fallback


def build_manifest(
    capture_dir: Path,
    *,
    cid: str,
    root_url: str,
    title: str,
    scope_type: str,
    created_at: str,
) -> Manifest:
    """Read the session + Pages under *capture_dir*, write ``manifest.json``,
    and return the :class:`Manifest`."""
    pages = capture_dir / "pages"
    entries = _load_session_entries(capture_dir) or _scan_pages(pages)

    manifest_pages: list[ManifestPage] = []
    seen: set[str] = set()
    for url, filename, depth in entries:
        page_path = pages / filename
        if not page_path.is_file():
            continue
        page_html = page_path.read_text(encoding="utf-8", errors="replace")
        resolved_url = url or _extract_singlefile_url(page_html) or filename
        pid = page_id(resolved_url)
        if pid in seen:
            continue  # same original url captured twice — keep the first
        seen.add(pid)
        page_title = _extract_title(page_html) or resolved_url
        manifest_pages.append(
            ManifestPage(id=pid, url=resolved_url, title=page_title, file=filename, depth=depth)
        )

    manifest_pages.sort(key=lambda p: (p.depth, p.url))
    manifest = Manifest(
        cid=cid,
        root_url=root_url,
        title=_pick_capture_title(manifest_pages, root_url, title),
        scope_type=scope_type,
        created_at=created_at,
        pages=manifest_pages,
    )
    (capture_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    return manifest
