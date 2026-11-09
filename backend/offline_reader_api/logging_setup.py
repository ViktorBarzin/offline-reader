"""JSON log lines in the OpenTelemetry field names (ADR-0007, infra ADR-0041).

One object per line on stdout, written by ``viktorbarzin_telemetry``'s
formatter: ``timestamp``, ``severity_text``, ``severity_number``, ``body``,
``logger.name``, ``service.name`` (``offline-reader``), ``service.version``,
``deployment.environment.name``, ``enduser.id`` while a request from a known
Person is served, plus any ``extra={...}`` fields as snake_case attributes.
This replaces the earlier ``ts``/``level``/``logger``/``msg`` lines.

The formatter masks the Write key, bearer tokens, Basic credentials and JWTs,
and here also ``INGEST_TOKEN``, which an iOS Shortcut sends as ``?token=`` and
uvicorn's access line would otherwise print.

uvicorn gives its own loggers text handlers before it imports the app; they
are handed to the root logger so the access and error lines are JSON too.
"""

import logging
import os
from collections.abc import Mapping
from typing import TextIO

import viktorbarzin_telemetry as telemetry

from offline_reader_api import __version__

APP = "offline-reader"

#: uvicorn's loggers, which it configures with handlers of their own.
UVICORN_LOGGERS: tuple[str, ...] = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(
    env: Mapping[str, str] | None = None,
    *,
    stream: TextIO | None = None,
    level: int = logging.INFO,
) -> logging.Handler:
    """Make every log line JSON, on stdout or ``stream``. Returns the handler."""
    values = os.environ if env is None else env
    environment = values.get(telemetry.ENVIRONMENT_VARIABLE, "").strip() or None
    ingest_token = values.get("INGEST_TOKEN", "").strip()
    handler = telemetry.setup_logging(
        service_name=APP,
        service_version=__version__,
        environment=environment,
        level=level,
        stream=stream,
        secrets=[ingest_token] if ingest_token else [],
    )
    for name in UVICORN_LOGGERS:
        named = logging.getLogger(name)
        for existing in list(named.handlers):
            named.removeHandler(existing)
        named.propagate = True
    return handler
