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

# One agent run can reach five apps. Past that it is a workflow, not a chain:
# the tool belt stops being a belt and becomes a haystack, and the model picks
# worse tools the more it has. Five is the point where breadth still helps.
MAX_CHAIN_APPS = 5
TOOLS_PER_APP = 6
MAX_BELT_TOOLS = 30
MAX_STEPS_CAP = 12


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
    """A schema a model can fill in without knowing the vendor's vocabulary.

    ``srsearch`` becomes ``query`` and ``maxResults`` becomes ``limit``; the
    original name travels in x-tony, and the executor accepts either, so nothing
    that already works breaks.
    """
    from . import naming

    props: dict[str, Any] = {}
    renamed: dict[str, str] = {}
    for name, spec in (action.params or {}).items():
        friendly = naming.friendly_param(name)
        renamed[name] = friendly
        source = spec if isinstance(spec, dict) else {}
        desc = source.get("description", "")
        if friendly != name:
            desc = (desc + f" (provider parameter: {name})").strip()
        props[friendly] = {"type": _json_type(spec), "description": desc[:300]}
    required = [renamed.get(r, r) for r in (action.required or [])]
    return {
        "name": _tool_name(app_slug, action.slug),
        "description": f"[{app_slug}] {action.name}: {action.description}".strip()[:900],
        "parameters": {
            "type": "object",
            "properties": props,
            "required": required,
            "additionalProperties": True,
        },
        "x-tony": {"app": app_slug, "action": action.slug, "tier": action.tier,
                   "action_name": action.name, "param_map": renamed},
    }


def _pick_apps(names: list[str], limit: int = MAX_CHAIN_APPS) -> list[Any]:
    out = []
    for raw in names:
        key = raw.strip()
        spec = (catalog.resolve(key) or catalog.get(key)) if key else None
        if spec:
            out.append(spec)
        if len(out) >= limit:
            break
    return out


def _usable_actions(spec: Any, approve_writes: bool) -> list[Any]:
    """The actions worth putting in front of a model for this app.

    Reads first, then the ones that need no arguments, then the shortest names.
    A 41-action vendor spec otherwise spends the whole belt on GET /health
    variants and never shows the one call the goal needs.
    """
    acts = [a for a in spec.actions if a.tier == "read" or approve_writes]
    acts.sort(key=lambda a: (a.tier != "read", len(a.required or []), len(a.slug or "")))
    return acts


def _build_belt(specs: list[Any], approve_writes: bool) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]], list[str]]:
    """One tool belt for up to five apps, dealt round-robin.

    The old belt was filled app by app and then cut at twelve, so with five apps
    the last three were unreachable: the model could not call an app that was
    not in the list, and the chain silently became a one-app run. Dealing
    round-robin guarantees every app gets its first tool before any app gets a
    second, so a five-app belt is genuinely five apps wide.
    """
    queues: list[tuple[Any, list[Any]]] = [(spec, _usable_actions(spec, approve_writes)[:TOOLS_PER_APP])
                                           for spec in specs]
    belt: list[dict[str, Any]] = []
    index: dict[str, tuple[str, str]] = {}
    starved: list[str] = [spec.slug for spec, acts in queues if not acts]
    while len(belt) < MAX_BELT_TOOLS:
        dealt = False
        for spec, acts in queues:
            if not acts or len(belt) >= MAX_BELT_TOOLS:
                continue
            action = acts.pop(0)
            tool = _tool_schema(spec.slug, action)
            name = tool["name"]
            if name in index:          # same app, two actions, same 64-char name
                continue
            belt.append({"type": "function", "function": tool})
            index[name] = (spec.slug, action.slug)
            dealt = True
        if not dealt:
            break
    return belt, index, starved


def _connect_link(spec: Any, entity: str) -> dict[str, Any]:
    """Where a human (or an agent's client) goes to unblock this app."""
    from urllib.parse import quote

    target = (f"/connect/{spec.slug}?entity_id={quote(entity)}&next=/playground"
              if spec.auth.type == "oauth2" else f"/connections?app={spec.slug}&mode=key")
    return {"app": spec.slug, "name": getattr(spec, "name", spec.slug),
            "connect_url": target, "mode": "oauth2" if spec.auth.type == "oauth2" else "key"}


@router.get("/tools/connected")
def connected_tools(request: Request, include_writes: bool = False, fmt: str = "",
                    format: str = "openai", limit: int = 2000) -> dict[str, Any]:
    """The tool belt an agent can actually use right now: live connections only."""
    from sqlalchemy import select

    from .db import session
    from .models import ConnectedAccount

    ws, _ = workspace_from_request(request)
    with session() as sx:
        live = sorted({r.app_slug for r in sx.scalars(select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == ws, ConnectedAccount.status == "active")).all()})
    if not live:
        return {"tools": [], "apps": [], "note": "No live connections yet. Mint a connect link first."}
    out = tools(request, apps=",".join(live), include_writes=include_writes,
                fmt=fmt, format=format, limit=limit)
    out["apps"] = live
    return out


