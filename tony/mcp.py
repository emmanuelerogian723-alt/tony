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
from .auth import workspace_from_request
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
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "tony", "version": __version__},
            "instructions": (
                "Tony is an integration gateway. Tools are named app__action "
                "(e.g. github__list_repos). Read-only tools run immediately; write "
                "or destructive tools return a pending_approval record that the "
                "operator must approve before the action executes."
            ),
        })
    if method == "ping":
        return ok({})
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
        return ok({
            "content": [{"type": "text", "text": json.dumps(result.as_dict(), indent=2, default=str)}],
            "isError": not result.ok,
            "_meta": {"app": spec.slug, "action": action.slug, "latency_ms": result.latency_ms},
        })
    if method == "resources/list":
        return ok({"resources": [
            {"uri": "tony://catalog", "name": "App catalogue", "mimeType": "application/json"},
            {"uri": "tony://runs", "name": "Recent runs", "mimeType": "application/json"},
        ]})
    if method == "prompts/list":
        return ok({"prompts": []})
    return err(-32601, f"Method not found: {method}")
