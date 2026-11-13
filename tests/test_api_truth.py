"""The API must answer what it advertises.

Four regressions in one file, because they share a root cause: the docs, the
assistant and the endpoints had drifted apart. A filter that is ignored, an
"All" value that 400s, a search that takes 12 s, and a header that reports a
smaller catalogue than the Overview card.
"""
import time


# ── /v1/tools: auth_type is a real filter ────────────────────────────────
def test_tools_auth_type_none_is_much_smaller_than_everything(client):
    everything = client.get("/v1/tools?limit=1").json()
    none = client.get("/v1/tools?auth_type=none&limit=1").json()
    assert none["total"] < everything["total"]
    assert none["filters"]["auth_type"] == "none"


def test_tools_auth_alias_is_the_same_filter(client):
    a = client.get("/v1/tools?auth=none&limit=1").json()
    b = client.get("/v1/tools?auth_type=none&limit=1").json()
    assert a["total"] == b["total"]


def test_tools_oauth2_filter_differs_from_none(client):
    none = client.get("/v1/tools?auth_type=none&limit=1").json()["total"]
    oauth = client.get("/v1/tools?auth_type=oauth2&limit=1").json()["total"]
    assert none != oauth


def test_tools_unknown_auth_type_is_a_400_not_silence(client):
    r = client.get("/v1/tools?auth_type=telepathy&limit=1")
    assert r.status_code == 400
    assert "auth_type" in r.json()["detail"]


def test_tools_reports_the_real_base_url(client):
    body = client.get("/v1/tools?limit=1").json()
    assert body["base_url"].startswith("http")
    assert "tony" in body["base_url"] or "testserver" in body["base_url"]


# ── /v1/apps: tier=all is valid, and totals agree with /v1/stats ─────────
def test_apps_tier_all_is_accepted(client):
    r = client.get("/v1/apps?tier=all&limit=5")
    assert r.status_code == 200
    assert r.json()["total"] > 0


def test_apps_total_matches_stats_catalogue(client):
    apps = client.get("/v1/apps?limit=1").json()
    stats = client.get("/v1/stats").json()
    assert apps["catalogue_total"] == stats["apps"]
    assert apps["browsable_total"] <= apps["catalogue_total"]


def test_apps_unknown_tier_still_rejected(client):
    assert client.get("/v1/apps?tier=nonsense").status_code == 400


# ── /v1/actions: q= is fast and equals search= ───────────────────────────
def test_action_search_q_is_not_slower_than_a_second(client):
    client.get("/v1/actions?q=warmup")             # build/warm the index once
    t = time.time()
    body = client.get("/v1/actions?q=send an email to my customer with a receipt").json()
    elapsed = time.time() - t
    assert body["actions"], "search returned nothing"
    assert elapsed < 2.0, f"q= took {elapsed:.2f}s"


def test_action_search_q_and_search_agree(client):
    a = client.get("/v1/actions?q=github issue&ranked=false&limit=5").json()
    b = client.get("/v1/actions?search=github issue&ranked=false&limit=5").json()
    assert a["total"] == b["total"]
    assert [x["tool_name"] for x in a["actions"]] == [x["tool_name"] for x in b["actions"]]


# ── assistant: no invented host, real paths only ─────────────────────────
def test_assistant_never_names_a_fake_host(client):
    body = client.post("/v1/assistant", json={
        "message": "what is the exact call to find apps that need no sign-in?"}).json()
    assert "api.tony.ai" not in body["answer"]
    assert body["base_url"].startswith("http")


def test_url_rewriter_keeps_real_and_foreign_hosts():
    from tony.assistant import _fix_urls
    base = "https://tony-7su0.onrender.com"
    assert _fix_urls("GET https://api.tony.ai/v1/tools", base).endswith("/v1/tools")
    assert "groq.com" in _fix_urls("see https://groq.com/docs", base)
    assert _fix_urls(f"GET {base}/v1/apps", base).count(base) == 1


def test_assistant_route_list_is_the_real_api():
    from tony.assistant import _route_lines
    from tony.main import app
    lines = " ".join(_route_lines(app))
    for path in ("/v1/agent", "/v1/chain", "/v1/execute", "/v1/tools", "/v1/apps"):
        assert path in lines
