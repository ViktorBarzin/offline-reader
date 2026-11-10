"""Product events from where each thing happens (ADR-0007).

`FakeEvents` replaces Segment's client, so nothing here reaches the network.
"""

from collections.abc import Iterator

import pytest
import viktorbarzin_telemetry as telemetry
from fastapi import FastAPI
from fastapi.testclient import TestClient

from offline_reader_api import product_events
from offline_reader_api.models import Capture
from tests.conftest import auth
from tests.telemetry_fakes import PRODUCTION, FakeEvents

PERSON = "4f1c2b0e9d8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e"
TOKEN = "sh0rtcut-shared-secret"


def _capture() -> Capture:
    """A Capture as the background poller sees it: no request, no Person."""
    return Capture(
        id="abc123def456",
        root_url="https://docs.example.com/",
        title="https://docs.example.com/",
        scope_type="prefix",
        max_pages=50,
        status="crawling",
        page_count=0,
        size_bytes=0,
    )


def signed_in(person: str | None = PERSON) -> dict[str, str]:
    headers = auth()
    if person is not None:
        headers["X-Authentik-Uid"] = person
    return headers


@pytest.fixture
def events(client: TestClient) -> Iterator[FakeEvents]:
    """Turn events on with a recorder, after the app's own start turned them off."""
    fake = FakeEvents()
    assert product_events.start(PRODUCTION, client=fake) is True
    yield fake
    product_events.stop()


