"""Plans, quotas, sessions and payments."""
import time

import pytest


@pytest.fixture()
def fake_execute(monkeypatch):
    from tony.executor import ExecResult

    async def _fake(spec, action, args, creds, dry_run=False):
        return ExecResult(ok=True, status=200, data={"ok": True}, latency_ms=3)

    monkeypatch.setattr("tony.api.execute", _fake)
    monkeypatch.setattr("tony.api.credentials_for", lambda *a, **k: {"access_token": "t", "api_key": "t"})
    return _fake


_IP = [0]


def signup(client):
    _IP[0] += 1
    ip = f"10.9.{_IP[0] % 250}.7"
    email = f"p{int(time.time()*1000)}{_IP[0]}@tony.test"
    r = client.post("/v1/account/signup", json={"email": email, "password": "Tony-test-9271", "name": "Pat"},
                    headers={"x-forwarded-for": ip})
    assert r.status_code == 200, r.text
    return email


def test_plans_are_public_and_generous(client):
    d = client.get("/v1/billing/plans").json()
    ids = [p["id"] for p in d["plans"]]
    assert ids == ["free", "pro", "business"]
    free = d["plans"][0]
    assert free["runs"] >= 5000
    assert free["apps"] == "all" and free["write"] is True
    # A trial is opt-in per deployment: nothing paid is handed out by default.
    assert d["trial_days"] == 0


def test_signup_starts_on_free_not_pro(client):
    signup(client)
    me = client.get("/v1/account/me").json()
    assert me["billing"]["plan_id"] == "free"
    assert me["billing"]["paid"] is False
    assert me["billing"]["status"] in {"active", "trialing"}


def test_billing_me_reports_usage_and_limits(client):
    d = client.get("/v1/billing/me").json()
    assert d["plan_id"] in {"free", "pro", "business"}
    for key in ("runs", "connected_accounts", "keys", "sessions"):
        assert key in d["usage"] and key in d["limits"]


def test_run_quota_blocks_with_upgrade_message(client, fake_execute, monkeypatch):
    from tony.billing import PLANS

    monkeypatch.setitem(PLANS["free"], "runs", 0)
    r = client.post("/v1/execute", json={"action": "hackernews.top_stories"})
    assert r.status_code == 402
    detail = r.json()["detail"]
    assert detail["kind"] == "runs" and "upgrade" in detail


def test_key_capacity_follows_plan(client, monkeypatch):
    from tony.billing import PLANS

    signup(client)
    # the new account is on Free, so Free's key limit is what applies
    monkeypatch.setitem(PLANS["free"], "keys", 1)
    assert client.post("/v1/account/keys", json={"name": "one"}).status_code == 200
    r = client.post("/v1/account/keys", json={"name": "two"})
    assert r.status_code == 402
    assert r.json()["detail"]["kind"] == "keys"


def test_session_lifecycle_and_scoping(client, fake_execute):
    created = client.post("/v1/sessions", json={
        "entity_id": "user_42", "label": "support", "apps": ["hackernews"],
        "tiers": ["read"], "ttl_hours": 2, "run_limit": 2}).json()
    sid = created["id"]
    assert created["apps"] == ["hackernews"]

    listed = client.get("/v1/sessions").json()["sessions"]
    assert any(s["id"] == sid for s in listed)

    ok = client.post("/v1/execute", json={"action": "hackernews.top_stories"},
                     headers={"X-Tony-Session": sid})
    assert ok.status_code == 200

    blocked = client.post("/v1/execute", json={"action": "github.list_repos"},
                          headers={"X-Tony-Session": sid})
    assert blocked.status_code == 403
    assert "scoped to" in blocked.json()["detail"]

    # budget of 2: one spent, one left, then refused
    client.post("/v1/execute", json={"action": "hackernews.top_stories"}, headers={"X-Tony-Session": sid})
    over = client.post("/v1/execute", json={"action": "hackernews.top_stories"},
                       headers={"X-Tony-Session": sid})
    assert over.status_code == 402
    assert client.delete(f"/v1/sessions/{sid}").json()["revoked"] is True


def test_session_rejects_unknown_app(client):
    r = client.post("/v1/sessions", json={"apps": ["not_a_real_app"]})
    assert r.status_code == 400


def test_passcode_unlocks_tier(client, monkeypatch):
    monkeypatch.setenv("TONY_PASS_CODES", "TONY-PRO:pro:30")
    signup(client)
    r = client.post("/v1/billing/passcode", json={"code": "tony-pro"})
    assert r.status_code == 200
    assert r.json()["plan"] == "pro"
    me = client.get("/v1/account/me").json()
    assert me["billing"]["provider"] == "passcode"
    bad = client.post("/v1/billing/passcode", json={"code": "nope"})
    assert bad.status_code == 400


def test_checkout_without_payment_key_is_clear(client, monkeypatch):
    monkeypatch.delenv("PAYSTACK_SECRET_KEY", raising=False)
    signup(client)
    r = client.post("/v1/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 503
    assert "PAYSTACK_SECRET_KEY" in r.json()["detail"]["error"]


def test_paystack_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_123")
    r = client.post("/v1/billing/webhook/paystack", json={"event": "charge.success"},
                    headers={"x-paystack-signature": "deadbeef"})
    assert r.status_code == 401


def test_webhook_activates_paid_plan(client, monkeypatch):
    import hashlib
    import hmac
    import json
    from tony.db import session as db
    from tony.models import PaymentEvent, User

    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_123")
    email = signup(client)
    with db() as s:
        user = s.scalar(__import__("sqlalchemy").select(User).where(User.email == email))
        s.add(PaymentEvent(user_id=user.id, workspace_id=user.workspace_id, provider="paystack",
                           reference="ref_test_1", plan="business", months=1, amount=2500000,
                           currency="NGN", status="pending"))
    body = json.dumps({"event": "charge.success", "data": {"reference": "ref_test_1"}}).encode()
    sig = hmac.new(b"sk_test_123", body, hashlib.sha512).hexdigest()
    r = client.post("/v1/billing/webhook/paystack", content=body,
                    headers={"x-paystack-signature": sig, "content-type": "application/json"})
    assert r.status_code == 200
    me = client.get("/v1/account/me").json()
    assert me["billing"]["plan_id"] == "business"
    assert me["billing"]["status"] == "active"
