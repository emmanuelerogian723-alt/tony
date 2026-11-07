"""Polling triggers: watch an action's output, webhook the operator on change."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from .catalog import catalog
from .config import settings
from .crypto import sign_payload
from .db import session
from .executor import ExecutionError, execute
from .models import Trigger, WebhookDelivery
from .oauth import credentials_for

log = logging.getLogger("tony.triggers")


async def _deliver(trigger: Trigger, payload: dict) -> None:
    if not trigger.webhook_url:
        return
    body = json.dumps(payload, separators=(",", ":"), default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Tony-Signature": sign_payload(trigger.secret, body),
        "X-Tony-Trigger": trigger.id,
    }
    status_code, ok, error = 0, False, ""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(trigger.webhook_url, content=body, headers=headers)
        status_code, ok = resp.status_code, 200 <= resp.status_code < 300
        if not ok:
            error = resp.text[:200]
    except httpx.HTTPError as exc:
        error = f"{type(exc).__name__}: {exc}"
    with session() as s:
        s.add(WebhookDelivery(trigger_id=trigger.id, status_code=status_code, ok=ok, error=error))


async def run_trigger(trigger_id: str) -> dict | None:
    with session() as s:
        trigger = s.scalar(select(Trigger).where(Trigger.id == trigger_id))
        if trigger is None or not trigger.enabled:
            return None
        spec = catalog.get(trigger.app_slug)
        action = spec.action(trigger.action_slug) if spec else None
        if spec is None or action is None:
            return None
        args = json.loads(trigger.args_json or "{}")
        creds = credentials_for(trigger.workspace_id, trigger.entity_id, spec)
        now = datetime.now(timezone.utc)
        trigger.last_run_at = now
        snapshot = (trigger.workspace_id, trigger.entity_id, trigger.secret, trigger.webhook_url, trigger.last_hash)

    ws, entity, secret, webhook, last_hash = snapshot
    try:
        result = await execute(spec, action, args, creds)
    except ExecutionError as exc:
        log.warning("trigger %s failed: %s", trigger_id, exc)
        return None
    if not result.ok:
        return None
    digest = hashlib.sha256(json.dumps(result.data, sort_keys=True, default=str).encode()).hexdigest()
    if digest != last_hash and webhook:
        with session() as s:
            trig = s.scalar(select(Trigger).where(Trigger.id == trigger_id))
            if trig:
                await_delivery = _deliver(trig, {
                    "trigger_id": trigger_id,
                    "app": spec.slug,
                    "action": action.slug,
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                    "data": result.data,
                })
                await await_delivery
    with session() as s:
        trig = s.scalar(select(Trigger).where(Trigger.id == trigger_id))
        if trig:
            trig.last_hash = digest
    return result.data if isinstance(result.data, dict) else {"data": result.data}


async def poller() -> None:
    """Background loop: every TONY_POLL_INTERVAL seconds run due triggers."""
    log.info("Trigger poller started (every %ss)", settings.poll_interval)
    while True:
        try:
            cutoff = datetime.now(timezone.utc)
            with session() as s:
                rows = s.scalars(select(Trigger).where(Trigger.enabled.is_(True))).all()
                due = []
                for t in rows:
                    last = t.last_run_at
                    if last is not None and last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    if last is None or (cutoff - last) >= timedelta(seconds=t.interval_seconds):
                        due.append(t.id)
            for trigger_id in due:
                await run_trigger(trigger_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - keep the loop alive
            log.exception("trigger poll failed")
        await asyncio.sleep(settings.poll_interval)
