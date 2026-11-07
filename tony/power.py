"""Tony's power layer.

Three things live here:

* ``/v1/tools``   - LLM-ready tool schemas (OpenAI, Anthropic, MCP) for any slice
                    of the catalogue, so a developer can hand Tony's 40k actions
                    straight to their own model.
* ``/v1/agent``   - a goal-in, answer-out runtime. It picks apps, runs real
                    actions in a loop, feeds results back to the model and
                    returns the trace. Without an LLM key it still executes the
                    best matching action, so it degrades instead of failing.
* ``/v1/proxy``   - universal passthrough for any documented REST endpoint of a
                    connected app, with Tony's stored credentials injected.

Plus ``/v1/memory`` for agent state, ``/v1/usage`` and ``/v1/audit`` for the
observability a real system needs.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import __version__
from .auth import rate_limit, workspace_from_request
from .billing import check_run, rate_for
from .catalog import catalog
from .db import session
from .executor import execute
from .models import ActionRun, AgentMemory, ConnectedAccount
from .oauth import credentials_for

router = APIRouter(prefix="/v1")

MAX_TOOL_RESULT_CHARS = 6000


def _entity(ws: str, entity_id: str) -> str:
    from .api import _entity as api_entity

    return api_entity(ws, entity_id)


# ── tool schemas ──────────────────────────────────────────────────────────
def _json_type(raw: Any) -> str:
    t = (raw if isinstance(raw, str) else (raw or {}).get("type", "string") if isinstance(raw, dict) else "string") or "string"
    t = t.lower()
    if t in {"int", "integer", "number", "float"}:
        return "number"
    if t in {"bool", "boolean"}:
        return "boolean"
    if t in {"array", "list"}:
        return "array"
    if t in {"object", "dict"}:
        return "object"
    return "string"


def _tool_name(app_slug: str, action_slug: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", f"{app_slug}__{action_slug}")[:64]


def _tool_schema(app_slug: str, action: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for name, spec in (action.params or {}).items():
        props[name] = {"type": _json_type(spec), "description": (spec or {}).get("description", "") if isinstance(spec, dict) else ""}
    return {
        "name": _tool_name(app_slug, action.slug),
        "description": f"[{app_slug}] {action.name}: {action.description}".strip()[:900],
        "parameters": {
            "type": "object",
            "properties": props,
            "required": list(action.required or []),
            "additionalProperties": True,
        },
        "x-tony": {"app": app_slug, "action": action.slug, "tier": action.tier, "action_name": action.name},
    }


def _pick_apps(names: list[str], limit: int = 40) -> list[Any]:
    out = []
    for raw in names:
        spec = catalog.get(raw.strip()) if raw.strip() else None
        if spec:
            out.append(spec)
        if len(out) >= limit:
            break
    return out


@router.get("/tools")
def tools(apps: str = "", app: str = "", q: str = "", include_writes: bool = False,
          fmt: str = "", format: str = "openai", limit: int = 2000) -> dict[str, Any]:
    """Tool definitions your model can call. Tony executes them for you."""
    format = fmt or format
    limit = max(1, min(limit, 5000))
    names = [a for a in apps.split(",") if a.strip()]
    if app:
        names.append(app)
    specs = _pick_apps(names, limit=500)
    if not specs and q:
        from .search import find_apps

        specs = [catalog.get(hit["slug"]) for hit in find_apps(q, limit=8)]
        specs = [s for s in specs if s]
    if not specs:
        specs = list(catalog.apps.values())[:400]

    tools = []
    for spec in specs:
        for action in spec.actions:
            if action.tier != "read" and not include_writes:
                continue
            tools.append(_tool_schema(spec.slug, action))
            if len(tools) >= limit:
                break
        if len(tools) >= limit:
            break

    if format == "anthropic":
        shaped = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]
    elif format == "mcp":
        shaped = [{"name": t["name"], "description": t["description"], "inputSchema": t["parameters"]} for t in tools]
    else:
        shaped = [{"type": "function", "function": t} for t in tools]
    return {"format": format, "count": len(shaped), "tools": shaped,
            "note": "Send the call back to POST /v1/agent with the same goal, or run it with POST /v1/execute."}


# ── agent runtime ─────────────────────────────────────────────────────────
class AgentIn(BaseModel):
    goal: str
    apps: list[str] = Field(default_factory=list)
    entity_id: str = "default"
    max_steps: int = 4
    approve_writes: bool = False
    dry_run: bool = False
    history: list[dict[str, str]] = Field(default_factory=list)


def _llm_target() -> tuple[str, str, dict[str, str]] | None:
    if os.getenv("GROQ_API_KEY"):
        return ("https://api.groq.com/openai/v1/chat/completions",
                os.getenv("TONY_AGENT_MODEL", "llama-3.3-70b-versatile"),
                {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"})
    if os.getenv("OPENAI_API_KEY"):
        return ("https://api.openai.com/v1/chat/completions",
                os.getenv("TONY_AGENT_MODEL", "gpt-4o-mini"),
                {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"})
    if os.getenv("OPENROUTER_API_KEY"):
        return ("https://openrouter.ai/api/v1/chat/completions",
                os.getenv("TONY_AGENT_MODEL", "openai/gpt-4o-mini"),
                {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"})
    return None


async def _chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                temperature: float = 0.2) -> dict[str, Any] | None:
    target = _llm_target()
    if not target:
        return None
    url, model, hdr = target
    payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(url, json=payload, headers={**hdr, "Content-Type": "application/json"})
            if r.status_code >= 400:
                return None
            return r.json()["choices"][0]["message"]
    except Exception:
        return None


def _score_app(goal: str, spec: Any) -> int:
    words = set(re.findall(r"[a-z0-9]{3,}", goal.lower()))
    hay = " ".join([spec.slug, spec.name, spec.category, spec.description or ""]).lower()
    score = sum(3 for w in words if w in hay)
    score += sum(1 for a in spec.actions if any(w in a.slug or w in a.name.lower() for w in words))
    return score


def _best_action(goal: str, spec: Any) -> Any | None:
    words = set(re.findall(r"[a-z0-9]{3,}", goal.lower()))
    best, best_score = None, 0
    for a in spec.actions:
        hay = f"{a.slug} {a.name} {a.description}".lower()
        score = sum(2 for w in words if w in hay)
        if a.tier == "read" and not a.required:
            score += 1
        if score > best_score:
            best, best_score = a, score
    return best or (spec.actions[0] if spec.actions else None)


async def _run_one(ws: str, entity: str, app_slug: str, action_slug: str | None,
                   args: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    spec = catalog.get(app_slug)
    if not spec:
        return {"ok": False, "error": "unknown app"}
    action = None
    if action_slug:
        action = next((a for a in spec.actions if a.slug == action_slug or a.name == action_slug), None)
    action = action or _best_action("", spec)
    if action is None:
        return {"ok": False, "error": "no actions"}
    creds = credentials_for(ws, entity, spec)
    if spec.auth.type != "none" and creds is None and not action.public:
        return {"ok": False, "error": f"{spec.name} is not connected", "needs_connection": spec.slug}
    check_run(ws)
    started = time.perf_counter()
    status, code, error, body = "error", 0, "", None
    try:
        result = await asyncio.wait_for(execute(spec, action, args or {}, creds, dry_run=dry_run), timeout=30)
        ms = int((time.perf_counter() - started) * 1000)
        data = result.as_dict() if hasattr(result, "as_dict") else result
        status = "success"
        code = getattr(result, "status_code", 200)
        out = {"ok": True, "app": spec.slug, "action": action.slug, "tier": action.tier,
               "status_code": code, "latency_ms": ms, "data": data}
        body = json.dumps(data, default=str)
        return out
    except Exception as exc:  # noqa: BLE001 - the agent reports, never crashes
        ms = int((time.perf_counter() - started) * 1000)
        error = f"{type(exc).__name__}: {exc}"[:400]
        return {"ok": False, "app": spec.slug, "action": action.slug, "latency_ms": ms, "error": error}
    finally:
        try:
            with session() as s:
                s.add(ActionRun(workspace_id=ws, entity_id=entity, app_slug=spec.slug,
                                action_slug=action.slug, tier=action.tier, status=status,
                                status_code=code, latency_ms=ms, chars_out=len(body or ""),
                                request_json=json.dumps(args or {}, default=str)[:2000],
                                response_json=(body or "")[:6000], error=error))
                s.commit()
        except Exception:
            pass


def _compact(data: Any) -> Any:
    blob = json.dumps(data, default=str)
    if len(blob) <= MAX_TOOL_RESULT_CHARS:
        return data
    return {"truncated": True, "chars": len(blob), "preview": json.loads(json.dumps(data, default=str))[:0] or
            blob[:MAX_TOOL_RESULT_CHARS]}


def _items_of(step: dict[str, Any]) -> list[dict[str, Any]]:
    data = (step.get("data") or {})
    inner = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(inner, list):
        return [x for x in inner if isinstance(x, dict)]
    return []


def _headline(item: dict[str, Any]) -> str:
    for key in ("title", "name", "description", "login", "full_name", "subject", "text"):
        if item.get(key):
            return str(item[key])[:140]
    return ""


def _summarise(goal: str, steps: list[dict[str, Any]]) -> str:
    good = [s for s in steps if s.get("ok")]
    if not good:
        err = steps[-1].get("error") if steps else "nothing ran"
        return (f"I could not finish that: {err}. The plan is still on record, so you can retry with a "
                f"connected app or a narrower goal.")
    last = good[-1]
    lines = [f"{last['app']}.{last['action']} answered in {last.get('latency_ms', 0)} ms."]
    items = _items_of(last)
    if items:
        lines.append(f"{len(items)} result(s).")
        for item in items[:5]:
            head = _headline(item)
            if head:
                lines.append(f"• {head}")
    elif isinstance((last.get("data") or {}).get("data", last.get("data")), dict):
        inner = (last.get("data") or {}).get("data", last.get("data"))
        lines.append("Fields: " + ", ".join(list(inner)[:8]) + ".")
    if len(good) > 1:
        lines.append(f"{len(good) - 1} extra step(s) ran before that.")
    return "\n".join(lines)


@router.post("/agent")
async def agent(body: AgentIn, request: Request) -> dict[str, Any]:
    """Give Tony a goal. It plans, calls real apps, and answers with receipts."""
    ws, _ = workspace_from_request(request)
    goal = (body.goal or "").strip()
    if not goal:
        raise HTTPException(400, detail="Tell me what to do, e.g. {'goal': 'latest hacker news'}")

    rate_limit(f"ws:{ws}", rate_for(ws))
    entity = _entity(ws, body.entity_id)
    steps: list[dict[str, Any]] = []
    started = time.perf_counter()

    # 1. choose candidate apps
    if body.apps:
        specs = _pick_apps(body.apps)
    else:
        ranked = sorted(catalog.apps.values(), key=lambda s: _score_app(goal, s), reverse=True)
        specs = [s for s in ranked[:3] if _score_app(goal, s) > 0]
        if not specs:
            specs = [s for s in ranked[:1] if s.actions]
    if not specs:
        return {"answer": "No app in the catalogue matches that. Search with GET /v1/apps?q=.",
                "steps": [], "elapsed_ms": 0, "engine": "none"}

    # 2. build the tool belt
    belt: list[dict[str, Any]] = []
    index: dict[str, tuple[str, str]] = {}
    for spec in specs:
        taken = 0
        for action in spec.actions:
            if action.tier != "read" and not body.approve_writes:
                continue
            t = _tool_schema(spec.slug, action)
            belt.append({"type": "function", "function": t})
            index[t["name"]] = (spec.slug, action.slug)
            taken += 1
            if taken >= 8:
                break
    belt = belt[:24]

    # 3. run the loop
    engine = "heuristic"
    answer = ""
    messages: list[dict[str, Any]] = [{
        "role": "system",
        "content": ("You are Tony, an execution agent with real hands on real apps. You call tools and answer "
                    "with what actually came back. Rules: never invent data; if a tool errors, say so and try a "
                    "different tool once; keep the final answer under 110 words; no markdown headings."),
    }, {"role": "user", "content": goal}]
    for turn in (body.history or [])[-4:]:
        messages.insert(-1, {"role": turn.get("role", "user"), "content": turn.get("content", "")})

    if belt:
        for _ in range(max(1, min(body.max_steps, 6))):
            reply = await _chat(messages, belt)
            if reply is None:
                break
            engine = "llm"
            calls = reply.get("tool_calls") or []
            if not calls:
                answer = (reply.get("content") or "").strip()
                break
            messages.append({"role": "assistant", "content": reply.get("content") or "",
                             "tool_calls": calls})
            for call in calls:
                fn = (call.get("function") or {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                app_slug, action_slug = index.get(name, ("", ""))
                out = await _run_one(ws, entity, app_slug, action_slug, args, body.dry_run)
                steps.append(out)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", name),
                    "name": name,
                    "content": json.dumps(_compact(out), default=str)[:MAX_TOOL_RESULT_CHARS],
                })
            if answer:
                break

    # 4. never fail: if the model was unavailable, execute the best guess
    if not steps:
        spec = specs[0]
        action = _best_action(goal, spec)
        if action is not None:
            if action.tier != "read" and not body.approve_writes:
                steps.append({"ok": False, "app": spec.slug, "action": action.slug,
                              "error": f"{action.tier} action needs approve_writes=true"})
            else:
                steps.append(await _run_one(ws, entity, spec.slug, action.slug, {}, body.dry_run))

    if engine == "heuristic" and steps and steps[0].get("ok") and body.max_steps > 1:
        first = steps[0]
        spec = next((x for x in specs if x.slug == first["app"]), specs[0])
        items = _items_of(first)
        if items:
            id_key = next((k for k in ("id", "key", "uuid", "number") if items[0].get(k) is not None), "")
            value = items[0].get(id_key) if id_key else None
            if value not in (None, ""):
                follow = next((a for a in spec.actions
                               if a.tier == "read" and a.slug != first["action"]
                               and len(a.required or []) == 1
                               and (a.required[0] in {"id", "item_id", "story_id", "issue_number", "number"})), None)
                if follow is not None:
                    steps.append(await _run_one(ws, entity, spec.slug, follow.slug,
                                                {follow.required[0]: value}, body.dry_run))

    if not answer:
        answer = _summarise(goal, steps)
    elapsed = int((time.perf_counter() - started) * 1000)
    return {
        "answer": answer,
        "steps": steps,
        "apps_considered": [s.slug for s in specs],
        "engine": engine,
        "elapsed_ms": elapsed,
        "version": __version__,
    }


# ── universal proxy ───────────────────────────────────────────────────────
BLOCKED_HOST = re.compile(r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1)$", re.I)


def _app_origin(spec: Any, creds: dict[str, Any] | None) -> str:
    base = (creds or {}).get("base_url") or ""
    if base:
        return base.rstrip("/")
    for action in spec.actions:
        url = action.url or ""
        if url.startswith("http"):
            parts = urlsplit(url)
            return f"{parts.scheme}://{parts.netloc}"
    return ""


@router.api_route("/proxy/{app_slug}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(app_slug: str, path: str, request: Request, entity_id: str = "default"):
    """Call any endpoint of a connected app. Tony adds the credentials."""
    from .executor import apply_auth

    ws, _ = workspace_from_request(request)
    spec = catalog.get(app_slug)
    if not spec:
        raise HTTPException(404, detail="Unknown app")
    entity = _entity(ws, entity_id)
    creds = credentials_for(ws, entity, spec)
    origin = _app_origin(spec, creds)
    if not origin:
        raise HTTPException(400, detail=f"No base URL for {spec.name}. Connect it with a base URL first.")
    host = urlsplit(origin).hostname or ""
    if BLOCKED_HOST.match(host):
        raise HTTPException(400, detail="Private hosts are blocked")
    url = f"{origin}/{path.lstrip('/')}"
    headers: dict[str, str] = {"User-Agent": "Tony/1.0 (+https://tony.io)"}
    query = dict(request.query_params)
    headers.update({k: v for k, v in request.headers.items()
                    if k.lower() in {"accept", "content-type"}})
    apply_auth(spec, headers, query, creds)
    body = await request.body()
    check_run(ws)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.request(request.method, url, headers=headers, params=query,
                                content=body if body else None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, detail=f"{spec.name} did not answer: {type(exc).__name__}") from exc
    latency = int((time.perf_counter() - started) * 1000)
    with session() as s:
        s.add(ActionRun(workspace_id=ws, entity_id=entity, app_slug=spec.slug,
                        action_slug=f"proxy:{path[:60]}", tier="read", status="success" if r.status_code < 400 else "error",
                        status_code=r.status_code, latency_ms=latency, chars_out=len(r.content),
                        request_json=json.dumps({"method": request.method, "path": path})[:2000],
                        response_json=r.text[:4000], error="" if r.status_code < 400 else r.text[:300]))
        s.commit()
    ctype = r.headers.get("content-type", "")
    if "application/json" in ctype:
        return Response(content=r.content, status_code=r.status_code, media_type="application/json")
    return Response(content=r.content[:400000], status_code=r.status_code, media_type=ctype or "text/plain")


# ── memory ────────────────────────────────────────────────────────────────
class MemoryIn(BaseModel):
    value: Any = None
    entity_id: str = "default"


@router.put("/memory/{key}")
def memory_put(key: str, body: MemoryIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    _entity(ws, body.entity_id)
    with session() as s:
        row = s.scalar(select(AgentMemory).where(AgentMemory.workspace_id == ws,
                                                AgentMemory.entity_id == body.entity_id,
                                                AgentMemory.key == key[:200]))
        if row is None:
            row = AgentMemory(workspace_id=ws, entity_id=body.entity_id, key=key[:200])
            s.add(row)
        row.value_json = json.dumps(body.value, default=str)[:100000]
        s.commit()
    return {"key": key, "ok": True}


@router.get("/memory/{key}")
def memory_get(key: str, request: Request, entity_id: str = "default") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(AgentMemory).where(AgentMemory.workspace_id == ws,
                                                AgentMemory.entity_id == entity_id,
                                                AgentMemory.key == key[:200]))
        if row is None:
            raise HTTPException(404, detail="No such key")
        return {"key": key, "value": json.loads(row.value_json or "null")}


@router.get("/memory")
def memory_list(request: Request, entity_id: str = "") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        q = select(AgentMemory).where(AgentMemory.workspace_id == ws)
        if entity_id:
            q = q.where(AgentMemory.entity_id == entity_id)
        rows = s.scalars(q).all()
        return {"keys": [{"key": r.key, "entity_id": r.entity_id, "updated_at": r.updated_at.isoformat()} for r in rows]}


@router.delete("/memory/{key}")
def memory_delete(key: str, request: Request, entity_id: str = "default") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(AgentMemory).where(AgentMemory.workspace_id == ws,
                                                AgentMemory.entity_id == entity_id,
                                                AgentMemory.key == key[:200]))
        if row is not None:
            s.delete(row)
            s.commit()
    return {"key": key, "deleted": True}


# ── observability ─────────────────────────────────────────────────────────
@router.get("/usage")
def usage(request: Request, days: int = 30) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))
    with session() as s:
        rows = s.scalars(select(ActionRun).where(ActionRun.workspace_id == ws,
                                                 ActionRun.created_at >= since)).all()
    by_app: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_day: dict[str, int] = {}
    for r in rows:
        by_app[r.app_slug] = by_app.get(r.app_slug, 0) + 1
        by_status[r.status] = by_status.get(r.status, 0) + 1
        day = r.created_at.strftime("%Y-%m-%d")
        by_day[day] = by_day.get(day, 0) + 1
    return {
        "window_days": days,
        "runs": len(rows),
        "success_rate": round(100 * by_status.get("success", 0) / len(rows), 1) if rows else None,
        "by_status": by_status,
        "top_apps": sorted(by_app.items(), key=lambda kv: kv[1], reverse=True)[:10],
        "by_day": dict(sorted(by_day.items())),
    }


@router.get("/audit")
def audit(request: Request, limit: int = 50) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(ActionRun).where(ActionRun.workspace_id == ws)
                         .order_by(ActionRun.created_at.desc()).limit(max(1, min(limit, 200)))).all()
        return {"runs": [{
            "id": r.id, "app": r.app_slug, "action": r.action_slug, "tier": r.tier,
            "status": r.status, "code": r.status_code, "latency_ms": r.latency_ms,
            "error": (r.error or "")[:200], "at": r.created_at.isoformat(),
        } for r in rows]}