META_TOOLS: list[dict[str, Any]] = [
    {
        "name": "tony_find_apps",
        "description": ("Find apps Tony can call. Use this before guessing a slug. Returns slug, name, auth "
                        "mode and action count for each match."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "What the app does, e.g. 'send email' or 'github'"},
            "limit": {"type": "number", "description": "How many results, default 10, max 50"}},
            "required": ["query"]},
        "route": {"method": "GET", "path": "/v1/apps", "query": {"q": "{{query}}", "limit": "{{limit}}"}},
    },
    {
        "name": "tony_app_actions",
        "description": ("List the callable actions of one app, with the exact action slug, HTTP verb and "
                        "required arguments. Read before calling tony_execute."),
        "parameters": {"type": "object", "properties": {
            "app": {"type": "string", "description": "App slug from tony_find_apps"},
            "query": {"type": "string", "description": "Optional filter, e.g. 'create'"}},
            "required": ["app"]},
        "route": {"method": "GET", "path": "/v1/apps/{{app}}"},
    },
    {
        "name": "tony_execute",
        "description": ("Run one action on one connected app. Tony adds the stored credentials, so the "
                        "agent never holds a provider token. Returns the provider's real response."),
        "parameters": {"type": "object", "properties": {
            "app": {"type": "string"}, "action": {"type": "string"},
            "args": {"type": "object", "description": "Action arguments"},
            "entity_id": {"type": "string", "description": "Which connected account, default 'default'"},
            "approved": {"type": "boolean", "description": "Required for write and destructive actions"},
            "dry_run": {"type": "boolean", "description": "Validate without sending"}},
            "required": ["app", "action"]},
        "route": {"method": "POST", "path": "/v1/execute", "body": {
            "app": "{{app}}", "action": "{{action}}", "args": "{{args}}",
            "entity_id": "{{entity_id}}", "dry_run": "{{dry_run}}"}},
    },
    {
        "name": "tony_chain",
        "description": (f"Run one ordered chain across up to {MAX_CHAIN_APPS} connected apps in a single call. "
                        "Each step names app, action and args; {{name.data.field}} passes an earlier step's "
                        "output forward. The whole plan is validated before anything runs, so a bad step or a "
                        "missing connection returns a clean answer instead of a half-finished side effect. "
                        "Use this when the job spans several apps."),
        "parameters": {"type": "object", "properties": {
            "apps": {"type": "array", "items": {"type": "string"},
                     "description": f"At most {MAX_CHAIN_APPS} app slugs this chain may touch"},
            "steps": {"type": "array", "description": "Ordered steps: {app, action, args, as, if, on_error}",
                      "items": {"type": "object"}},
            "entity_id": {"type": "string"},
            "approve_writes": {"type": "boolean", "description": "Required for write or destructive steps"},
            "dry_run": {"type": "boolean"},
            "on_error": {"type": "string", "enum": ["stop", "continue"]}},
            "required": ["steps"]},
        "route": {"method": "POST", "path": "/v1/chain"},
    },
    {
        "name": "tony_agent",
        "description": ("Hand Tony a goal in plain language and let it plan across apps, run the calls and "
                        "answer with a trace. Use when the sequence is not known in advance."),
        "parameters": {"type": "object", "properties": {
            "goal": {"type": "string"},
            "apps": {"type": "array", "items": {"type": "string"},
                     "description": f"Optional allow-list, at most {MAX_CHAIN_APPS} apps"},
            "entity_id": {"type": "string"},
            "approve_writes": {"type": "boolean"},
            "dry_run": {"type": "boolean"}},
            "required": ["goal"]},
        "route": {"method": "POST", "path": "/v1/agent"},
    },
]


@router.get("/tools/meta")
def meta_tools(fmt: str = "", format: str = "openai") -> dict[str, Any]:
    """Five orchestration tools instead of 40,000 action tools.

    A model handed the whole catalogue picks worse tools and burns context. These
    five let it discover an app, read its actions, call one, chain up to five,
    and hand over a goal - the same infrastructure Tony runs internally, with the
    provider credentials staying on Tony's side.
    """
    format = (fmt or format or "openai").lower()
    shaped: list[dict[str, Any]] = []
    for tool in META_TOOLS:
        if format == "anthropic":
            entry = {"name": tool["name"], "description": tool["description"],
                     "input_schema": tool["parameters"]}
        elif format == "mcp":
            entry = {"name": tool["name"], "description": tool["description"],
                     "inputSchema": tool["parameters"]}
        else:
            entry = {"type": "function", "function": {
                "name": tool["name"], "description": tool["description"],
                "parameters": tool["parameters"]}}
        entry["x-tony-route"] = tool["route"]
        shaped.append(entry)
    return {
        "format": format,
        "count": len(shaped),
        "tools": shaped,
        "base": "/v1",
        "apps_per_chain": MAX_CHAIN_APPS,
        "note": ("Call tony_find_apps, then tony_app_actions, then tony_execute or tony_chain. "
                 "An app that is not connected returns a connect_url; send the human there once and "
                 "the chain resumes unchanged. Write and destructive actions need approve_writes=true."),
    }


