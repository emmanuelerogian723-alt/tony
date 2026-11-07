"""Public REST API (v1) and the dashboard's JSON surface."""
from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import __version__
from .auth import workspace_from_request
from .catalog import catalog
from .config import settings
from .db import session
from .executor import ExecutionError, execute
from .models import ActionRun, ConnectedAccount, Entity, Trigger, WebhookDelivery
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
        row = s.scalar(select(Entity).where(Entity.workspace_id == ws, Entity.external_id == entity_id))
        if row is None:
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


@router.get("/apps")
def list_apps(search: str = "", category: str = "", tier: str = "", source: str = "",
              with_actions: bool = False, limit: int = 60, offset: int = 0) -> dict[str, Any]:
    """Paginated catalogue search. `limit=0` returns everything (use with care)."""
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


@router.get("/tools")
def tool_schemas(fmt: str = "openai", app: str = "") -> dict[str, Any]:
    """Export the catalogue as LLM tool definitions."""
    tools: list[dict[str, Any]] = []
    for spec in catalog.apps.values():
        if app and spec.slug != app:
            continue
        for act in spec.actions:
            name = f"{spec.slug}__{act.slug}"
            desc = f"{spec.name}: {act.name}. {act.description}".strip()
            if fmt == "anthropic":
                tools.append({
                    "name": name,
                    "description": desc,
                    "input_schema": {
                        "type": "object",
                        "properties": act.params,
                        "required": act.required,
                        "additionalProperties": False,
                    },
                })
            else:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": desc,
                        "parameters": {
                            "type": "object",
                            "properties": act.params,
                            "required": act.required,
                            "additionalProperties": False,
                        },
                    },
                })
    return {"tools": tools, "count": len(tools), "format": fmt}


# ── connections ───────────────────────────────────────────────────────────
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
def connect_start(app_slug: str, request: Request, entity_id: str = "default",
                  redirect_after: str = "/app") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    spec = catalog.get(app_slug)
    if not spec:
        raise HTTPException(404, detail="Unknown app")
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
        raise HTTPException(400, detail="This app uses a key, not OAuth. POST /v1/connections/{app}/key with your credentials.")
    _entity(ws, entity_id)
    try:
        session_id, url = start_oauth(ws, entity_id, spec, redirect_after)
    except OAuthError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"mode": "oauth", "auth_session_id": session_id, "authorization_url": url}


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
    if not body.values:
        raise HTTPException(400, detail="Provide the credential values for this app")
    _entity(ws, body.entity_id)
    acct = store_api_key(ws, body.entity_id, spec, body.values, body.label)
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
    resolved = catalog.find_action(body.action)
    if not resolved:
        raise HTTPException(404, detail=f"Unknown action '{body.action}'. Try app.action, e.g. github.list_repos")
    spec, action = resolved
    entity = _entity(ws, body.entity_id)

    if action.tier != "read" and settings.require_approval and not body.approved and not body.dry_run:
        run_id = _log_run(ws, entity, spec, action, "pending_approval",
                          request_payload={"args": body.args, "action": body.action})
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
    if spec.auth.type != "none" and creds is None:
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
        result = await execute(spec, action, body.args, creds, dry_run=body.dry_run)
    except ExecutionError as exc:
        run_id = _log_run(ws, entity, spec, action, "error", None,
                          {"args": body.args, "action": body.action}, error=str(exc))
        return {"ok": False, "error": str(exc), "status_code": exc.status,
                "detail": exc.detail, "run_id": run_id}

    run_id = _log_run(ws, entity, spec, action, "success", result,
                      {"args": body.args, "action": body.action})
    payload = result.as_dict()
    payload["run_id"] = run_id
    payload["app"] = spec.slug
    payload["action"] = action.slug
    return payload


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
