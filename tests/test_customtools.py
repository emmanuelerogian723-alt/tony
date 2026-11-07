"""Custom HTTP tools and batch execution."""
import pytest


@pytest.fixture()
def fake_http(monkeypatch):
    from tony import customtools

    calls = {}

    class Resp:
        status_code = 200
        text = '{"ok": true}'

        def json(self):
            return {"ok": True, "echo": calls.get("last")}

    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, headers=None, json=None):
            calls["last"] = {"method": method, "url": url, "headers": headers, "body": json}
            return Resp()

    monkeypatch.setattr(customtools.httpx, "AsyncClient", Client)
    return calls


def make(client, slug="my_api", **kw):
    body = {"slug": slug, "url": "https://api.example.com/v1/items/{item_id}", "method": "GET"}
    body.update(kw)
    return client.post("/v1/custom-tools", json=body)


def test_create_list_update_delete(client):
    r = make(client, description="internal catalogue")
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "custom.my_api"
    assert client.get("/v1/custom-tools").json()["total"] >= 1
    upd = client.put("/v1/custom-tools/my_api", json={"slug": "my_api", "url": "https://api.example.com/v2/{item_id}",
                                                      "method": "GET", "tier": "write"})
    assert upd.status_code == 200 and upd.json()["tier"] == "write"
    assert client.delete("/v1/custom-tools/my_api").status_code == 200


def test_rejects_private_hosts_and_bad_slug(client):
    assert make(client, slug="x", url="https://a.example.com").status_code in {400, 422}
    assert make(client, slug="local1", url="http://localhost:9000/x").status_code == 400
    assert make(client, slug="local2", url="http://192.168.0.4/x").status_code == 400


def test_execute_fills_placeholders_and_secret(client, fake_http):
    make(client, slug="fill_test", secret="s3cret", auth_style="bearer", token_url="")
    r = client.post("/v1/execute", json={"action": "custom.fill_test", "args": {"item_id": "42"}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["run_id"]
    sent = fake_http["last"]
    assert sent["url"].endswith("/v1/items/42")
    assert sent["headers"]["Authorization"] == "Bearer s3cret"


def test_write_tier_needs_approval(client, fake_http):
    make(client, slug="writer", tier="write", method="POST", url="https://api.example.com/write",
         body_template='{"id": "{item_id}"}')
    first = client.post("/v1/execute", json={"action": "custom.writer", "args": {"item_id": "7"}}).json()
    assert first["status"] == "pending_approval"
    second = client.post("/v1/execute", json={"action": "custom.writer", "args": {"item_id": "7"},
                                              "approved": True}).json()
    assert second["ok"] is True
    assert fake_http["last"]["body"] == {"id": "7"}


def test_unknown_custom_tool_is_404(client):
    r = client.post("/v1/execute", json={"action": "custom.ghost"})
    assert r.status_code == 404


def test_batch_runs_and_reports_each_call(client, fake_http):
    make(client, slug="batcher")
    r = client.post("/v1/batch", json={"calls": [
        {"action": "hackernews.top_stories"},
        {"action": "custom.batcher", "args": {"item_id": "9"}},
        {"action": "custom.missing"}]})
    d = r.json()
    assert d["count"] == 3
    assert d["succeeded"] >= 1
    assert [x["ok"] for x in d["results"]][2] is False


def test_batch_is_capped(client):
    r = client.post("/v1/batch", json={"calls": [{"action": "hackernews.top_stories"}] * 21})
    assert r.status_code == 400


def test_custom_tool_capacity(client, monkeypatch):
    from tony.billing import PLANS

    monkeypatch.setitem(PLANS["free"], "custom_tools", 0)
    r = make(client, slug="over_cap")
    assert r.status_code == 402
    assert r.json()["detail"]["kind"] == "custom_tools"