@router.get("/tools")
def tools(request: Request, apps: str = "", app: str = "", q: str = "", include_writes: bool = False,
          fmt: str = "", format: str = "openai", limit: int = 2000, offset: int = 0) -> dict[str, Any]:
    """Tool definitions your model can call, page by page over the whole catalogue.

    The first page used to be the whole story: a hard 2,000-tool ceiling across
    48,000 actions, so an agent never saw most of the catalogue and had no way to
    ask for the rest. Every response now carries ``total`` and ``next_offset``,
    and ``q`` ranks actions, so coverage is a paging loop, not a lottery.
    """
    format = (fmt or format or "openai").lower()
    limit = max(1, min(int(limit or 2000), 2000))
    offset = max(0, int(offset or 0))

    wanted_apps: list[str] = []
    for raw in [a for a in (apps or "").split(",") if a.strip()]:
        spec = catalog.resolve(raw.strip()) or catalog.get(raw.strip())
        if spec:
            wanted_apps.append(spec.slug)
    if app:
        spec = catalog.resolve(app.strip()) or catalog.get(app.strip())
        if spec and spec.slug not in wanted_apps:
            wanted_apps.append(spec.slug)

    query = (q or "").strip().lower()

    def _rank(spec: Any) -> tuple[int, str]:
        order = {"actions": 0, "proxy": 1, "directory": 2}
        return (order.get(spec.tier, 3), spec.slug)

    if wanted_apps:
        specs = [catalog.resolve(s) or catalog.get(s) for s in wanted_apps]
        specs = [s for s in specs if s]
    elif query:
        from .search import find_apps
        specs = [catalog.resolve(hit["slug"]) or catalog.get(hit["slug"]) for hit in find_apps(query, limit=40)]
        specs = [s for s in specs if s]
    else:
        specs = sorted(catalog.apps.values(), key=_rank)

    matched: list[tuple[str, Any]] = []
    for spec in specs:
        for action in spec.actions:
            if action.tier != "read" and not include_writes:
                continue
            if query and not wanted_apps:
                hay = f"{spec.slug} {spec.name} {action.slug} {action.name} {action.description}".lower()
                if not all(word in hay for word in query.split()):
                    continue
            matched.append((spec.slug, action))

    total = len(matched)
    window = matched[offset: offset + limit]
    shaped_tools = []
    for app_slug, action in window:
        t = _tool_schema(app_slug, action)
        if format == "anthropic":
            shaped_tools.append({"name": t["name"], "description": t["description"], "input_schema": t["parameters"]})
        elif format == "mcp":
            shaped_tools.append({"name": t["name"], "description": t["description"], "inputSchema": t["parameters"]})
        else:
            shaped_tools.append({"type": "function", "function": t})

    seen: list[str] = []
    for app_slug, _action in window:
        if app_slug not in seen:
            seen.append(app_slug)
    next_offset = offset + len(window)
    return {
        "format": format,
        "count": len(shaped_tools),
        "tools": shaped_tools,
        "total": total,
        "offset": offset,
        "limit": limit,
        "max_limit": 2000,
        "has_more": next_offset < total,
        "next_offset": next_offset if next_offset < total else None,
        "has_more": next_offset < total,
        "next_offset": next_offset if next_offset < total else None,
        "apps_in_page": seen,
        "apps_total": len(catalog.apps),
        "actions_total": sum(len(a.actions) for a in catalog.apps.values()),
        "note": ("Walk offsets until has_more is false to see every tool. "
                 "Send the call back to POST /v1/execute, or POST /v1/agent with the same goal."),
    }


# ── agent runtime ─────────────────────────────────────────────────────────
class AgentIn(BaseModel):
    """A goal, plus the scope the caller is willing to grant.

    ``apps`` names up to ``MAX_CHAIN_APPS`` apps to chain; leave it empty and
    Tony ranks the catalogue itself. ``max_steps`` counts model turns, not app
    calls, so one turn that fires three tool calls still counts once.
    """
    goal: str
    apps: list[str] = Field(default_factory=list)
    entity_id: str = "default"
    max_steps: int = 10
    approve_writes: bool = False
    dry_run: bool = False
    history: list[dict[str, str]] = Field(default_factory=list)


DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
# Groq's free tier rate-limits per model, and a retired model is a 404 rather than an
# error the caller can see. A ladder of live models turns both into a fall-through.
DEFAULT_GROQ_LADDER = ("openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b")
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"


