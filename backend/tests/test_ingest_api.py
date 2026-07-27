"""Token-authed /api/ingest — the iOS-Shortcut path that skips Authentik SSO.

Every request here is sent WITHOUT the ``X-Authentik-Username`` header, proving
the middleware exemption; auth is the ``INGEST_TOKEN`` shared secret instead.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth

TOKEN = "sh0rtcut-shared-secret"
URL = "https://blog.example.com/posts/hello-world"


def test_query_token_creates_page_capture_without_sso(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """?token=<correct> with no SSO header -> 201; row persisted; scope == page."""
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)

    resp = client.post(f"/api/ingest?token={TOKEN}", json={"url": URL})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["root_url"] == URL
    assert body["scope_type"] == "page"  # not the /api/captures "prefix" default
    assert body["max_pages"] == 1000
    assert body["status"] in ("crawling", "queued")

    # The row really exists: the authed library lists it.
    listed = client.get("/api/captures", headers=auth()).json()
    assert any(c["id"] == body["id"] for c in listed)


def test_header_token_form_also_works(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The X-Ingest-Token header is accepted in place of the query param."""
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)

    resp = client.post("/api/ingest", json={"url": URL}, headers={"X-Ingest-Token": TOKEN})
    assert resp.status_code == 201, resp.text
    assert resp.json()["scope_type"] == "page"


def test_wrong_token_is_401_from_handler_not_middleware(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)

    resp = client.post("/api/ingest?token=not-the-token", json={"url": URL})
    assert resp.status_code == 401
    message = resp.json()["error"]["message"]
    # Reached the ingest handler (exemption worked) — not the middleware's
    # "missing X-Authentik-Username header" rejection.
    assert "token" in message
    assert "X-Authentik-Username" not in message


def test_missing_token_is_401_from_handler_not_middleware(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)

    resp = client.post("/api/ingest", json={"url": URL})  # no token anywhere
    assert resp.status_code == 401
    message = resp.json()["error"]["message"]
    assert "token" in message
    assert "X-Authentik-Username" not in message


def test_disabled_when_token_unset_is_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No INGEST_TOKEN configured -> 503, even if the caller presents a token."""
    monkeypatch.delenv("INGEST_TOKEN", raising=False)

    resp = client.post(f"/api/ingest?token={TOKEN}", json={"url": URL})
    assert resp.status_code == 503


def test_middleware_exempts_ingest_but_still_guards_other_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contrast: a normal /api route 401s without the SSO header; ingest does not."""
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)

    # A normal /api route with no identity header is blocked by the middleware.
    assert client.get("/api/captures").status_code == 401

    # /api/ingest is exempt: it reaches the handler and succeeds on a good token.
    resp = client.post(f"/api/ingest?token={TOKEN}", json={"url": URL})
    assert resp.status_code == 201, resp.text


def test_invalid_url_rejected_like_main_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reused CaptureCreate URL validator still applies (422 on a bad URL)."""
    monkeypatch.setenv("INGEST_TOKEN", TOKEN)

    resp = client.post(f"/api/ingest?token={TOKEN}", json={"url": "not-a-url"})
    assert resp.status_code == 422
