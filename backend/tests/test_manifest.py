"""Unit tests for build_manifest: title extraction, id stability, ordering,
and the pages-scan fallback when the session file is absent."""

import hashlib
import json
from pathlib import Path

from offline_reader_api.manifest import build_manifest, page_id
from offline_reader_api.schemas import Manifest

ROOT_URL = "https://docs.example.com/"
CREATED_AT = "2026-07-27T00:00:00+00:00"


def _page(url: str, title: str | None) -> str:
    title_tag = f"<title>{title}</title>" if title is not None else ""
    return (
        f"<!-- Page saved with SingleFile url: {url} -->\n"
        f"<!doctype html><html><head><meta charset='utf-8'>{title_tag}</head>"
        f"<body>content of {url}</body></html>\n"
    )


def _write_capture(tmp_path: Path, *, with_session: bool = True) -> Path:
    capture_dir = tmp_path / "captures" / "cap1"
    pages = capture_dir / "pages"
    pages.mkdir(parents=True)
    (pages / "index.html").write_text(_page(ROOT_URL, "Docs Home"), encoding="utf-8")
    (pages / "guide.html").write_text(
        _page("https://docs.example.com/guide", "Guide &amp; Tips"), encoding="utf-8"
    )
    (pages / "intro.html").write_text(
        _page("https://docs.example.com/intro", None), encoding="utf-8"
    )
    if with_session:
        session = [
            {"url": "https://docs.example.com/guide", "filename": "guide.html", "depth": 1,
             "status": "processed"},
            {"url": ROOT_URL, "originalUrl": ROOT_URL, "filename": "index.html", "depth": 0,
             "status": "processed"},
            {"url": "https://docs.example.com/intro", "filename": "intro.html", "depth": 1,
             "status": "processed"},
            # Still-processing entry with no filename yet -> excluded.
            {"url": "https://docs.example.com/pending", "depth": 2, "status": "processing"},
        ]
        (capture_dir / "session.json").write_text(json.dumps(session), encoding="utf-8")
    return capture_dir


def _build(capture_dir: Path) -> Manifest:
    return build_manifest(
        capture_dir,
        cid="cap1",
        root_url=ROOT_URL,
        title=ROOT_URL,
        scope_type="prefix",
        created_at=CREATED_AT,
    )


def test_page_id_is_stable_sha1_prefix() -> None:
    assert page_id(ROOT_URL) == hashlib.sha1(ROOT_URL.encode()).hexdigest()[:12]


def test_manifest_orders_by_depth_then_url(tmp_path: Path) -> None:
    manifest = _build(_write_capture(tmp_path))
    urls = [p.url for p in manifest.pages]
    # depth 0 first, then the two depth-1 pages ordered by url.
    assert urls == [
        ROOT_URL,
        "https://docs.example.com/guide",
        "https://docs.example.com/intro",
    ]


def test_titles_are_extracted_and_unescaped(tmp_path: Path) -> None:
    manifest = _build(_write_capture(tmp_path))
    by_url = {p.url: p for p in manifest.pages}
    assert by_url["https://docs.example.com/guide"].title == "Guide & Tips"
    # No <title> -> falls back to the url.
    assert by_url["https://docs.example.com/intro"].title == "https://docs.example.com/intro"
    # Capture title = the root page's <title>.
    assert manifest.title == "Docs Home"


def test_ids_stable_across_rebuilds(tmp_path: Path) -> None:
    first = _build(_write_capture(tmp_path))
    ids_first = [p.id for p in first.pages]
    second = _build(tmp_path / "captures" / "cap1")
    assert [p.id for p in second.pages] == ids_first
    assert ids_first[0] == page_id(ROOT_URL)


def test_manifest_written_to_disk(tmp_path: Path) -> None:
    capture_dir = _write_capture(tmp_path)
    _build(capture_dir)
    written = json.loads((capture_dir / "manifest.json").read_text())
    assert written["cid"] == "cap1"
    assert written["root_url"] == ROOT_URL
    assert written["scope_type"] == "prefix"
    assert written["created_at"] == CREATED_AT
    assert {p["file"] for p in written["pages"]} == {"index.html", "guide.html", "intro.html"}


def test_pending_entry_without_filename_excluded(tmp_path: Path) -> None:
    manifest = _build(_write_capture(tmp_path))
    assert all("pending" not in p.url for p in manifest.pages)
    assert len(manifest.pages) == 3


def test_falls_back_to_scanning_pages_without_session(tmp_path: Path) -> None:
    capture_dir = _write_capture(tmp_path, with_session=False)
    manifest = _build(capture_dir)
    # URLs recovered from single-file's `url:` comment; all three pages present.
    assert len(manifest.pages) == 3
    assert ROOT_URL in {p.url for p in manifest.pages}
