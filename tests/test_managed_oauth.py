"""End-to-end managed OAuth: click Connect, consent, callback, tokens, agent use.

A real local provider stands in for Google/Slack so the whole pipeline is
exercised over HTTP: authorize -> state -> token exchange -> identity -> encrypted
storage -> agent execution -> refresh -> revoke. No credentials are mocked away.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

STATE = {"tokens": 0, "revoked": 0, "userinfo": 0, "last_scope": "", "refresh": 0}


def make_provider(port: int) -> FastAPI:
    app = FastAPI()

    @app.get("/authorize")
    def authorize(client_id: str = "", redirect_uri: str = "", state: str = "", scope: str = "",
                  code_challenge: str = "", **kw):
        STATE["last_scope"] = scope
        return RedirectResponse(f"{redirect_uri}?code=good-code&state={state}")

    @app.post("/token")
    async def token(request: Request):
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        if form.get("grant_type") == "refresh_token":
            STATE["refresh"] += 1
            return JSONResponse({"access_token": "refreshed-token", "expires_in": 3600,
                                 "token_type": "Bearer"})
        STATE["tokens"] += 1
        return JSONResponse({
            "access_token": "at-123", "refresh_token": "rt-123", "expires_in": 3600,
            "token_type": "Bearer", "scope": "read write",
        })

    @app.get("/userinfo")
    def userinfo():
        STATE["userinfo"] += 1
        return {"email": "rejoice@example.com", "name": "Rejoice Gideon"}

    @app.post("/revoke")
    def revoke():
        STATE["revoked"] += 1
        return {"ok": True}

    return app


@pytest.fixture(scope="module")
def provider():
    port = 8931
    server = uvicorn.Server(uvicorn.Config(make_provider(port), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(60):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.fixture()
def wiring(provider, monkeypatch):
    """Point a fake app at the local provider and register its managed metadata."""
    from tony import catalog as catalog_mod, provider_registry as reg
    from tony.catalog import ActionSpec, AppSpec, AuthSpec

    monkeypatch.setenv("MOCKAPP_CLIENT_ID", "client-abc")
    monkeypatch.setenv("MOCKAPP_CLIENT_SECRET", "secret-xyz")
    prob = reg.Provider(
        slug="mockapp", name="Mock App", authorize_url=f"{provider}/authorize",
        token_url=f"{provider}/token", scopes=("read", "write"),
        env=("MOCKAPP_CLIENT_ID", "MOCKAPP_CLIENT_SECRET"),
        identity_url=f"{provider}/userinfo", identity_json=("email",),
        revoke_url=f"{provider}/revoke", docs="", pkce=True,
    )
    monkeypatch.setitem(reg.PROVIDERS, "mockapp", prob)
    spec = AppSpec(
        slug="mockapp", name="Mock App", category="Testing", description="Mock OAuth app",
        docs="", logo="", auth=AuthSpec(type="oauth2"),
        actions=[ActionSpec(slug="whoami", name="Who am I", description="who am i",
                            method="GET", url=f"{provider}/userinfo", tier="read")],
        base_url=provider,
    )
    catalog_mod.catalog.apps["mockapp"] = reg.apply(spec)
    yield spec
    catalog_mod.catalog.apps.pop("mockapp", None)
    reg.PROVIDERS.pop("mockapp", None)


def connect(client, app="mockapp", entity="playground", new_account=False):
    r = client.post(f"/v1/connections/{app}/start?entity_id={entity}&redirect_after=/connections"
                    f"&new_account={str(new_account).lower()}")
    return r.json()


def finish(client, auth_url: str):
    q = parse_qs(urlparse(auth_url).query)
    state = (q.get("state") or [""])[0]
    resp = client.get(f"/oauth/callback?code=good-code&state={state}", follow_redirects=False)
    return resp


def test_one_click_sign_in_returns_provider_url(client, wiring):
    body = connect(client)
    assert body["mode"] == "oauth"
    url = body["authorization_url"]
    q = parse_qs(urlparse(url).query)
    assert q["client_id"][0] == "client-abc"
    assert q["response_type"][0] == "code"
    assert q["code_challenge_method"][0] == "S256"          # PKCE by default
    assert "read" in q["scope"][0]
    assert body["auth_session_id"]


def test_callback_stores_encrypted_tokens_and_identity(client, wiring):
    body = connect(client)
    resp = finish(client, body["authorization_url"])
    assert resp.status_code in (302, 307)
    assert STATE["tokens"] >= 1

    conns = client.get("/v1/connections?entity_id=playground").json()["connections"]
    mine = [c for c in conns if c["app"] == "mockapp"]
    assert mine, "the account should be listed after consent"
    acc = mine[-1]
    assert acc["status"] == "active"
    assert acc["identity"] == "rejoice@example.com"
    assert acc["scopes"] == ["read", "write"]

    # no token material ever reaches the client
    blob = str(conns)
    assert "at-123" not in blob and "rt-123" not in blob


def test_agent_uses_the_connected_account(client, wiring):
    body = connect(client)
    finish(client, body["authorization_url"])
    from tony import power
    from tony.db import session
    from tony.models import ConnectedAccount
    from sqlalchemy import select

    with session() as s:
        acct = s.scalars(select(ConnectedAccount).where(ConnectedAccount.app_slug == "mockapp")).first()
        assert acct is not None and acct.credentials_enc
        assert "at-123" not in acct.credentials_enc       # encrypted at rest

    from tony.oauth import credentials_for
    from tony.catalog import catalog

    with session() as s:
        ws = s.scalars(select(ConnectedAccount).where(ConnectedAccount.app_slug == "mockapp")).first().workspace_id
    creds = credentials_for(ws, "playground", catalog.get("mockapp"))
    assert creds["access_token"] == "at-123"


def test_agent_reports_connection_link_when_absent(client, wiring):
    from tony.power import AgentIn, run_agent

    import asyncio

    out = asyncio.run(run_agent("default", AgentIn(goal="check mock app who am i", entity_id="nobody-here")))
    missing = out.get("needs_connection") or []
    assert missing or out.get("steps"), "the agent must either work or ask for a connection"
    if missing:
        assert missing[0]["connect_url"].startswith("/connect/mockapp")


def test_multiple_accounts_and_default(client, wiring):
    for _ in range(2):
        body = connect(client, new_account=True)
        finish(client, body["authorization_url"])
    conns = client.get("/v1/connections?entity_id=playground").json()["connections"]
    mine = [c for c in conns if c["app"] == "mockapp" and c["status"] == "active"]
    assert len(mine) >= 2, "a second account must be stored separately"
    pick = mine[-1]["id"]
    assert client.post(f"/v1/connections/id/{pick}/default").json()["ok"] is True


def test_token_refresh_happens_automatically(client, wiring):
    import asyncio
    from datetime import datetime, timedelta, timezone

    from tony.catalog import catalog
    from tony.db import session
    from tony.models import ConnectedAccount
    from tony.oauth import refresh_if_needed
    from sqlalchemy import select

    body = connect(client)
    finish(client, body["authorization_url"])
    before = STATE["refresh"]
    with session() as s:
        acct = s.scalars(select(ConnectedAccount).where(ConnectedAccount.app_slug == "mockapp")).first()
        acct.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        s.flush()
        asyncio.get_event_loop_policy()
        asyncio.run(refresh_if_needed(acct, catalog.get("mockapp")))
        assert acct.status == "active"
    assert STATE["refresh"] > before


def test_disconnect_revokes_at_provider(client, wiring):
    body = connect(client)
    finish(client, body["authorization_url"])
    conns = client.get("/v1/connections?entity_id=playground").json()["connections"]
    acc = [c for c in conns if c["app"] == "mockapp"][-1]
    before = STATE["revoked"]
    res = client.delete(f"/v1/connections/id/{acc['id']}").json()
    assert res["ok"] is True
    assert STATE["revoked"] > before
    left = client.get("/v1/connections?entity_id=playground").json()["connections"]
    assert not [c for c in left if c["id"] == acc["id"]]


def test_state_is_single_use(client, wiring):
    body = connect(client)
    first = finish(client, body["authorization_url"])
    assert first.status_code in (302, 307)
    again = finish(client, body["authorization_url"])
    assert again.status_code in (302, 307)
    assert "connection=error" in again.headers.get("location", "")


def test_providers_registry_is_ready_for_core_apps():
    from tony import provider_registry as reg

    for slug in ("gmail", "google_drive", "google_calendar", "outlook", "slack", "discord",
                 "github", "gitlab", "notion", "linkedin", "dropbox", "salesforce", "hubspot"):
        p = reg.provider_for(slug)
        assert p is not None, slug
        assert p.authorize_url and p.token_url, slug
        assert p.identity_url, slug
