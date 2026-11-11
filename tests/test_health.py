from tony.health import classify


def test_classify_covers_the_failure_modes():
    assert classify(200, "")[0] == "healthy"
    assert classify(401, "")[0] == "auth_expired"
    assert classify(403, "")[0] == "auth_expired"
    assert classify(404, "")[0] == "schema_changed"
    assert classify(429, "")[0] == "rate_limited"
    assert classify(503, "")[0] == "unhealthy"
    assert classify(None, "ConnectTimeout: timed out")[0] == "slow"
    assert classify(None, "getaddrinfo failed")[0] == "unreachable"


def test_health_endpoints_require_a_workspace(client):
    summary = client.get("/v1/health")
    assert summary.status_code == 200 and summary.json()["total"] >= 0


def test_check_runs_and_reports(client):
    client.post("/v1/account/signup", json={"email": "h@example.com", "password": "Tony-tour-9271"})
    r = client.post("/v1/health/check")
    assert r.status_code == 200
    body = r.json()
    assert "checked" in body and "counts" in body
