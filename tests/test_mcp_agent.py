import json


def _rpc(client, method, params=None, name=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    return client.post("/mcp", json=payload)


def test_mcp_exposes_agent_and_catalogue_tools(client):
    r = _rpc(client, "tools/list", {"cursor": "0"})
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["result"]["tools"]]
    assert "tony_agent" in names
    assert "tony_apps" in names


def test_mcp_apps_tool_returns_catalogue(client):
    r = _rpc(client, "tools/call", {"name": "tony_apps", "arguments": {"query": "hacker", "limit": 5}})
    body = r.json()["result"]
    data = json.loads(body["content"][0]["text"])
    assert data["ok"] and data["apps"], data
    assert any(a["app"] == "hackernews" for a in data["apps"])


def test_mcp_discovery_mentions_stdio_bridge(client):
    r = client.get("/mcp")
    assert r.status_code == 200
    assert "stdio_bridge" in r.json()
