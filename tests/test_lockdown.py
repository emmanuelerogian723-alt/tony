"""The five v1 gaps closed together: SSRF, key scope, latency, providers, headers.

Each test is named after the symptom a caller saw, so a regression is obvious.
"""
from __future__ import annotations

import pytest


# ── 1. SSRF: /v1/read must refuse inward targets at submit ───────────────────

@pytest.mark.parametrize("target", [
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost:8000/",
    "http://127.0.0.1/",
    "http://10.0.0.5/x",
    "http://192.168.1.1/",
    "http://metadata.google.internal/",
    "http://[::1]/",
    "http://intranet/",
])
def test_read_refuses_inward_targets_at_submit(client, target):
    r = client.post("/v1/read", json={"url": target})
    assert r.status_code == 400, r.text
    assert "Refused target" in r.json()["detail"]


def test_read_still_accepts_a_public_site(client):
    r = client.post("/v1/read", json={"site": "https://example.com", "max_pages": 1})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_network_guard_units():
    from tony import netguard

    assert netguard.blocked_ip("169.254.169.254")
    assert netguard.blocked_ip("93.184.216.34") == ""
    assert netguard.blocked_host("metadata.google.internal")
    assert netguard.blocked_host("wiki")
    assert netguard.blocked_host("example.com") == ""
    with pytest.raises(netguard.Blocked):
        netguard.check_url("file:///etc/passwd")
    with pytest.raises(netguard.Blocked):
        netguard.check_url("http://user:pass@example.com/")
    # a name that does not resolve is not proof of a private target
    assert netguard.check_url_resolved_sync("https://nothing-here.invalid") == "https://nothing-here.invalid"


def test_directory_base_url_uses_the_same_guard(client):
    from fastapi import HTTPException

    from tony.api import normalise_base_url

    assert normalise_base_url("https://api.example.com/v1")
    with pytest.raises(HTTPException):
        normalise_base_url("http://169.254.169.254")


def test_read_pages_blocked_mid_crawl(monkeypatch):
    """A page that resolves inward fails with a reason instead of hanging."""
    import asyncio

    from tony import netguard, reader

    calls = {}

    def fake_save(page_id, **kw):
        calls.update(kw)

    monkeypatch.setattr(reader, "_save_page", fake_save)
    monkeypatch.setattr(reader, "_hash", lambda _u: "h")

    async def boom(_url):
        raise netguard.Blocked("127.0.0.1 is a private or link-local address")

    monkeypatch.setattr(netguard, "check_url_resolved", boom)
    out = asyncio.run(reader._fetch_one(None, {"id": "j", "seed_url": ""},
                                        {"id": "p", "url": "http://169.254.169.254/"}))
    assert "blocked" in out
    assert calls["status"] == "failed"
    assert "private" in calls["error"]


# ── 2. Scoped keys ───────────────────────────────────────────────────────────

def _key(client, **body):
    import uuid

    email = f"scope-{uuid.uuid4().hex[:8]}@x.com"
    r = client.post("/v1/account/signup", json={"email": email, "password": "longenough1"})
    assert r.status_code == 200, r.text
    r = client.post("/v1/account/keys", json=body)
    assert r.status_code == 200, r.text
    return r.json()["key"], r.json()


def test_key_can_be_limited_to_apps(client):
    key, made = _key(client, name="narrow", apps=["github"])
    assert made["apps"] == ["github"]

    # a scoped key is refused on another app, before any provider call
    r = client.post("/v1/execute", json={"action": "hackernews.top", "entity_id": "default", "args": {}},
                    headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 403, r.text
    assert "limited to github" in r.json()["detail"]


def test_key_can_be_read_only(client):
    key, made = _key(client, name="reader", read_only=True)
    assert made["read_only"] is True

    from tony import auth

    class FakeRequest:
        class state:  # noqa: N801 - mimics Starlette's attribute bag
            pass

    req = FakeRequest()
    token = auth.key_row(key)
    req.state.key_scope = token
    auth.enforce_key_scope(req, "github", "read")
    with pytest.raises(Exception) as exc:
        auth.enforce_key_scope(req, "github", "write")
    assert getattr(exc.value, "status_code", 0) == 403


def test_scope_can_be_narrowed_without_a_new_secret(client):
    key, made = _key(client, name="grow")
    assert made["apps"] == []

    r = client.patch(f"/v1/account/keys/{made['id']}", json={"apps": ["github"], "read_only": True})
    assert r.status_code == 200, r.text
    assert r.json()["apps"] == ["github"] and r.json()["read_only"] is True

    # unknown slugs are refused rather than silently dropped
    assert client.patch(f"/v1/account/keys/{made['id']}",
                        json={"apps": ["not-a-real-app"]}).status_code == 400

    listed = client.get("/v1/account/keys").json()["keys"]
    assert listed[0]["apps"] == ["github"]


# ── 3. Unfiltered /v1/actions is a slice, not a rebuild ──────────────────────

def test_unfiltered_actions_is_fast_and_complete(client):
    import time

    client.get("/v1/actions?limit=1")           # warm the flat index
    start = time.perf_counter()
    r = client.get("/v1/actions?limit=50")
    took = time.perf_counter() - start
    body = r.json()
    assert r.status_code == 200
    assert body["total"] > 30_000
    assert len(body["actions"]) == 50
    assert took < 1.0, f"unfiltered listing took {took:.2f}s"


def test_action_paging_and_filters_still_agree_with_search(client):
    a = client.get("/v1/actions?limit=5").json()
    b = client.get("/v1/actions?limit=5&offset=5").json()
    assert {x["tool_name"] for x in a["actions"]}.isdisjoint({x["tool_name"] for x in b["actions"]})
    assert b["offset"] == 5
    write = client.get("/v1/actions?tier=write&limit=3").json()
    assert all(x["tier"] == "write" for x in write["actions"])


# ── 4. /v1/account/providers accepts a key ──────────────────────────────────

def test_providers_accepts_a_valid_key(client):
    key, _made = _key(client, name="prov")
    r = client.get("/v1/account/providers", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200, r.text
    assert "providers" in r.json()


def test_providers_without_credentials_is_401_not_403(client):
    r = client.get("/v1/account/providers")
    assert r.status_code == 401


# ── 5. Security and budget headers ──────────────────────────────────────────

def test_security_headers_on_every_response(client):
    for path in ("/v1/apps?limit=1", "/v1/health", "/does-not-exist"):
        r = client.get(path)
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "SAMEORIGIN"
        assert "camera=()" in r.headers["permissions-policy"]
        assert "default-src 'self'" in r.headers["content-security-policy"]


def test_rate_limit_headers_are_visible(client):
    r = client.get("/v1/apps?limit=1")
    assert r.headers["x-ratelimit-limit"] == "3000"
    assert int(r.headers["x-ratelimit-remaining"]) >= 0
    assert r.headers["ratelimit-policy"] == "3000;w=60"


def test_hsts_only_when_served_over_https(client):
    assert "strict-transport-security" not in client.get("/v1/health").headers
    r = client.get("/v1/health", headers={"x-forwarded-proto": "https"})
    assert "max-age=31536000" in r.headers["strict-transport-security"]
