"""Model Context Protocol server (JSON-RPC 2.0 over HTTP).

Any MCP-capable agent (Claude Desktop, Cursor, your own runtime) can point at
<TONY_URL>/mcp and immediately see every action in the catalogue as a tool.
"""
from __future__ import annotations

import asyncio

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import __version__
from .auth import rate_limit, workspace_from_request
from .billing import check_run, enforce_session, rate_for, resolve_session, touch_session
from .config import settings
from .catalog import catalog
from .executor import ExecutionError, execute
from .oauth import credentials_for

router = APIRouter(tags=["mcp"])
PROTOCOL_VERSION = "2024-11-05"


META_TOOLS: list[dict[str, Any]] = [
    {
        "name": "tony_search_tools",
        "description": ("Search Tony's catalogue of app actions by intent, then call the matching "
                        "tool. Use this instead of guessing tool names."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you want to do, e.g. 'send email'"},
                "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 25},
            },
            "required": ["query"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": True},
    },
    {
        "name": "tony_agent",
        "description": ("Give Tony a goal in plain language and it plans across the whole catalogue, runs the "
                        "calls and answers with evidence. Use this for multi-step work ('summarise today's "
                        "Hacker News and draft a post about it') instead of picking tools yourself."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The outcome you want, in plain words"},
                "apps": {"type": "array", "items": {"type": "string"},
                         "description": "Optional app slugs to restrict the plan to"},
                "max_steps": {"type": "integer", "default": 4, "minimum": 1, "maximum": 6},
                "approve_writes": {"type": "boolean", "default": False,
                                   "description": "Only true when the operator approved write actions"},
            },
            "required": ["goal"],
        },
        "annotations": {"readOnlyHint": False, "openWorldHint": True},
    },
    {
        "name": "tony_apps",
        "description": ("List or search apps in the catalogue (slug, name, action count, auth type). "
                        "Use it before tony_search_tools when you only know the product name."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name fragment, e.g. 'notion'"},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 40},
            },
            "required": [],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "tony_execute",
        "description": ("Run any action by its dotted name (app.action). Same behaviour as calling "
                        "the tool directly; handy when the name came from tony_search_tools."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "e.g. github.list_repos"},
                "arguments": {"type": "object", "description": "Action arguments"},
                "_entity_id": {"type": "string", "description": "End-user identity"},
                "_approved": {"type": "boolean", "description": "Approved write/destructive call"},
            },
            "required": ["action"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
]


def _search_tools(args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "")
    limit = max(1, min(int(args.get("limit") or 8), 25))
    results: list[dict[str, Any]] = []
    for spec in catalog.search(query, limit=limit):
        for act in spec.actions[:3]:
            results.append({
                "tool": f"{spec.slug}__{act.slug}",
                "action": f"{spec.slug}.{act.slug}",
                "app": spec.name,
                "summary": f"{act.name}. {act.description}".strip()[:220],
                "tier": act.tier,
                "input_schema": {"type": "object", "properties": act.params, "required": act.required},
            })
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return {"content": [{"type": "text", "text": json.dumps(
        {"query": query, "results": results, "total_apps": len(catalog.apps)}, indent=2)}],
        "isError": False}


def _tool_def(spec, action) -> dict[str, Any]:
    return {
        "name": f"{spec.slug}__{action.slug}",
        "title": f"{spec.name}: {action.name}",
        "description": action.description or action.name,
        "inputSchema": {
            "type": "object",
            "properties": action.params,
            "required": action.required,
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": action.tier == "read",
            "destructiveHint": action.tier == "destructive",
            "openWorldHint": True,
        },
    }


@router.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse({"jsonrpc": "2.0", "id": None,
                             "error": {"code": -32700, "message": "Parse error"}}, status_code=200)

    messages = body if isinstance(body, list) else [body]
    results = []
    for msg in messages:
        results.append(await _handle(msg, request))
    return JSONResponse(results if isinstance(body, list) else results[0])


async def _handle(msg: dict[str, Any], request: Request) -> dict[str, Any]:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    rpc_id = msg.get("id")
    method = str(msg.get("method") or "")
    params = msg.get("params") or {}

    def ok(result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}

    def err(code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}

    if method in {"notifications/initialized", "notifications/cancelled"}:
        return {}
    if method == "initialize":
        return ok({
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False},
                             "prompts": {"listChanged": False},
                             "resources": {"subscribe": False, "listChanged": False}},
            "serverInfo": {"name": "tony", "version": __version__},
            "instructions": (
                "Tony is an integration gateway with {apps} apps and {actions} actions. "
                "Start with tony_search_tools to find the right action, then call "
                "app__action tools (e.g. github__list_repos). Read-only tools run "
                "immediately. Write and destructive tools return a pending_approval "
                "record; the operator approves it once in the console and the exact "
                "request executes. Accounts are connected by signing in on the "
                "provider's own page, so you never handle the user's credentials."
            ).format(apps=len(catalog.apps),
                     actions=sum(len(a.actions) for a in catalog.apps.values())),
        })
    if method == "ping":
        return ok({})
    if method == "prompts/list":
        return ok({"prompts": [
            {"name": "connect_app", "description": "Guide the user through connecting an app by signing in",
             "arguments": [{"name": "app", "description": "App slug, e.g. gmail", "required": True}]},
            {"name": "safe_write", "description": "Run a write action with the approval gate",
             "arguments": [{"name": "action", "description": "app.action, e.g. github.create_issue", "required": True}]},
            {"name": "weekly_digest", "description": "Summarise activity across connected apps",
             "arguments": []},
        ]})
    if method == "prompts/get":
        name = str(params.get("name") or "")
        a = params.get("arguments") or {}
        if name == "connect_app":
            text = (f"Connect {a.get('app', 'the app')} to Tony by signing in. Call the MCP tool for that app; "
                    f"if it is not connected, tell the user to open the Tony console, pick the app, press Connect "
                    f"and sign in on the provider's page. Never ask for an API key.")
        elif name == "safe_write":
            text = (f"Call {a.get('action', 'the write action')} with approved=false first, show the user the exact "
                    f"request Tony would send, and only re-send with approved=true after they approve.")
        elif name == "weekly_digest":
            text = ("Summarise this week's activity: what ran, what failed, what is waiting for approval, "
                    "and which connected accounts need re-authentication.")
        else:
            return err(-32602, "Unknown prompt")
        return ok({"description": name, "messages": [{"role": "user", "content": {"type": "text", "text": text}}]})
    if method == "resources/list":
        return ok({"resources": [
            {"uri": "tony://meta", "name": "Catalogue and policy", "mimeType": "application/json"},
            {"uri": "tony://connections", "name": "Connected accounts", "mimeType": "application/json"},
            {"uri": "tony://approvals", "name": "Runs waiting for approval", "mimeType": "application/json"},
        ]})
    if method == "resources/read":
        uri = str(params.get("uri") or "")
        ws, _ = workspace_from_request(request)
        payload: Any = {}
        if uri == "tony://meta":
            payload = {"apps": len(catalog.apps),
                       "actions": sum(len(a.actions) for a in catalog.apps.values()),
                       "requires_approval": settings.require_approval,
                       "gateway": settings.base_url}
        elif uri in {"tony://connections", "tony://approvals"}:
            from sqlalchemy import select

            from .db import session
            from .models import ActionRun, ConnectedAccount

            with session() as sess:
                if uri == "tony://connections":
                    rows = sess.scalars(select(ConnectedAccount).where(
                        ConnectedAccount.workspace_id == ws)).all()
                    payload = [{"app": r.app_slug, "entity": r.entity_id, "status": r.status,
                                "label": r.label} for r in rows]
                else:
                    rows = sess.scalars(select(ActionRun).where(
                        ActionRun.workspace_id == ws,
                        ActionRun.status == "pending_approval")).all()
                    payload = [{"run_id": r.id, "action": f"{r.app_slug}.{r.action_slug}",
                                "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
        else:
            return err(-32602, "Unknown resource")
        return ok({"contents": [{"uri": uri, "mimeType": "application/json",
                                 "text": json.dumps(payload, indent=2)}]})
    if method == "tools/list":
        cursor = params.get("cursor")
        offset = int(cursor) if cursor else 0
        limit = 120
        all_tools = META_TOOLS + [_tool_def(spec, act) for spec in catalog.apps.values() for act in spec.actions]
        page = all_tools[offset: offset + limit]
        result: dict[str, Any] = {"tools": page}
        if offset + limit < len(all_tools):
            result["nextCursor"] = str(offset + limit)
        return ok(result)
    if method in {"tools/call", "tools/execute"}:
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}

        if name == "tony_search_tools":
            return ok(_search_tools(args))
        if name == "tony_apps":
            q = str(args.get("query") or "").strip().lower()
            limit = max(1, min(int(args.get("limit") or 10), 40))
            rows = []
            for spec in catalog.apps.values():
                hay = f"{spec.slug} {spec.name} {spec.category}".lower()
                if q and q not in hay:
                    continue
                rows.append({"app": spec.slug, "name": spec.name, "actions": len(spec.actions),
                             "auth": spec.auth.type, "category": spec.category,
                             "connected_by": "sign in on the provider page" if spec.auth.type != "none" else "not required"})
            rows.sort(key=lambda r: (r["app"] != q, -r["actions"]))
            return ok({"content": [{"type": "text", "text": json.dumps(
                {"ok": True, "count": len(rows), "apps": rows[:limit],
                 "total_apps": len(catalog.apps)}, indent=2)}], "isError": False})
        if name == "tony_agent":
            from .power import AgentIn, agent as run_agent
            goal = str(args.get("goal") or "").strip()
            if not goal:
                return err(-32602, "goal is required")
            body = AgentIn(goal=goal, apps=[str(a) for a in (args.get("apps") or [])][:6],
                           max_steps=int(args.get("max_steps") or 4),
                           approve_writes=bool(args.get("approve_writes")))
            try:
                out = await run_agent(body, request)
            except Exception as exc:  # noqa: BLE001
                return ok({"content": [{"type": "text", "text": json.dumps(
                    {"ok": False, "error": f"{type(exc).__name__}: {exc}"})}], "isError": True})
            return ok({"content": [{"type": "text", "text": json.dumps(out, indent=2, default=str)}],
                       "isError": False,
                       "_meta": {"engine": out.get("engine"), "steps": len(out.get("steps") or []),
                                 "elapsed_ms": out.get("elapsed_ms")}})
        if name == "tony_execute":
            name = str(args.get("action") or "")

        resolved = catalog.find_action(name)
        if not resolved:
            return err(-32602, f"Unknown tool '{name}'")
        spec, action = resolved
        entity = str(args.pop("_entity_id", "") or request.headers.get("x-tony-entity", "") or "default")
        approved = bool(args.pop("_approved", False))
        try:
            ws, _demo = workspace_from_request(request)
        except Exception:
            return err(-32001, "Missing or invalid API key")
        sess = resolve_session(request, ws)
        enforce_session(sess, spec.slug, action.tier)
        rate_limit(f"ws:{ws}", rate_for(ws))
        check_run(ws)
        if sess:
            entity = sess.entity_id
        if action.tier != "read" and not approved:
            return ok({
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "ok": False,
                        "status": "pending_approval",
                        "tier": action.tier,
                        "message": f"{name} is a {action.tier} action. Ask the operator to approve, "
                                   "then call again with _approved=true.",
                    }, indent=2),
                }],
                "isError": False,
            })
        touch_session(sess)
        creds = credentials_for(ws, entity, spec)
        if spec.auth.type != "none" and creds is None and not action.public:
            return ok({
                "content": [{"type": "text", "text": json.dumps({
                    "ok": False, "error": f"No connected {spec.name} account for entity '{entity}'"} , indent=2)}],
                "isError": True,
            })
        try:
            try:
                result = await asyncio.wait_for(
                    execute(spec, action, args, creds), timeout=settings.execution_deadline)
            except asyncio.TimeoutError:
                raise ExecError(f"{spec.slug}.{action.slug} exceeded {settings.execution_deadline:g}s")
        except ExecutionError as exc:
            return ok({
                "content": [{"type": "text", "text": json.dumps(
                    {"ok": False, "error": str(exc), "detail": exc.detail}, indent=2, default=str)}],
                "isError": True,
            })
        touch_session(sess)
        return ok({
            "content": [{"type": "text", "text": json.dumps(result.as_dict(), indent=2, default=str)}],
            "isError": not result.ok,
            "_meta": {"app": spec.slug, "action": action.slug, "latency_ms": result.latency_ms},
        })
    return err(-32601, f"Method not found: {method}")


@router.get("/mcp")
def mcp_info() -> dict[str, Any]:
    """Discovery for humans and agents: how to attach Tony as an MCP server."""
    base = (settings.base_url or "").rstrip("/")
    return {
        "name": "tony",
        "transport": "http",
        "stdio_bridge": "python mcp_bridge/tony_mcp.py  (TONY_URL + TONY_API_KEY)",
        "endpoint": f"{base}/mcp",
        "protocolVersion": PROTOCOL_VERSION,
        "auth": "Authorization: Bearer tk_live_...",
        "apps": len(catalog.apps),
        "actions": sum(len(a.actions) for a in catalog.apps.values()),
        "clients": {
            "claude_desktop": {"mcpServers": {"tony": {"url": f"{base}/mcp",
                                                       "headers": {"Authorization": "Bearer tk_live_YOUR_KEY"}}}},
            "cursor": {"url": f"{base}/mcp", "headers": {"Authorization": "Bearer tk_live_YOUR_KEY"}},
            "cli_bridge": "python mcp_bridge/tony_mcp.py --url " + f"{base}/mcp" + " --key tk_live_YOUR_KEY",
        },
        "approval_policy": "write and destructive actions pause for one human approval",
    }
