def test_install_lists_clients_pointing_at_this_host(client):
    d = client.get("/v1/install", headers={"host": "tony.example.com"}).json()
    ids = {c["id"] for c in d["clients"]}
    assert {"claude-code", "cursor", "vscode", "codex", "curl", "python"} <= ids
    cursor = next(c for c in d["clients"] if c["id"] == "cursor")
    assert "tony.example.com/mcp" in cursor["snippet"]
    assert d["mcp_url"].endswith("/mcp")


def test_install_key_is_sanitised(client):
    d = client.get("/v1/install", params={"key": 'x"; DROP TABLE'}).json()
    assert "DROP TABLE" not in str(d)


def test_oauth_client_without_secret_fails_fast(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    r = client.post("/v1/connections/gmail/start?entity_id=default")
    assert r.status_code == 409
    assert "client secret" in r.json()["detail"].lower()
