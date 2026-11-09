"""offline-reader's Product events and error reports (ADR-0007, infra ADR-0041).

Events go through ``viktorbarzin_telemetry`` (Segment's SDK) to the Event
pipeline, and errors through Sentry to GlitchTip. ``start`` turns both on from
the environment:

- ``TELEMETRY_WRITE_KEY``: offline-reader's Write key. Unset or blank means no
  events, which is how dev, tests and a laptop run.
- ``TELEMETRY_HOST``: the Event pipeline's base URL (the event-pipeline
  Service inside the cluster).
- ``TELEMETRY_ENVIRONMENT``: only ``production`` sends anything.
- ``SENTRY_DSN``: GlitchTip's DSN for offline-reader. Unset means no reports.

Each event names the Person by the request's Authentik ``uid``
(``EnduserMiddleware`` puts it on the log context). A Capture shared from the
iOS Shortcut has no Person, so it carries the fixed anonymous id
``SHORTCUT_ANONYMOUS_ID``. Properties name the captured site's host and never
its path, query, title or an error text, which can carry a token.

Every helper here returns at once and never raises: an event is worth less
than the request it rides on.
"""

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

import viktorbarzin_telemetry as telemetry

from offline_reader_api import __version__
from offline_reader_api.logging_setup import APP
from offline_reader_api.models import Capture

logger = logging.getLogger(__name__)

CAPTURE_REQUESTED = "capture.requested"
CAPTURE_COMPLETED = "capture.completed"
CAPTURE_FAILED = "capture.failed"
CAPTURE_REFRESHED = "capture.refreshed"
CAPTURE_DELETED = "capture.deleted"
DOWNLOAD_STARTED = "download.started"

#: Every event offline-reader sends, for the ADR and the tests.
EVENTS: tuple[str, ...] = (
    CAPTURE_REQUESTED,
    CAPTURE_COMPLETED,
    CAPTURE_FAILED,
    CAPTURE_REFRESHED,
    CAPTURE_DELETED,
    DOWNLOAD_STARTED,
)

#: The anonymous id of Captures shared from the iOS Shortcut, which has no Person.
SHORTCUT_ANONYMOUS_ID = "ios-shortcut"

#: Where a Capture was asked for: the PWA, or the iOS Shortcut's /api/ingest.
Source = Literal["web", "shortcut"]
#: Where a crawl failed: starting its Job, or the Job itself.
FailedStage = Literal["start", "crawl"]


def start(env: Mapping[str, str], *, client: telemetry.EventClient | None = None) -> bool:
    """Turn events and error reports on from ``env``. True when events are sent.

    ``client`` replaces Segment's, for tests.
    """
    write_key = env.get("TELEMETRY_WRITE_KEY", "").strip()
    environment = env.get(telemetry.ENVIRONMENT_VARIABLE, "").strip() or "dev"
    dsn = env.get("SENTRY_DSN", "").strip() or None
    if not write_key:
        stop()
        if dsn and environment == telemetry.PRODUCTION:
            telemetry.init_sentry(dsn, release=__version__, environment=environment)
        return False
    try:
        sender = telemetry.configure(
            app=APP,
            write_key=write_key,
            release=__version__,
            environment=environment,
            dsn=dsn,
            host=env.get(telemetry.HOST_VARIABLE, "").strip() or None,
            client=client,
        )
    except ValueError as exc:
        # Production with no pipeline URL: say so once and send nothing,
        # rather than keep the pod from starting.
        logger.warning("product events are off: %s", exc)
        stop()
        return False
    logger.info("product events %s", "on" if sender.enabled else "off (not production)")
    return sender.enabled


def stop() -> None:
    """Send nothing from here on. For tests, and a start that cannot send."""
    telemetry.configure(app=APP, write_key="", release="0", environment="dev")


def flush() -> None:
    """Send what is queued. Called once, on shutdown."""
    try:
        telemetry.flush()
    except Exception:
        logger.warning("product events: the last flush failed", exc_info=True)


def _send(event: str, properties: telemetry.Properties, *, anonymous_id: str | None = None) -> None:
    try:
        telemetry.track(event, properties, anonymous_id=anonymous_id)
    except Exception:
        logger.warning("product events: %s was not sent", event, exc_info=True)


def _site(capture: Capture) -> str:
    """The captured site's host, without the path or query."""
    return urlparse(capture.root_url).hostname or ""


def _age_days(capture: Capture) -> int:
    created = capture.created_at
    if created.tzinfo is None:  # SQLite hands datetimes back without a zone
        created = created.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - created).days)


def capture_requested(capture: Capture, *, source: Source) -> None:
    """Somebody asked for a site to be saved, from the PWA or the Shortcut."""
    _send(
        CAPTURE_REQUESTED,
        {
            "source": source,
            "scope_type": capture.scope_type,
            "max_pages": capture.max_pages,
            "site": _site(capture),
        },
        anonymous_id=SHORTCUT_ANONYMOUS_ID if source == "shortcut" else None,
    )


def capture_completed(capture: Capture) -> None:
    """A crawl finished and its manifest is built."""
    _send(
        CAPTURE_COMPLETED,
        {
            "scope_type": capture.scope_type,
            "site": _site(capture),
            "page_count": capture.page_count,
            "size_bytes": capture.size_bytes,
        },
    )


def capture_failed(capture: Capture, *, stage: FailedStage) -> None:
    """A crawl could not start, or its Job failed."""
    _send(
        CAPTURE_FAILED,
        {"stage": stage, "scope_type": capture.scope_type, "site": _site(capture)},
    )


def capture_refreshed(capture: Capture) -> None:
    """A saved site is crawled again, replacing its Pages."""
    _send(
        CAPTURE_REFRESHED,
        {"scope_type": capture.scope_type, "site": _site(capture), "age_days": _age_days(capture)},
    )


def capture_deleted(capture: Capture) -> None:
    """A Capture left the Library."""
    _send(
        CAPTURE_DELETED,
        {
            "status": capture.status,
            "page_count": capture.page_count,
            "age_days": _age_days(capture),
        },
    )


def download_started(capture: Capture) -> None:
    """The PWA fetched a finished Capture's manifest to Download it to a device."""
    _send(
        DOWNLOAD_STARTED,
        {
            "page_count": capture.page_count,
            "size_bytes": capture.size_bytes,
            "age_days": _age_days(capture),
        },
    )
