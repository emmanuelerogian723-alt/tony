"""Cross-app chains: one call, up to five connected apps, in order.

An AI agent should not have to babysit Tony call by call. This endpoint hands it
the whole infrastructure in one request:

    POST /v1/chain
    {"apps": ["gmail", "notion", "slack"],
     "steps": [
        {"app": "gmail", "action": "search_emails", "args": {"query": "invoice"}, "as": "mail"},
        {"app": "notion", "action": "create_page",
         "args": {"title": "Invoice digest", "content": "{{mail.data.0.snippet}}"}, "as": "page"},
        {"app": "slack", "action": "post_message", "args": {"text": "{{page.data.url}}"}}
     ]}

Guarantees, because an agent cannot debug a half-finished side effect:

* **Plan checked before anything runs.** Every app, action and argument is
  resolved first. A typo or a missing connection returns one clean answer with
  the connect link, and nothing has been sent to a provider.
* **Five apps, not fifty.** A chain names at most ``MAX_APPS`` distinct apps.
  Anything wider is a workflow, not a chain, and is refused with the count.
* **No blind retries.** Reads retry on network/5xx/429 with backoff. Writes are
  never retried, so a chain cannot double-send an email.
* **Failure is reported, not hidden.** ``on_error: stop`` (default) halts at the
  first failure and returns the partial trace; ``continue`` keeps going and
  marks the step. Either way every step carries app, action, latency and error.
* **Outputs flow forward.** ``{{name.data.items.0.id}}`` reaches into an earlier
  step's real response; a lone placeholder keeps its JSON type.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import __version__
from .auth import rate_limit, workspace_from_request
from .billing import check_run, rate_for
from .catalog import catalog
from .db import session
from .executor import execute
from .models import ActionRun
from .oauth import credentials_for
from .runtime import backoff, classify, is_retryable

router = APIRouter(prefix="/v1", tags=["chain"])

MAX_APPS = 5
MAX_STEPS = 25
DEFAULT_TIMEOUT = 30.0
PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
SECRETISH = ("password", "secret", "token", "api_key", "apikey", "authorization", "cookie")


class ChainStep(BaseModel):
    app: str = ""
    action: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    as_: str = Field("", alias="as")
    if_: str = Field("", alias="if")
    on_error: str = ""
    timeout_s: float = 0.0

    model_config = {"populate_by_name": True}


class ChainIn(BaseModel):
    steps: list[ChainStep] = Field(default_factory=list)
    apps: list[str] = Field(default_factory=list)
    entity_id: str = "default"
    dry_run: bool = False
    approve_writes: bool = False
    on_error: str = "stop"
    require_all_connected: bool = True
    include_results: bool = True


# ── templating ────────────────────────────────────────────────────────────
def _lookup(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for part in [p for p in path.strip().split(".") if p]:
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return ""
        elif isinstance(cur, dict):
            if part not in cur:
                return ""
            cur = cur[part]
        else:
            return ""
        if cur is None:
            return ""
    return cur


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, default=str)
        except Exception:
            return str(value)
    return str(value)


def render(value: Any, ctx: dict[str, Any]) -> Any:
    """Substitute ``{{path}}``. A lone placeholder keeps its real type."""
    if isinstance(value, str):
        lone = PLACEHOLDER.fullmatch(value.strip())
        if lone:
            return _lookup(ctx, lone.group(1))
        return PLACEHOLDER.sub(lambda m: _text(_lookup(ctx, m.group(1))), value)
    if isinstance(value, dict):
        return {k: render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, ctx) for v in value]
    return value


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", 0, [], {}):
        return False
    return str(value).strip().lower() not in {"false", "0", "no", "none", "null"}


def _redact(args: Any) -> Any:
    if not isinstance(args, dict):
        return args
    out = {}
    for key, value in args.items():
        out[key] = "***" if any(s in str(key).lower() for s in SECRETISH) else value
    return out


# ── plan resolution, before any provider is touched ───────────────────────
def _resolve_app(name: str) -> Any | None:
    key = (name or "").strip()
    if not key:
        return None
    return catalog.resolve(key) or catalog.get(key)


def _resolve_action(spec: Any, action: str) -> Any | None:
    want = (action or "").strip()
    if not want:
        return None
    if "." in want:
        want = want.rsplit(".", 1)[-1]
    return next((a for a in spec.actions
                 if a.slug == want or a.name == want or a.slug.lower() == want.lower()), None)


def _suggest(spec: Any, action: str, limit: int = 5) -> list[str]:
    words = {w for w in re.findall(r"[a-z]{3,}", (action or "").lower())}
    scored = []
    for a in spec.actions:
        hay = f"{a.slug} {a.name}".lower()
        score = sum(1 for w in words if w in hay)
        if score:
            scored.append((score, a.slug))
    scored.sort(reverse=True)
    return [slug for _s, slug in scored[:limit]]


def _connect_link(spec: Any, entity: str) -> dict[str, Any]:
    from urllib.parse import quote

    link = (f"/connect/{spec.slug}?entity_id={quote(entity)}&next=/playground"
            if spec.auth.type == "oauth2" else f"/connections?app={spec.slug}&mode=key")
    return {"app": spec.slug, "name": getattr(spec, "name", spec.slug),
            "connect_url": link, "mode": "oauth2" if spec.auth.type == "oauth2" else "key"}


def plan(body: ChainIn) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve every step to a real app and action. Raises 400 on anything wrong."""
    if not body.steps:
        raise HTTPException(400, detail=(
            "A chain needs steps. Example: {\"apps\": [\"gmail\",\"notion\"], \"steps\": "
            "[{\"app\":\"gmail\",\"action\":\"search_emails\",\"args\":{\"query\":\"invoice\"},\"as\":\"mail\"},"
            "{\"app\":\"notion\",\"action\":\"create_page\",\"args\":{\"title\":\"{{mail.data.0.subject}}\"}}]}"))
    if len(body.steps) > MAX_STEPS:
        raise HTTPException(400, detail=f"A chain runs at most {MAX_STEPS} steps, got {len(body.steps)}.")

    # breadth first: an over-wide chain is refused before any action lookup,
    # because the answer is the same whatever those actions turn out to be
    specs: list[Any] = []
    used: list[str] = []
    for index, step in enumerate(body.steps):
        spec = _resolve_app(step.app)
        if spec is None:
            raise HTTPException(400, detail={
                "error": f"Step {index}: unknown app '{step.app}'.",
                "hint": "Search apps with GET /v1/apps?q=...",
            })
        specs.append(spec)
        if spec.slug not in used:
            used.append(spec.slug)

    names = set(used) | {str(n).strip() for n in (body.apps or []) if str(n).strip()}
    if len(names) > MAX_APPS:
        raise HTTPException(400, detail={
            "error": f"A chain spans at most {MAX_APPS} apps; this one names {len(names)}.",
            "apps": sorted(names),
            "hint": "Split it into two chains, or use POST /v1/flows for a durable longer workflow.",
        })

    planned: list[dict[str, Any]] = []
    for index, step in enumerate(body.steps):
        spec = specs[index]
        action = _resolve_action(spec, step.action)
        if action is None:
            raise HTTPException(400, detail={
                "error": f"Step {index}: {spec.name} has no action '{step.action}'.",
                "suggestions": _suggest(spec, step.action),
                "hint": f"List actions with GET /v1/apps/{spec.slug}",
            })
        planned.append({"index": index, "spec": spec, "action": action, "raw": step,
                        "name": (step.as_ or f"step{index}").strip()})
    return planned, used


