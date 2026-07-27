"""On-PVC layout helpers (ADR-0004). One directory per Capture::

    ${DATA_DIR}/captures/<cid>/
        pages/*.html      self-contained Pages (written by the capture Job)
        session.json      single-file-cli crawl session (url -> filename map)
        manifest.json     built by build_manifest after the crawl finishes
"""

import contextlib
import shutil
from pathlib import Path


def capture_dir(data_dir: str, cid: str) -> Path:
    """``${DATA_DIR}/captures/<cid>``."""
    return Path(data_dir) / "captures" / cid


def pages_dir(data_dir: str, cid: str) -> Path:
    """``${DATA_DIR}/captures/<cid>/pages``."""
    return capture_dir(data_dir, cid) / "pages"


def ensure_capture_dirs(data_dir: str, cid: str) -> None:
    """Create the per-Capture tree BEFORE the capture Job runs, world-writable.

    The app (uid 10001) and the capture Job (the capture image's own, different
    uid) both write under ``captures/<cid>/`` over NFS, so the tree must be
    writable by any uid. Mode ``0o777`` is set with explicit ``chmod`` to defeat
    the process umask. Without this the Job's ``mkdir`` is denied (the app owns
    ``captures/`` as 0755) and the crawl fails.
    """
    pages = pages_dir(data_dir, cid)
    pages.mkdir(parents=True, exist_ok=True)
    for path in (pages.parent.parent, pages.parent, pages):  # captures/, <cid>/, <cid>/pages/
        with contextlib.suppress(OSError):
            path.chmod(0o777)


def count_pages(pages: Path) -> tuple[int, int]:
    """(number of ``*.html`` Pages, total bytes) — the runner's progress signal."""
    if not pages.is_dir():
        return (0, 0)
    files = [f for f in pages.glob("*.html") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    return (len(files), total)


def remove_capture(data_dir: str, cid: str) -> None:
    """Delete a Capture's whole directory tree (Pages + manifest + session)."""
    shutil.rmtree(capture_dir(data_dir, cid), ignore_errors=True)
