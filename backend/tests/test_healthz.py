"""Skeleton smoke tests: liveness endpoint + identity middleware wiring.

The first two run WITHOUT the lifespan on purpose: /healthz and the identity
middleware must work before (and regardless of) DB/runner startup.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_reader_api.app import create_app
from tests.conftest import auth


def test_healthz() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_rejects_missing_identity_header() -> None:
    client = TestClient(create_app())
    # 401 comes from the middleware, before any DB/route work — no lifespan needed.
    assert client.get("/api/captures").status_code == 401


def test_dev_user_env_is_the_identity_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CAPTURE_MODE", "fake")
    monkeypatch.setenv("CAPTURE_POLL_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("DEV_USER", "dev-viktor")
    with TestClient(create_app()) as client:
        # No X-Authentik-Username header, but DEV_USER stands in.
        assert client.get("/api/captures").status_code == 200
        # A real header still wins over the fallback.
        assert client.get("/api/captures", headers=auth()).status_code == 200
