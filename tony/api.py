"""Public REST API (v1) and the dashboard's JSON surface."""
from __future__ import annotations

import asyncio

import json
import time

import httpx
import os
import re
import secrets
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import __version__
from . import agenttokens
from .auth import rate_limit, workspace_from_request
from .billing import (check_capacity, check_run, enforce_session, rate_for, read_budget_left,
                      read_page_limit, resolve_session, touch_session)
from .catalog import catalog
from .config import settings
from .db import session
from .executor import ExecutionError, execute, execute_plan, needs_base_url
from .models import ActionRun, ApiKey, ConnectedAccount, Entity, Trigger, WebhookDelivery
from .oauth import (
    OAuthError,
    credentials_for,
    is_configured,
    public_redact,
    start_oauth,
    store_api_key,
)

router = APIRouter(prefix="/v1", tags=["api"])
mcp_tools_cache: list[dict[str, Any]] = []


def _entity(ws: str, entity_id: str) -> str:
    entity_id = (entity_id or "default").strip()[:160] or "default"
    with session() as s:
        if s.scalar(select(Entity).where(Entity.workspace_id == ws, Entity.external_id == entity_id)):
            return entity_id
    check_capacity(ws, "entities")
    with session() as s:
        if not s.scalar(select(Entity).where(Entity.workspace_id == ws, Entity.external_id == entity_id)):
            s.add(Entity(workspace_id=ws, external_id=entity_id))
    return entity_id


# ── catalogue ─────────────────────────────────────────────────────────────
@router.get("/stats")
def stats() -> dict[str, Any]:
    base = catalog.stats()
    with session() as s:
        runs = s.query(ActionRun).count()
        conns = s.query(ConnectedAccount).count()
    return {**base, "runs": runs, "connections": conns, "version": __version__}


@router.get("/demo/session")
def demo_session(request: Request) -> dict[str, Any]:
    """Claim (or look up) this caller's private demo room.

    Anonymous use of the API is a room of one's own, not a shared lobby: a signed
    cookie proves the room, and ``api_key`` lets a client without a cookie jar use
    the same room by sending ``X-Tony-Demo-Session``. Nothing here is ever shared
    with another visitor.
    """
    from . import demo

    if not settings.demo_open:
        raise HTTPException(403, detail="The demo is closed on this deployment. Sign up for a key.")
    info = demo.current(request) or demo.provision(request)
    return {"workspace_id": info["workspace_id"], "api_key": info["api_key"],
            "token": info["token"], "expires_in": info["expires_in"],
            "expires_at": info.get("expires_at", ""),
            "private": True,
            "header": "X-Tony-Demo-Session",
            "note": ("Each visitor gets an empty workspace with its own key. Send the token in "
                     "X-Tony-Demo-Session to stay in the same room without cookies.")}


@router.get("/whoami")
def whoami(request: Request) -> dict[str, Any]:
    """Which workspace, user and key is behind this call.

    Every key carries its owner, so an agent can prove whose data it touches.
    """
    from .models import User

    ws, demo = workspace_from_request(request)
    with session() as s:
        user = s.scalar(select(User).where(User.workspace_id == ws))
        conns = s.scalars(select(ConnectedAccount).where(ConnectedAccount.workspace_id == ws,
                                                        ConnectedAccount.status == "active")).all()
        keys = s.scalars(select(ApiKey).where(ApiKey.workspace_id == ws, ApiKey.revoked.is_(False))).all()
        key = s.scalar(select(ApiKey).where(ApiKey.workspace_id == ws,
                                            ApiKey.prefix == (_key_prefix(request) or ""))) if _key_prefix(request) else None
        return {
            "workspace_id": ws,
            "demo_session": demo,
            "owner": {"id": user.id, "email": user.email, "name": user.name} if user else None,
            "key": {"id": key.id, "name": key.name, "prefix": key.prefix,
                    "owner": (user.email if user else None)} if key else None,
            "connections": [{"app": c.app_slug, "entity_id": c.entity_id, "status": c.status} for c in conns],
            "keys": len(keys),
        }


def _key_prefix(request: Request) -> str:
    raw = request.headers.get("authorization") or request.headers.get("x-api-key") or ""
    if raw.lower().startswith("bearer "):
        raw = raw.split(" ", 1)[1]
    raw = raw.strip()
    return raw[:16] if raw.startswith("tk_") else ""


@router.get("/meta")
def meta() -> dict[str, Any]:
    """Agent-facing manifest: what Tony is, what it can do, how to call it."""
    base = catalog.stats()
    writes = 0
    try:
        for spec in catalog.apps.values():
            for act in spec.actions:
                if act.tier in ("write", "destructive"):
                    writes += 1
    except Exception:
        writes = 0
    return {
        "name": "Tony",
        "version": __version__,
        "summary": "Self-hosted integration gateway: one HTTP call to run any action in any app.",
        "apps": base["apps"],
        "actions": base["actions"],
        "write_actions": writes,
        "reads": base["actions"] - writes,
        "auth": {"scheme": "Bearer", "header": "Authorization",
                 "note": "Workspace API key (tk_live_…) or a browser session cookie."},
        "endpoints": {
            "search_apps": "GET /v1/apps?search=&category=&tier=&limit=&offset=",
            "search_actions": "GET /v1/actions?q=&limit=",
            "app_detail": "GET /v1/apps/{slug}",
            "run": "POST /v1/execute {action, args, approved, dry_run}",
            "approve": "POST /v1/runs/{run_id}/approve",
            "mcp": "POST /mcp (JSON-RPC, every action is a tool)",
            "openapi": "GET /openapi.json",
        },
        "docs": {"openapi": "/openapi.json", "mcp": "/mcp", "ui": "/account"},
    }


MAX_PAGE = 500
_APP_TIERS = {"actions", "proxy", "directory", "homeassistant"}

# How people (and models) name the sign-in styles versus what the catalogue
# stores. "oauth" means oauth2, "key" is the whole family of user-supplied keys.
_AUTH_GROUPS: dict[str, set[str]] = {
    "none": {"none"}, "public": {"none"}, "keyless": {"none"},
    "key": {"api_key", "bearer", "basic", "path"},
    "api_key": {"api_key"}, "apikey": {"api_key"}, "bearer": {"bearer"},
    "basic": {"basic"}, "oauth": {"oauth2"}, "oauth2": {"oauth2"},
}


