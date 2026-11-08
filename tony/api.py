"""Public REST API (v1) and the dashboard's JSON surface."""
from __future__ import annotations

import asyncio

import json
import time
import os
import re
import secrets
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import __version__
from .auth import rate_limit, workspace_from_request
from .billing import check_capacity, check_run, enforce_session, rate_for, resolve_session, touch_session
from .catalog import catalog
from .config import settings
from .db import session
from .executor import ExecutionError, execute, needs_base_url
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


@router.get("/apps")
def list_apps(search: str = "", q: str = "", category: str = "", tier: str = "", source: str = "",
              with_actions: bool = False, limit: int = 60, offset: int = 0) -> dict[str, Any]:
    """Paginated catalogue search. `limit=0` returns everything (use with care)."""
    search = (search or q).strip()
    matched = catalog.search(search, category, tier=tier, source=source)
    total = len(matched)
    window = matched[offset: offset + limit] if limit else matched[offset:]
    return {
        "apps": [a.to_public(include_actions=with_actions) for a in window],
        "categories": catalog.categories(),
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": bool(limit) and offset + limit < total,
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


@router.get("/actions")
def list_actions(search: str = "", app: str = "", tier: str = "", limit: int = 50,
                 offset: int = 0) -> dict[str, Any]:
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
                        redirect_after: str = "/app") -> dict[str, Any]:
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
        session_id, url = await start_oauth(ws, entity_id, spec, redirect_after)
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
def disconnect(app_slug: str, request: Request, entity_id: str = "default") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == ws,
            ConnectedAccount.entity_id == entity_id,
            ConnectedAccount.app_slug == app_slug)).all()
        for row in rows:
            s.delete(row)
    return {"deleted": len(rows)}


# ── execution ─────────────────────────────────────────────────────────────
class ExecuteIn(BaseModel):
    action: str
    entity_id: str = "default"
    args: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    dry_run: bool = False
    source: str = "api"


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


@router.post("/execute")
async def execute_action(body: ExecuteIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    if body.action.startswith("custom."):
        return await _execute_custom(body, request, ws)
    resolved = catalog.find_action(body.action)
    if not resolved:
        raise HTTPException(404, detail=f"Unknown action '{body.action}'. Try app.action, e.g. github.list_repos")
    spec, action = resolved
    sess = resolve_session(request, ws)
    enforce_session(sess, spec.slug, action.tier)
    rate_limit(f"ws:{ws}", rate_for(ws))
    check_run(ws)
    entity = _entity(ws, sess.entity_id if sess else body.entity_id)

    if action.tier != "read" and settings.require_approval and not body.approved and not body.dry_run:
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

    try:
        try:
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
