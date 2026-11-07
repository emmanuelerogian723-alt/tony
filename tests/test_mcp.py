"""MCP protocol: handshake, tool listing and tool calls."""
import json

from tony.executor import ExecResult


def rpc(client, method, params=None, rpc_id=1):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params or {}})
    assert r.status_code == 200
    return r.json()


def test_initialize(client):
    d = rpc(client, "initialize", {"protocolVersion": "2024-11-05"})
    assert d["result"]["serverInfo"]["name"] == "tony"
    assert d["result"]["capabilities"]["tools"] == {"listChanged": False}


def test_ping(client):
    assert rpc(client, "ping")["result"] == {}


def test_tools_list_paginates(client):
    first = rpc(client, "tools/list")["result"]
    assert len(first["tools"]) == 120
    assert first["nextCursor"] == "120"
    second = rpc(client, "tools/list", {"cursor": "120"})["result"]
    assert second["tools"]
    names = {t["name"] for t in first["tools"]} | {t["name"] for t in second["tools"]}
    assert "github__list_repos" in names
    assert any(t["annotations"]["readOnlyHint"] for t in first["tools"])


def test_notification_returns_empty(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 200


def test_unknown_method(client):
    d = rpc(client, "does/not/exist")
    assert d["error"]["code"] == -32601


def test_tool_call_unknown(client):
    d = rpc(client, "tools/call", {"name": "nope__nope", "arguments": {}})
    assert d["error"]["code"] == -32602


def test_tool_call_executes(client, monkeypatch):
    async def _fake(spec, action, args, creds, **kw):
        return ExecResult(True, 200, 15, {"ok": True, "args": args}, {"chars": 12})

    monkeypatch.setattr("tony.mcp.execute", _fake)
    d = rpc(client, "tools/call", {"name": "hackernews__top_stories", "arguments": {}})
    payload = json.loads(d["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert d["result"]["isError"] is False


def test_write_tool_requires_approval(client):
    d = rpc(client, "tools/call", {"name": "github__create_issue",
                                   "arguments": {"owner": "o", "repo": "r", "title": "t"}})
    payload = json.loads(d["result"]["content"][0]["text"])
    assert payload["status"] == "pending_approval"


def test_batch_request(client):
    r = client.post("/mcp", json=[
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])
    assert len(r.json()) == 2