def _llm_targets(fast: bool = False) -> list[tuple[str, str, dict[str, str]]]:
    """Every usable model endpoint, strongest first. Providers retire models, so the
    chain is a list and a 404 on one model falls through to the next instead of
    silently dropping to the deterministic path."""
    out: list[tuple[str, str, dict[str, str]]] = []
    groq = os.getenv("GROQ_API_KEY", "").strip()
    fast_model = os.getenv("TONY_FAST_MODEL", DEFAULT_GROQ_LADDER[0])
    if groq:
        models = [m.strip() for m in (os.getenv("TONY_GROQ_MODELS") or "").split(",") if m.strip()]
        if not models:
            models = list(DEFAULT_GROQ_LADDER)
            agent_model = os.getenv("TONY_AGENT_MODEL", "").strip()
            if agent_model and agent_model not in models:
                models.append(agent_model)
        if fast:
            models = [fast_model] + [m for m in models if m != fast_model]
        for model in models:
            out.append(("https://api.groq.com/openai/v1/chat/completions", model,
                        {"Authorization": f"Bearer {groq}"}))
    if os.getenv("OPENAI_API_KEY"):
        out.append(("https://api.openai.com/v1/chat/completions",
                    os.getenv("TONY_AGENT_MODEL", "gpt-4o-mini"),
                    {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}))
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if or_key:
        out.append(("https://openrouter.ai/api/v1/chat/completions",
                    os.getenv("TONY_AGENT_MODEL", DEFAULT_OPENROUTER_MODEL),
                    {"Authorization": f"Bearer {or_key}", "HTTP-Referer": "https://tony-7su0.onrender.com",
                     "X-Title": "Tony"}))
    seen, uniq = set(), []
    for target in out:
        key = (target[0], target[1])
        if key not in seen:
            seen.add(key)
            uniq.append(target)
    return uniq


def _llm_target() -> tuple[str, str, dict[str, str]] | None:
    chain = _llm_targets()
    return chain[0] if chain else None


def _retry_after_seconds(resp: Any) -> float | None:
    """The provider's own advice on when to come back, in seconds."""
    raw = (resp.headers.get("retry-after") or "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    try:
        body = resp.json()
    except Exception:
        return None
    text = str(body.get("error", {}).get("message", "")) if isinstance(body, dict) else ""
    m = re.search(r"try again in ([0-9.]+)\s*(ms|s)", text, re.I)
    if not m:
        return None
    value = float(m.group(1))
    return value / 1000 if m.group(2).lower() == "ms" else value


async def _chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                temperature: float = 0.2, fast: bool = False) -> dict[str, Any] | None:
    """Ask the model with the whole configured chain. A retired model, a rate limit
    or a bad key walks to the next provider; the caller only sees None when all fail."""
    chain = _llm_targets(fast=fast)
    if not chain:
        return None
    for url, model, hdr in chain:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature,
                                   "max_tokens": 700 if not tools else 900}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                for attempt in range(2):
                    r = await c.post(url, json=payload, headers={**hdr, "Content-Type": "application/json"})
                    if r.status_code == 429 and attempt == 0:
                        wait = _retry_after_seconds(r)
                        if wait is not None and wait <= 3.0:
                            await asyncio.sleep(wait)
                            continue
                    break
                if r.status_code >= 400:
                    continue
                return r.json()["choices"][0]["message"]
        except Exception:
            continue
    return None


STOPWORDS = {"the", "and", "for", "with", "from", "this", "that", "into", "then", "right", "now", "please",
             "can", "you", "get", "give", "show", "make", "let", "about", "what", "which", "how", "all", "any",
             "top", "best", "summary", "summarize", "summarise", "list"}


# Plain-language words people use that never appear in an app's name. Without this,
# "price of bitcoin" matched a VTEX pricing API instead of CoinGecko.
INTENT_ALIASES: dict[str, tuple[str, ...]] = {
    "bitcoin": ("coinbase", "coingecko"), "btc": ("coinbase", "coingecko"),
    "ethereum": ("coinbase", "coingecko"), "eth": ("coinbase", "coingecko"),
    "crypto": ("coinbase", "coingecko"), "cryptocurrency": ("coinbase", "coingecko"),
    "coin": ("coinbase", "coingecko"), "price": ("coinbase", "coingecko"),
    "email": ("gmail",), "emails": ("gmail",), "inbox": ("gmail",), "mail": ("gmail",),
    "calendar": ("google_calendar",), "meeting": ("google_calendar",), "meetings": ("google_calendar",),
    "schedule": ("google_calendar",), "events": ("google_calendar",),
    "repo": ("github",), "repos": ("github",), "repository": ("github",), "commits": ("github",),
    "pull": ("github",), "issues": ("github", "linear"),
    "slack": ("slack",), "channel": ("slack",),
    "news": ("hackernews", "gnews"), "headlines": ("gnews",), "stories": ("hackernews",),
    "spreadsheet": ("google_sheets",), "sheet": ("google_sheets",), "sheets": ("google_sheets",),
    "drive": ("google_drive",), "files": ("google_drive", "dropbox"),
    "stock": ("alpha_vantage", "finnhub"), "stocks": ("alpha_vantage", "finnhub"),
    "weather": ("open_meteo", "openweathermap"), "temperature": ("open_meteo",),
    "forecast": ("open_meteo", "openweathermap"),
    "currency": ("exchangerate", "exchangerate-api"), "convert": ("exchangerate",),
    "exchange": ("exchangerate",), "rate": ("exchangerate", "exchangerate-api"),
    "naira": ("exchangerate",), "usd": ("exchangerate",), "dollar": ("exchangerate",),
    "paper": ("arxiv",), "papers": ("arxiv",),
    "tweet": ("x",), "tweets": ("x",), "notion": ("notion",), "page": ("notion",),
    "payment": ("stripe", "flutterwave"), "payments": ("stripe", "flutterwave"),
    "invoice": ("stripe",), "customers": ("stripe",), "ticket": ("linear",),
}