def missing_connections(ws: str, entity: str, used: list[str]) -> list[dict[str, Any]]:
    """Every app in the chain that cannot run yet, with its connect link."""
    out: list[dict[str, Any]] = []
    for slug in used:
        spec = catalog.get(slug) or catalog.resolve(slug)
        if spec is None or spec.auth.type == "none":
            continue
        if credentials_for(ws, entity, spec) is not None:
            continue
        if spec.actions and all(a.public for a in spec.actions):
            continue
        out.append(_connect_link(spec, entity))
    return out


# ── step execution ────────────────────────────────────────────────────────
def _record(ws: str, entity: str, spec: Any, action: Any, error: str, latency: int,
            status: int = 0, args: Any = None, body: str = "") -> None:
    try:
        with session() as s:
            s.add(ActionRun(workspace_id=ws, entity_id=entity, app_slug=spec.slug,
                            action_slug=action.slug, tier=action.tier,
                            status="success" if not error else "error", status_code=status,
                            latency_ms=latency, chars_out=len(body or ""),
                            request_json=json.dumps(_redact(args or {}), default=str)[:2000],
                            response_json=(body or "")[:4000], error=error))
            s.commit()
    except Exception:
        pass


async def run_step(ws: str, entity: str, planned: dict[str, Any], args: dict[str, Any],
                   dry_run: bool, approve_writes: bool) -> dict[str, Any]:
    spec, action, name = planned["spec"], planned["action"], planned["name"]
    base = {"step": planned["index"], "as": name, "app": spec.slug, "action": action.slug,
            "tier": action.tier, "args": _redact(args)}

    if action.tier != "read" and not approve_writes:
        return {**base, "ok": False, "skipped": True, "attempts": 0,
                "error": f"{action.tier} action needs approve_writes=true",
                "hint": "Re-send with approve_writes=true to let the chain write."}

    creds = credentials_for(ws, entity, spec)
    if spec.auth.type != "none" and creds is None and not action.public:
        link = _connect_link(spec, entity)
        return {**base, "ok": False, "attempts": 0, "error": f"{spec.name} is not connected",
                "needs_connection": spec.slug, "connect_url": link["connect_url"],
                "connect_mode": link["mode"]}

    check_run(ws)
    timeout = planned["raw"].timeout_s or DEFAULT_TIMEOUT
    started = time.perf_counter()
    attempts, last_error, kind = 0, "", ""

    while attempts < 3:
        attempts += 1
        try:
            result = await asyncio.wait_for(execute(spec, action, args or {}, creds, dry_run=dry_run),
                                            timeout=timeout)
        except asyncio.TimeoutError:
            last_error, kind = f"{spec.slug}.{action.slug} exceeded {timeout:g}s", "network"
        except Exception as exc:  # noqa: BLE001 - a chain reports, never crashes
            message = f"{type(exc).__name__}: {exc}"
            bad = re.search(r"Unknown argument\(s\): ([^.]+)\.", message)
            if bad and args and attempts < 3:
                drop = {k.strip() for k in bad.group(1).split(",")}
                args = {k: v for k, v in args.items() if k not in drop}
                base["args"] = _redact(args)
                base["note"] = f"dropped unsupported argument(s): {', '.join(sorted(drop))}"
                continue
            last_error, kind = message[:400], classify(0, message)
        else:
            latency = int((time.perf_counter() - started) * 1000)
            if result.ok:
                _record(ws, entity, spec, action, "", latency, result.status, args,
                        json.dumps(result.data, default=str) if result.data is not None else "")
                row = {**base, "ok": True, "attempts": attempts, "latency_ms": latency,
                       "status_code": result.status}
                if result.data is not None:
                    row["data"] = result.data
                if result.meta:
                    row["meta"] = result.meta
                return row
            last_error = (result.error or "provider error")[:400]
            kind = classify(result.status, last_error)

        if attempts < 3 and is_retryable(kind, method=action.method):
            await asyncio.sleep(backoff(attempts))
            continue
        break

    latency = int((time.perf_counter() - started) * 1000)
    _record(ws, entity, spec, action, last_error, latency, 0, args)
    return {**base, "ok": False, "attempts": attempts, "latency_ms": latency,
            "error": last_error or "failed", "kind": kind}


