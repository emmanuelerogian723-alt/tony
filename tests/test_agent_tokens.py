from tony import agenttokens


def test_roundtrip_and_expiry(monkeypatch):
    monkeypatch.setenv("TONY_TOKEN_SECRET", "test-secret")
    tok = agenttokens.issue("ws_1", "cursor", ["hackernews"], ["read"], 2)
    payload = agenttokens.verify(tok["token"])
    assert payload and payload["ws"] == "ws_1"
    assert agenttokens.allows(payload, "hackernews", "read")
    assert not agenttokens.allows(payload, "github", "read")
    assert not agenttokens.allows(payload, "hackernews", "write")


def test_tampering_rejected(monkeypatch):
    monkeypatch.setenv("TONY_TOKEN_SECRET", "test-secret")
    tok = agenttokens.issue("ws_1", "a", ["hackernews"], ["read"])["token"]
    assert agenttokens.verify(tok[:-2] + "00") is None
    assert agenttokens.verify("tony_at_garbage") is None


def test_agent_token_is_enforced_on_execute(client, monkeypatch):
    monkeypatch.setenv("TONY_TOKEN_SECRET", "test-secret")
    minted = client.post("/v1/agent-tokens", json={"name": "scoped", "apps": ["hackernews"],
                                                   "tiers": ["read"]}).json()
    tok = minted["token"]
    ok = client.post("/v1/execute", headers={"Authorization": f"Bearer {tok}"},
                     json={"action": "hackernews.top_stories", "args": {}})
    assert ok.status_code == 200, ok.text
    blocked = client.post("/v1/execute", headers={"Authorization": f"Bearer {tok}"},
                          json={"action": "github.list_repos", "args": {}})
    assert blocked.status_code == 403
    assert "grants" in blocked.json()["detail"]
