"""Every app in the catalogue resolves to a real connect strategy, not a dead button."""

import json


def test_coverage_covers_the_whole_catalog(client):
    d = client.get("/v1/coverage").json()
    # The catalogue is no longer padded: real products only, and a number that adds up.
    assert d["apps_total"] > 5000
    assert sum(d["coverage"].values()) == d["apps_total"]
    assert 0 < d["connectable_now"] <= d["apps_total"]
    labels = {row["strategy"]: row["label"] for row in d["by_strategy"]}
    assert labels["key"] and labels["public"]


def test_app_auth_plan_has_strategy_and_access(client):
    d = client.get("/v1/apps/github/auth").json()
    assert d["app"] == "github"
    assert d["strategy"] in {"oauth_ready", "oauth_byo", "oauth_dcr", "key"}
    assert isinstance(d["scopes_requested"], list)


def test_key_app_reports_write_surface(client):
    apps = client.get("/v1/apps?limit=50").json()["apps"]
    assert all("strategy" in a and "connectable" in a for a in apps)
    assert any(a.get("can_write") is not None for a in apps)


def test_dynamic_registration_uses_declared_endpoint(client, monkeypatch):
    """No client id, no secret: Tony registers itself with the provider."""
    from tony import oauth

    called = {}

    class FakeResp:
        status_code = 201
        text = "{}"

        def json(self):
            return {"client_id": "dcr_client_123", "client_secret": "dcr_secret_456"}

    async def fake_post(url, payload):
        called["url"] = url
        called["payload"] = payload
        return FakeResp()

    monkeypatch.setattr(oauth, "_post_registration", fake_post)

    # An MCP twin now folds into its product, and a managed provider keeps its own
    # curated OAuth app, so the one-click MCP route belongs to non-managed vendors.
    spec = __import__("tony.catalog", fromlist=["catalog"]).catalog.get("attio")
    assert spec and spec.auth.registration_url.startswith("https://")
    import asyncio
    cid, secret = asyncio.run(oauth.dynamic_client(spec))
    assert cid == "dcr_client_123" and secret == "dcr_secret_456"
    assert called["url"] == spec.auth.registration_url, "must use the declared endpoint, not discovery"
    assert called["payload"]["redirect_uris"]
