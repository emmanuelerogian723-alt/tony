def test_nango_status_reports_unconfigured(client, monkeypatch):
    monkeypatch.delenv("NANGO_HOST", raising=False)
    monkeypatch.delenv("NANGO_SECRET_KEY", raising=False)
    d = client.get("/v1/nango/status").json()
    assert d["configured"] is False


def test_session_without_config_asks_for_setup(client, monkeypatch):
    monkeypatch.delenv("NANGO_HOST", raising=False)
    r = client.post("/v1/connections/gmail/nango-session")
    assert r.status_code == 409
    assert r.json()["needs_setup"] is True


def test_webhook_rejects_bad_signature(client):
    r = client.post("/v1/nango/webhook", json={"providerConfigKey": "gmail"})
    assert r.status_code == 401


def test_webhook_signature_roundtrip():
    import hashlib, hmac
    from tony import nango
    body = b'{"providerConfigKey":"gmail"}'
    sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert nango.verify_webhook(body, sig, "s3cret") is True
    assert nango.verify_webhook(body, sig, "other") is False
