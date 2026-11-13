"""Owner-facing security endpoints: read the trail, lift a block, check posture."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from . import agenttokens, shield
from .auth import workspace_from_request
from .db import session
from .models import BlockedSubject

router = APIRouter(prefix="/v1/security", tags=["security"])


@router.get("/events")
def events(request: Request, limit: int = 50) -> dict[str, Any]:
    workspace_from_request(request)          # API key or console session, same rule as /v1/execute
    return {"events": shield.recent_events(min(max(limit, 1), 200))}


@router.get("/blocked")
def blocked(request: Request) -> dict[str, Any]:
    workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(BlockedSubject).order_by(BlockedSubject.created_at.desc()).limit(100)).all()
        return {"blocked": [{"subject": r.subject, "reason": r.reason,
                             "until": r.expires_at.isoformat(timespec="seconds")} for r in rows]}


@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    """Is this caller blocked, and for how much longer?

    No credential is needed: a blocked visitor must be able to see why the API
    stopped answering and clear it themselves. This endpoint is exempt from the
    shield for exactly that reason.
    """
    subject = shield.subject_of(request)
    left = shield.block_remaining(subject)
    return {"subject": subject, "blocked": left > 0, "retry_after_seconds": left,
            "clear": "POST /v1/security/unblock",
            "note": "Blocks are per address, short, and self-healing."}


@router.post("/unblock")
def unblock_self(request: Request) -> dict[str, Any]:
    """Lift this caller's own block immediately.

    A behavioural block is a speed bump, not a sentence. Making people wait out a
    timer (or email support) when one script tripped the shield is how a security
    feature becomes an outage.
    """
    subject = shield.subject_of(request)
    with session() as s:
        rows = s.scalars(select(BlockedSubject).where(BlockedSubject.subject == subject)).all()
        for row in rows:
            s.delete(row)
        s.commit()
    shield._block_cache.pop(subject, None)
    shield._score.pop(subject, None)
    shield._recent_paths.pop(subject, None)
    shield._recent_fail.pop(subject, None)
    return {"unblocked": subject, "was_blocked": bool(rows)}


@router.delete("/blocked/{subject}")
def unblock(subject: str, request: Request) -> dict[str, Any]:
    workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(BlockedSubject).where(BlockedSubject.subject == subject))
        if row is None:
            raise HTTPException(404, detail="That subject is not blocked")
        s.delete(row)
    shield._block_cache.pop(subject, None)
    return {"unblocked": subject}


@router.get("/posture")
def posture(request: Request) -> dict[str, Any]:
    """Readable with the same credential that runs actions: an API key, an agent
    token or a console session. It used to demand a browser cookie, which made a
    perfectly valid key look broken on exactly the endpoint that proves safety."""
    ws, is_demo = workspace_from_request(request)
    scope = getattr(request.state, "agent_scope", None)
    return {"workspace": ws, "demo": is_demo,
            "credential": "agent_token" if scope else "api_key_or_session",
            "scope": agenttokens.describe(scope) if scope else "full workspace",
            "layers": [
        {"name": "Behavioural scoring", "detail": "probe paths, scanner agents, endpoint sweeps, bursts"},
        {"name": "Credential-stuffing guard", "detail": "repeated rejected keys raise a decaying score"},
        {"name": "Timed blocks", "detail": "10 minutes first, doubling on repeat, self-healing"},
        {"name": "Scoped agent tokens", "detail": "apps, tiers and expiry enforced on every call"},
        {"name": "Approval gate", "detail": "writes and deletes can wait for a human"},
        {"name": "Encrypted credentials", "detail": "tokens encrypted at rest, never returned by the API"},
        {"name": "Hosted consent", "detail": "users grant access on the provider's own page"},
        {"name": "Security headers", "detail": "nosniff, frame and referrer protection on every response"},
    ], "events_last_50": len(shield.recent_events(50))}
