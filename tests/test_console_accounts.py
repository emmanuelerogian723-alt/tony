"""Console accounts: signup, login, sessions, profile, keys, workspace isolation."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tony.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TONY_DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c


def test_console_page_renders_auth_screen(client):
    r = client.get("/account")
    assert r.status_code == 200
    body = r.text
    assert 'id="auth"' in body and 'id="shell"' in body
    assert "/v1/account/login" in body and "google.accounts.id.initialize" in body


def test_app_redirects_to_console(client):
    r = client.get("/app", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"].endswith("/account")


def test_signup_login_and_me(client):
    r = client.post("/v1/account/signup", json={"email": "a@b.com", "password": "hunter2hunter2", "name": "Ada"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "a@b.com"
    assert client.get("/v1/account/me").json()["user"]["name"] == "Ada"
    assert client.post("/v1/account/logout").status_code == 200
    assert client.get("/v1/account/me").json()["user"] is None
    assert client.post("/v1/account/login", json={"email": "a@b.com", "password": "nope"}).status_code == 401
    r = client.post("/v1/account/login", json={"email": "a@b.com", "password": "hunter2hunter2"})
    assert r.status_code == 200


def test_signup_rejects_duplicate_and_short_password(client):
    client.post("/v1/account/signup", json={"email": "c@d.com", "password": "longenough1"})
    assert client.post("/v1/account/signup", json={"email": "c@d.com", "password": "longenough1"}).status_code == 409
    assert client.post("/v1/account/signup", json={"email": "e@f.com", "password": "short"}).status_code == 422


def test_session_acts_as_its_own_workspace(client):
    client.post("/v1/account/signup", json={"email": "ws1@x.com", "password": "longenough1"})
    first = client.post("/v1/account/keys", json={"name": "k1"}).json()["key"]
    assert client.get("/v1/connections").json()["total"] == 0
    client.post("/v1/account/logout")
    client.post("/v1/account/signup", json={"email": "ws2@x.com", "password": "longenough1"})
    assert client.get("/v1/account/keys").json()["keys"] == []
    assert client.post("/v1/account/keys", json={"name": "k2"}).status_code == 200
    # the first user's key still authenticates into its own workspace
    r = client.get("/v1/account/keys", headers={"Authorization": f"Bearer {first}"})
    assert r.status_code == 200


def test_profile_and_password(client):
    client.post("/v1/account/signup", json={"email": "p@q.com", "password": "longenough1"})
    r = client.patch("/v1/account/profile", json={"name": "Grace H"})
    assert r.json()["user"]["name"] == "Grace H"
    assert client.post("/v1/account/password", json={"current": "wrong", "new": "anotherpass1"}).status_code == 400
    assert client.post("/v1/account/password", json={"current": "longenough1", "new": "anotherpass1"}).status_code == 200
    client.post("/v1/account/logout")
    assert client.post("/v1/account/login", json={"email": "p@q.com", "password": "anotherpass1"}).status_code == 200


def test_keys_are_listed_and_revocable(client):
    client.post("/v1/account/signup", json={"email": "k@k.com", "password": "longenough1"})
    kid = client.post("/v1/account/keys", json={"name": "server"}).json()["id"]
    keys = client.get("/v1/account/keys").json()["keys"]
    assert [k["id"] for k in keys] == [kid]
    assert client.delete(f"/v1/account/keys/{kid}").status_code == 200
    assert client.get("/v1/account/keys").json()["keys"] == []


def test_anonymous_is_401_not_demo_workspace(client):
    assert client.get("/v1/account/keys").status_code == 401


def test_google_verification_rejects_garbage(client):
    r = client.post("/v1/account/google", json={"credential": "not.a.token"})
    assert r.status_code in (401, 503)
