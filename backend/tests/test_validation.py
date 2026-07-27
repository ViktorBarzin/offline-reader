"""Input validation: URL scheme + scope_type + max_pages, at both the schema
(property-based) and the API boundary."""

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from offline_reader_api.schemas import CaptureCreate
from tests.conftest import auth


def test_defaults() -> None:
    model = CaptureCreate(url="https://example.com/docs/")
    assert model.scope_type == "prefix"
    assert model.max_pages == 1000
    assert model.include == []
    assert model.exclude == []


@pytest.mark.parametrize("url", ["https://example.com/", "http://a.b/c?d=1"])
def test_accepts_http_urls(url: str) -> None:
    assert CaptureCreate(url=url).url == url


@pytest.mark.parametrize(
    "url",
    ["", "ftp://example.com/x", "file:///etc/passwd", "example.com", "javascript:alert(1)", "/rel"],
)
def test_rejects_non_http_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        CaptureCreate(url=url)


@given(st.text().filter(lambda s: "://" not in s))
def test_property_non_url_strings_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        CaptureCreate(url=text)


def test_invalid_scope_type_rejected() -> None:
    with pytest.raises(ValidationError):
        CaptureCreate(url="https://example.com/", scope_type="everything")  # type: ignore[arg-type]


def test_max_pages_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        CaptureCreate(url="https://example.com/", max_pages=0)


def test_api_rejects_bad_url(client: TestClient) -> None:
    response = client.post("/api/captures", json={"url": "not-a-url"}, headers=auth())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_api_rejects_bad_scope(client: TestClient) -> None:
    response = client.post(
        "/api/captures",
        json={"url": "https://example.com/", "scope_type": "nonsense"},
        headers=auth(),
    )
    assert response.status_code == 422