def _create(client: TestClient, url: str = "https://docs.example.com/guide/") -> str:
    response = client.post(
        "/api/captures",
        json={"url": url, "scope_type": "prefix", "max_pages": 50},
        headers=signed_in(),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_every_event_name_meets_the_standard() -> None:
    assert len(product_events.EVENTS) == len(set(product_events.EVENTS))
    for name in product_events.EVENTS:
        assert telemetry.event_name_problem(name) is None, name


def test_nothing_is_sent_without_a_write_key() -> None:
    env = {k: v for k, v in PRODUCTION.items() if k != "TELEMETRY_WRITE_KEY"}
    assert product_events.start(env, client=FakeEvents()) is False


def test_nothing_is_sent_outside_production() -> None:
    fake = FakeEvents()
    env = {**PRODUCTION, "TELEMETRY_ENVIRONMENT": "dev"}
    assert product_events.start(env, client=fake) is False


def test_production_without_a_host_sends_nothing_and_still_starts() -> None:
    # Segment's own client is built here, and refuses before it sends anything.
    env = {k: v for k, v in PRODUCTION.items() if k != "TELEMETRY_HOST"}
    assert product_events.start(env) is False


def test_a_web_capture_is_requested_by_the_signed_in_person(
    client: TestClient, events: FakeEvents
) -> None:
    _create(client)
    [sent] = events.named(product_events.CAPTURE_REQUESTED)
    assert sent.user_id == PERSON
    assert sent.properties == {
        "source": "web",
        "scope_type": "prefix",
        "max_pages": 50,
        "site": "docs.example.com",
    }


def test_a_web_event_joins_the_browsers_visitor_and_carries_its_ip_and_agent(
    client: TestClient, events: FakeEvents
) -> None:
    agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Safari/605.1.15"
    response = client.post(
        "/api/captures",
        json={"url": "https://docs.example.com/guide/"},
        headers={
            **signed_in(),
            "X-Visitor-Id": "visitor-123",
            "X-Real-Ip": "81.2.69.142",
            "User-Agent": agent,
        },
    )
    assert response.status_code == 201, response.text
    [sent] = events.named(product_events.CAPTURE_REQUESTED)
    assert sent.user_id == PERSON
    assert sent.anonymous_id == "visitor-123"
    assert sent.context["ip"] == "81.2.69.142"
    assert sent.context["userAgent"] == agent


def test_a_signed_in_event_without_a_visitor_id_invents_no_anonymous_id(
    client: TestClient, events: FakeEvents
) -> None:
    _create(client)
    _create(client)
    sent = events.named(product_events.CAPTURE_REQUESTED)
    assert [s.anonymous_id for s in sent] == [None, None]


def test_an_event_outside_a_request_uses_the_stable_server_id(events: FakeEvents) -> None:
    product_events.capture_failed(_capture(), stage="crawl")
    product_events.capture_failed(_capture(), stage="crawl")
    sent = events.named(product_events.CAPTURE_FAILED)
    assert [s.anonymous_id for s in sent] == ["server:offline-reader"] * 2
    assert [s.user_id for s in sent] == [None, None]


def test_a_shortcut_capture_has_no_person_even_with_a_forged_uid(
    client: TestClient, events: FakeEvents, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)
    response = client.post(
        "/api/ingest",
        json={"url": "https://blog.example.com/posts/hello"},
        headers={"X-Ingest-Token": TOKEN, "X-Authentik-Uid": "forged"},
    )
    assert response.status_code == 201, response.text
    [sent] = events.named(product_events.CAPTURE_REQUESTED)
    assert sent.user_id is None
    assert sent.anonymous_id == product_events.SHORTCUT_ANONYMOUS_ID
    assert sent.properties["source"] == "shortcut"
    assert sent.properties["scope_type"] == "page"


def test_a_finished_crawl_is_completed_once(
    app: FastAPI, client: TestClient, events: FakeEvents
) -> None:
    cid = _create(client)
    app.state.capture_runner.complete(cid)
    client.get(f"/api/captures/{cid}", headers=signed_in())
    client.get(f"/api/captures/{cid}", headers=signed_in())
    [sent] = events.named(product_events.CAPTURE_COMPLETED)
    assert sent.user_id == PERSON
    assert sent.properties["scope_type"] == "prefix"
    assert sent.properties["site"] == "docs.example.com"
    assert sent.properties["page_count"] == 2
    size = sent.properties["size_bytes"]
    assert isinstance(size, int) and size > 0


def test_a_failed_crawl_is_failed_once_at_the_crawl_stage(
    app: FastAPI, client: TestClient, events: FakeEvents
) -> None:
    cid = _create(client)
    app.state.capture_runner.fail(cid, "secret detail https://internal.example/")
    client.get(f"/api/captures/{cid}", headers=signed_in())
    client.get(f"/api/captures/{cid}", headers=signed_in())
    [sent] = events.named(product_events.CAPTURE_FAILED)
    assert sent.properties == {"stage": "crawl", "scope_type": "prefix", "site": "docs.example.com"}


def test_a_crawl_that_cannot_start_is_failed_at_the_start_stage(
    app: FastAPI, client: TestClient, events: FakeEvents, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_capture: object) -> str:
        raise RuntimeError("no cluster")

    monkeypatch.setattr(app.state.capture_runner, "start", refuse)
    response = client.post(
        "/api/captures", json={"url": "https://docs.example.com/"}, headers=signed_in()
    )
    assert response.json()["status"] == "failed"
    [sent] = events.named(product_events.CAPTURE_FAILED)
    assert sent.properties["stage"] == "start"
    assert not events.named(product_events.CAPTURE_COMPLETED)


def test_refresh_delete_and_download_each_send_one_event(
    app: FastAPI, client: TestClient, events: FakeEvents
) -> None:
    cid = _create(client)
    app.state.capture_runner.complete(cid)
    client.get(f"/api/captures/{cid}", headers=signed_in())

    assert client.get(f"/api/captures/{cid}/manifest", headers=signed_in()).status_code == 200
    [download] = events.named(product_events.DOWNLOAD_STARTED)
    assert download.user_id == PERSON
    assert download.properties["page_count"] == 2
    assert download.properties["age_days"] == 0

    assert client.post(f"/api/captures/{cid}/refresh", headers=signed_in()).status_code == 200
    [refreshed] = events.named(product_events.CAPTURE_REFRESHED)
    assert refreshed.properties == {
        "scope_type": "prefix",
        "site": "docs.example.com",
        "age_days": 0,
    }

    assert client.delete(f"/api/captures/{cid}", headers=signed_in()).status_code == 204
    [deleted] = events.named(product_events.CAPTURE_DELETED)
    assert deleted.properties["status"] == "crawling"
    assert deleted.properties["age_days"] == 0


def test_a_manifest_that_is_not_ready_sends_nothing(
    client: TestClient, events: FakeEvents
) -> None:
    cid = _create(client)
    assert client.get(f"/api/captures/{cid}/manifest", headers=signed_in()).status_code == 404
    assert not events.named(product_events.DOWNLOAD_STARTED)


def test_no_property_carries_the_captured_url_path_or_an_error(
    app: FastAPI, client: TestClient, events: FakeEvents
) -> None:
    cid = _create(client, "https://docs.example.com/private/path?token=abc")
    app.state.capture_runner.fail(cid, "boom at https://docs.example.com/private/path")
    client.get(f"/api/captures/{cid}", headers=signed_in())
    for sent in events.tracks:
        for value in sent.properties.values():
            assert "/private" not in str(value)
            assert "boom" not in str(value)


def test_shutdown_flushes_what_is_queued(app: FastAPI) -> None:
    fake = FakeEvents()
    with TestClient(app):
        product_events.start(PRODUCTION, client=fake)
    assert fake.flushed == 1
    product_events.stop()