def _alias_bonus(goal: str, slug: str) -> float:
    toks = set(re.findall(r"[a-z0-9]{2,}", goal.lower()))
    return 14.0 if any(slug in INTENT_ALIASES.get(t, ()) for t in toks) else 0.0


def _score_app(goal: str, spec: Any) -> float:
    """How well an app fits the goal.

    Name and slug evidence outweighs description text, and action matches are
    capped, because a 900-action cloud API used to win on volume alone even when
    the user clearly asked for something like Hacker News.
    """
    words = {w for w in re.findall(r"[a-z0-9]{3,}", goal.lower()) if w not in STOPWORDS}
    if not words:
        return 0.0
    slug = spec.slug.lower()
    name = (spec.name or "").lower()
    name_tokens = set(re.findall(r"[a-z0-9]{3,}", f"{slug} {name}"))
    desc = (spec.description or "").lower()
    cat = (spec.category or "").lower()
    score = 0.0
    for w in words:
        if w in name_tokens:
            score += 12
        elif w in slug or w in name:
            score += 6
        elif w in desc:
            score += 3
        elif w in cat:
            score += 2
    hits = 0
    if getattr(getattr(spec, "auth", None), "type", "") == "none":
        score += 8            # works immediately: no key, no connect step
    for a in spec.actions[:400]:
        hay = f"{a.slug} {a.name}".lower()
        if any(w in hay for w in words):
            hits += 1
            if hits >= 8:
                break
    score += hits * 0.6
    if getattr(spec, "source", "") == "curated":
        score += 4
    score += _alias_bonus(goal, spec.slug)
    score -= min(len(slug) * 0.05, 3)   # long generated slugs lose ties to real names
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
    spec = catalog.get(app_slug) or catalog.resolve(app_slug)
    if not spec:
        return {"ok": False, "error": "unknown app"}
    # the same product ships twice in the catalog (curated + generated twin); if the
    # twin we were handed cannot run, fall through to the canonical one
    twin = catalog.resolve(spec.slug)
    if twin is not None and twin.slug != spec.slug:
        if spec.auth.type != "none" and credentials_for(ws, entity, spec) is None:
            spec = twin
    action = None
    if action_slug:
        action = next((a for a in spec.actions if a.slug == action_slug or a.name == action_slug), None)
    action = action or _best_action("", spec)
    if action is None:
        return {"ok": False, "error": "no actions"}
    creds = credentials_for(ws, entity, spec)
    if spec.auth.type != "none" and creds is None and not action.public:
        link = _connect_link(spec, entity)
        return {"ok": False, "app": spec.slug, "action": action.slug,
                "error": f"{spec.name} is not connected",
                "needs_connection": spec.slug,
                "connect_url": link["connect_url"],
                "connect_mode": link["mode"]}
    check_run(ws)
    started = time.perf_counter()
    status, code, error, body = "error", 0, "", None
    try:
        try:
            result = await asyncio.wait_for(execute(spec, action, args or {}, creds, dry_run=dry_run), timeout=30)
        except Exception as first:  # noqa: BLE001
            # Self-heal: an LLM often invents an argument the action does not take.
            # Drop exactly the rejected keys and try once more before giving up.
            bad = re.search(r"Unknown argument\(s\): ([^.]+)\.", str(first))
            if not (bad and args):
                raise
            drop = {k.strip() for k in bad.group(1).split(",")}
            cleaned = {k: v for k, v in args.items() if k not in drop}
            result = await asyncio.wait_for(execute(spec, action, cleaned, creds, dry_run=dry_run), timeout=30)
            args = cleaned
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
    """Shrink a tool result so it fits a context window. Never raises."""
    try:
        blob = json.dumps(data, default=str)
    except Exception:
        blob = str(data)
    if len(blob) <= MAX_TOOL_RESULT_CHARS:
        return data
    return {"truncated": True, "chars": len(blob), "preview": blob[:MAX_TOOL_RESULT_CHARS]}


def _raw_items(step: dict[str, Any]) -> list[Any]:
    data = (step.get("data") or {})
    inner = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(inner, dict):
        for key in ("items", "results", "data", "stories"):
            if isinstance(inner.get(key), list):
                return inner[key]
        return []
    return inner if isinstance(inner, list) else []


