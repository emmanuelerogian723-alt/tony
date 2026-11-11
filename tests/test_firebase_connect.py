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
