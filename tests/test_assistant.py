"""Tony assistant scope, live numbers, gap logging and ecosystem endpoints."""
import time

import pytest


def signup(client):
    r = client.post("/v1/account/signup", json={
        "email": f"a{int(time.time()*1000000)}@tony.test",
        "password": "Tony-test-9271"}, headers={"x-forwarded-for": f"10.4.{int(time.time()) % 250}.9"})
    assert r.status_code == 200, r.text


def test_pricing_answer_is_grounded(client):
    d = client.post("/v1/assistant", json={"message": "how much is the pro plan?"}).json()
    assert d["topic"] == "pricing" and d["grounded"] is True
    assert "7,500" in d["answer"]
    assert d["scope"] == "tony-only"


def test_usage_answer_reads_live_state(client):
    signup(client)
    d = client.post("/v1/assistant", json={"message": "how many runs do I have left?"}).json()
    assert d["topic"] == "usage"
    assert "5,000" in d["answer"] or "150,000" in d["answer"]
    assert "billing" in d["answer"].lower()


def test_out_of_scope_question_is_refused_and_logged(client):
    d = client.post("/v1/assistant", json={"message": "who won the world cup in 1998?"}).json()
    assert d["grounded"] is False
    assert "Tony" in d["answer"]
    gaps = client.get("/v1/assistant/insights").json()["questions_without_answers"]
    assert any("world cup" in g["question"].lower() for g in gaps)


def test_insights_report_success_rate_and_failures(client):
    d = client.get("/v1/assistant/insights").json()
    assert 0 <= d["success_rate"] <= 100
    assert isinstance(d["failing_actions"], list)


def test_rating_roundtrip(client):
    r = client.post("/v1/ratings", json={"app_slug": "hackernews", "stars": 5, "review": "fast"})
    assert r.status_code == 200 and r.json()["average"] > 0
    listed = client.get("/v1/ratings?app=hackernews").json()
    assert any(a["app"] == "hackernews" for a in listed["apps"])


def test_rating_rejects_unknown_app_and_bad_stars(client):
    assert client.post("/v1/ratings", json={"app_slug": "nope", "stars": 5}).status_code == 404
    assert client.post("/v1/ratings", json={"app_slug": "hackernews", "stars": 9}).status_code == 422


def test_versions_and_security_defaults(client):
    v = client.get("/v1/apps/github/versions").json()
    assert v["versions"][0]["version"] == "1.0.0"
    s = client.get("/v1/apps/github/security").json()
    assert s["verdict"] in {"pass", "review"}
    assert s["approval_gate"]


def test_usage_stats_shape(client):
    d = client.get("/v1/stats/usage?days=7").json()
    assert d["window_days"] == 7
    assert isinstance(d["by_app"], list) and isinstance(d["by_day"], list)


def test_revenue_and_ecosystem_summary(client):
    r = client.get("/v1/revenue").json()
    assert "pending_ngn" in r and "60%" in r["policy"]
    s = client.get("/v1/ecosystem/summary").json()
    assert s["apps"] > 1000 and s["actions"] > s["apps"]


def test_sdk_page_and_downloads(client):
    page = client.get("/sdk")
    assert page.status_code == 200 and "Python" in page.text and "Java" in page.text
    for name in ("tony_sdk.py", "tony.ts", "tony.js", "tony.go", "Tony.java"):
        f = client.get(f"/sdk/{name}")
        assert f.status_code == 200 and len(f.text) > 500, name
    assert client.get("/sdk/evil.sh").status_code == 404


def test_plugins_listed(client):
    d = client.get("/v1/plugins").json()
    assert d["count"] >= 8
    assert any(p["kind"] == "MCP" for p in d["plugins"])
