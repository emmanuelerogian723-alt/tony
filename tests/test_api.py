"""API surface: catalogue, execution, approvals, runs, triggers, workspaces."""

import pytest

from tony.executor import ExecResult


@pytest.fixture()
def fake_execute(monkeypatch):
    async def _fake(spec, action, args, creds, **kw):
        return ExecResult(True, 200, 42, {"echo": args, "app": spec.slug, "action": action.slug}, {"chars": 20})

    monkeypatch.setattr("tony.api.execute", _fake)
    # pretend every app is connected so the credential gate passes
    monkeypatch.setattr("tony.api.credentials_for", lambda *a, **k: {"access_token": "test", "api_key": "test"})
    return _fake


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["apps"] >= 40


def test_stats_and_apps(client):
    stats = client.get("/v1/stats").json()
    assert stats["apps"] >= 40 and stats["actions"] >= 100
    apps = client.get("/v1/apps").json()
    assert apps["total"] == stats["apps"]
    assert "Developer" in apps["categories"]


def test_app_detail_includes_actions(client):
    d = client.get("/v1/apps/github").json()
    assert d["slug"] == "github"
    assert any(a["slug"] == "list_repos" for a in d["actions"])
    assert d["auth"]["client_id_env"] == "GITHUB_CLIENT_ID"


def test_unknown_app_404(client):
    assert client.get("/v1/apps/nope").status_code == 404


def test_tool_schemas_openai_and_anthropic(client):
    oa = client.get("/v1/tools?fmt=openai").json()
    an = client.get("/v1/tools?fmt=anthropic").json()
    assert oa["count"] == an["count"] > 100
    assert oa["tools"][0]["function"]["name"]
    assert an["tools"][0]["input_schema"]["type"] == "object"


def test_execute_success(client, fake_execute):
    r = client.post("/v1/execute", json={"action": "github.list_repos", "args": {"per_page": 2}})
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["app"] == "github"
    assert body["run_id"]


def test_execute_unknown_action(client):
    r = client.post("/v1/execute", json={"action": "nope.nope"})
    assert r.status_code == 404


def test_write_action_requires_approval(client, fake_execute):
    r = client.post("/v1/execute", json={"action": "github.create_issue",
                                         "args": {"owner": "o", "repo": "r", "title": "t"}})
    body = r.json()
    assert body["status"] == "pending_approval"
    assert body["tier"] == "write"
    run_id = body["run_id"]

    approved = client.post(f"/v1/runs/{run_id}/approve").json()
    assert approved["ok"] is True


def test_approved_executes_directly(client, fake_execute):
    r = client.post("/v1/execute", json={"action": "github.create_issue", "approved": True,
                                         "args": {"owner": "o", "repo": "r", "title": "t"}})
    assert r.json()["ok"] is True


def test_dry_run_builds_request(client):
    r = client.post("/v1/execute", json={"action": "hackernews.top_stories", "dry_run": True})
    body = r.json()
    assert body["ok"] is True
    assert body["meta"]["dry_run"] is True
    assert body["meta"]["url"].startswith("https://hacker-news.firebaseio.com")


def test_runs_list(client, fake_execute):
    client.post("/v1/execute", json={"action": "github.list_repos", "args": {}})
    runs = client.get("/v1/runs").json()["runs"]
    assert runs and runs[0]["status"] in {"success", "pending_approval"}


def test_missing_credentials_is_clear(client, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("should not execute without credentials")

    monkeypatch.setattr("tony.api.execute", boom)
    r = client.post("/v1/execute", json={"action": "github.me"})
    # github requires OAuth and the demo workspace has no connection
    assert r.status_code == 400
    assert "No GitHub account connected" in r.json()["detail"]


def test_public_app_needs_no_credentials(client, fake_execute):
    r = client.post("/v1/execute", json={"action": "hackernews.top_stories", "args": {}})
    assert r.status_code == 200


def test_trigger_requires_min_interval(client):
    r = client.post("/v1/triggers", json={"action": "hackernews.top_stories", "interval_seconds": 5})
    assert r.status_code == 400


def test_trigger_create_list_delete(client):
    created = client.post("/v1/triggers", json={
        "action": "coingecko.price", "args": {"ids": "bitcoin", "vs_currencies": "usd"},
        "interval_seconds": 120, "webhook_url": "https://example.com/hook"}).json()
    assert created["id"] and created["secret"]
    listed = client.get("/v1/triggers").json()["triggers"]
    assert any(t["id"] == created["id"] for t in listed)
    assert client.delete(f"/v1/triggers/{created['id']}").status_code == 200


def test_connections_empty_then_public_connect(client):
    before = client.get("/v1/connections").json()
    assert "connections" in before
    r = client.post("/v1/connections/hackernews/start")
    assert r.status_code == 200
    assert r.json()["mode"] == "public"


def test_api_key_required_when_demo_closed(client, monkeypatch):
    from tony.config import settings
    monkeypatch.setattr(settings, "demo_open", False)
    r = client.post("/v1/execute", json={"action": "hackernews.top_stories"})
    assert r.status_code == 401
