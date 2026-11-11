"""Durable flows: multi-step runs that survive restarts, waits and failures.

/v1/execute does one call and hangs up. Real agent work is a sequence: read,
decide, wait for a human, write, notify. This module runs that sequence as a
state machine in the database, so a Render restart mid-flow is a pause, not a
lost job.

Guarantees:
  * a step is only retried under the runtime policy (never a blind write retry)
  * waits are durable: the flow parks with a resume time and the worker wakes it
  * a flow that exhausts its attempts lands in the dead-letter queue, replayable
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from .auth import workspace_from_request
from .catalog import catalog
from .config import settings
from .db import session
from .executor import ExecutionError, execute
from .models import ActionRun, Base, now, uid
from .oauth import credentials_for
from .runtime import classify, is_retryable

router = APIRouter(prefix="/v1", tags=["flows"])
log = logging.getLogger("tony.flows")

STEP_KINDS = ("action", "set", "wait", "webhook")
MAX_STEPS = 50
DEFAULT_MAX_ATTEMPTS = 3


# ── tables ───────────────────────────────────────────────────────────────
class Flow(Base):
    __tablename__ = "flows"
    __table_args__ = (Index("ix_flow_ws", "workspace_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), default="default")
    name: Mapped[str] = mapped_column(String(160), default="flow")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    spec_json: Mapped[str] = mapped_column(Text, default="{}")
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    origin: Mapped[str] = mapped_column(String(200), default="api")
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_ATTEMPTS)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FlowStep(Base):
    __tablename__ = "flow_steps"
    __table_args__ = (Index("ix_stepid", "flow_id", "position"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    flow_id: Mapped[str] = mapped_column(String(32), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16), default="action")
    name: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|ok|failed|skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StepError(Exception):
    def __init__(self, message: str, status: int = 0, retryable: bool = False,
                 kind: str = "unknown") -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable
        self.kind = kind


# ── templating ───────────────────────────────────────────────────────────
_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_.\[\]-]+)\s*\}\}")


def _resolve_path(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for raw in path.split("."):
        key = raw
        idx = None
        m = re.match(r"^([^\[\]]*)\[(\d+)\]$", raw)
        if m:
            key, idx = m.group(1), int(m.group(2))
        if key:
            if isinstance(cur, dict):
                if key not in cur:
                    return None
                cur = cur[key]
            elif isinstance(cur, list):
                try:
                    cur = cur[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        if idx is not None:
            if isinstance(cur, list) and idx < len(cur):
                cur = cur[idx]
            else:
                return None
    return cur


def render(value: Any, ctx: dict[str, Any]) -> Any:
    """Substitute {{path}} in strings. A lone placeholder keeps its real type."""
    if isinstance(value, str):
        single = _PLACEHOLDER.fullmatch(value.strip())
        if single:
            return _resolve_path(ctx, single.group(1))
        return _PLACEHOLDER.sub(lambda m: _str(_resolve_path(ctx, m.group(1))), value)
    if isinstance(value, dict):
        return {k: render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, ctx) for v in value]
    return value


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


# ── creation ─────────────────────────────────────────────────────────────
def valid_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise HTTPException(400, detail="spec.steps must be a non-empty list")
    if len(steps) > MAX_STEPS:
        raise HTTPException(400, detail=f"A flow is capped at {MAX_STEPS} steps")
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise HTTPException(400, detail=f"step {i} must be an object")
        kind = str(step.get("kind") or "action").lower()
        if kind not in STEP_KINDS:
            raise HTTPException(400, detail=f"step {i}: kind must be one of {', '.join(STEP_KINDS)}")
        if kind == "action" and not step.get("action"):
            raise HTTPException(400, detail=f"step {i}: action is required")
        if kind == "wait" and not isinstance(step.get("seconds"), (int, float)):
            raise HTTPException(400, detail=f"step {i}: wait needs numeric seconds")
        if kind == "webhook" and not str(step.get("url") or "").startswith(("http://", "https://")):
            raise HTTPException(400, detail=f"step {i}: webhook needs an http(s) url")
    return steps


def create_flow(ws: str, entity: str, spec: dict[str, Any], *, event: Any = None,
                origin: str = "api") -> Flow:
    steps = valid_spec(spec)
    ctx: dict[str, Any] = {"event": event, "steps": {}, "now": datetime.now(timezone.utc).isoformat()}
    with session() as s:
        flow = Flow(workspace_id=ws, entity_id=entity or "default",
                    name=str(spec.get("name") or "flow")[:160], spec_json=json.dumps(spec),
                    context_json=json.dumps(ctx, default=str)[:200000], origin=origin[:200],
                    max_attempts=int(spec.get("max_attempts") or DEFAULT_MAX_ATTEMPTS),
                    next_run_at=datetime.now(timezone.utc))
        s.add(flow)
        s.flush()
        for i, step in enumerate(steps):
            s.add(FlowStep(flow_id=flow.id, position=i,
                           kind=str(step.get("kind") or "action").lower(),
                           name=str(step.get("name") or step.get("action") or step.get("kind"))[:80]))
        s.flush()
        return flow


# ── step execution ───────────────────────────────────────────────────────
async def _run_action_step(flow: Flow, step: dict[str, Any], ctx: dict[str, Any]) -> Any:
    from .billing import check_run

    check_run(flow.workspace_id)
    name = str(step.get("action") or "")
    resolved = catalog.find_action(name)
    if not resolved:
        raise StepError(f"Unknown action '{name}'", 404, retryable=False, kind="not_found")
    spec, action = resolved
    args = render(step.get("args") or {}, ctx) or {}
    creds = credentials_for(flow.workspace_id, flow.entity_id, spec)
    if spec.auth.type != "none" and creds is None and not action.public:
        raise StepError(f"No {spec.name} account connected for '{flow.entity_id}'",
                        400, retryable=False, kind="auth")
    try:
        result = await execute(spec, action, args, creds)
    except ExecutionError as exc:
        raise StepError(str(exc), 0, retryable=action.method.upper() == "GET", kind="network") from exc
    with session() as s:
        s.add(ActionRun(workspace_id=flow.workspace_id, entity_id=flow.entity_id,
                        app_slug=spec.slug, action_slug=action.slug, tier=action.tier,
                        status="success" if result.ok else "error", status_code=result.status,
                        latency_ms=result.latency_ms,
                        request_json=json.dumps(args, default=str)[:8000],
                        response_json=json.dumps(result.data, default=str)[:20000] if result.ok else "{}",
                        error=(result.error or "")[:2000]))
    if not result.ok:
        kind = classify(result.status, result.error)
        raise StepError(result.error or kind, result.status,
                        retryable=is_retryable(kind, method=action.method), kind=kind)
    return result.data


async def _run_webhook_step(step: dict[str, Any], ctx: dict[str, Any]) -> Any:
    url = str(render(step.get("url") or "", ctx))
    body = render(step.get("body") or {}, ctx)
    headers = {"Content-Type": "application/json"}
    for key, value in (step.get("headers") or {}).items():
        headers[str(key)] = _str(render(value, ctx))
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        resp = await client.request(str(step.get("method") or "POST").upper(), url,
                                    content=json.dumps(body, default=str).encode(), headers=headers)
    if not (200 <= resp.status_code < 300):
        raise StepError(f"webhook returned {resp.status_code}: {resp.text[:200]}",
                        resp.status_code, retryable=resp.status_code >= 500 or resp.status_code == 429,
                        kind=classify(resp.status_code, resp.text))
    return {"status": resp.status_code, "body": resp.text[:2000]}


async def advance(flow_id: str) -> str:
    """Run a flow as far as it can go right now. Returns the resulting status."""
    with session() as s:
        flow = s.scalar(select(Flow).where(Flow.id == flow_id))
        if flow is None or flow.status in {"succeeded", "failed", "cancelled", "dead"}:
            return flow.status if flow else "missing"
        steps = s.scalars(select(FlowStep).where(FlowStep.flow_id == flow_id)
                          .order_by(FlowStep.position)).all()
        spec = json.loads(flow.spec_json or "{}")
        ctx = json.loads(flow.context_json or "{}")
    raw_steps = spec.get("steps") or []

    for i in range(flow.current_step, len(steps)):
        step_row = steps[i]
        if step_row.status == "ok":
            continue
        raw = raw_steps[i] if i < len(raw_steps) else {}
        kind = step_row.kind

        # durable wait: park once, resume when the clock says so
        if kind == "wait":
            seconds = float(raw.get("seconds") or 0)
            if step_row.status != "running":
                resume = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, seconds))
                with session() as s:
                    row = s.get(FlowStep, step_row.id)
                    row.status = "running"
                    row.started_at = datetime.now(timezone.utc)
                    f = s.get(Flow, flow_id)
                    f.status = "waiting"
                    f.next_run_at = resume
                    f.updated_at = datetime.now(timezone.utc)
                return "waiting"
            due = flow.next_run_at
            if due is not None and due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if due is not None and due > datetime.now(timezone.utc):
                return "waiting"

        with session() as s:
            row = s.get(FlowStep, step_row.id)
            row.status = "running"
            row.started_at = row.started_at or datetime.now(timezone.utc)
            f = s.get(Flow, flow_id)
            f.status = "running"
            f.current_step = i
            f.updated_at = datetime.now(timezone.utc)

        try:
            if kind == "set":
                value = render(raw.get("value"), ctx)
                result: Any = value
            elif kind == "wait":
                result = {"waited": raw.get("seconds")}
            elif kind == "webhook":
                result = await _run_webhook_step(raw, ctx)
            else:
                result = await _run_action_step(flow, raw, ctx)
        except StepError as exc:
            return _fail(flow_id, step_row.id, str(exc), exc.retryable)
        except Exception as exc:  # noqa: BLE001 - surfaces as a failed step, not a dead worker
            return _fail(flow_id, step_row.id, f"{type(exc).__name__}: {exc}", False)

        save_as = str(raw.get("save_as") or step_row.name or f"step{i}")
        ctx.setdefault("steps", {})[save_as] = {"data": result}
        with session() as s:
            row = s.get(FlowStep, step_row.id)
            row.status = "ok"
            row.result_json = json.dumps(result, default=str)[:20000]
            row.error = ""
            row.finished_at = datetime.now(timezone.utc)
            f = s.get(Flow, flow_id)
            f.context_json = json.dumps(ctx, default=str)[:200000]
            f.current_step = i + 1
            f.attempts = 0
            f.status = "running"
            f.next_run_at = None
            f.updated_at = datetime.now(timezone.utc)

    with session() as s:
        f = s.get(Flow, flow_id)
        f.status = "succeeded"
        f.finished_at = datetime.now(timezone.utc)
        f.updated_at = datetime.now(timezone.utc)
        f.next_run_at = None
    return "succeeded"


def _fail(flow_id: str, step_id: str, message: str, retryable: bool) -> str:
    with session() as s:
        flow = s.get(Flow, flow_id)
        step = s.get(FlowStep, step_id)
        flow.attempts = (flow.attempts or 0) + 1
        flow.last_error = message[:2000]
        flow.updated_at = datetime.now(timezone.utc)
        step.attempts = (step.attempts or 0) + 1
        step.error = message[:2000]
        if retryable and flow.attempts < max(1, flow.max_attempts):
            delay = min(2 ** flow.attempts, 60)
            flow.status = "queued"
            flow.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            step.status = "pending"
        else:
            step.status = "failed"
            step.finished_at = datetime.now(timezone.utc)
            flow.status = "dead"        # dead-letter queue: explicit, replayable
            flow.finished_at = datetime.now(timezone.utc)
        return flow.status


async def runner() -> None:
    """Wake due flows. Cheap query, no per-flow timers in memory."""
    every = max(2, min(15, int(settings.poll_interval)))
    log.info("Flow runner started (every %ss)", every)
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            with session() as s:
                rows = s.scalars(select(Flow).where(Flow.status.in_(("queued", "running", "waiting")))
                                 .limit(50)).all()
                due = []
                for f in rows:
                    nxt = f.next_run_at
                    if nxt is not None and nxt.tzinfo is None:
                        nxt = nxt.replace(tzinfo=timezone.utc)
                    if f.status in ("queued", "running") or (nxt and nxt <= now_utc):
                        due.append(f.id)
            for flow_id in due:
                try:
                    await advance(flow_id)
                except Exception:  # noqa: BLE001
                    log.exception("flow %s crashed", flow_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover
            log.exception("flow runner tick failed")
        await asyncio.sleep(every)


# ── API ──────────────────────────────────────────────────────────────────
class FlowIn(BaseModel):
    name: str = Field(default="flow", max_length=160)
    steps: list[dict[str, Any]]
    entity_id: str = Field(default="default", max_length=160)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1, le=10)


def flow_public(flow: Flow, steps: list[FlowStep] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": flow.id,
        "name": flow.name,
        "status": flow.status,
        "entity_id": flow.entity_id,
        "origin": flow.origin,
        "current_step": flow.current_step,
        "attempts": flow.attempts,
        "max_attempts": flow.max_attempts,
        "next_run_at": flow.next_run_at.isoformat() if flow.next_run_at else None,
        "last_error": flow.last_error,
        "created_at": flow.created_at.isoformat(),
        "finished_at": flow.finished_at.isoformat() if flow.finished_at else None,
    }
    if steps is not None:
        out["steps"] = [{
            "position": s.position, "kind": s.kind, "name": s.name, "status": s.status,
            "attempts": s.attempts, "error": s.error,
            "result": json.loads(s.result_json) if s.result_json else None,
        } for s in steps]
    return out


@router.post("/flows")
async def start_flow(body: FlowIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    spec = {"name": body.name, "steps": body.steps, "max_attempts": body.max_attempts}
    flow = create_flow(ws, body.entity_id, spec, origin="api")
    await advance(flow.id)
    with session() as s:
        row = s.get(Flow, flow.id)
        steps = s.scalars(select(FlowStep).where(FlowStep.flow_id == flow.id)
                          .order_by(FlowStep.position)).all()
        return flow_public(row, steps)


@router.get("/flows/dlq")
def dead_letters(request: Request, limit: int = 50) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    limit = max(1, min(limit, 200))
    with session() as s:
        rows = s.scalars(select(Flow).where(Flow.workspace_id == ws, Flow.status == "dead")
                         .order_by(Flow.updated_at.desc()).limit(limit)).all()
        return {"dead": [flow_public(r) for r in rows]}


@router.get("/flows")
def list_flows(request: Request, status: str = "", limit: int = 50) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    limit = max(1, min(limit, 200))
    with session() as s:
        q = select(Flow).where(Flow.workspace_id == ws)
        if status:
            q = q.where(Flow.status == status)
        rows = s.scalars(q.order_by(Flow.created_at.desc()).limit(limit)).all()
        return {"flows": [flow_public(r) for r in rows]}


@router.get("/flows/{flow_id}")
def get_flow(flow_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        flow = s.scalar(select(Flow).where(Flow.id == flow_id, Flow.workspace_id == ws))
        if flow is None:
            raise HTTPException(404, detail="Unknown flow")
        steps = s.scalars(select(FlowStep).where(FlowStep.flow_id == flow_id)
                          .order_by(FlowStep.position)).all()
        return flow_public(flow, steps)


@router.post("/flows/{flow_id}/cancel")
def cancel_flow(flow_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        flow = s.scalar(select(Flow).where(Flow.id == flow_id, Flow.workspace_id == ws))
        if flow is None:
            raise HTTPException(404, detail="Unknown flow")
        if flow.status in {"succeeded", "failed", "cancelled"}:
            return flow_public(flow)
        flow.status = "cancelled"
        flow.finished_at = datetime.now(timezone.utc)
        flow.updated_at = datetime.now(timezone.utc)
        return flow_public(flow)


@router.post("/flows/{flow_id}/retry")
async def retry_flow(flow_id: str, request: Request) -> dict[str, Any]:
    """Bring a dead flow back: reset the failed step and its attempt budget."""
    ws, _ = workspace_from_request(request)
    with session() as s:
        flow = s.scalar(select(Flow).where(Flow.id == flow_id, Flow.workspace_id == ws))
        if flow is None:
            raise HTTPException(404, detail="Unknown flow")
        if flow.status not in {"dead", "failed"}:
            raise HTTPException(400, detail=f"Flow is '{flow.status}', not dead")
        steps = s.scalars(select(FlowStep).where(FlowStep.flow_id == flow_id)
                          .order_by(FlowStep.position)).all()
        target = next((st for st in steps if st.status in {"failed", "pending"}), None)
        if target is None:
            raise HTTPException(400, detail="Nothing to retry")
        target.status = "pending"
        target.attempts = 0
        target.error = ""
        flow.status = "queued"
        flow.attempts = 0
        flow.last_error = ""
        flow.current_step = target.position
        flow.next_run_at = datetime.now(timezone.utc)
        flow.finished_at = None
        flow.updated_at = datetime.now(timezone.utc)
    await advance(flow_id)
    with session() as s:
        row = s.get(Flow, flow_id)
        steps = s.scalars(select(FlowStep).where(FlowStep.flow_id == flow_id)
                          .order_by(FlowStep.position)).all()
        return flow_public(row, steps)
