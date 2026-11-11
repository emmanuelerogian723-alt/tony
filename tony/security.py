"""Owner-facing security endpoints: read the trail, lift a block, check posture."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from . import shield
from .accounts import require_user
from .db import session
from .models import BlockedSubject

router = APIRouter(prefix="/v1/security", tags=["security"])


@router.get("/events")
def events(request: Request, limit: int = 50) -> dict[str, Any]:
    require_user(request)
    return {"events": shield.recent_events(min(max(limit, 1), 200))}


@router.get("/blocked")
def blocked(request: Request) -> dict[str, Any]:
    require_user(request)
    with session() as s:
        rows = s.scalars(select(BlockedSubject).order_by(BlockedSubject.created_at.desc()).limit(100)).all()
        return {"blocked": [{"subject": r.subject, "reason": r.reason,
                             "until": r.expires_at.isoformat(timespec="seconds")} for r in rows]}


@router.delete("/blocked/{subject}")
def unblock(subject: str, request: Request) -> dict[str, Any]:
    require_user(request)
    with session() as s:
        row = s.scalar(select(BlockedSubject).where(BlockedSubject.subject == subject))
        if row is None:
            raise HTTPException(404, detail="That subject is not blocked")
        s.delete(row)
    shield._block_cache.pop(subject, None)
    return {"unblocked": subject}


@router.get("/posture")
def posture(request: Request) -> dict[str, Any]:
    require_user(request)
    return {"layers": [
        {"name": "Behavioural scoring", "detail": "probe paths, scanner agents, endpoint sweeps, bursts"},
        {"name": "Credential-stuffing guard", "detail": "repeated rejected keys raise a decaying score"},
        {"name": "Timed blocks", "detail": "10 minutes first, doubling on repeat, self-healing"},
        {"name": "Scoped agent tokens", "detail": "apps, tiers and expiry enforced on every call"},
        {"name": "Approval gate", "detail": "writes and deletes can wait for a human"},
        {"name": "Encrypted credentials", "detail": "tokens encrypted at rest, never returned by the API"},
        {"name": "Hosted consent", "detail": "users grant access on the provider's own page"},
        {"name": "Security headers", "detail": "nosniff, frame and referrer protection on every response"},
    ], "events_last_50": len(shield.recent_events(50))}
