"""End-to-end API flow against the FakeRunner (no cluster): create -> status
transitions -> manifest -> page -> refresh -> delete."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from offline_reader_api import storage
from tests.conftest import auth


def _create(client: TestClient, url: str = "https://docs.example.com/") -> str:
    response = client.post(
        "/api/captures",
        json={"url": url, "scope_type": "prefix", "max_pages": 50},
        headers=auth(),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "crawling"
    assert body["job_name"]
    assert body["scope_type"] == "prefix"
    assert body["max_pages"] == 50
    return str(body["id"])


def test_capture_lifecycle(app: FastAPI, client: TestClient) -> None:
    cid = _create(client)
    runner = app.state.capture_runner

    # Listed, and still crawling until the runner reports done.
    listed = client.get("/api/captures", headers=auth()).json()
    assert any(c["id"] == cid for c in listed)
    assert client.get(f"/api/captures/{cid}", headers=auth()).json()["status"] == "crawling"

    # Manifest 404s until done.
    assert client.get(f"/api/captures/{cid}/manifest", headers=auth()).status_code == 404

    # Drive the fake crawl to completion, then GET advances the status.
    runner.complete(cid)
    done = client.get(f"/api/captures/{cid}", headers=auth()).json()
    assert done["status"] == "done"
    assert done["page_count"] == 2
    assert done["size_bytes"] > 0
    assert done["title"]  # picked up from the captured root page

    # Manifest served.
    manifest = client.get(f"/api/captures/{cid}/manifest", headers=auth())
    assert manifest.status_code == 200
    assert "application/json" in manifest.headers["content-type"]
    body = manifest.json()
    assert body["cid"] == cid
    assert len(body["pages"]) == 2
    page_id = body["pages"][0]["id"]

    # Page served as HTML.
    page = client.get(f"/api/captures/{cid}/pages/{page_id}", headers=auth())
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "<title>" in page.text.lower()

    # Unknown page id -> 404.
    assert client.get(f"/api/captures/{cid}/pages/deadbeef0000", headers=auth()).status_code == 404


def test_refresh_replaces_pages(app: FastAPI, client: TestClient) -> None:
    cid = _create(client)
    runner = app.state.capture_runner
    runner.complete(cid)
    assert client.get(f"/api/captures/{cid}", headers=auth()).json()["status"] == "done"

    refreshed = client.post(f"/api/captures/{cid}/refresh", headers=auth())
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["status"] == "crawling"
    assert body["page_count"] == 0  # reset
    # Manifest gone until the re-crawl finishes.
    assert client.get(f"/api/captures/{cid}/manifest", headers=auth()).status_code == 404

    runner.complete(cid)
    assert client.get(f"/api/captures/{cid}", headers=auth()).json()["status"] == "done"
    assert client.get(f"/api/captures/{cid}/manifest", headers=auth()).status_code == 200


def test_delete_removes_files_and_row(app: FastAPI, client: TestClient) -> None:
    cid = _create(client)
    data_dir = app.state.settings.data_dir
    assert storage.capture_dir(data_dir, cid).exists()

    assert client.delete(f"/api/captures/{cid}", headers=auth()).status_code == 204
    assert client.get(f"/api/captures/{cid}", headers=auth()).status_code == 404
    assert not storage.capture_dir(data_dir, cid).exists()


def test_failed_capture_reports_error(app: FastAPI, client: TestClient) -> None:
    cid = _create(client)
    app.state.capture_runner.fail(cid, "boom")
    body = client.get(f"/api/captures/{cid}", headers=auth()).json()
    assert body["status"] == "failed"
    assert body["error"] == "boom"
    # Terminal is sticky: a later poll does not revive it.
    assert client.get(f"/api/captures/{cid}", headers=auth()).json()["status"] == "failed"


def test_get_and_delete_unknown_capture_404(client: TestClient) -> None:
    assert client.get("/api/captures/nope", headers=auth()).status_code == 404
    assert client.delete("/api/captures/nope", headers=auth()).status_code == 404
    assert client.post("/api/captures/nope/refresh", headers=auth()).status_code == 404


def test_pages_use_pvc_layout(app: FastAPI, client: TestClient, data_dir: Path) -> None:
    cid = _create(client)
    app.state.capture_runner.complete(cid)
    client.get(f"/api/captures/{cid}", headers=auth())  # advance -> builds manifest
    pages = storage.pages_dir(str(data_dir), cid)
    assert (pages / "index.html").is_file()
    assert (storage.capture_dir(str(data_dir), cid) / "manifest.json").is_file()