def _items_of(step: dict[str, Any]) -> list[dict[str, Any]]:
    return [x for x in _raw_items(step) if isinstance(x, dict)]


def _headline(item: dict[str, Any]) -> str:
    for key in ("title", "name", "description", "login", "full_name", "subject", "text"):
        if item.get(key):
            return str(item[key])[:140]
    return ""


def _flat(d: Any, prefix: str = "", out: list[str] | None = None, depth: int = 0) -> list[str]:
    """Render nested data as short 'key: value' lines a person can read."""
    out = [] if out is None else out
    if len(out) >= 10 or depth > 3:
        return out
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)) and depth < 3:
                if isinstance(v, list) and v and not isinstance(v[0], (dict, list)):
                    out.append(f"{prefix}{k}: " + ", ".join(str(x) for x in v[:5]))
                else:
                    _flat(v, f"{prefix}{k} / ", out, depth + 1)
            elif v not in (None, "", [], {}):
                out.append(f"{prefix}{k}: {str(v)[:100]}")
            if len(out) >= 10:
                break
    return out


def _app_line(slug: str, step: dict[str, Any]) -> list[str]:
    """One app's contribution to a multi-app answer: a name and a real value."""
    items = _items_of(step)
    raw = _raw_items(step)
    inner = (step.get("data") or {})
    if isinstance(inner, dict) and isinstance(inner.get("data"), dict):
        inner = inner["data"]
    if items:
        head = _headline(items[0])
        return [f"• {slug}: {head}" if head else f"• {slug}: {len(items)} result(s)"]
    if raw and isinstance(raw[0], (int, str, float)):
        return [f"• {slug}: {len(raw)} item(s), first {raw[0]}"[:200]]
    if isinstance(inner, dict):
        for key, value in inner.items():
            if isinstance(value, (str, int, float)) and value not in ("", None):
                return [f"• {slug}: {key} {str(value)[:80]}"]
        head = _headline(inner)
        if head:
            return [f"• {slug}: {head}"]
    return [f"• {slug}: {step.get('action')} ran in {step.get('latency_ms', 0)} ms"]


def _summarise(goal: str, steps: list[dict[str, Any]]) -> str:
    good = [s for s in steps if s.get("ok")]
    if not good:
        err = steps[-1].get("error") if steps else "nothing ran"
        return (f"I could not finish that: {err}. The plan is still on record, so you can retry with a "
                f"connected app or a narrower goal.")

    # A chain that touched several apps must show several apps. Picking only the
    # fattest step made a five-app run read like a one-app run.
    apps: list[str] = []
    for step in good:
        if step.get("app") and step["app"] not in apps:
            apps.append(step["app"])
    if len(apps) > 1:
        lines = []
        for slug in apps:
            mine = [st for st in good if st.get("app") == slug]
            best = max(mine, key=lambda st: (len(_items_of(st)),
                                             len(json.dumps(st.get("data"), default=str))))
            lines.extend(_app_line(slug, best))
        if lines:
            return "\n".join(lines[:10])

    # prefer the step that returned the most useful data
    last = max(good, key=lambda s: (len(_items_of(s)), len(json.dumps(s.get("data"), default=str))))
    lines: list[str] = []
    items = _items_of(last)
    raw = _raw_items(last)
    if items:
        lines.append(f"Here are {min(len(items), 5)} result(s) from {last['app']}:")
        for item in items[:5]:
            head = _headline(item)
            if head:
                lines.append(f"• {head}")
    elif raw and isinstance(raw[0], (int, str, float)):
        lines.append(f"{last['app']} returned {len(raw)} ids; first is {raw[0]}.")
    else:
        inner = (last.get("data") or {}).get("data", last.get("data"))
        if isinstance(inner, dict):
            head = _headline(inner)
            if head:
                lines.append(f"• {head}")
            lines.extend(_flat({k: v for k, v in inner.items() if k not in ("title", "name")}))
    if not lines:
        lines.append(f"{last['app']}.{last['action']} ran successfully in {last.get('latency_ms', 0)} ms.")
    return "\n".join(lines)


@router.get("/llm/health")
async def llm_health() -> dict[str, Any]:
    """Which model endpoints this process can actually reach right now."""
    chain = _llm_targets()
    rows = []
    for url, model, hdr in chain:
        row = {"provider": url.split("/")[2], "model": model, "ok": False, "status": 0, "error": ""}
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.post(url, json={"model": model, "messages": [{"role": "user", "content": "reply ok"}],
                                            "max_tokens": 8}, headers={**hdr, "Content-Type": "application/json"})
                row["status"] = r.status_code
                row["ok"] = r.status_code < 400
                if not row["ok"]:
                    row["error"] = r.text[:220]
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"{type(exc).__name__}: {exc}"[:220]
        rows.append(row)
    return {"targets": rows}


GREETING = re.compile(
    r"^(hi|hey|hello|yo|sup|hiya|good (morning|afternoon|evening)|thanks|thank you|ok|okay|nice|cool)"
    r"[\s!.,?]*$", re.I)