@router.get("/apps")
def list_apps(search: str = "", q: str = "", category: str = "", tier: str = "", source: str = "",
              auth: str = "", strategy: str = "", with_actions: bool = False,
              limit: int = 60, offset: int = 0, dedupe: bool = True,
              include_hidden: bool = False) -> dict[str, Any]:
    """Paginated catalogue search. Pages are capped at 500 apps.

    Duplicates of the same product (``google-calendar`` and ``google_calendar``)
    and import artefacts named "API V1" are hidden by default; ``include_hidden``
    brings them back, and any slug still resolves on ``/v1/apps/{slug}``.

    Filters work three ways: named parameters (``auth=none``, ``strategy=key``),
    or the same thing typed into ``q`` (``q=auth:none``), which is what people
    and models try first. The assistant used to recommend that prefix form while
    the endpoint ignored it, so the answer is now the one the docs describe.
    """
    from . import appauth

    search = (search or q).strip()
    for prefix in ("auth", "strategy", "tier", "source"):
        if search.lower().startswith(prefix + ":"):
            value = search.split(":", 1)[1].strip()
            if prefix == "auth":
                auth = auth or value
            elif prefix == "strategy":
                strategy = strategy or value
            elif prefix == "tier":
                tier = tier or value
            else:
                source = source or value
            search = ""
            break

    if offset < 0:
        raise HTTPException(400, detail="offset must be zero or greater")
    if limit < 0:
        raise HTTPException(400, detail="limit must be zero or greater (0 means the first page)")
    tier_want = (tier or "").strip().lower()
    # Old names for the same shelves: imported OpenAPI apps are the "curated"
    # tier, and everything else that is not a listing proxies a real host.
    tier_want = {"curated": "actions", "openapi": "actions", "rest": "proxy",
                 "listing": "directory", "iot": "homeassistant"}.get(tier_want, tier_want)
    if tier_want and tier_want not in _APP_TIERS:
        raise HTTPException(400, detail=(f"Unknown tier '{tier}'. Use one of: {', '.join(sorted(_APP_TIERS))}"
                                         f", or an alias: curated, openapi, rest, listing, iot"))
    # A 5.7MB page is not a feature. Anything above the cap is clamped, and the
    # response says so instead of silently truncating or melting the client.
    capped = limit == 0 or limit > MAX_PAGE
    page_limit = MAX_PAGE if capped else limit

    matched = catalog.search(search, category, tier=tier, source=source, dedupe=dedupe)
    if not include_hidden:
        hidden = catalog.hidden
        if search:
            # An exact slug the catalogue hides still deserves an answer: point
            # the caller at the canonical app instead of a confusing empty list.
            wanted = search.strip().lower().replace(" ", "-")
            keeper = catalog.alias_of.get(wanted) if hasattr(catalog, "alias_of") else None
            if keeper and keeper in catalog.apps:
                matched = [catalog.apps[keeper]]
            else:
                matched = [a for a in matched if a.slug not in hidden]
        else:
            matched = [a for a in matched if a.slug not in hidden]
    auth_want = (auth or "").strip().lower()
    strat_want = (strategy or "").strip().lower()
    auth_set: set[str] = set()
    if auth_want:
        auth_set = _AUTH_GROUPS.get(auth_want, set())
        if not auth_set and auth_want not in {s.lower() for s in appauth.STRATEGY_LABEL}:
            raise HTTPException(400, detail=(f"Unknown auth '{auth}'. Use one of: "
                                             f"{', '.join(sorted(_AUTH_GROUPS))}, or a strategy name"))
    if auth_set or strat_want:
        kept = []
        for a in matched:
            plan = appauth.plan(a.slug) or {}
            row_auth = (getattr(a.auth, "type", "") or "none").lower()
            row_strategy = str(plan.get("strategy") or ("key" if row_auth != "none" else "public")).lower()
            if auth_set and row_auth not in auth_set and auth_want not in {row_strategy, "public" if row_auth == "none" else ""}:
                continue
            if strat_want and strat_want != row_strategy:
                continue
            kept.append(a)
        matched = kept

    total = len(matched)
    window = matched[offset: offset + page_limit]

    items = []
    for a in window:
        row = a.to_public(include_actions=with_actions)
        p = appauth.plan(a.slug) or {}
        row["strategy"] = p.get("strategy", "key" if a.auth.type != "none" else "public")
        row["strategy_label"] = appauth.STRATEGY_LABEL.get(row["strategy"], "")
        row["connectable"] = row["strategy"] != "oauth_byo" or bool(p.get("keyless_via"))
        row["keyless_via"] = p.get("keyless_via", "")
        row["can_write"] = p.get("can_write", row.get("writes", 0) > 0)
        items.append(row)
    return {
        "apps": items,
        "categories": catalog.categories(),
        "category_counts": catalog.category_counts(),
        "total": total,
        "offset": offset,
        "limit": page_limit,
        "limit_capped": capped,
        "max_limit": MAX_PAGE,
        "has_more": offset + len(items) < total,
        "next_offset": offset + len(items) if offset + len(items) < total else None,
        "stats": catalog.stats(),
    }


@router.get("/apps/{slug}")
def get_app(slug: str) -> dict[str, Any]:
    spec = catalog.get(slug)
    if not spec:
        raise HTTPException(404, detail=f"Unknown app '{slug}'")
    data = spec.to_public()
    data["configured"] = is_configured(spec)
    data["auth"] = {
        **data["auth"],
        "client_id_env": spec.auth.client_id_env,
        "client_secret_env": spec.auth.client_secret_env,
        "static_env": spec.auth.static_env,
        "user_supplied": spec.auth.type in {"api_key", "bearer", "basic", "custom"},
    }
    data["needs_base_url"] = needs_base_url(spec)
    data["needs_token"] = spec.auth.type != "none"
    return data


@router.get("/coverage")
def auth_coverage() -> dict[str, Any]:
    """How every app in the catalogue actually gets connected.

    Two numbers used to disagree: the catalogue said 7,924 apps and this endpoint
    said 7,857, because it counted only the apps the auth registry had written a
    plan for. The total is the catalogue now, and the registry subset is named.
    The claim is spelled out too: one-click OAuth is real for the providers Tony
    holds credentials for, everything else is a key or an owner-registered client.
    """
    from . import appauth

    data = appauth.coverage()
    raw = appauth._data()
    registry_cov = dict(raw.get("coverage") or {})
    managed = __import__("tony.provider_registry", fromlist=["PROVIDERS"]).PROVIDERS
    catalog_total = len(catalog.apps)

    # Count every app in the catalogue under exactly one strategy, so the split
    # always adds up to the headline instead of stopping at the registry subset.
    cov: dict[str, int] = {}
    for spec in catalog.apps.values():
        plan = appauth.plan(spec.slug) or {}
        strategy = str(plan.get("strategy")
                       or ("public" if getattr(spec.auth, "type", "none") == "none" else "key"))
        cov[strategy] = cov.get(strategy, 0) + 1
    registered = sum(registry_cov.values())
    data.update({
        "apps_total": catalog_total,
        "coverage": cov,
        "catalog_apps": catalog_total,
        "registry_apps": registered,
        "registry_coverage": registry_cov,
        "unregistered_apps": max(0, catalog_total - registered),
        "managed_providers": len(managed),
        "oauth_one_click": len(managed),
        "oauth_byo": cov.get("oauth_byo", 0),
        "oauth_dcr": cov.get("oauth_dcr", 0),
        "mcp_dcr": cov.get("mcp_dcr", 0),
        "api_key": cov.get("key", 0),
        "public": cov.get("public", 0),
        "claim": (
            f"{len(managed) + cov.get('oauth_ready', 0) + cov.get('oauth_dcr', 0)} apps sign in with one click "
            f"because Tony holds the OAuth client. {cov.get('oauth_byo', 0)} need an owner to register one client "
            f"id and secret once. {cov.get('mcp_dcr', 0)} authorise through the vendor's own MCP server. "
            f"{cov.get('key', 0)} take a key the user supplies, and {cov.get('public', 0)} need no sign-in at all."
        ),
    })
    return data


