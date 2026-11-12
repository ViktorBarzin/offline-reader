"""JSON log lines in the OpenTelemetry field names, and the Person id (ADR-0007)."""

import io
import json
import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from offline_reader_api import __version__, logging_setup, product_events
from tests.conftest import auth
from tests.telemetry_fakes import PRODUCTION, FakeEvents

PERSON = "4f1c2b0e9d8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e"


@pytest.fixture
def stream(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """Send log lines to a buffer, after the app's own setup sent them to stdout."""
    monkeypatch.setenv("INGEST_TOKEN", "sh0rtcut-shared-secret")
    monkeypatch.setenv("TELEMETRY_ENVIRONMENT", "production")
    buffer = io.StringIO()
    logging_setup.configure_logging(stream=buffer)
    yield buffer
    logging_setup.configure_logging()


def _lines(buffer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line]


def test_a_line_carries_the_open_telemetry_fields(stream: io.StringIO) -> None:
    logging.getLogger("offline_reader_api.test").warning(
        "capture slow", extra={"capture_id": "abc"}
    )
    [line] = _lines(stream)
    assert line["severity_text"] == "WARN"
    assert line["severity_number"] == 13
    assert line["body"] == "capture slow"
    assert line["service.name"] == "offline-reader"
    assert line["service.version"] == __version__
    assert line["deployment.environment.name"] == "production"
    assert line["capture_id"] == "abc"
    assert isinstance(line["timestamp"], str) and line["timestamp"].endswith("Z")
    for old in ("ts", "level", "logger", "msg"):
        assert old not in line


def test_the_ingest_token_never_reaches_a_line(stream: io.StringIO) -> None:
    logging.getLogger("uvicorn.access").info("POST /api/ingest?token=sh0rtcut-shared-secret")
    text = stream.getvalue()
    assert "sh0rtcut-shared-secret" not in text
    assert text  # the line itself is kept


def test_uvicorn_lines_are_json_too(stream: io.StringIO) -> None:
    for name in logging_setup.UVICORN_LOGGERS:
        named = logging.getLogger(name)
        assert named.handlers == []
        assert named.propagate is True


def test_a_request_from_a_person_names_them_on_its_lines(
    client: TestClient, stream: io.StringIO
) -> None:
    client.post(
        "/api/captures",
        json={"url": "https://docs.example.com/"},
        headers={**auth(), "X-Authentik-Uid": PERSON},
    )
    named = [line for line in _lines(stream) if line.get("enduser.id") == PERSON]
    assert named, _lines(stream)


def test_me_names_the_user_and_their_person_id(client: TestClient) -> None:
    response = client.get("/api/me", headers={**auth("viktor"), "X-Authentik-Uid": PERSON})
    assert response.status_code == 200
    assert response.json() == {"username": "viktor", "person_id": PERSON, "telemetry": None}


def test_me_without_a_uid_has_no_person_id(client: TestClient) -> None:
    response = client.get("/api/me", headers=auth("viktor"))
    assert response.json() == {"username": "viktor", "person_id": None, "telemetry": None}


def test_me_hands_the_browser_the_write_key_while_events_are_on(client: TestClient) -> None:
    assert product_events.start(PRODUCTION, client=FakeEvents()) is True
    try:
        response = client.get("/api/me", headers=auth("viktor"))
    finally:
        product_events.stop()
    assert response.json()["telemetry"] == {
        "write_key": PRODUCTION["TELEMETRY_WRITE_KEY"],
        "release": __version__,
    }


def test_me_hands_out_no_write_key_outside_production(client: TestClient) -> None:
    env = {**PRODUCTION, "TELEMETRY_ENVIRONMENT": "dev"}
    assert product_events.start(env, client=FakeEvents()) is False
    try:
        response = client.get("/api/me", headers=auth("viktor"))
    finally:
        product_events.stop()
    assert response.json()["telemetry"] is None


def test_me_needs_the_identity_header(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401
