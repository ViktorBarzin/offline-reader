"""GET /api/signin: the target of the PWA's "Sign in" link.

It sits under /api, so forward-auth gates it and the service worker never
answers it from the precache. Reaching the app at all means the SSO session is
fresh, so it only has to send the browser back to the app.
"""

from fastapi.testclient import TestClient

from tests.conftest import auth


def test_signin_redirects_a_signed_in_browser_to_the_app(client: TestClient) -> None:
    response = client.get("/api/signin", headers=auth(), follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_signin_still_requires_the_identity_header(client: TestClient) -> None:
    assert client.get("/api/signin", follow_redirects=False).status_code == 401
