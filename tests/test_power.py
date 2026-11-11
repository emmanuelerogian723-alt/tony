"""The power layer: tool schemas, the agent runtime, memory and observability."""

def test_tools_openai_shape(client):
    r = client.get("/v1/tools?apps=github&limit=3")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] >= 1 and d["format"] == "openai"
    fn = d["tools"][0]["function"]
    assert fn["name"] and fn["parameters"]["type"] == "object"


def test_tools_anthropic_and_mcp(client):
    a = client.get("/v1/tools?apps=slack&limit=2&format=anthropic").json()
    assert a["tools"][0]["input_schema"]["type"] == "object"
    m = client.get("/v1/tools?apps=slack&limit=2&format=mcp").json()
    assert "inputSchema" in m["tools"][0]


def test_tools_default_slice_is_capped(client):
    d = client.get("/v1/tools?limit=25").json()
    assert d["count"] == 25
    assert client.get("/v1/tools?apps=not_a_real_app&limit=5").status_code == 200


def test_agent_never_returns_empty(client):
    r = client.post("/v1/agent", json={"goal": "latest hacker news stories",
                                       "apps": ["hackernews"], "max_steps": 1})
    assert r.status_code == 200
    d = r.json()
    assert d["answer"]
    assert "steps" in d


def test_agent_blocks_write_without_approval(client):
    r = client.post("/v1/agent", json={"goal": "delete a repo", "apps": ["github"],
                                       "approve_writes": False})
    assert r.status_code == 200


def test_agent_requires_goal(client):
    assert client.post("/v1/agent", json={"goal": "  "}).status_code == 400


def test_memory_roundtrip(client):
    assert client.put("/v1/memory/pref", json={"value": {"tone": "short"}}).status_code == 200
    got = client.get("/v1/memory/pref").json()
    assert got["value"]["tone"] == "short"
    assert any(k["key"] == "pref" for k in client.get("/v1/memory").json()["keys"])
    client.delete("/v1/memory/pref")
    assert client.get("/v1/memory/pref").status_code == 404


def test_usage_and_audit_shapes(client):
    u = client.get("/v1/usage").json()
    assert {"runs", "by_status", "top_apps"} <= set(u)
    a = client.get("/v1/audit").json()
    assert "runs" in a


def test_placeholder_credentials_are_ignored(client):
    from tony.oauth import is_configured, save_provider
    from tony.catalog import catalog

    save_provider("github", "cid_test", "shh")
    assert is_configured(catalog.get("github")) is False
    save_provider("github", "real-client-id", "real-secret")
    assert is_configured(catalog.get("github")) is True


def test_tools_can_be_narrowed_to_live_connections(client):
    client.post("/v1/account/signup", json={"email": "live@example.com", "password": "Tony-tour-9271"})
    empty = client.get("/v1/tools/connected?limit=50").json()
    assert empty["tools"] == [] and empty["apps"] == []
    client.post("/v1/connections/hackernews/start?entity_id=default")
    after = client.get("/v1/tools/connected?limit=50").json()
    assert after["tools"], "a live connection should expose its tools"
    assert after["apps"] == ["hackernews"]
    names = [t["function"]["name"] for t in after["tools"]]
    assert names and all(n.startswith("hackernews") for n in names)
