"""Plans, quotas, subscriptions and payments.

The rule here is simple: the free tier must be big enough to build and ship a
real product on. Paid tiers exist for volume, not to unlock basic ability.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from .config import settings
from .db import session
from .models import (
    ActionRun,
    AgentSession,
    ApiKey,
    ConnectedAccount,
    Entity,
    PaymentEvent,
    Subscription,
    Trigger,
    User,
)

log = logging.getLogger("tony.billing")
router = APIRouter(prefix="/v1/billing", tags=["billing"])

# No plan is granted without payment. A trial is opt-in per deployment:
# set TONY_TRIAL_DAYS to hand new accounts a temporary Pro window.
TRIAL_DAYS = int(os.getenv("TONY_TRIAL_DAYS", "0"))
PAYSTACK_API = "https://api.paystack.co"

# Generous by design. Free is a real product tier, not a demo.
PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "tagline": "Build the whole thing, ship it, then grow into a paid plan.",
        "price_ngn": 0,
        "price_usd": 0,
        "read_pages": 3_000,
        "runs": 5_000,
        "connected_accounts": 15,
        "entities": 5,
        "keys": 3,
        "triggers": 3,
        "sessions": 5,
        "custom_tools": 5,
        "rate_per_min": 120,
        "retention_days": 14,
        "apps": "all",
        "actions": "all",
        "write": True,
        "support": "Community",
        "highlights": [
            "Every connectable app in Tony's catalogue and 40,000+ actions",
            "5,000 action runs a month",
            "Write actions with the approval gate",
            "15 connected accounts, 5 end-user identities",
            "3 API keys, 3 triggers, 5 agent sessions",
            "14-day run history",
        ],
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "tagline": "For a product in production with real users on it.",
        "price_ngn": 7_500,
        "price_usd": 5,
        "read_pages": 100_000,
        "runs": 150_000,
        "connected_accounts": 250,
        "entities": 100,
        "keys": 25,
        "triggers": 40,
        "sessions": 50,
        "custom_tools": 25,
        "rate_per_min": 600,
        "retention_days": 90,
        "apps": "all",
        "actions": "all",
        "write": True,
        "support": "Email, 24h",
        "highlights": [
            "150,000 action runs a month",
            "250 connected accounts, 100 end-user identities",
            "25 keys, 40 triggers, 50 agent sessions",
            "600 requests a minute",
            "90-day run history",
            "Everything in Free, plus priority on the queue",
        ],
    },
    "business": {
        "id": "business",
        "name": "Business",
        "tagline": "For teams running automations for other people.",
        "price_ngn": 25_000,
        "price_usd": 20,
        "read_pages": 1_000_000,
        "runs": 1_000_000,
        "connected_accounts": 2_000,
        "entities": 1_000,
        "keys": 100,
        "triggers": 250,
        "sessions": 500,
        "custom_tools": 100,
        "rate_per_min": 1_200,
        "retention_days": 365,
        "apps": "all",
        "actions": "all",
        "write": True,
        "support": "Priority, 4h",
        "highlights": [
            "1,000,000 action runs a month",
            "2,000 connected accounts, 1,000 end-user identities",
            "100 keys, 250 triggers, 500 agent sessions",
            "1,200 requests a minute",
            "365-day run history",
            "Priority support and early features",
        ],
    },
}

PLAN_ORDER = ["free", "pro", "business"]


def plan_public(plan_id: str) -> dict[str, Any]:
    p = dict(PLANS.get(plan_id, PLANS["free"]))
    p["annual_ngn"] = p["price_ngn"] * 10  # two months free
    p["annual_usd"] = p["price_usd"] * 10
    return p


def all_plans() -> list[dict[str, Any]]:
    return [plan_public(p) for p in PLAN_ORDER]


# ── subscription resolution ──────────────────────────────────────────────
def get_subscription(s, user_id: str) -> Subscription | None:
    return s.scalar(select(Subscription).where(Subscription.user_id == user_id))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def effective_plan(sub: Subscription | None) -> str:
    if sub is None:
        return "free"
    end = _aware(sub.current_period_end)
    # A trial that nobody configured is not a plan. This also revokes trials
    # handed out by an older build, so nobody keeps Pro without paying.
    if sub.status == "trialing" and sub.provider == "none" and TRIAL_DAYS <= 0:
        return "free"
    if sub.status in {"active", "trialing"} and (end is None or end > _now()):
        return sub.plan if sub.plan in PLANS else "free"
    return "free"


def plan_id_for_workspace(ws: str) -> tuple[str, Subscription | None, User | None]:
    with session() as s:
        user = s.scalar(select(User).where(User.workspace_id == ws))
        if user is not None and user.email.lower() in admin_emails():
            sub = get_subscription(s, user.id)
            if sub is None:
                sub = Subscription(user_id=user.id, workspace_id=ws, plan="business",
                                   status="active", provider="admin",
                                   current_period_end=_now() + timedelta(days=3650))
                s.add(sub)
            else:
                sub.plan, sub.status, sub.provider = "business", "active", "admin"
                sub.current_period_end = max(_aware(sub.current_period_end) or _now(),
                                             _now() + timedelta(days=3650))
            s.flush()
            return "business", sub, user
        sub = get_subscription(s, user.id) if user else None
        return effective_plan(sub), sub, user


def admin_emails() -> set[str]:
    raw = os.getenv("TONY_ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def ensure_subscription(s, user: User) -> Subscription:
    """New accounts start on a full Pro trial, then glide to Free."""
    sub = get_subscription(s, user.id)
    if sub is not None:
        return sub
    now = _now()
    if user.email.lower() in admin_emails():
        sub = Subscription(user_id=user.id, workspace_id=user.workspace_id, plan="business",
                           status="active", provider="admin",
                           current_period_start=now, current_period_end=now + timedelta(days=3650))
    elif TRIAL_DAYS > 0:
        sub = Subscription(user_id=user.id, workspace_id=user.workspace_id, plan="pro",
                           status="trialing", provider="none", current_period_start=now,
                           current_period_end=now + timedelta(days=TRIAL_DAYS),
                           trial_ends_at=now + timedelta(days=TRIAL_DAYS))
    else:
        sub = Subscription(user_id=user.id, workspace_id=user.workspace_id, plan="free",
                           status="active", provider="none",
                           current_period_start=now, current_period_end=now + timedelta(days=3650))
    s.add(sub)
    s.flush()
    return sub


def _period_start() -> datetime:
    now = _now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_for(ws: str) -> dict[str, int]:
    start = _period_start()
    with session() as s:
        runs = s.scalar(select(func.count(ActionRun.id)).where(
            ActionRun.workspace_id == ws, ActionRun.created_at >= start)) or 0
        from .models import ReadJob

        read_pages = s.scalar(select(func.coalesce(func.sum(ReadJob.fetched), 0)).where(
            ReadJob.workspace_id == ws, ReadJob.created_at >= start)) or 0
        return {
            "runs": int(runs),
            "read_pages": int(read_pages),
            "connected_accounts": int(s.scalar(select(func.count(ConnectedAccount.id)).where(
                ConnectedAccount.workspace_id == ws,
                ConnectedAccount.status == "active")) or 0),
            "entities": int(s.scalar(select(func.count(Entity.id)).where(
                Entity.workspace_id == ws)) or 0),
            "keys": int(s.scalar(select(func.count(ApiKey.id)).where(
                ApiKey.workspace_id == ws, ApiKey.revoked.is_(False))) or 0),
            "triggers": int(s.scalar(select(func.count(Trigger.id)).where(
                Trigger.workspace_id == ws)) or 0),
            "sessions": int(s.scalar(select(func.count(AgentSession.id)).where(
                AgentSession.workspace_id == ws, AgentSession.revoked.is_(False))) or 0),
            "custom_tools": int(s.scalar(select(func.count(__import__("tony.models", fromlist=["CustomTool"]).CustomTool.id)).where(
                __import__("tony.models", fromlist=["CustomTool"]).CustomTool.workspace_id == ws)) or 0),
        }


def _limit_key(kind: str) -> str:
    return {"connections": "connected_accounts", "connected_accounts": "connected_accounts"}.get(kind, kind)


def summary(ws: str) -> dict[str, Any]:
    plan_id, sub, user = plan_id_for_workspace(ws)
    plan = plan_public(plan_id)
    usage = usage_for(ws)
    limits = {k: plan[k] for k in
              ("runs", "connected_accounts", "entities", "keys", "triggers", "sessions",
               "custom_tools", "rate_per_min", "retention_days")}
    end = _aware(sub.current_period_end) if sub else None
    return {
        "plan": plan,
        "plan_id": plan_id,
        "status": sub.status if sub else "active",
        "provider": sub.provider if sub else "none",
        "trial": bool(sub and sub.status == "trialing"),
        "paid": bool(sub and sub.status == "active"
                     and sub.provider in {"paystack", "passcode", "admin", "stripe"}),
        "period_start": (sub.current_period_start.isoformat() if sub and sub.current_period_start else _period_start().isoformat()),
        "period_end": end.isoformat() if end else None,
        "days_left": max(0, (end - _now()).days) if end else None,
        "cancel_at_period_end": bool(sub and sub.cancel_at_period_end),
        "usage": usage,
        "limits": limits,
        "remaining": {k: max(0, limits.get(k, 10**9) - usage[k]) for k in usage},
        "user": {"email": user.email, "id": user.id} if user else None,
        "upgrade_url": "/app",
    }


# ── enforcement ──────────────────────────────────────────────────────────
def _upgrade_error(plan: dict, kind: str, used: int, limit: int) -> HTTPException:
    return HTTPException(
        402,
        detail={
            "error": f"{plan['name']} plan limit reached for {kind.replace('_', ' ')} ({used:,}/{limit:,}).",
            "kind": kind,
            "plan": plan["id"],
            "used": used,
            "limit": limit,
            "upgrade": "Open /app → Billing to move up a tier. Free keeps every app and action available.",
        },
    )


def check_run(ws: str) -> dict[str, Any]:
    """Raise 402 when this workspace is out of runs for the month."""
    plan_id, _sub, _user = plan_id_for_workspace(ws)
    plan = PLANS[plan_id]
    used = usage_for(ws)["runs"]
    if used >= plan["runs"]:
        raise _upgrade_error(plan, "runs", used, plan["runs"])
    return {"plan": plan_id, "used": used, "limit": plan["runs"]}


def check_capacity(ws: str, kind: str) -> None:
    kind = _limit_key(kind)
    plan_id, _sub, _user = plan_id_for_workspace(ws)
    plan = PLANS[plan_id]
    raw = plan.get(kind)
    limit = 10**9 if raw is None else int(raw)
    used = usage_for(ws).get(kind, 0)
    if used >= limit:
        raise _upgrade_error(plan, kind, used, limit)


def read_page_limit(ws: str) -> int:
    plan_id, _sub, _user = plan_id_for_workspace(ws)
    return int(PLANS.get(plan_id, PLANS["free"]).get("read_pages", 3000))


def read_budget_left(ws: str) -> int:
    return max(0, read_page_limit(ws) - int(usage_for(ws).get("read_pages", 0)))


def rate_for(ws: str) -> int:
    plan_id, _sub, _user = plan_id_for_workspace(ws)
    return int(PLANS[plan_id]["rate_per_min"])


# ── sessions helpers ─────────────────────────────────────────────────────
def session_public(row: AgentSession) -> dict[str, Any]:
    exp = _aware(row.expires_at)
    return {
        "id": row.id,
        "entity_id": row.entity_id,
        "label": row.label,
        "apps": [a for a in (row.allowed_apps or "").split(",") if a] or ["*"],
        "tiers": [t for t in (row.allowed_tiers or "read").split(",") if t],
        "run_limit": row.run_limit,
        "runs_used": row.runs_used,
        "runs_left": max(0, row.run_limit - row.runs_used) if row.run_limit else None,
        "expires_at": exp.isoformat() if exp else None,
        "expired": bool(exp and exp <= _now()),
        "revoked": row.revoked,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }


def resolve_session(request: Request, ws: str) -> AgentSession | None:
    """Optional X-Tony-Session header pins a call to one end-user and one budget."""
    sid = (request.headers.get("x-tony-session") or "").strip()
    if not sid:
        return None
    with session() as s:
        row = s.scalar(select(AgentSession).where(AgentSession.id == sid, AgentSession.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown session for this workspace")
        if row.revoked:
            raise HTTPException(403, detail="This session was revoked")
        exp = _aware(row.expires_at)
        if exp and exp <= _now():
            raise HTTPException(403, detail="Session expired. Create a new one at POST /v1/sessions.")
        if row.run_limit and row.runs_used >= row.run_limit:
            raise HTTPException(402, detail="Session run budget used up. Raise run_limit or open a new session.")
        return row


def enforce_session(sess: AgentSession | None, app_slug: str, tier: str) -> None:
    if sess is None:
        return
    apps = [a for a in (sess.allowed_apps or "").split(",") if a]
    if apps and app_slug not in apps:
        raise HTTPException(403, detail=f"Session is scoped to {', '.join(apps)}; {app_slug} is outside it.")
    tiers = [t for t in (sess.allowed_tiers or "read").split(",") if t]
    if tier not in tiers:
        raise HTTPException(403, detail=f"Session allows {', '.join(tiers)} actions; this one is {tier}.")


def touch_session(sess: AgentSession | None) -> None:
    if sess is None:
        return
    with session() as s:
        row = s.get(AgentSession, sess.id)
        if row is None:
            return
        row.runs_used = (row.runs_used or 0) + 1
        row.last_used_at = _now()


# ── payments ─────────────────────────────────────────────────────────────
def paystack_key() -> str:
    return os.getenv("PAYSTACK_SECRET_KEY", "").strip()


def payments_ready() -> bool:
    return bool(paystack_key())


def _amount(plan_id: str, months: int) -> int:
    plan = PLANS[plan_id]
    months = max(1, min(int(months or 1), 12))
    total = plan["price_ngn"] * (10 if months == 12 else months)
    return int(total * 100)


class CheckoutIn(BaseModel):
    plan: str
    months: int = 1


@router.get("/plans")
def plans() -> dict[str, Any]:
    return {"plans": all_plans(), "currency": "NGN",
            "trial_days": TRIAL_DAYS, "payments_ready": payments_ready(),
            "note": "Free includes every app and action. Upgrade only when you need volume."}


@router.get("/me")
def billing_me(request: Request) -> dict[str, Any]:
    from .auth import workspace_from_request

    ws, _demo = workspace_from_request(request)
    return summary(ws)


@router.post("/checkout")
async def checkout(body: CheckoutIn, request: Request) -> dict[str, Any]:
    from .accounts import require_user

    user = require_user(request)
    if body.plan not in PLANS:
        raise HTTPException(404, detail="Unknown plan")
    if body.plan == "free":
        raise HTTPException(400, detail="Free is already free. Nothing to pay.")
    months = max(1, min(int(body.months or 1), 12))
    amount = _amount(body.plan, months)
    reference = f"tony_{user.id[:8]}_{secrets.token_hex(6)}"
    with session() as s:
        s.add(PaymentEvent(user_id=user.id, workspace_id=user.workspace_id, provider="paystack",
                           reference=reference, plan=body.plan, months=months,
                           amount=amount, currency="NGN", status="pending"))
    if not payments_ready():
        raise HTTPException(
            503,
            detail={
                "error": "Card payments are not switched on yet: this deployment has no PAYSTACK_SECRET_KEY.",
                "still_works": "Every feature is usable on the free tier right now, and a pass code unlocks a paid tier instantly.",
                "fix": "Add PAYSTACK_SECRET_KEY (and PAYSTACK_PUBLIC_KEY) in Render → Environment, then retry.",
                "reference": reference,
            },
        )
    payload = {
        "email": user.email,
        "amount": amount,
        "currency": "NGN",
        "reference": reference,
        "callback_url": f"{settings.base_url}/app?billing=verify&reference={reference}",
        "metadata": {"user_id": user.id, "workspace_id": user.workspace_id,
                     "plan": body.plan, "months": months, "product": "tony"},
    }
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(f"{PAYSTACK_API}/transaction/initialize", json=payload,
                              headers={"Authorization": f"Bearer {paystack_key()}"})
    if r.status_code >= 400:
        raise HTTPException(502, detail=f"Paystack rejected the checkout ({r.status_code}): {r.text[:200]}")
    data = r.json().get("data") or {}
    return {"authorization_url": data.get("authorization_url"), "reference": reference,
            "amount_ngn": amount // 100, "plan": body.plan, "months": months}


def _activate_payment(reference: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    with session() as s:
        ev = s.scalar(select(PaymentEvent).where(PaymentEvent.reference == reference))
        if ev is None:
            raise HTTPException(404, detail="Unknown payment reference")
        if ev.status == "paid":
            return {"ok": True, "already": True, "plan": ev.plan}
        user = s.get(User, ev.user_id)
        if user is None:
            raise HTTPException(404, detail="Payer account no longer exists")
        sub = ensure_subscription(s, user)
        now = _now()
        base = _aware(sub.current_period_end) if sub.current_period_end and _aware(sub.current_period_end) > now else now
        sub.plan, sub.status, sub.provider = ev.plan, "active", "paystack"
        sub.external_ref = reference
        sub.current_period_start = now
        sub.current_period_end = base + timedelta(days=30 * ev.months)
        sub.cancel_at_period_end = False
        ev.status = "paid"
        ev.paid_at = now
        if payload:
            ev.raw_json = json.dumps(payload, default=str)[:20000]
        if ev.workspace_id and not sub.workspace_id:
            sub.workspace_id = ev.workspace_id
        s.flush()
        return {"ok": True, "plan": ev.plan, "period_end": sub.current_period_end.isoformat()}


@router.get("/verify")
async def verify(reference: str) -> dict[str, Any]:
    if not payments_ready():
        raise HTTPException(503, detail="Payments are not configured on this deployment")
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(f"{PAYSTACK_API}/transaction/verify/{reference}",
                             headers={"Authorization": f"Bearer {paystack_key()}"})
    data = (r.json() or {}).get("data") or {}
    if r.status_code >= 400 or data.get("status") != "success":
        return {"ok": False, "status": data.get("status") or r.status_code, "reference": reference}
    return _activate_payment(reference, data)


@router.post("/webhook/paystack")
async def paystack_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body()
    secret = paystack_key()
    if secret:
        sig = request.headers.get("x-paystack-signature", "")
        expected = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(401, detail="Bad signature")
    try:
        event: dict[str, Any] = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, detail="Bad payload")
    if event.get("event") == "charge.success":
        ref = ((event.get("data") or {}).get("reference")) or ""
        if ref:
            try:
                _activate_payment(ref, event.get("data"))
            except HTTPException as exc:
                log.warning("webhook could not activate %s: %s", ref, exc.detail)
    return {"ok": True}


class PasscodeIn(BaseModel):
    code: str


@router.post("/passcode")
def redeem_passcode(body: PasscodeIn, request: Request) -> dict[str, Any]:
    """Owner-issued codes: 'CODE:plan:days' pairs in TONY_PASS_CODES."""
    from .accounts import require_user

    user = require_user(request)
    code = (body.code or "").strip()
    table: dict[str, tuple[str, int]] = {}
    for chunk in os.getenv("TONY_PASS_CODES", "").split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, rest = chunk.split(":", 1)
        parts = rest.split(":")
        plan = parts[0] if parts and parts[0] in PLANS else "pro"
        days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
        table[name.strip().upper()] = (plan, days)
    plan_days = table.get(code.upper())
    if not plan_days:
        raise HTTPException(400, detail="That pass code is not valid on this deployment.")
    plan, days = plan_days
    with session() as s:
        sub = ensure_subscription(s, user)
        now = _now()
        base = _aware(sub.current_period_end) if sub.current_period_end and _aware(sub.current_period_end) > now else now
        sub.plan, sub.status, sub.provider = plan, "active", "passcode"
        sub.external_ref = f"passcode:{code.upper()}"
        sub.current_period_start = now
        sub.current_period_end = base + timedelta(days=days)
        sub.cancel_at_period_end = False
        s.flush()
        return {"ok": True, "plan": plan, "days": days, "period_end": sub.current_period_end.isoformat()}


@router.post("/cancel")
def cancel(request: Request) -> dict[str, Any]:
    from .accounts import require_user

    user = require_user(request)
    with session() as s:
        sub = ensure_subscription(s, user)
        sub.cancel_at_period_end = True
        s.flush()
        return {"ok": True, "cancel_at_period_end": True,
                "period_end": sub.current_period_end.isoformat() if sub.current_period_end else None}


@router.post("/resume")
def resume(request: Request) -> dict[str, Any]:
    from .accounts import require_user

    user = require_user(request)
    with session() as s:
        sub = ensure_subscription(s, user)
        sub.cancel_at_period_end = False
        s.flush()
        return {"ok": True, "cancel_at_period_end": False}
