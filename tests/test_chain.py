"""Cross-app chains: up to five apps, planned before anything runs."""

import pytest

from tony.chain import MAX_APPS, render


def test_chain_doc_is_agent_readable(client):
    d = client.get("/v1/chain").json()
    assert d["apps_per_chain"] == MAX_APPS == 5
    assert "templating" in d and d["example"]["steps"]


def test_six_apps_are_refused_with_the_count(client):
    steps = [{"app": a, "action": "x"} for a in
             ("hackernews", "coingecko", "arxiv", "open_meteo", "exchangerate", "dnd5eapi")]
    r = client.post("/v1/chain", json={"steps": steps})
    assert r.status_code == 400
    assert "at most 5 apps" in str(r.json()["detail"])


def test_unknown_app_is_named(client):
    r = client.post("/v1/chain", json={"steps": [{"app": "not_a_real_app", "action": "x"}]})
    assert r.status_code == 400
    assert "not_a_real_app" in str(r.json()["detail"])


def test_unknown_action_suggests_real_ones(client):
    r = client.post("/v1/chain", json={"steps": [{"app": "hackernews", "action": "stories_top"}]})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "no action" in detail["error"]


def test_template_rendering_keeps_types():
    ctx = {"steps": [{"ok": True, "data": {"items": [{"id": "abc"}]}}],
           "mail": {"data": {"count": 3, "link": "https://x.test/1"}, "ok": True}}
    assert render("{{mail.data.count}}", ctx) == 3
    assert render("see {{mail.data.link}}", ctx) == "see https://x.test/1"
    assert render("{{steps.0.data.items.0.id}}", ctx) == "abc"
    assert render("{{nope.here}}", ctx) == ""
    assert render({"a": ["{{mail.ok}}"]}, ctx) == {"a": [True]}


def test_preflight_refuses_to_half_run_a_chain(client):
    d = client.post("/v1/chain", json={"steps": [
        {"app": "hackernews", "action": "top_stories"},
        {"app": "notion", "action": "search", "args": {"query": "x"}},
    ]}).json()
    if d.get("status") != "needs_connection":   # a connected notion account wins
        pytest.skip("notion is connected in this workspace")
    assert d["ok"] is False
    assert d["steps"] == []
    assert d["needs_connection"][0]["app"] == "notion"
    assert "connect_url" in d["needs_connection"][0]


def test_five_keyless_apps_run_in_one_chain(client):
    d = client.post("/v1/chain", json={"dry_run": True, "steps": [
        {"app": "hackernews", "action": "top_stories", "as": "news"},
        {"app": "coingecko", "action": "trending", "as": "coins"},
        {"app": "exchangerate", "action": "latest", "args": {"base": "USD"}, "as": "fx"},
        {"app": "arxiv", "action": "search", "args": {"search_query": "agents"}, "as": "papers"},
        {"app": "dnd5eapi", "action": "get-api"},
    ]}).json()
    assert d["status"] == "succeeded", d
    assert len(d["apps"]) == 5
    assert d["steps_ok"] == 5 and d["steps_run"] == 5
    assert d["apps_used"] == sorted(d["apps"])
    for step in d["steps"]:
        assert step["ok"] and "latency_ms" in step


def test_write_step_needs_approval(client):
    d = client.post("/v1/chain", json={"steps": [
        {"app": "hackernews", "action": "api_request", "args": {"path": "/v0/topstories.json"}},
    ]}).json()
    assert d["ok"] is False
    assert d["steps"][0]["skipped"] is True
    assert "approve_writes" in d["steps"][0]["error"]


def test_condition_skips_a_step_cleanly(client):
    d = client.post("/v1/chain", json={"dry_run": True, "steps": [
        {"app": "hackernews", "action": "top_stories", "as": "news"},
        {"app": "coingecko", "action": "trending", "if": "{{nothing.here}}"},
    ]}).json()
    assert d["status"] == "succeeded"
    assert d["steps"][1]["skipped"] is True


def test_on_error_continue_reports_partial(client):
    d = client.post("/v1/chain", json={"dry_run": True, "on_error": "continue", "steps": [
        {"app": "hackernews", "action": "api_request", "args": {}},          # blocked write
        {"app": "coingecko", "action": "trending"},
    ]}).json()
    assert d["status"] in {"partial", "succeeded"}
    assert d["steps_ok"] >= 1


def test_bad_on_error_policy_is_400(client):
    r = client.post("/v1/chain", json={"on_error": "explode",
                                       "steps": [{"app": "hackernews", "action": "top_stories"}]})
    assert r.status_code == 400


# ── the agent's own five-app belt ─────────────────────────────────────────
def test_belt_deals_one_tool_per_app_before_a_second(client):
    from tony import power
    from tony.catalog import catalog

    specs = [catalog.get(s) for s in
             ("hackernews", "coingecko", "arxiv", "open_meteo", "exchangerate")]
    belt, index, starved = power._build_belt(specs, False)
    assert not starved
    assert len(belt) <= power.MAX_BELT_TOOLS
    assert {app for app, _action in index.values()} == {s.slug for s in specs}
    first_five = [entry["function"]["name"].split("__")[0] for entry in belt[:5]]
    assert len(set(first_five)) == 5


def test_agent_states_its_chain_limit(client):
    d = client.post("/v1/agent", json={"goal": "latest hacker news", "apps": ["hackernews"],
                                       "max_steps": 1}).json()
    assert d["apps_chain_limit"] == 5
    assert d["unknown_apps"] == []


def test_agent_reports_unknown_app_instead_of_dropping_it(client):
    d = client.post("/v1/agent", json={"goal": "anything", "apps": ["hackernews", "nope_app"],
                                       "max_steps": 1}).json()
    assert d["unknown_apps"] == ["nope_app"]


def test_meta_toolbelt_is_five_tools(client):
    d = client.get("/v1/tools/meta").json()
    assert d["count"] == 5
    names = [t["function"]["name"] for t in d["tools"]]
    assert names == ["tony_find_apps", "tony_app_actions", "tony_execute", "tony_chain", "tony_agent"]
    assert d["tools"][3]["x-tony-route"]["path"] == "/v1/chain"
    a = client.get("/v1/tools/meta?format=anthropic").json()
    assert a["tools"][0]["input_schema"]["type"] == "object"
    m = client.get("/v1/tools/meta?format=mcp").json()
    assert "inputSchema" in m["tools"][0]
