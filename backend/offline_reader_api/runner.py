"""The CaptureRunner abstraction: how a Capture's crawl is executed.

Two implementations, chosen by ``CAPTURE_MODE`` (config): ``k8s`` (prod — one
``single-file-cli`` Job per Capture, ADR-0002) and ``fake`` (default — no
cluster; writes deterministic fixture Pages so the whole API is testable).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from offline_reader_api.models import Capture

if TYPE_CHECKING:
    from offline_reader_api.config import Settings


@dataclass(frozen=True)
class CaptureProgress:
    """A point-in-time reading of a crawl. ``status`` is the mapped Capture
    status (``crawling`` | ``done`` | ``failed``); ``queued`` means not started."""

    status: str
    page_count: int
    size_bytes: int
    error: str | None = None


@runtime_checkable
class CaptureRunner(Protocol):
    """Executes and observes a Capture's crawl. Implementations are synchronous
    (the service calls them on a worker thread)."""

    def start(self, capture: Capture) -> str:
        """Kick off the crawl; return the runner's job handle (stored as job_name)."""
        ...

    def poll(self, capture: Capture) -> CaptureProgress:
        """Current progress for an in-flight Capture."""
        ...

    def cancel(self, capture: Capture) -> None:
        """Best-effort stop + cleanup of the crawl job (idempotent)."""
        ...


def build_runner(settings: "Settings") -> CaptureRunner:
    """The runner for the configured ``CAPTURE_MODE`` (``fake`` unless ``k8s``)."""
    if settings.capture_mode == "k8s":
        from offline_reader_api.runners.k8s import K8sJobRunner

        return K8sJobRunner(settings)
    from offline_reader_api.runners.fake import FakeRunner

    return FakeRunner(settings)
