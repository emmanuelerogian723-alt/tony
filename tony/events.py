"""Inbound event layer: a provider pushes, Tony normalises, subscriptions fire.

Tony could already *ask* (execute an action). It could not *wake up*. This module
adds the missing half: an unguessable ingest URL per source, provider-correct
signature verification, a normalised envelope, deduplication, and fan-out to
webhook subscriptions or durable flows.

Rules that matter in production:
  * a webhook is only trusted when its signature verifies; the URL alone is not auth
  * the same provider event delivered twice must not double-fire a subscription
  * a failed delivery is retried with backoff and recorded, never silently dropped
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
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
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from .auth import workspace_from_request
from .billing import PLANS, plan_id_for_workspace
from .config import settings
from .crypto import sign_payload, verify_signature
from .db import session
from .models import Base, now, uid

router = APIRouter(prefix="/v1", tags=["events"])
log = logging.getLogger("tony.events")

MAX_BODY = 1_000_000          # 1 MB: bigger than any real provider event
DELIVERY_ATTEMPTS = 3
SIGNATURE_SCHEMES = ("auto", "github", "stripe", "slack", "shopify", "linear", "generic", "none")


# ── tables ───────────────────────────────────────────────────────────────
class HookEndpoint(Base):
    """One ingest URL per workspace + source. The id is the capability URL."""

    __tablename__ = "hook_endpoints"
    __table_args__ = (Index("ix_hook_ws", "workspace_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(80), default="generic")
    label: Mapped[str] = mapped_column(String(120), default="")
    secret: Mapped[str] = mapped_column(String(120), default="")
    scheme: Mapped[str] = mapped_column(String(20), default="auto")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InboundEvent(Base):
    __tablename__ = "inbound_events"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "dedupe_key", name="uq_event_dedupe"),
        Index("ix_event_ws", "workspace_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    endpoint_id: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(80), default="")
    event_type: Mapped[str] = mapped_column(String(160), default="")
    dedupe_key: Mapped[str] = mapped_column(String(200), default="")
    signature_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="received")  # received|routed|ignored
    routed: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    headers_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class EventSubscription(Base):
    __tablename__ = "event_subscriptions"
    __table_args__ = (Index("ix_sub_ws", "workspace_id", "source"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), default="default")
    source: Mapped[str] = mapped_column(String(80), default="*")
    events: Mapped[str] = mapped_column(String(400), default="*")   # comma list, globs allowed
    target_url: Mapped[str] = mapped_column(String(500), default="")
    secret: Mapped[str] = mapped_column(String(120), default="")
    flow_spec_json: Mapped[str] = mapped_column(Text, default="")   # optional: start a durable flow
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    fire_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EventDelivery(Base):
    __tablename__ = "event_deliveries"
    __table_args__ = (Index("ix_delivery_event", "event_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(String(32), index=True)
    subscription_id: Mapped[str] = mapped_column(String(32), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# ── signature verification ───────────────────────────────────────────────
def _hmac_hex(secret: str, body: bytes, algo=hashlib.sha256) -> str:
    return hmac.new(secret.encode(), body, algo).hexdigest()


def verify(scheme: str, secret: str, body: bytes, headers: dict[str, str]) -> tuple[bool, str]:
    """Return (ok, why-not). Unknown or missing signatures fail closed."""
    if scheme == "none":
        return True, ""
    if not secret:
        return False, "endpoint has no secret set"
    low = {k.lower(): v for k, v in headers.items()}

    if scheme == "auto":
        if "x-hub-signature-256" in low:
            scheme = "github"
        elif "stripe-signature" in low:
            scheme = "stripe"
        elif "x-slack-signature" in low:
            scheme = "slack"
        elif "x-shopify-hmac-sha256" in low:
            scheme = "shopify"
        elif "linear-signature" in low:
            scheme = "linear"
        else:
            scheme = "generic"

    if scheme == "github":
        sent = low.get("x-hub-signature-256", "")
        expected = "sha256=" + _hmac_hex(secret, body)
        return (hmac.compare_digest(sent, expected), "github signature mismatch")
    if scheme == "stripe":
        parts = dict(p.split("=", 1) for p in low.get("stripe-signature", "").split(",") if "=" in p)
        ts, sent = parts.get("t", ""), parts.get("v1", "")
        if not ts or not sent:
            return False, "missing stripe-signature parts"
        expected = _hmac_hex(secret, f"{ts}.".encode() + body)
        return (hmac.compare_digest(sent, expected), "stripe signature mismatch")
    if scheme == "slack":
        ts = low.get("x-slack-request-timestamp", "")
        sent = low.get("x-slack-signature", "")
        try:
            if abs(time.time() - int(ts)) > 300:
                return False, "slack timestamp too old"
        except ValueError:
            return False, "bad slack timestamp"
        expected = "v0=" + _hmac_hex(secret, f"v0:{ts}:".encode() + body)
        return (hmac.compare_digest(sent, expected), "slack signature mismatch")
    if scheme == "shopify":
        sent = low.get("x-shopify-hmac-sha256", "")
        digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode()
        return (hmac.compare_digest(sent, expected), "shopify signature mismatch")
    if scheme == "linear":
        sent = low.get("linear-signature", "")
        return (hmac.compare_digest(sent, _hmac_hex(secret, body)), "linear signature mismatch")
    # generic: Tony's own t=..,v1=.. format, same as what we sign outbound
    return (verify_signature(secret, body, low.get("x-tony-signature", "")), "generic signature mismatch")


# ── normalisation ────────────────────────────────────────────────────────
_TYPE_HEADERS = ("x-github-event", "x-event-type", "x-linear-event", "x-shopify-topic",
                 "x-trello-webhook", "x-webhook-topic")


def event_type_of(headers: dict[str, str], payload: Any) -> str:
    low = {k.lower(): v for k, v in headers.items()}
    base = next((low[h] for h in _TYPE_HEADERS if low.get(h)), "")
    action = ""
    if isinstance(payload, dict):
        for key in ("action", "event_type", "type", "event"):
            val = payload.get(key)
            if isinstance(val, str) and val and val != base:
                if key == "action" and base:
                    action = val
                elif not base:
                    base = val
                break
        if not base and isinstance(payload.get("object"), dict):
            base = str(payload["object"].get("kind") or "")
    return f"{base}.{action}" if base and action else (base or "unknown")


_DEDUPE_HEADERS = ("x-github-delivery", "x-shopify-webhook-id", "x-linear-delivery",
                   "x-webhook-id", "x-request-id")


def dedupe_key_of(headers: dict[str, str], payload: Any, body: bytes) -> str:
    low = {k.lower(): v for k, v in headers.items()}
    for h in _DEDUPE_HEADERS:
        if low.get(h):
            return low[h][:200]
    if isinstance(payload, dict):
        for key in ("id", "event_id", "delivery_id", "webhook_id"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val[:200]
    return hashlib.sha256(body).hexdigest()


def envelope(source: str, endpoint_id: str, event_type: str, payload: Any,
             headers: dict[str, str], event_id: str) -> dict[str, Any]:
    """The shape every subscription and flow sees, whatever the provider sent."""
    return {
        "id": event_id,
        "source": source,
        "endpoint_id": endpoint_id,
        "type": event_type,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "body": payload,
        "headers": {k.lower(): v for k, v in headers.items()
                    if k.lower() in {"user-agent", "content-type", "x-github-event", "x-shopify-topic"}},
    }


# ── matching ─────────────────────────────────────────────────────────────
def _matches(pattern: str, value: str) -> bool:
    import fnmatch

    for part in [p.strip() for p in pattern.split(",") if p.strip()]:
        if part == "*" or fnmatch.fnmatch(value, part):
            return True
        # "pull_request" should match "pull_request.opened"
        if value.startswith(part + ".") or fnmatch.fnmatch(value.split(".")[0], part):
            return True
    return False


def subscriptions_for(ws: str, source: str, event_type: str) -> list[EventSubscription]:
    with session() as s:
        rows = s.scalars(select(EventSubscription).where(
            EventSubscription.workspace_id == ws,
            EventSubscription.enabled.is_(True))).all()
        return [r for r in rows
                if r.source in ("*", source) and _matches(r.events or "*", event_type)]


# ── delivery ─────────────────────────────────────────────────────────────
async def deliver(sub: EventSubscription, event_id: str, body: bytes,
                  headers: dict[str, str]) -> bool:
    """POST with backoff. Every attempt is recorded, success or not."""
    if not sub.target_url:
        return False
    ok_any = False
    for attempt in range(1, DELIVERY_ATTEMPTS + 1):
        status_code, ok, error = 0, False, ""
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
                resp = await client.post(sub.target_url, content=body, headers=headers)
            status_code = resp.status_code
            ok = 200 <= status_code < 300
            if not ok:
                error = resp.text[:200]
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"[:200]
        with session() as s:
            s.add(EventDelivery(event_id=event_id, subscription_id=sub.id, attempt=attempt,
                                status_code=status_code, ok=ok, error=error))
        if ok:
            ok_any = True
            break
        if attempt < DELIVERY_ATTEMPTS:
            await asyncio.sleep(min(0.5 * (2 ** (attempt - 1)), 4.0))
    with session() as s:
        row = s.scalar(select(EventSubscription).where(EventSubscription.id == sub.id))
        if row is not None:
            row.fire_count = (row.fire_count or 0) + 1
            if not ok_any:
                row.fail_count = (row.fail_count or 0) + 1
            row.last_fired_at = datetime.now(timezone.utc)
    return ok_any


async def route(event_id: str) -> int:
    """Fan an inbound event out to every matching subscription."""
    with session() as s:
        ev = s.scalar(select(InboundEvent).where(InboundEvent.id == event_id))
        if ev is None:
            return 0
        ws, source, event_type = ev.workspace_id, ev.source, ev.event_type
        endpoint_id = ev.endpoint_id
        payload = json.loads(ev.payload_json or "{}")
    subs = subscriptions_for(ws, source, event_type)
    fired = 0
    for sub in subs:
        body_obj = envelope(source, endpoint_id, event_type, payload, {}, event_id)
        raw = json.dumps(body_obj, separators=(",", ":"), default=str).encode()
        headers = {
            "Content-Type": "application/json",
            "X-Tony-Event": event_type[:160],
            "X-Tony-Source": source[:80],
            "X-Tony-Event-Id": event_id,
            "X-Tony-Delivery": sub.id,
            "X-Tony-Signature": sign_payload(sub.secret or "tony-unsigned", raw),
        }
        if sub.flow_spec_json:
            try:
                from .flows import create_flow

                spec = json.loads(sub.flow_spec_json)
                create_flow(ws, sub.entity_id or "default", spec, event=body_obj,
                            origin=f"event:{event_id}")
                fired += 1
            except Exception as exc:  # noqa: BLE001 - a bad spec must not kill the fan-out
                log.warning("subscription %s flow failed: %s", sub.id, exc)
            continue
        if await deliver(sub, event_id, raw, headers):
            fired += 1
    with session() as s:
        ev = s.scalar(select(InboundEvent).where(InboundEvent.id == event_id))
        if ev is not None:
            ev.status = "routed" if fired else "ignored"
            ev.routed = fired
    return fired


# ── limits ───────────────────────────────────────────────────────────────
def _enforce_subscription_limit(ws: str) -> None:
    from .models import Trigger

    plan_id, _sub, _user = plan_id_for_workspace(ws)
    limit = int(PLANS[plan_id].get("triggers", 3))
    with session() as s:
        used = len(s.scalars(select(EventSubscription).where(
            EventSubscription.workspace_id == ws)).all())
        used += s.query(Trigger).filter(Trigger.workspace_id == ws).count()
    if used >= limit:
        raise HTTPException(402, detail=(
            f"The {plan_id} plan allows {limit} triggers/subscriptions. "
            "Upgrade to add more, or delete one first."))


# ── API: ingest ──────────────────────────────────────────────────────────
@router.post("/hooks/{endpoint_id}", include_in_schema=False)
async def ingest(endpoint_id: str, request: Request) -> dict[str, Any]:
    """Provider-facing. No bearer key: the capability URL plus the signature is the auth."""
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, detail="Event body too large")
    with session() as s:
        ep = s.scalar(select(HookEndpoint).where(HookEndpoint.id == endpoint_id))
        if ep is None or not ep.enabled:
            raise HTTPException(404, detail="Unknown endpoint")
        ws, source, secret, scheme = ep.workspace_id, ep.source, ep.secret, ep.scheme
    headers = dict(request.headers)
    ok, why = verify(scheme, secret, body, headers)
    if not ok:
        raise HTTPException(401, detail=f"Signature check failed: {why}")
    try:
        payload: Any = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {"raw": body.decode("utf-8", "replace")[:20000]}
    etype = event_type_of(headers, payload)
    key = dedupe_key_of(headers, payload, body)
    with session() as s:
        existing = s.scalar(select(InboundEvent).where(
            InboundEvent.endpoint_id == endpoint_id, InboundEvent.dedupe_key == key))
        if existing is not None:
            return {"ok": True, "duplicate": True, "event_id": existing.id}
        ev = InboundEvent(workspace_id=ws, endpoint_id=endpoint_id, source=source,
                          event_type=etype, dedupe_key=key, signature_ok=True,
                          payload_json=json.dumps(payload, default=str)[:200000],
                          headers_json=json.dumps({k.lower(): v for k, v in headers.items()
                                                   if k.lower() not in {"authorization", "cookie"}})[:8000])
        s.add(ev)
        s.flush()
        event_id = ev.id
        ep = s.scalar(select(HookEndpoint).where(HookEndpoint.id == endpoint_id))
        if ep is not None:
            ep.event_count = (ep.event_count or 0) + 1
            ep.last_event_at = datetime.now(timezone.utc)
    asyncio.create_task(route(event_id))
    return {"ok": True, "event_id": event_id, "type": etype}


# ── API: endpoints & subscriptions ───────────────────────────────────────
class EndpointIn(BaseModel):
    source: str = Field(default="generic", max_length=80)
    label: str = Field(default="", max_length=120)
    scheme: str = Field(default="auto")
    secret: str = Field(default="")


class SubscriptionIn(BaseModel):
    source: str = Field(default="*", max_length=80)
    events: str = Field(default="*", max_length=400)
    target_url: str = Field(default="", max_length=500)
    flow_spec: dict[str, Any] | None = None
    entity_id: str = Field(default="default", max_length=160)


def endpoint_public(row: HookEndpoint) -> dict[str, Any]:
    base = settings.base_url.rstrip("/")
    return {
        "id": row.id,
        "source": row.source,
        "label": row.label,
        "scheme": row.scheme,
        "enabled": row.enabled,
        "url": f"{base}/v1/hooks/{row.id}",
        "event_count": row.event_count,
        "last_event_at": row.last_event_at.isoformat() if row.last_event_at else None,
        "created_at": row.created_at.isoformat(),
    }


def subscription_public(row: EventSubscription) -> dict[str, Any]:
    return {
        "id": row.id,
        "source": row.source,
        "events": row.events,
        "target_url": row.target_url,
        "has_flow": bool(row.flow_spec_json),
        "entity_id": row.entity_id,
        "enabled": row.enabled,
        "fire_count": row.fire_count,
        "fail_count": row.fail_count,
        "last_fired_at": row.last_fired_at.isoformat() if row.last_fired_at else None,
    }


@router.post("/event-endpoints")
def create_endpoint(body: EndpointIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    if body.scheme not in SIGNATURE_SCHEMES:
        raise HTTPException(400, detail=f"scheme must be one of {', '.join(SIGNATURE_SCHEMES)}")
    secret = body.secret.strip() or ("whsec_" + secrets.token_urlsafe(24))
    with session() as s:
        row = HookEndpoint(workspace_id=ws, source=body.source.strip() or "generic",
                           label=body.label, scheme=body.scheme, secret=secret)
        s.add(row)
        s.flush()
        out = endpoint_public(row)
    out["secret"] = secret       # shown once, at creation only
    out["signature_scheme"] = body.scheme
    return out


@router.get("/event-endpoints")
def list_endpoints(request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(HookEndpoint).where(HookEndpoint.workspace_id == ws)
                         .order_by(HookEndpoint.created_at.desc())).all()
        return {"endpoints": [endpoint_public(r) for r in rows]}


@router.delete("/event-endpoints/{endpoint_id}")
def delete_endpoint(endpoint_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(HookEndpoint).where(HookEndpoint.id == endpoint_id,
                                                  HookEndpoint.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown endpoint")
        s.delete(row)
    return {"ok": True}


@router.post("/subscriptions")
def create_subscription(body: SubscriptionIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    if not body.target_url and not body.flow_spec:
        raise HTTPException(400, detail="A subscription needs target_url or flow_spec")
    if body.target_url and not body.target_url.startswith(("http://", "https://")):
        raise HTTPException(400, detail="target_url must be http(s)")
    _enforce_subscription_limit(ws)
    with session() as s:
        row = EventSubscription(
            workspace_id=ws, source=body.source or "*", events=body.events or "*",
            target_url=body.target_url, entity_id=body.entity_id or "default",
            secret=secrets.token_urlsafe(24),
            flow_spec_json=json.dumps(body.flow_spec) if body.flow_spec else "")
        s.add(row)
        s.flush()
        return subscription_public(row)


@router.get("/subscriptions")
def list_subscriptions(request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(EventSubscription).where(EventSubscription.workspace_id == ws)
                         .order_by(EventSubscription.created_at.desc())).all()
        return {"subscriptions": [subscription_public(r) for r in rows]}


@router.patch("/subscriptions/{sub_id}")
def update_subscription(sub_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    allowed = {"enabled", "events", "target_url", "source"}
    with session() as s:
        row = s.scalar(select(EventSubscription).where(EventSubscription.id == sub_id,
                                                       EventSubscription.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown subscription")
        for key, value in body.items():
            if key in allowed:
                setattr(row, key, value)
        s.flush()
        return subscription_public(row)


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(EventSubscription).where(EventSubscription.id == sub_id,
                                                       EventSubscription.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown subscription")
        s.delete(row)
    return {"ok": True}


# ── API: events ──────────────────────────────────────────────────────────
@router.get("/events")
def list_events(request: Request, limit: int = 50, source: str = "") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    limit = max(1, min(limit, 200))
    with session() as s:
        q = select(InboundEvent).where(InboundEvent.workspace_id == ws)
        if source:
            q = q.where(InboundEvent.source == source)
        rows = s.scalars(q.order_by(InboundEvent.created_at.desc()).limit(limit)).all()
        return {"events": [{
            "id": r.id, "source": r.source, "type": r.event_type, "status": r.status,
            "routed": r.routed, "at": r.created_at.isoformat(),
        } for r in rows]}


@router.get("/events/{event_id}")
def get_event(event_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        ev = s.scalar(select(InboundEvent).where(InboundEvent.id == event_id,
                                                 InboundEvent.workspace_id == ws))
        if ev is None:
            raise HTTPException(404, detail="Unknown event")
        deliveries = s.scalars(select(EventDelivery).where(EventDelivery.event_id == event_id)
                               .order_by(EventDelivery.created_at)).all()
        return {
            "id": ev.id, "source": ev.source, "type": ev.event_type, "status": ev.status,
            "signature_ok": ev.signature_ok, "at": ev.created_at.isoformat(),
            "payload": json.loads(ev.payload_json or "{}"),
            "deliveries": [{"subscription": d.subscription_id, "attempt": d.attempt,
                            "status": d.status_code, "ok": d.ok, "error": d.error}
                           for d in deliveries],
        }


@router.post("/events/{event_id}/replay")
async def replay_event(event_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        ev = s.scalar(select(InboundEvent).where(InboundEvent.id == event_id,
                                                 InboundEvent.workspace_id == ws))
        if ev is None:
            raise HTTPException(404, detail="Unknown event")
    fired = await route(event_id)
    return {"ok": True, "fired": fired}
