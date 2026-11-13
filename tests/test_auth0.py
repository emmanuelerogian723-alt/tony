from tony import auth0


def test_state_roundtrip_and_expiry(monkeypatch):
    monkeypatch.setenv("TONY_TOKEN_SECRET", "s3cret")
    st = auth0.make_state("/account")
    assert auth0.check_state(st) == "/account"
    assert auth0.check_state("tony_state_deadbeef:1:/x") is None
    assert auth0.check_state(st[:-1] + "0") is None


def test_configured_requires_three_values(monkeypatch):
    monkeypatch.setenv("AUTH0_DOMAIN", "tony2.eu.auth0.com")
    monkeypatch.setenv("AUTH0_CLIENT_ID", "abc")
    monkeypatch.delenv("AUTH0_CLIENT_SECRET", raising=False)
    assert auth0.configured() is False
    monkeypatch.setenv("AUTH0_CLIENT_SECRET", "shh")
    assert auth0.configured() is True
    url = auth0.authorize_url("https://tony-7su0.onrender.com/v1/account/auth0/callback", "st")
    assert url.startswith("https://tony2.eu.auth0.com/authorize?")
    assert "response_type=code" in url


def test_login_route_404_when_unconfigured(client, monkeypatch):
    """An unconfigured provider is absent, not broken: no 503 that looks like an outage."""
    monkeypatch.delenv("AUTH0_DOMAIN", raising=False)
    r = client.get("/v1/account/auth0/login", follow_redirects=False)
    assert r.status_code == 404
    assert "not enabled" in r.json()["detail"].lower()