async def _direct_answer(goal: str, history: list[dict[str, str]] | None = None) -> str:
    """Answer without touching an app. Tony is a general assistant first: conversation,
    explanations, drafts and small talk all belong here, not in a tool loop."""
    system = ("You are Tony, a friendly, capable assistant. Answer the person directly and usefully. "
              "For small talk, be warm and brief (one or two sentences) and offer a concrete thing you can do next. "
              "For explanations, code, drafts or planning, just do the work well. Never say you cannot help with "
              "something unless it truly needs a connected app; in that case name the app (for example gmail or "
              "github) and say what pressing Connect unlocks. No markdown headings.")
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for turn in (history or [])[-6:]:
        if turn.get("role") in {"user", "assistant"} and turn.get("content"):
            msgs.append({"role": turn["role"], "content": str(turn["content"])[:1500]})
    msgs.append({"role": "user", "content": goal})
    reply = await _chat(msgs, None, temperature=0.5, fast=True)
    if reply is None:
        return ("I'm here. Tell me what you want done - today's news, a draft, a repo lookup, "
                "or anything about connecting an app - and I'll take it from there.")
    content = (reply.get("content") or "").strip()
    if content:
        return content
    return ("I'm here and ready. Give me a goal like 'summarise Hacker News' or ask me anything about "
            "APIs, keys or OAuth.")


@router.post("/agent")
async def agent(body: AgentIn, request: Request) -> dict[str, Any]:
    """Give Tony a goal. It plans, calls real apps, and answers with receipts."""
    ws, _ = workspace_from_request(request)
    return await run_agent(ws, body)


