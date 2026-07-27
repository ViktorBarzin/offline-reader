"""Shared fixtures: a fresh tmp DATA_DIR + SQLite DB per test, the app wired to
the FakeRunner (no cluster), and an identity-header helper. The whole suite runs
offline and deterministically (the background poller is disabled)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from offline_reader_api.app import create_app


def auth(user: str = "viktor") -> dict[str, str]:
    """Authentik forward-auth header the middleware trusts."""
    return {"X-Authentik-Username": user}


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the app at a fresh PVC layout + SQLite file, FakeRunner, poller off."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAPTURE_MODE", "fake")
    monkeypatch.setenv("CAPTURE_POLL_INTERVAL_SECONDS", "0")
    monkeypatch.delenv("DEV_USER", raising=False)
    return tmp_path


@pytest.fixture
def app(data_dir: Path) -> FastAPI:
    """A fresh app bound to the tmp DATA_DIR (kept so tests can reach app.state)."""
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """App with lifespan run (creates the schema, builds the FakeRunner)."""
    with TestClient(app) as test_client:
        yield test_client
