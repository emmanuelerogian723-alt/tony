"""OAuth session lifecycle with a mocked token endpoint."""
from urllib.parse import parse_qs, urlparse

import asyncio

import httpx
import pytest

from tony.catalog import catalog
from tony.db import session as db_session
from tony.models import AuthSession


class FakeClient:
    def __init__(self, *a, **kw):
        self.status = 200
        self.payload = {"access_token": "at-123", "refresh_token": "rt-123", "expires_in": 3600,
                        "scope": "read:user repo", "token_type": "bearer"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, data=None, headers=None):
        return httpx.Response(200, json=self.payload, request=httpx.Request("POST", url))


def test_start_oauth_requires_client_id(monkeypatch):
    from tony.oauth import OAuthError, start_oauth
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_CLIENT_SECRET", raising=False)
    with pytest.raises(OAuthError):
        asyncio.run(start_oauth("ws", "ent", catalog.get("github")))


def test_start_oauth_builds_authorize_url(monkeypatch):
    from tony.oauth import start_oauth
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "cs")
    session_id, url = asyncio.run(start_oauth("ws1", "entity1", catalog.get("github"), "/app"))
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert parsed.netloc == "github.com"
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"][0].endswith("/oauth/callback")
    assert "repo" in q["scope"][0]
    assert q["state"]
    with db_session() as s:
        row = s.get(AuthSession, session_id)
        assert row and row.state == q["state"][0] and row.consumed is False


def test_complete_oauth_stores_encrypted_credentials(monkeypatch):
    from tony.oauth import complete_oauth, start_oauth
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "cs")
    monkeypatch.setattr("tony.oauth.httpx.AsyncClient", FakeClient)

    session_id, url = asyncio.run(start_oauth("ws2", "entity2", catalog.get("github"), "/app"))
    state = parse_qs(urlparse(url).query)["state"][0]

    account = asyncio.run(complete_oauth(state, "the-code"))
    assert account.status == "active"
    assert account.app_slug == "github"
    assert "at-123" not in account.credentials_enc

    # replaying the same state must fail
    import pytest as _pytest

    from tony.oauth import OAuthError
    with _pytest.raises(OAuthError):
        asyncio.run(complete_oauth(state, "again"))