@router.post("/chain")
async def chain(body: ChainIn, request: Request) -> dict[str, Any]:
    """Run up to five connected apps in one ordered chain. One clean trace back."""
    ws, _ = workspace_from_request(request)
    rate_limit(f"ws:{ws}", rate_for(ws))
    entity = body.entity_id or "default"
    policy = (body.on_error or "stop").strip().lower()
    if policy not in {"stop", "continue"}:
        raise HTTPException(400, detail="on_error must be 'stop' or 'continue'.")

    started = time.perf_counter()
    planned, used = plan(body)
    missing = missing_connections(ws, entity, used)

    if missing and body.require_all_connected:
        return {
            "ok": False,
            "status": "needs_connection",
            "error": "Connect every app in this chain first; nothing was executed.",
            "needs_connection": missing,
            "resume": "Connect, then re-send the same request. Nothing was sent to any provider.",
            "apps": used,
            "steps": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "version": __version__,
        }

    ctx: dict[str, Any] = {"steps": [], "prev": {}, "apps": {}}
    trace: list[dict[str, Any]] = []

    for item in planned:
        step = item["raw"]
        if step.if_:
            try:
                allow = _truthy(render(step.if_, ctx))
            except Exception:
                allow = True
            if not allow:
                row = {"step": item["index"], "as": item["name"], "app": item["spec"].slug,
                       "action": item["action"].slug, "ok": True, "skipped": True,
                       "reason": "condition was false"}
                trace.append(row)
                ctx[item["name"]] = row
                ctx["steps"].append(row)
                continue

        try:
            args = render(step.args or {}, ctx)
        except Exception as exc:  # noqa: BLE001
            args = {}
            row = {"step": item["index"], "as": item["name"], "app": item["spec"].slug,
                   "action": item["action"].slug, "ok": False,
                   "error": f"arguments could not be rendered: {exc}"}
        else:
            row = await run_step(ws, entity, item, args if isinstance(args, dict) else {},
                                 body.dry_run, body.approve_writes)

        if not body.include_results:
            row.pop("data", None)
        trace.append(row)
        ctx[item["name"]] = row
        ctx["steps"].append(row)
        ctx["prev"] = row
        ctx["apps"][row["app"]] = {"ok": row.get("ok", False)}

        if row.get("needs_connection") and row["needs_connection"] not in {m["app"] for m in missing}:
            missing.append({"app": row["needs_connection"], "connect_url": row.get("connect_url", ""),
                            "mode": row.get("connect_mode", "key")})
        if not row.get("ok") and (step.on_error or policy) != "continue":
            break

    failed = [r for r in trace if not r.get("ok")]
    ran = [r for r in trace if not r.get("skipped")]
    status = ("succeeded" if not failed and not missing else
              "needs_connection" if missing else
              "partial" if any(r.get("ok") for r in ran) else "failed")
    out: dict[str, Any] = {
        "ok": not failed and not missing,
        "status": status,
        "apps": used,
        "apps_used": sorted({r["app"] for r in ran if r.get("ok")}),
        "steps_total": len(planned),
        "steps_run": len(ran),
        "steps_ok": sum(1 for r in ran if r.get("ok")),
        "steps": trace,
        "needs_connection": missing,
        "dry_run": body.dry_run,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "version": __version__,
    }
    if failed:
        first = failed[0]
        out["error"] = f"{first.get('app')}.{first.get('action')}: {first.get('error', 'failed')}"
    return out


