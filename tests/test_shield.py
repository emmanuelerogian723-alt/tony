import pytest

from tony import shield


@pytest.fixture(autouse=True)
def _clean():
    shield.reset()
    yield
    shield.reset()


def test_probe_paths_get_blocked_quickly(client):
    codes = [client.get(p, headers={"x-forwarded-for": "9.9.9.9"}).status_code
             for p in ("/.env", "/wp-admin", "/.git/config", "/phpmyadmin", "/etc/passwd")]
    assert 403 in codes
    after = client.get("/health", headers={"x-forwarded-for": "9.9.9.9"})
    assert after.status_code in (200, 403)
    blocked = client.get("/v1/stats", headers={"x-forwarded-for": "9.9.9.9"})
    assert blocked.status_code == 403


def test_scanner_user_agent_is_scored(client):
    for _ in range(4):
        client.get("/v1/stats", headers={"user-agent": "sqlmap/1.7", "x-forwarded-for": "8.8.4.4"})
    assert client.get("/v1/stats", headers={"x-forwarded-for": "8.8.4.4"}).status_code == 403


def test_credential_stuffing_is_blocked(client):
    last = 0
    for i in range(25):
        last = client.get("/v1/runs", headers={"authorization": f"Bearer tk_live_wrong{i:04d}",
                                               "x-forwarded-for": "7.7.7.7"}).status_code
    assert last == 403


def test_normal_traffic_is_untouched(client):
    for _ in range(12):
        assert client.get("/v1/stats", headers={"x-forwarded-for": "1.2.3.4"}).status_code == 200


def test_one_attacker_does_not_block_others(client):
    for p in ("/.env", "/wp-admin", "/.git/config", "/phpmyadmin"):
        client.get(p, headers={"x-forwarded-for": "6.6.6.6"})
    assert client.get("/v1/stats", headers={"x-forwarded-for": "5.5.5.5"}).status_code == 200


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_ordinary_api_clients_are_not_scanners(client):
    # curl and python-requests are how developers test; a handful of calls must
    # never lock them out of the API or the site.
    for i in range(6):
        r = client.get("/v1/stats", headers={"user-agent": "python-requests/2.31.0",
                                             "x-forwarded-for": "7.7.7.7"})
        assert r.status_code != 403
    for i in range(6):
        r = client.get("/v1/stats", headers={"user-agent": "curl/7.81.0",
                                             "x-forwarded-for": "7.7.7.6"})
        assert r.status_code != 403


def test_page_views_are_never_blocked(client):
    for p in ("/.env", "/wp-admin", "/.git/config", "/phpmyadmin", "/etc/passwd"):
        client.get(p, headers={"x-forwarded-for": "6.6.6.6"})
    home = client.get("/", headers={"x-forwarded-for": "6.6.6.6"})
    assert home.status_code == 200