async def run_agent(ws: str, body: AgentIn) -> dict[str, Any]:
    """The same execution path, addressable without a signed request (used by resume)."""
    goal = (body.goal or "").strip()
    if not goal:
        raise HTTPException(400, detail="Tell me what to do, e.g. {'goal': 'latest hacker news'}")

    rate_limit(f"ws:{ws}", rate_for(ws))
    entity = _entity(ws, body.entity_id)
    steps: list[dict[str, Any]] = []
    started = time.perf_counter()

    # 0. conversation, questions and writing need no app at all
    if not body.apps and (GREETING.match(goal) or len(goal.split()) <= 3 and goal.endswith("?")):
        text = await _direct_answer(goal, body.history)
        return {"answer": text, "steps": [], "engine": "chat",
                "elapsed_ms": int((time.perf_counter() - started) * 1000)}

    # 1. choose candidate apps
    unknown_apps: list[str] = []
    if body.apps:
        specs = _pick_apps(body.apps)
        unknown_apps = [a for a in body.apps
                        if str(a).strip() and not (catalog.resolve(str(a).strip()) or catalog.get(str(a).strip()))]
    else:
        ranked = sorted(catalog.apps.values(),
                        key=lambda s: (_score_app(goal, s), -len(s.slug)), reverse=True)
        specs, seen = [], set()
        for cand in ranked[:14]:
            if _score_app(goal, cand) < 6:
                break
            canon = catalog.resolve(cand.slug) or cand     # skip empty duplicate twins
            if canon.slug in seen:
                continue
            seen.add(canon.slug)
            specs.append(canon)
            if len(specs) >= MAX_CHAIN_APPS:
                break
        if not specs:
            text = await _direct_answer(goal, body.history)
            return {"answer": text, "steps": [],
                    "elapsed_ms": int((time.perf_counter() - started) * 1000), "engine": "chat"}
    if not specs:
        text = await _direct_answer(goal, body.history)
        return {"answer": text, "steps": [],
                "elapsed_ms": int((time.perf_counter() - started) * 1000), "engine": "chat"}

    # 2. build the tool belt, wide enough for every app in the chain
    blocked: list[dict[str, Any]] = []
    runnable: list[Any] = []
    for spec in specs:
        if (spec.auth.type != "none" and credentials_for(ws, entity, spec) is None
                and not any(a.public for a in spec.actions)):
            blocked.append(_connect_link(spec, entity))
        else:
            runnable.append(spec)
    # if nothing is connected yet, keep the belt intact so each call comes back
    # carrying its own connect link rather than a vague "not connected"
    belt_specs = runnable or specs
    belt, index, starved = _build_belt(belt_specs, body.approve_writes)

    # 3. run the loop
    engine = "heuristic"
    answer = ""
    messages: list[dict[str, Any]] = [{
        "role": "system",
        "content": ("You are Tony, an execution agent with real hands on real apps and a competent general "
                    "assistant. Useful beats cautious: answer the goal, or do the work with tools, or both. "
                    "Rules: never invent data, ids or results - anything factual about an app comes from a tool "
                    "return. If a goal is a question you can answer from knowledge or from what tools already "
                    "returned, answer it directly instead of searching for a tool. But never report data as "
                    "missing or unavailable when a tool in your belt can fetch it - call that tool instead, "
                    "and keep going until the goal is actually satisfied. Bare ids, urls or keys are a step, "
                    "not an answer. If a tool errors, read the "
                    "error, adjust, and retry at most twice before explaining the blocker. Prefer the fewest calls "
                    "that satisfy the goal. If the goal needs a write and writes are not approved, name the exact "
                    "app.action and the arguments you would send, then stop. You may also draft, rewrite, plan or "
                    "explain when that is what was asked. You may chain across every app in your belt: "
                    "one app's output is the next app's argument, and a tool name is prefixed with [app] so "
                    "you always know which app you are calling. If one app fails or is not connected, keep "
                    "working the rest of the plan and say which app blocked. "
                    "Lead with the answer, then the evidence that supports it; "
                    "under 200 words; no markdown headings."),
    }, {"role": "user", "content": goal}]
    for turn in (body.history or [])[-4:]:
        messages.insert(-1, {"role": turn.get("role", "user"), "content": turn.get("content", "")})

    if belt:
        budget = max(1, min(body.max_steps, MAX_STEPS_CAP))
        for _ in range(budget):
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

    # 3b. a plan that stalled on a bare id/url list is unfinished: fetch the detail
    stalled = bool(steps) and bool(steps[-1].get("ok")) and not _items_of(steps[-1]) \
        and bool(_raw_items(steps[-1]))
    if engine == "llm" and stalled and body.max_steps > 1 and answer:
        answer = ""

    if (engine == "heuristic" or engine == "llm") and steps and steps[0].get("ok") and body.max_steps > 1:
        first = steps[0]
        spec = next((x for x in specs if x.slug == first["app"]), specs[0])
        items = _items_of(first)
        raw = _raw_items(first)
        values: list[Any] = []
        if items:
            id_key = next((k for k in ("id", "key", "uuid", "number") if items[0].get(k) is not None), "")
            if id_key:
                values = [i.get(id_key) for i in items if i.get(id_key) not in (None, "")]
        elif raw and isinstance(raw[0], (int, str, float)):
            values = list(raw)
        # with several apps in play, one detail fetch per app is plenty; five is
        # for a single-app list where the ids are the whole answer
        values = [v for v in values if v not in (None, "")][: 2 if len(specs) > 2 else 5]
        if values:
            follow = next((a for a in spec.actions
                           if a.tier == "read" and a.slug != first["action"]
                           and len(a.required or []) == 1
                           and "random" not in (a.url or "")), None)
            if follow is not None:
                # A ranked id list is a step, not an answer: fetch detail for each id so
                # the reply can name every item instead of printing bare numbers.
                for value in values:
                    if any(st.get("action") == follow.slug and
                           json.dumps(st.get("args") or {}) != "{}" and
                           str(value) in json.dumps(st.get("args") or {}, default=str) for st in steps[1:]):
                        continue
                    steps.append(await _run_one(ws, entity, spec.slug, follow.slug,
                                                {follow.required[0]: value}, body.dry_run))

    # 3c. answer from the full evidence trail, not from a half-finished plan
    if not answer and engine == "llm" and steps:
        synthesis = messages + [{
            "role": "user",
            "content": ("Stop calling tools. Using only the tool results above, answer the original goal in "
                        "under 120 words. Lead with the answer, then the specific evidence (titles, numbers, "
                        "ids) that supports it. If something failed, say which part and what it means."),
        }]
        final = await _chat(synthesis, None, temperature=0.3, fast=True)
        if not (final and (final.get("content") or "").strip()):
            final = await _chat(synthesis, None, temperature=0.3, fast=False)
        if final and (final.get("content") or "").strip():
            answer = final["content"].strip()

    if not answer:
        answer = _summarise(goal, steps)

    # hand the client everything it needs to finish the job: which app, and the
    # exact link that starts one-click sign-in, so it can resume automatically
    missing: list[dict[str, Any]] = []
    seen: set[str] = set()
    for st in steps:
        slug = st.get("needs_connection")
        if slug and slug not in seen:
            seen.add(slug)
            spec = catalog.resolve(slug) or catalog.get(slug)
            missing.append({
                "app": slug,
                "name": getattr(spec, "name", slug),
                "connect_url": st.get("connect_url", f"/connect/{slug}"),
                "mode": st.get("connect_mode", "oauth2"),
            })
    for entry in blocked:
        if entry["app"] not in seen:
            seen.add(entry["app"])
            missing.append(entry)
    elapsed = int((time.perf_counter() - started) * 1000)
    attempted = [st.get("app") for st in steps if st.get("app")]
    return {
        "answer": answer,
        "steps": steps,
        "needs_connection": missing,
        "resume_after_connect": bool(missing),
        "apps_considered": [s.slug for s in specs],
        "apps_used": sorted({a for a in attempted}),
        "apps_chain_limit": MAX_CHAIN_APPS,
        "apps_blocked": [b["app"] for b in blocked],
        "apps_without_tools": starved,
        "unknown_apps": unknown_apps,
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
