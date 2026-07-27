"""Environment-driven settings (no config files — the k8s stack injects env)."""

import os
from dataclasses import dataclass

USERNAME_HEADER = "X-Authentik-Username"
DEFAULT_DATA_DIR = "/data"


def _db_dsn_for(data_dir: str) -> str:
    """The SQLite DSN co-located with the capture data on the PVC (ADR-0004)."""
    return f"sqlite+aiosqlite:///{data_dir}/offline-reader.db"


DEFAULT_DB_DSN = _db_dsn_for(DEFAULT_DATA_DIR)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration, read from the environment.

    - ``data_dir``: ``DATA_DIR`` — the NFS PVC mount (``/data`` in prod); holds
      the SQLite DB, ``captures/<cid>/pages/*.html`` and the manifests.
    - ``db_dsn``: ``OFFLINE_READER_DB_DSN`` — defaults to a SQLite file under
      ``data_dir``; a tmp file in tests, ``/data/offline-reader.db`` in prod.
    - ``dev_user``: ``DEV_USER`` — dev-only identity fallback when Authentik's
      forward-auth header is absent (never set in production).
    - ``ingest_token``: ``INGEST_TOKEN`` — shared secret for the token-authed
      ``POST /api/ingest`` endpoint (the iOS Shortcut path, which bypasses the
      Authentik SSO login). ``None``/empty disables the endpoint (503).
    - ``capture_mode``: ``CAPTURE_MODE`` — ``fake`` (default, no cluster) or
      ``k8s`` (one ``single-file-cli`` Job per Capture).
    - ``max_depth`` / ``workers`` / ``wait_ms``: per-Job crawl tuning knobs.
    - ``poll_interval_seconds``: ``CAPTURE_POLL_INTERVAL_SECONDS`` — the
      background poller cadence; ``0`` disables it (GET still advances captures).
    - ``pod_namespace`` / ``singlefile_image`` / ``nfs_pvc_claim``: the
      K8sJobRunner's Job namespace, capture image, and PVC claim.
    """

    data_dir: str = DEFAULT_DATA_DIR
    db_dsn: str = DEFAULT_DB_DSN
    dev_user: str | None = None
    ingest_token: str | None = None
    capture_mode: str = "fake"
    fake_auto_complete: bool = False
    max_depth: int = 3
    workers: int = 2
    wait_ms: int = 500
    poll_interval_seconds: float = 0.0
    pod_namespace: str = "offline-reader"
    singlefile_image: str = "ghcr.io/viktorbarzin/offline-reader-capture:latest"
    nfs_pvc_claim: str = "offline-reader"

    @property
    def captures_dir(self) -> str:
        """``${DATA_DIR}/captures`` — the per-Capture directory root."""
        return os.path.join(self.data_dir, "captures")


def get_settings() -> Settings:
    """Read settings fresh from the environment (cheap; also keeps tests simple)."""
    data_dir = os.environ.get("DATA_DIR", DEFAULT_DATA_DIR)
    return Settings(
        data_dir=data_dir,
        db_dsn=os.environ.get("OFFLINE_READER_DB_DSN", _db_dsn_for(data_dir)),
        dev_user=os.environ.get("DEV_USER"),
        ingest_token=os.environ.get("INGEST_TOKEN"),
        capture_mode=os.environ.get("CAPTURE_MODE", "fake"),
        fake_auto_complete=os.environ.get("FAKE_AUTO_COMPLETE", "").lower()
        in ("1", "true", "yes"),
        max_depth=int(os.environ.get("CAPTURE_MAX_DEPTH", "3")),
        workers=int(os.environ.get("CAPTURE_WORKERS", "2")),
        wait_ms=int(os.environ.get("CAPTURE_WAIT_MS", "500")),
        poll_interval_seconds=float(os.environ.get("CAPTURE_POLL_INTERVAL_SECONDS", "0")),
        pod_namespace=os.environ.get("POD_NAMESPACE", "offline-reader"),
        singlefile_image=os.environ.get(
            "SINGLEFILE_IMAGE", "ghcr.io/viktorbarzin/offline-reader-capture:latest"
        ),
        nfs_pvc_claim=os.environ.get("NFS_PVC_CLAIM", "offline-reader"),
    )
