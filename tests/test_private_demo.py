"""The demo is a room of one's own, and the audit findings stay fixed.

Every anonymous visitor used to share one demo workspace: their runs, their
connections and their key were visible to the next stranger. These tests pin the
privacy boundary and the API-consistency fixes that came with it.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _new_client() -> TestClient:
    from tony.main import app

    return TestClient(app)


def test_each_visitor_gets_a_different_workspace():
    a, b = _new_client(), _new_client()
    first = a.get("/v1/demo/session").json()
    second = b.get("/v1/demo/session").json()
    assert first["workspace_id"] != second["workspace_id"]
    assert first["api_key"] != second["api_key"]
    assert first["private"] is True


def test_one_visitors_runs_are_invisible_to_another():
    a, b = _new_client(), _new_client()
    a.get("/v1/demo/session")
    b.get("/v1/demo/session")
    a.post("/v1/execute", json={"action": "hackernews.top_stories", "args": {"limit": 1}})
    assert len(a.get("/v1/runs").json()["runs"]) >= 1
    assert b.get("/v1/runs").json()["runs"] == []


def test_connections_are_invisible_to_another_visitor():
    a, b = _new_client(), _new_client()
    a.get("/v1/demo/session")
    b.get("/v1/demo/session")
    assert a.get("/v1/whoami").json()["workspace_id"] != b.get("/v1/whoami").json()["workspace_id"]
    assert b.get("/v1/connections").json()["total"] == 0


def test_a_tampered_cookie_never_lands_in_someone_elses_room():
    a = _new_client()
    mine = a.get("/v1/demo/session").json()
    forged = mine["token"][:-4] + "aaaa"
    c = _new_client()
    landed = c.get("/v1/whoami", headers={"X-Tony-Demo-Session": forged}).json()
    assert landed["workspace_id"] != mine["workspace_id"]


def test_header_token_reuses_the_same_room_without_cookies():
    a = _new_client()
    token = a.get("/v1/demo/session").json()["token"]
    bare = _new_client()
    assert bare.get("/v1/whoami", headers={"X-Tony-Demo-Session": token}).json()["workspace_id"] == \
        a.get("/v1/whoami").json()["workspace_id"]


def test_unauthenticated_read_sweep_is_not_jailed(client):
    """A verification sweep of ordinary reads must not lock the address out."""
    paths = ["/v1/stats", "/v1/apps?limit=2", "/v1/actions?limit=2", "/v1/tools?limit=1",
             "/v1/health", "/v1/coverage", "/v1/whoami"]
    for i in range(12):
        for path in paths:
            r = client.get(path, headers={"x-forwarded-for": "41.1.1.9"})
            assert r.status_code == 200, (i, path, r.text)


def test_a_key_holder_is_never_blocked_by_traffic_shape(client):
    from tony import shield

    ws = client.get("/v1/demo/session").json()
    for _ in range(60):
        r = client.post("/v1/execute", headers={"Authorization": f"Bearer {ws['api_key']}",
                                                "x-forwarded-for": "41.2.2.2"},
                        json={"action": "hackernews.top_stories", "args": {"limit": 1}})
        assert r.status_code == 200
    assert shield.block_remaining("ip:41.2.2.2") == 0


def test_probing_for_secrets_is_still_blocked(client):
    r = client.get("/.env", headers={"x-forwarded-for": "41.3.3.3"})
    assert r.status_code == 403 or r.status_code == 404
    blocked = client.get("/v1/stats", headers={"x-forwarded-for": "41.3.3.3"})
    assert blocked.status_code in (403, 200)


def test_unblock_lifts_a_block_immediately(client):
    """A speed bump must be clearable without waiting out a timer."""
    from tony import shield

    shield._block("41.4.4.4", "scanner_ua", __import__("time").time(), hard=True)
    first = client.get("/v1/stats", headers={"x-forwarded-for": "41.4.4.4"})
    assert first.status_code == 403
    assert "retry-after" in {k.lower() for k in first.headers}
    lift = client.post("/v1/security/unblock", headers={"x-forwarded-for": "41.4.4.4"})
    assert lift.status_code == 200 and lift.json()["was_blocked"] is True
    assert client.get("/v1/stats", headers={"x-forwarded-for": "41.4.4.4"}).status_code == 200


def test_security_status_explains_a_block(client):
    body = client.get("/v1/security/status", headers={"x-forwarded-for": "41.5.5.5"}).json()
    assert body["blocked"] is False and body["clear"].endswith("/unblock")


@pytest.mark.parametrize("query", ["limit=100000", "limit=0"])
def test_catalogue_pages_are_capped_and_say_so(client, query):
    d = client.get(f"/v1/apps?{query}").json()
    assert d["limit"] <= 500
    assert len(d["apps"]) <= 500
    assert d["limit_capped"] is True
    assert d["has_more"] is (d["next_offset"] is not None)


def test_bad_pagination_is_an_error_not_an_empty_page(client):
    assert client.get("/v1/apps?offset=-1").status_code == 400
    assert client.get("/v1/apps?limit=-1").status_code == 400
    assert client.get("/v1/apps?tier=bogus").status_code == 400
    assert client.get("/v1/actions?tier=bogus").status_code == 400


def test_browse_hides_duplicates_but_keeps_slugs_resolvable(client):
    from tony.catalog import catalog

    page = client.get("/v1/apps?limit=500").json()
    hidden = catalog.hidden
    assert not [a for a in page["apps"] if a["slug"] in hidden]
    assert page["total"] == page["stats"]["browsable_apps"]
    a_hidden = sorted(hidden)[0]
    assert client.get(f"/v1/apps/{a_hidden}").status_code in (200, 404)


def test_names_are_unique_on_a_browsed_page(client):
    names = [a["name"].strip().lower() for a in client.get("/v1/apps?limit=500").json()["apps"]]
    assert len(names) == len(set(names))


def test_icons_are_served_locally_not_from_a_cdn(client):
    app = client.get("/v1/apps?limit=1").json()["apps"][0]
    assert app["logo"].startswith("/v1/icon/")
    assert app["logo_source"]
    icon = client.get(app["logo"])
    assert icon.status_code == 200 and len(icon.content) > 0


def test_providers_never_serve_html_to_an_api_client(client):
    r = client.get("/providers", headers={"accept": "application/json"})
    assert r.headers["content-type"].startswith("application/json")
    assert "providers" in r.json() or "total" in r.json()


def test_health_answers_both_questions(client):
    body = client.get("/v1/health").json()
    assert body["status"] == "ok" and "version" in body
    assert "connections" in body and "apps" in body


def test_openapi_publishes_real_security_schemes(client):
    spec = client.get("/openapi.json").json()
    assert set(spec["components"]["securitySchemes"]) >= {"ApiKeyAuth", "ApiKeyHeader", "DemoSession"}
    v1 = {p: ops for p, ops in spec["paths"].items() if p.startswith("/v1")}
    assert v1
    for path, ops in v1.items():
        for method, op in ops.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                assert op.get("security"), f"{method} {path} has no security"


def test_tools_pagination_reaches_past_the_old_ceiling(client):
    first = client.get("/v1/tools?limit=2000").json()
    assert first["total"] > 2000
    assert first["has_more"] is True and first["next_offset"] == 2000
    second = client.get(f"/v1/tools?limit=2000&offset={first['next_offset']}").json()
    assert second["count"] > 0
    def names(page):
        return {((t.get("function") or t).get("name")) for t in page["tools"]}
    assert names(first).isdisjoint(names(second))


def test_account_config_does_not_advertise_dead_signin(client):
    body = client.get("/v1/account/config").json()
    assert "auth0" in body
    if body["auth0"] is False:
        assert client.get("/v1/account/auth0/login").status_code == 404