@router.get("/apps/{slug}/auth")
def app_auth(slug: str, access: str = "read") -> dict[str, Any]:
    """The connect plan for one app: strategy, endpoints, and least-privilege scopes."""
    from . import appauth

    spec = catalog.get(slug)
    if not spec:
        raise HTTPException(404, detail=f"Unknown app '{slug}'")
    p = appauth.plan_or_default(spec.slug, spec.auth.type)
    p = {**p,
         "app": spec.slug,
         "name": spec.name,
         "auth_type": spec.auth.type,
         "label": appauth.STRATEGY_LABEL.get(p.get("strategy", ""), ""),
         "scopes_requested": appauth.scope_list(spec.slug, access),
         "needs_setup": p.get("strategy") == "oauth_byo",
         "setup_endpoint": f"/v1/connections/{spec.slug}/key",
         "docs": p.get("docs") or spec.docs}
    if p.get("keyless_via"):
        p["keyless_url"] = f"/v1/apps/{p['keyless_via']}/auth"
        p["keyless_note"] = ("This vendor's MCP server registers Tony automatically, "
                             f"so {p['keyless_via']} connects with one click and no setup.")
    return p


@router.get("/actions")
def list_actions(search: str = "", q: str = "", app: str = "", tier: str = "", limit: int = 50,
                 offset: int = 0, ranked: bool = True) -> dict[str, Any]:
    """Action search. ``q`` and ``search`` are the same thing here, as on /v1/apps."""
    if offset < 0:
        raise HTTPException(400, detail="offset must be zero or greater")
    if limit < 0:
        raise HTTPException(400, detail="limit must be zero or greater")
    limit = min(limit, MAX_PAGE) if limit else 50
    tier_want = (tier or "").strip().lower()
    if tier_want and tier_want not in {"read", "write", "destructive"}:
        raise HTTPException(400, detail="Unknown tier. Use read, write or destructive")
    search = (search or q or "").strip()
    # natural-language search: rank ACTIONS by meaning, not substring luck
    if search and ranked:
        from .toolsearch import search_actions
        hits = search_actions(catalog, search, limit=max(limit, 25), app=app or None,
                              tier=tier or None)
        payload = []
        for h in hits:
            spec = catalog.get(h["app"])
            act = spec.action(h["action"].split(".", 1)[1]) if spec else None
            payload.append({"app": h["app"], "app_name": h["app_name"], "score": h["score"],
                            **({"slug": act.slug, "name": act.name, "description": act.description,
                                "tier": act.tier, "tool_name": f"{h['app']}__{act.slug}"}
                               if act else {"slug": h["action"], "name": h["name"],
                                            "description": h["description"], "tier": h["tier"],
                                            "tool_name": h["action"].replace('.', '__')})})
        page = payload[offset: offset + limit] if limit else payload[offset:]
        return {"actions": page, "total": len(payload), "offset": offset,
                "has_more": bool(limit) and offset + limit < len(payload), "ranked": True,
                "query": search}
    out = []
    for spec in catalog.apps.values():
        if app and spec.slug != app:
            continue
        for act in spec.actions:
            if tier and act.tier != tier:
                continue
            if search:
                q = search.lower()
                if q not in act.slug and q not in act.name.lower() and q not in act.description.lower():
                    continue
            out.append({"app": spec.slug, "app_name": spec.name, **act.to_public(),
                        "tool_name": f"{spec.slug}__{act.slug}"})
    matched = out[offset: offset + limit] if limit else out[offset:]
    return {"actions": matched, "total": len(out), "offset": offset,
            "has_more": bool(limit) and offset + limit < len(out)}


@router.get("/connections/health")
def connections_health(request: Request) -> dict[str, Any]:
    """Per-app connection health so a broken integration is visible early."""
    ws, _ = workspace_from_request(request)
    from . import connhealth
    return connhealth.summary(ws)


@router.post("/connections/refresh")
async def refresh_connections(request: Request) -> dict[str, Any]:
    """Sweep now: refresh anything expiring, mark what needs re-auth."""
    ws, _ = workspace_from_request(request)
    from . import connhealth
    result = await connhealth.sweep()
    result["workspace"] = ws
    return result


@router.get("/connections")
def list_connections(request: Request, entity_id: str = "") -> dict[str, Any]:
    ws, _demo = workspace_from_request(request)
    with session() as s:
        q = select(ConnectedAccount).where(ConnectedAccount.workspace_id == ws)
        if entity_id:
            q = q.where(ConnectedAccount.entity_id == entity_id)
        rows = s.scalars(q).all()
        return {"connections": [public_redact(r) for r in rows], "total": len(rows)}


@router.post("/connections/{app_slug}/start")
async def connect_start(app_slug: str, request: Request, entity_id: str = "default",
                        redirect_after: str = "/app", new_account: bool = False) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    spec = catalog.get(app_slug)
    if not spec:
        raise HTTPException(404, detail="Unknown app")
    check_capacity(ws, "connections")
    if spec.auth.type == "none":
        entities = _entity(ws, entity_id)
        with session() as s:
            acct = ConnectedAccount(
                workspace_id=ws, entity_id=entity_id, app_slug=spec.slug,
                auth_type="none", status="active", label="public access",
                credentials_enc="", scopes="", meta_json="{}",
            )
            s.add(acct)
            s.flush()
            return {"mode": "public", "connection": public_redact(acct)}
    if spec.auth.type != "oauth2":
        return JSONResponse(status_code=409, content={
            "detail": f"{spec.name} connects with a key, not a sign-in.",
            "app": spec.slug, "needs_setup": True, "mode": "key",
            "can_use_key": True, "setup_endpoint": f"/v1/connections/{spec.slug}/key",
            "setup_hint": "Paste the API key or token for this app.",
            "docs": spec.docs or "",
        })
    _entity(ws, entity_id)
    try:
        session_id, url = await start_oauth(ws, entity_id, spec, redirect_after, new_account=new_account)
    except OAuthError as exc:
        return JSONResponse(status_code=409, content={
            "detail": str(exc),
            "app": spec.slug, "needs_setup": True, "mode": "oauth",
            "can_use_key": True, "setup_endpoint": f"/v1/connections/{spec.slug}/key",
            "provider_endpoint": f"/v1/account/providers/{spec.slug}",
            "setup_hint": ("The workspace owner adds this app's OAuth client id and secret once, "
                           "then everyone just signs in. A personal token also works."),
            "docs": spec.docs or "",
        })
    return {"mode": "oauth", "auth_session_id": session_id, "authorization_url": url}


PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1|\[::1\]|"
    r"172\.(1[6-9]|2\d|3[01])\.|.*\.(internal|local|localhost)$)", re.IGNORECASE)


def normalise_base_url(raw: str) -> str:
    """Validate and tidy the API root a user pastes for a directory app.

    Rejects anything that is not http(s), and blocks link-local / private
    addresses so a connected app cannot be pointed at the host's own network.
    Self-hosters who really do call an internal API can set
    TONY_ALLOW_PRIVATE_BASE_URLS=1.
    """
    value = (raw or "").strip()
    if not value:
        raise HTTPException(400, detail="Base URL is required for this app")
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(400, detail="Base URL must start with http:// or https://")
    host = (parsed.hostname or "").strip().lower()
    if not host or "." not in host.replace("[", "").replace("]", "") and host != "localhost":
        raise HTTPException(400, detail="That does not look like a host, e.g. https://api.example.com")
    allow_private = os.getenv("TONY_ALLOW_PRIVATE_BASE_URLS", "").strip() in {"1", "true", "yes"}
    if not allow_private and PRIVATE_HOST_RE.match(host):
        raise HTTPException(400, detail="Private and loopback hosts are blocked. Set TONY_ALLOW_PRIVATE_BASE_URLS=1 to allow them.")
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{query}"


class KeyIn(BaseModel):
    entity_id: str = "default"
    values: dict[str, str] = Field(default_factory=dict)
    label: str = ""


@router.post("/connections/{app_slug}/key")
def connect_key(app_slug: str, body: KeyIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    spec = catalog.get(app_slug)
    if not spec:
        raise HTTPException(404, detail="Unknown app")
    values = dict(body.values)
    if needs_base_url(spec) or "base_url" in values:
        values["base_url"] = normalise_base_url(values.get("base_url", ""))
    elif not values:
        raise HTTPException(400, detail="Provide the credential values for this app")
    if not values or (spec.auth.type != "none" and not any(v for k, v in values.items() if k != "base_url")):
        raise HTTPException(400, detail=f"{spec.name} needs a token as well as a base URL")
    check_capacity(ws, "connections")
    _entity(ws, body.entity_id)
    acct = store_api_key(ws, body.entity_id, spec, values, body.label)
    return {"mode": "key", "connection": public_redact(acct)}


@router.delete("/connections/{app_slug}")
async def disconnect(app_slug: str, request: Request, entity_id: str = "default") -> dict[str, Any]:
    """Revoke every account for one app (provider-side revocation included)."""
    from .oauth import disconnect as _disconnect

    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == ws,
            ConnectedAccount.entity_id == entity_id,
            ConnectedAccount.app_slug == app_slug)).all()
    revoked = 0
    for row in rows:
        res = await _disconnect(row)
        revoked += 1 if res.get("revoked_remote") else 0
    return {"deleted": len(rows), "revoked_remote": revoked}


@router.delete("/connections/id/{account_id}")
async def disconnect_one(account_id: str, request: Request) -> dict[str, Any]:
    """Remove one connected account: revoke at the provider, then forget it."""
    from .oauth import disconnect as _disconnect, purge

    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.get(ConnectedAccount, account_id)
        if row is None or row.workspace_id != ws:
            raise HTTPException(404, detail="No such connection")
    res = await _disconnect(row)
    purge(account_id)
    return {"ok": True, **res}


@router.post("/connections/id/{account_id}/default")
def make_default(account_id: str, request: Request) -> dict[str, Any]:
    """Pin one account as the one the agent uses for that app."""
    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == ws)).all()
        target = next((r for r in rows if r.id == account_id), None)
        if target is None:
            raise HTTPException(404, detail="No such connection")
        for r in rows:
            if r.app_slug != target.app_slug:
                continue
            from .oauth import account_meta, set_account_meta
            set_account_meta(r, is_default=(r.id == account_id))
            if r.id == account_id:
                r.meta_json = r.meta_json  # touched below by the flush
        s.flush()
    return {"ok": True, "account_id": account_id}


@router.get("/providers")
def managed_providers() -> dict[str, Any]:
    """Every managed integration, its scopes and whether one-click sign-in is armed."""
    from . import provider_registry as managed

    out = []
    for slug, p in managed.PROVIDERS.items():
        spec = catalog.get(slug)
        out.append({
            "app": slug,
            "name": p.name,
            "category": p.category,
            "logo": f"/v1/icon/{slug}",
            "logo_source": getattr(spec, "logo", "") if spec else "",
            "scopes": list(p.scopes),
            "ready": managed.ready(slug),
            "managed_by": managed.managed_by_platform(slug),
            "env": list(p.env),
            "docs": p.docs,
            "google": "accounts.google.com" in p.authorize_url,
            "authorize_url": p.authorize_url,
            "pkce": p.pkce,
            "setup_endpoint": f"/v1/account/providers/{slug}",
            "connect_url": f"/connect/{slug}",
        })
    return {"providers": out, "total": len(out),
            "ready": sum(1 for x in out if x["ready"])}