@router.get("/chain")
def chain_doc() -> dict[str, Any]:
    """How to chain apps, in the shape an agent can read."""
    return {
        "endpoint": "POST /v1/chain",
        "apps_per_chain": MAX_APPS,
        "steps_per_chain": MAX_STEPS,
        "templating": "{{name.data.items.0.id}} reaches into an earlier step's response. "
                      "'name' is the step's 'as'; {{prev.***}} and {{steps.0.***}} also work.",
        "policies": {"on_error": ["stop", "continue"],
                     "require_all_connected": "preflight refuses to half-run a chain",
                     "approve_writes": "required for write and destructive steps"},
        "example": {
            "apps": ["gmail", "notion", "slack"],
            "steps": [
                {"app": "gmail", "action": "search_emails", "args": {"query": "invoice"}, "as": "mail"},
                {"app": "notion", "action": "create_page",
                 "args": {"title": "Invoice digest", "content": "{{mail.data.0.snippet}}"}, "as": "page"},
                {"app": "slack", "action": "post_message", "args": {"text": "{{page.data.url}}"}},
            ],
        },
        "related": {"single call": "POST /v1/execute", "goal in, answer out": "POST /v1/agent",
                    "durable longer runs": "POST /v1/flows", "tool schemas": "GET /v1/tools"},
    }
