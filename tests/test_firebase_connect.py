"""Google consent through the Firebase identity Tony already uses."""
import pytest

from tony.authflow import _scope_urls


def test_gmail_scopes_map_to_google_urls():
    urls = _scope_urls(["openid", "email", "profile", "gmail.modify"])
    assert "openid" in urls
    assert "https://www.googleapis.com/auth/userinfo.email" in urls
    assert "https://www.googleapis.com/auth/userinfo.profile" in urls
    assert "https://www.googleapis.com/auth/gmail.modify" in urls


def test_scope_urls_keep_absolute_scopes():
    assert _scope_urls(["https://www.googleapis.com/auth/drive.file"]) == [
        "https://www.googleapis.com/auth/drive.file"]


def test_firebase_token_is_refused_for_a_non_google_app(client):
    # a key-based app must never be connected with a Google token
    r = client.post("/v1/connections/hackernews/firebase-token?entity_id=playground",
                    json={"access_token": "x"})
    assert r.status_code in (400, 404)


def test_firebase_token_requires_a_token(client):
    r = client.post("/v1/connections/gmail/firebase-token?entity_id=playground", json={})
    assert r.status_code == 400


def test_every_registered_provider_is_a_real_oauth_app():
    from tony import provider_registry as R

    assert len(R.PROVIDERS) >= 35
    for slug, p in R.PROVIDERS.items():
        assert p.authorize_url.startswith("https://"), slug
        assert p.token_url.startswith("https://"), slug
        assert p.env[0].endswith("_CLIENT_ID") and p.env[1].endswith("_CLIENT_SECRET"), slug
        assert R.provider_for(slug) is not None


def test_an_upgraded_app_no_longer_accepts_a_pasted_key(client):
    # Airtable used to be an API-key app; it is a sign-in app now.
    d = client.get("/v1/apps/airtable").json()
    assert d["auth"]["type"] == "oauth2"
    assert d["auth"]["user_supplied"] is False
    # endpoints stay server-side; the browser never needs them
    assert "token_url" not in d["auth"]