@router.get("/connections/events")
def connection_events(request: Request, limit: int = 50, app: str = "") -> dict[str, Any]:
    """Audit trail of authentication events. Tokens are never recorded."""
    from .models import ConnectionEvent

    ws, _ = workspace_from_request(request)
    with session() as s:
        q = select(ConnectionEvent).where(ConnectionEvent.workspace_id == ws)
        if app:
            q = q.where(ConnectionEvent.app_slug == app)
        rows = s.scalars(q.order_by(ConnectionEvent.created_at.desc()).limit(min(limit, 200))).all()
        return {"events": [{
            "id": r.id, "app": r.app_slug, "kind": r.kind, "identity": r.identity,
            "account_id": r.account_id, "detail": r.detail,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]}


# ── execution ─────────────────────────────────────────────────────────────
class ExecuteIn(BaseModel):
    action: str
    app: str = ""            # optional: {"app": "gmail", "action": "fetch_emails"} works too
    entity_id: str = "default"
    args: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    dry_run: bool = False
    source: str = "api"
    idempotency_key: str | None = None


class AgentTokenIn(BaseModel):
    name: str = "agent"
    apps: list[str] = Field(default_factory=list)
    tiers: list[str] = Field(default_factory=lambda: ["read"])
    ttl_days: int = 7


@router.post("/agent-tokens")
def mint_agent_token(body: AgentTokenIn, request: Request) -> dict[str, Any]:
    """Give an AI agent its own narrow key instead of your full workspace key."""
    ws, _ = workspace_from_request(request)
    if getattr(request.state, "agent_scope", None):
        raise HTTPException(403, detail="An agent token cannot mint another token")
    unknown = [a for a in body.apps if not catalog.get(a)]
    if unknown:
        raise HTTPException(400, detail=f"Unknown app(s): {', '.join(unknown[:5])}")
    return agenttokens.issue(ws, body.name, body.apps, body.tiers, body.ttl_days)


@router.get("/agent-tokens/scopes")
def agent_token_scopes(request: Request) -> dict[str, Any]:
    payload = getattr(request.state, "agent_scope", None)
    return {"agent_token": bool(payload), "scope": payload or {},
            "description": agenttokens.describe(payload)}


def _log_run(ws: str, entity: str, spec, action, status: str, result=None, request_payload=None,
             error: str = "") -> str:
    with session() as s:
        run = ActionRun(
            workspace_id=ws,
            entity_id=entity,
            app_slug=spec.slug,
            action_slug=action.slug,
            tier=action.tier,
            status=status,
            status_code=getattr(result, "status", 0) or 0,
            latency_ms=getattr(result, "latency_ms", 0) or 0,
            chars_out=len(json.dumps(getattr(result, "data", None), default=str)) if result else 0,
            request_json=json.dumps(request_payload or {}, default=str),
            response_json=json.dumps((result.as_dict() if result else {}), default=str)[:60000],
            error=error,
        )
        s.add(run)
        s.flush()
        return run.id


def _effective_verb(action: Any, args: dict[str, Any] | None) -> str:
    """The verb the request will actually use.

    The universal passthrough is a write action by design, but a plain GET through
    it reads data. Approval is for changes, so a read must not queue for one.
    """
    verb = str((args or {}).get("method") or "").upper()
    if verb in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return verb
    return (getattr(action, "method", "") or "GET").upper()


@router.post("/execute")
async def execute_action(body: ExecuteIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    if body.app and "." not in body.action and not body.action.startswith("custom."):
        body.action = f"{body.app.strip()}.{body.action.strip()}"
    if body.action.startswith("custom."):
        return await _execute_custom(body, request, ws)
    resolved = catalog.find_action(body.action)
    typed_plan: dict[str, Any] | None = None
    # typed connectors: friendly args, real payloads (email MIME, file handles)
    typed_app = body.action.split(".", 1)[0] if "." in body.action else ""
    typed_slug = body.action.split(".", 1)[1] if "." in body.action else ""
    spec0 = catalog.get(typed_app) if typed_app else None
    if spec0 is not None and typed_slug:
        from . import connectors as _typed
        if _typed.has(typed_app, typed_slug):
            if not resolved:
                # synthesise an ActionSpec so auth/approval machinery still applies
                from .catalog import ActionSpec
                resolved = (spec0, ActionSpec(slug=typed_slug, name=typed_slug.replace("_", " ").title(),
                                              description=f"Typed {typed_app} action",
                                              method="POST", url=(spec0.base_url or ""), tier="write"))
            spec0b, action0b = resolved
            try:
                plan = _typed.build(typed_app, typed_slug, body.args,
                                    workspace_id=workspace_from_request(request)[0])
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(400, detail=f"{body.action}: {exc}") from exc
            if body.dry_run:
                return {"ok": True, "dry_run": True, "plan": {k: plan[k] for k in plan if k != "file"},
                        "action": body.action, "typed": True}
            # keep the plan on the request itself: storing it inside args would leak
            # into approvals and the run log, and it is rebuilt deterministically
            typed_plan = plan
    if not resolved:
        from . import naming

        head, _, tail = body.action.partition(".")
        named = catalog.resolve(head) or catalog.get(head) if head else None
        if named is not None:
            raise HTTPException(404, detail=naming.explain(named, tail))
        raise HTTPException(404, detail=(
            f"Unknown action '{body.action}': there is no app '{head}' in the catalogue. "
            "Send app.action, e.g. github.list_repos, or app plus action."))
    spec, action = resolved
    scope = getattr(request.state, "agent_scope", None)
    if not agenttokens.allows(scope, spec.slug, action.tier):
        raise HTTPException(403, detail=(
            f"This agent token grants {agenttokens.describe(scope)}, not "
            f"{spec.slug}.{action.slug} ({action.tier})"))
    sess = resolve_session(request, ws)
    enforce_session(sess, spec.slug, action.tier)
    rate_limit(f"ws:{ws}", rate_for(ws))
    check_run(ws)
    entity = _entity(ws, sess.entity_id if sess else body.entity_id)

    if (action.tier != "read" and settings.require_approval and not body.approved
            and not body.dry_run and _effective_verb(action, body.args) != "GET"):
        run_id = _log_run(ws, entity, spec, action, "pending_approval",
                          request_payload={"args": body.args, "action": body.action})
        touch_session(sess)
        return {
            "ok": False,
            "status": "pending_approval",
            "run_id": run_id,
            "tier": action.tier,
            "message": f"'{action.name}' is a {action.tier} action. Re-send with approved=true or approve run {run_id}.",
            "preview": {
                "app": spec.slug, "action": action.slug, "method": action.method,
                "args": body.args, "danger_note": action.danger_note,
            },
        }

    acct = None
    creds = credentials_for(ws, entity, spec)
    if spec.auth.type != "none" and creds is None and not action.public:
        raise HTTPException(
            400,
            detail=f"No {spec.name} account connected for entity '{entity}'. "
                   f"Start a connection first (POST /v1/connections/{spec.slug}/start).",
        )
    if body.approved and body.dry_run is False:
        with session() as s:
            row = s.scalar(select(ConnectedAccount).where(
                ConnectedAccount.workspace_id == ws,
                ConnectedAccount.entity_id == entity,
                ConnectedAccount.app_slug == spec.slug))
            if row is not None and spec.auth.type == "oauth2":
                from .oauth import refresh_if_needed as _refresh
                await _refresh(row, spec)
                creds = credentials_for(ws, entity, spec)

    if typed_plan is None and isinstance(body.args, dict):
        typed_plan = body.args.pop("__typed_plan__", None)   # older queued approvals
    try:
        try:
            if typed_plan:
                result = await asyncio.wait_for(
                    execute_plan(spec, action, typed_plan, creds, dry_run=body.dry_run),
                    timeout=settings.execution_deadline,
                )
            else:
                result = await asyncio.wait_for(
                    execute(spec, action, body.args, creds, dry_run=body.dry_run),
                    timeout=settings.execution_deadline,
                )
        except asyncio.TimeoutError:
            raise HTTPException(
                504,
                detail=f"{action.full_name if hasattr(action, 'full_name') else action.slug} exceeded "
                       f"{settings.execution_deadline:g}s. The provider hung; Tony cut it off so your "
                       f"agent stays responsive.",
            )
    except ExecutionError as exc:
        run_id = _log_run(ws, entity, spec, action, "error", None,
                          {"args": body.args, "action": body.action}, error=str(exc))
        return {"ok": False, "error": str(exc), "status_code": exc.status,
                "detail": exc.detail, "run_id": run_id}

    run_id = _log_run(ws, entity, spec, action, "success", result,
                      {"args": body.args, "action": body.action})
    touch_session(sess)
    payload = result.as_dict()
    payload["run_id"] = run_id
    payload["app"] = spec.slug
    payload["action"] = action.slug
    return payload


async def _execute_custom(body: ExecuteIn, request: Request, ws: str) -> dict[str, Any]:
    """Run one user-defined HTTP tool through the same gates as the catalog."""
    from . import customtools

    slug = body.action.split(".", 1)[1]
    tool = customtools.find(ws, slug)
    if tool is None:
        raise HTTPException(404, detail=f"No custom tool '{slug}' in this workspace. Create one at POST /v1/custom-tools.")
    sess = resolve_session(request, ws)
    enforce_session(sess, "custom", tool.tier)
    rate_limit(f"ws:{ws}", rate_for(ws))
    check_run(ws)
    entity = _entity(ws, sess.entity_id if sess else body.entity_id)

    if tool.tier != "read" and settings.require_approval and not body.approved and not body.dry_run:
        with session() as s:
            run = ActionRun(workspace_id=ws, entity_id=entity, app_slug="custom",
                            action_slug=tool.slug, tier=tool.tier, status="pending_approval",
                            request_json=json.dumps({"args": body.args, "action": body.action}, default=str))
            s.add(run)
            s.flush()
            run_id = run.id
        touch_session(sess)
        return {"ok": False, "status": "pending_approval", "run_id": run_id, "tier": tool.tier,
                "message": f"'{tool.name}' is a {tool.tier} tool. Approve it, then call again with approved=true.",
                "preview": {"app": "custom", "action": tool.slug, "method": tool.method,
                            "args": body.args, "url": tool.url}}

    try:
        res = await asyncio.wait_for(customtools.run(tool, body.args), timeout=settings.execution_deadline)
    except asyncio.TimeoutError:
        raise HTTPException(504, detail=f"custom.{slug} exceeded {settings.execution_deadline:g}s and was cut off.")
    except Exception as exc:  # noqa: BLE001
        with session() as s:
            run = ActionRun(workspace_id=ws, entity_id=entity, app_slug="custom", action_slug=tool.slug,
                            tier=tool.tier, status="error", error=str(exc)[:2000],
                            request_json=json.dumps({"args": body.args, "action": body.action}, default=str))
            s.add(run)
            s.flush()
            run_id = run.id
        return {"ok": False, "error": str(exc), "run_id": run_id, "app": "custom", "action": tool.slug}

    with session() as s:
        run = ActionRun(workspace_id=ws, entity_id=entity, app_slug="custom", action_slug=tool.slug,
                        tier=tool.tier, status="success" if res["ok"] else "error",
                        status_code=res["status"], latency_ms=res["latency_ms"],
                        chars_out=len(json.dumps(res["data"], default=str)),
                        request_json=json.dumps({"args": body.args, "action": body.action}, default=str),
                        response_json=json.dumps(res, default=str)[:60000])
        s.add(run)
        s.flush()
        run_id = run.id
    touch_session(sess)
    return {**res, "run_id": run_id, "app": "custom", "action": tool.slug}


class BatchIn(BaseModel):
    calls: list[ExecuteIn] = Field(default_factory=list)


@router.post("/batch")
async def batch(body: BatchIn, request: Request) -> dict[str, Any]:
    """Run up to 20 actions in one request. Sequential, so quota and approvals stay honest."""
    if not body.calls:
        raise HTTPException(400, detail="Send at least one call")
    if len(body.calls) > 20:
        raise HTTPException(400, detail="Batch is capped at 20 calls. Split larger jobs.")
    results: list[dict[str, Any]] = []
    started = time.time()
    for call in body.calls:
        try:
            out = await execute_action(call, request)
            results.append({"action": call.action, "ok": bool(out.get("ok")),
                            "status": out.get("status", "ok"), "result": out})
        except HTTPException as exc:
            results.append({"action": call.action, "ok": False, "status": "error",
                            "status_code": exc.status_code, "error": exc.detail})
        except Exception as exc:  # noqa: BLE001
            results.append({"action": call.action, "ok": False, "status": "error", "error": str(exc)})
    return {"results": results, "count": len(results),
            "succeeded": sum(1 for r in results if r["ok"]),
            "elapsed_ms": int((time.time() - started) * 1000)}


@router.post("/runs/{run_id}/approve")
async def approve_run(run_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        run = s.scalar(select(ActionRun).where(ActionRun.id == run_id, ActionRun.workspace_id == ws))
        if run is None:
            raise HTTPException(404, detail="Run not found")
        if run.status != "pending_approval":
            raise HTTPException(400, detail=f"Run is {run.status}, not awaiting approval")
        payload = json.loads(run.request_json or "{}")
        entity = run.entity_id
        s.delete(run)
    body = ExecuteIn(action=payload.get("action", ""), entity_id=entity,
                     args=payload.get("args", {}), approved=True)
    return await execute_action(body, request)


# ── Read Anything: urls / site / sitemap at scale ─────────────────────────

class ReadIn(BaseModel):
    urls: list[str] = Field(default_factory=list)
    url: str = ""            # single-page form, matching the console field
    seed: str = ""           # the word the rest of the API uses for "where to start"
    site: str = ""
    sitemap: str = ""
    depth: int = 1
    max_pages: int = 50
    entity_id: str = "default"
    follow_links: bool = True
    render: bool = False


@router.post("/read")
async def read_create(body: ReadIn, request: Request) -> dict[str, Any]:
    """Queue a read job: specific URLs, a sitemap, or a site crawled to `depth`.

    Returns immediately with a job id. Poll `GET /v1/read/{id}` for progress or
    stream the pages as they land with `GET /v1/read/{id}/pages?stream=1`.
    """
    from . import reader

    ws, _ = workspace_from_request(request)
    rate_limit(f"ws:{ws}", rate_for(ws))
    max_pages = max(1, min(int(body.max_pages or 50), 20000))
    remaining = read_budget_left(ws)
    if remaining <= 0:
        raise HTTPException(402, detail=(
            f"This workspace has used its {read_page_limit(ws):,} read pages for the month. "
            "Upgrade the plan or wait for the period to reset."))
    max_pages = min(max_pages, remaining)
    # One URL is the most common call by far, so it is accepted under every name
    # it is written with: url, seed, site or a one-item urls list.
    single = (body.url or body.seed or "").strip()
    if single and not body.urls:
        body.urls = [single]
    elif single and single not in body.urls:
        body.urls = [single, *body.urls]
    if body.urls and not body.site and not body.sitemap and body.depth > 1:
        body.site = body.urls[0]
        body.urls = []
    try:
        job_id = reader.create_job(
            ws, urls=body.urls, site=body.site, sitemap=body.sitemap, depth=body.depth,
            max_pages=max_pages, entity_id=body.entity_id,
            follow_links=body.follow_links, render=body.render)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))
    reader.enqueue(job_id)
    state = reader.job_state(job_id, ws) or {}
    return {"ok": True, "job_id": job_id, "status": state.get("status", "queued"),
            "max_pages": max_pages, "stream": f"/v1/read/{job_id}/pages?stream=1",
            "poll": f"/v1/read/{job_id}"}


@router.get("/read")
def read_jobs(request: Request, limit: int = 20) -> dict[str, Any]:
    from . import reader

    ws, _ = workspace_from_request(request)
    from .models import ReadJob
    with session() as s:
        rows = s.scalars(select(ReadJob).where(ReadJob.workspace_id == ws)
                         .order_by(ReadJob.created_at.desc()).limit(min(limit, 100))).all()
        return {"jobs": [{"job_id": r.id, "status": r.status, "seed": r.seed_url,
                          "max_pages": r.max_pages, "fetched": r.fetched,
                          "created_at": r.created_at.isoformat() if r.created_at else ""} for r in rows]}


@router.get("/read/{job_id}")
def read_status(job_id: str, request: Request) -> dict[str, Any]:
    from . import reader

    ws, _ = workspace_from_request(request)
    state = reader.job_state(job_id, ws)
    if state is None:
        raise HTTPException(404, detail="Unknown read job")
    return state


@router.post("/read/{job_id}/cancel")
def read_cancel(job_id: str, request: Request) -> dict[str, Any]:
    from . import reader
    from .models import ReadJob

    ws, _ = workspace_from_request(request)
    with session() as s:
        job = s.scalar(select(ReadJob).where(ReadJob.id == job_id, ReadJob.workspace_id == ws))
        if job is None:
            raise HTTPException(404, detail="Unknown read job")
        job.status = "cancelled"
        s.flush()
    return {"ok": True, "job_id": job_id, "status": "cancelled"}


@router.get("/read/{job_id}/pages")
def read_pages(job_id: str, request: Request, offset: int = 0, limit: int = 50,
               content: bool = True, status: str = "", stream: bool = False):
    """Pages of a read job. `stream=1` emits NDJSON as pages finish."""
    from . import reader

    ws, _ = workspace_from_request(request)
    if not stream:
        try:
            return reader.job_pages(job_id, ws, offset=offset, limit=limit,
                                    include_content=content, status=status)
        except KeyError:
            raise HTTPException(404, detail="Unknown read job")

    if reader.job_state(job_id, ws) is None:
        raise HTTPException(404, detail="Unknown read job")

    async def events():
        cursor = offset
        idle = 0
        while True:
            chunk = reader.job_pages(job_id, ws, offset=cursor, limit=limit,
                                     include_content=content, status=status)
            for page in chunk["pages"]:
                cursor += 1
                yield json.dumps(page, ensure_ascii=False) + "\n"
            state = reader.job_state(job_id, ws) or {}
            if state.get("status") in {"done", "failed", "cancelled"} and not chunk["pages"]:
                yield json.dumps({"event": "finished", "state": state}, ensure_ascii=False) + "\n"
                return
            idle = 0 if chunk["pages"] else idle + 1
            if idle > 600:
                yield json.dumps({"event": "timeout", "state": state}, ensure_ascii=False) + "\n"
                return
            await asyncio.sleep(0.8)

    return StreamingResponse(events(), media_type="application/x-ndjson")


@router.post("/read/{job_id}/summarise")
def read_summarise(job_id: str, request: Request, max_points: int = 12, markdown: bool = False) -> dict[str, Any]:
    """Map-reduce the whole job into a brief: themes, key points, sources, compression."""
    from . import summarise

    ws, _ = workspace_from_request(request)
    try:
        brief = summarise.build_brief(job_id, ws, max_points=max(3, min(int(max_points), 40)))
    except KeyError:
        raise HTTPException(404, detail="Unknown read job")
    if markdown:
        brief["markdown"] = summarise.brief_markdown(brief)
    return brief


@router.get("/governor")
def governor_stats() -> dict[str, Any]:
    """Live politeness budget: how hard Tony is willing to fetch."""
    from .governor import GOVERNOR
    return GOVERNOR.snapshot()


# ── Hands: raw passthrough and governed fan-out ───────────────────────────

class ProxyIn(BaseModel):
    method: str = "GET"
    path: str = "/"
    query: dict[str, Any] = Field(default_factory=dict)
    body: Any = None
    headers: dict[str, str] = Field(default_factory=dict)
    entity_id: str = "default"
    max_chars: int = 200000


@router.post("/proxy/{app_slug}")
async def proxy(app_slug: str, body: ProxyIn, request: Request) -> dict[str, Any]:
    """Call any endpoint of a connected app, including ones not in the catalogue.

    The catalogue covers 48k actions; a real app has endpoints nobody wrapped.
    This passes the request through with the connection's credentials, the SSRF
    guard, redirect re-validation and the injection firewall still applied.
    """
    from . import firewall
    from .executor import _guarded_request, redact_url

    ws, _ = workspace_from_request(request)
    spec = catalog.get(app_slug)
    if spec is None:
        raise HTTPException(404, detail=f"Unknown app '{app_slug}'")
    if not (spec.base_url or "").startswith("http"):
        raise HTTPException(400, detail=f"{spec.name} has no base URL to proxy to")
    entity = _entity(ws, body.entity_id)
    creds = credentials_for(ws, entity, spec)
    if spec.auth.type != "none" and creds is None:
        raise HTTPException(409, detail=f"No {spec.name} account connected. Connect it first, then retry.")
    rate_limit(f"ws:{ws}", rate_for(ws))

    path = body.path if body.path.startswith("/") else "/" + body.path
    url = (spec.base_url or "").rstrip("/") + path
    headers = {"User-Agent": "TonyProxy/1.0", "Accept": "application/json"}
    headers.update(spec.default_headers or {})
    headers.update({k: v for k, v in (body.headers or {}).items()
                    if k.lower() not in {"authorization", "host", "cookie", "content-length"}})
    query = dict(body.query or {})
    from .executor import apply_auth
    apply_auth(spec, headers, query, creds)

    method = (body.method or "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
        raise HTTPException(400, detail="Unsupported method")
    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await _guarded_request(client, method, url, headers=headers,
                                          params=query or None,
                                          json_body=body.body if method not in {"GET", "HEAD"} else None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, detail=f"{spec.name} request failed: {type(exc).__name__}: {exc}"[:300])
    latency = int((time.time() - started) * 1000)
    text = resp.text or ""
    trimmed = text[: max(0, min(body.max_chars, 400000))]
    verdict = firewall.scan(trimmed[:40000]) if "json" in resp.headers.get("content-type", "") and trimmed else {"score": 0, "flags": []}
    payload: Any
    try:
        payload = json.loads(trimmed)
    except ValueError:
        payload = {"text": trimmed}
    return {
        "ok": resp.status_code < 400,
        "status": resp.status_code,
        "latency_ms": latency,
        "app": spec.slug,
        "method": method,
        "url": redact_url(url),
        "chars": len(text),
        "truncated": len(text) > len(trimmed),
        "neutralised": bool(verdict.get("score", 0)),
        "data": payload,
    }


class FanoutIn(BaseModel):
    calls: list[dict[str, Any]] = Field(default_factory=list)
    concurrency: int = 6
    entity_id: str = "default"
    stop_on_error: bool = False


@router.post("/fanout")
async def fanout(body: FanoutIn, request: Request) -> dict[str, Any]:
    """Run up to 200 actions in parallel, governed per host and per workspace.

    `POST /v1/batch` stays sequential and cheap; this is the bulk path for
    enrichment jobs. Concurrency is capped by the governor, not by the caller.
    """
    if not body.calls:
        raise HTTPException(400, detail="Send at least one call")
    if len(body.calls) > 200:
        raise HTTPException(400, detail="Fan-out is capped at 200 calls per request. Use /v1/read or split the job.")
    limit = max(1, min(int(body.concurrency or 6), 24))
    sem = asyncio.Semaphore(limit)
    started = time.time()

    async def one(call: dict[str, Any]) -> dict[str, Any]:
        payload = ExecuteIn(action=call.get("action", ""), entity_id=call.get("entity_id", body.entity_id),
                            args=call.get("args") or {}, approved=bool(call.get("approved")),
                            dry_run=bool(call.get("dry_run")), source="fanout")
        async with sem:
            try:
                out = await execute_action(payload, request)
                return {"action": payload.action, "ok": bool(out.get("ok")), "result": out}
            except HTTPException as exc:
                return {"action": payload.action, "ok": False, "status_code": exc.status_code,
                        "error": exc.detail}
            except Exception as exc:  # noqa: BLE001
                return {"action": payload.action, "ok": False, "error": str(exc)[:300]}

    results = await asyncio.gather(*[one(c) for c in body.calls])
    return {"results": results, "count": len(results),
            "succeeded": sum(1 for r in results if r["ok"]),
            "concurrency": limit,
            "elapsed_ms": int((time.time() - started) * 1000)}


@router.get("/runs")
def list_runs(request: Request, limit: int = 40, app: str = "") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        q = select(ActionRun).where(ActionRun.workspace_id == ws).order_by(ActionRun.created_at.desc()).limit(min(limit, 200))
        if app:
            q = q.where(ActionRun.app_slug == app)
        rows = s.scalars(q).all()
        return {"runs": [{
            "id": r.id, "app": r.app_slug, "action": r.action_slug, "tier": r.tier,
            "status": r.status, "status_code": r.status_code, "latency_ms": r.latency_ms,
            "chars": r.chars_out, "error": r.error,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]}


# ── triggers ──────────────────────────────────────────────────────────────
class TriggerIn(BaseModel):
    action: str
    entity_id: str = "default"
    args: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: int = 300
    webhook_url: str = ""


@router.post("/triggers")
def create_trigger(body: TriggerIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    check_capacity(ws, "triggers")
    resolved = catalog.find_action(body.action)
    if not resolved:
        raise HTTPException(404, detail="Unknown action")
    spec, action = resolved
    if body.interval_seconds < 60:
        raise HTTPException(400, detail="Minimum interval is 60 seconds")
    trigger = Trigger(
        workspace_id=ws, entity_id=body.entity_id or "default", app_slug=spec.slug,
        action_slug=action.slug, args_json=json.dumps(body.args), interval_seconds=body.interval_seconds,
        webhook_url=body.webhook_url, secret=secrets.token_hex(24),
    )
    with session() as s:
        s.add(trigger)
        s.flush()
        return {"id": trigger.id, "secret": trigger.secret, "interval_seconds": trigger.interval_seconds,
                "action": f"{spec.slug}.{action.slug}"}


@router.get("/triggers")
def list_triggers(request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(Trigger).where(Trigger.workspace_id == ws).order_by(Trigger.created_at.desc())).all()
        deliveries = {d.trigger_id: d for d in s.scalars(select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(200)).all()}
        return {"triggers": [{
            "id": t.id, "action": f"{t.app_slug}.{t.action_slug}", "entity_id": t.entity_id,
            "interval_seconds": t.interval_seconds, "webhook_url": t.webhook_url, "enabled": t.enabled,
            "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
            "last_delivery": (deliveries.get(t.id).ok if deliveries.get(t.id) else None),
        } for t in rows]}


@router.delete("/triggers/{trigger_id}")
def delete_trigger(trigger_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(Trigger).where(Trigger.id == trigger_id, Trigger.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Trigger not found")
        s.delete(row)
    return {"deleted": True}


# ── workspaces (bootstrap) ────────────────────────────────────────────────
class WorkspaceIn(BaseModel):
    name: str = "Workspace"


@router.post("/workspaces")
def create_workspace_api(body: WorkspaceIn, request: Request) -> dict[str, Any]:
    if not settings.demo_open:
        token = request.headers.get("x-admin-token", "")
        if not settings.admin_token or token != settings.admin_token:
            raise HTTPException(401, detail="Set X-Admin-Token to create workspaces")
    from .db import create_workspace
    ws, key = create_workspace(body.name)
    return {"workspace_id": ws.id, "api_key": key, "note": "Store this key now, it is not shown again."}


@router.post("/admin/db-setup", include_in_schema=False)
def db_setup(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Create a database inside this instance for an adjacent service.

    Guarded by TONY_SETUP_TOKEN because it is a one-time provisioning hook, not a
    feature. It only ever creates a database; it never drops or alters anything.
    """
    import os as _os
    import re as _re

    token = request.headers.get("x-setup-token", "")
    expected = _os.getenv("TONY_SETUP_TOKEN", "")
    if not expected or token != expected:
        raise HTTPException(401, detail="Bad setup token")
    name = str(body.get("database") or "").strip()
    if not _re.fullmatch(r"[a-z][a-z0-9_]{2,30}", name):
        raise HTTPException(400, detail="database must be a safe identifier")
    drop = bool(body.get("drop"))
    import psycopg2
    from .config import settings as _settings

    url = _os.getenv("DATABASE_URL", "") or getattr(_settings, "database_url", "")
    if not url:
        raise HTTPException(400, detail="No DATABASE_URL on this instance")
    admin_url = _re.sub(r"/[^/?]+(\?|$)", "/postgres\\1", url, count=1)
    try:
        conn = psycopg2.connect(admin_url, connect_timeout=15)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("select 1 from pg_database where datname = %s", (name,))
        exists = bool(cur.fetchone())
        if drop:
            if name in {"postgres", "template0", "template1"}:
                raise HTTPException(400, detail="refusing to drop a system database")
            if not exists:
                return {"ok": True, "database": name, "dropped": False}
            cur.execute("select pg_terminate_backend(pid) from pg_stat_activity where datname = %s", (name,))
            cur.execute(f'DROP DATABASE "{name}"')
            return {"ok": True, "database": name, "dropped": True}
        if exists:
            return {"ok": True, "database": name, "created": False}
        cur.execute(f'CREATE DATABASE "{name}"')
        return {"ok": True, "database": name, "created": True}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, detail=f"Could not create database: {exc}") from exc
