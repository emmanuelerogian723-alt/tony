"""Per-end-user agent sessions.

A session is the safe way to let an agent act for a specific person: it pins the
entity, narrows which apps and tiers are allowed, carries its own run budget and
expires on its own. Your workspace key stays server-side.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .billing import check_capacity, session_public, summary
from .catalog import catalog
from .db import session as db
from .models import AgentSession

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

VALID_TIERS = {"read", "write", "destructive"}


class SessionIn(BaseModel):
    entity_id: str = "default"
    label: str = ""
    apps: list[str] = Field(default_factory=list)
    tiers: list[str] = Field(default_factory=lambda: ["read", "write"])
    ttl_hours: int = 24
    run_limit: int = 0


def _ws(request: Request) -> str:
    from .auth import workspace_from_request

    ws, _demo = workspace_from_request(request)
    return ws


@router.get("")
def list_sessions(request: Request) -> dict[str, Any]:
    ws = _ws(request)
    with db() as s:
        rows = s.scalars(select(AgentSession).where(AgentSession.workspace_id == ws)
                         .order_by(AgentSession.created_at.desc()).limit(200)).all()
        return {"sessions": [session_public(r) for r in rows], "billing": summary(ws)}


@router.post("")
def create_session(body: SessionIn, request: Request) -> dict[str, Any]:
    ws = _ws(request)
    check_capacity(ws, "sessions")
    apps = [a.strip().lower() for a in body.apps if a.strip()]
    unknown = [a for a in apps if catalog.get(a) is None]
    if unknown:
        raise HTTPException(400, detail=f"Unknown app(s): {', '.join(unknown[:6])}")
    tiers = [t for t in (body.tiers or ["read"]) if t in VALID_TIERS]
    if not tiers:
        raise HTTPException(400, detail="Pick at least one of read, write, destructive")
    ttl = max(1, min(int(body.ttl_hours or 24), 24 * 30))
    limit = max(0, min(int(body.run_limit or 0), 5_000_000))
    now = datetime.now(timezone.utc)
    with db() as s:
        row = AgentSession(
            workspace_id=ws,
            entity_id=(body.entity_id or "default").strip()[:160],
            label=(body.label or "")[:160],
            allowed_apps=",".join(apps),
            allowed_tiers=",".join(tiers),
            run_limit=limit,
            expires_at=now + timedelta(hours=ttl),
        )
        s.add(row)
        s.flush()
        data = session_public(row)
        data["how_to_use"] = ("Send X-Tony-Session: " + row.id + " with every /v1/execute or MCP call. "
                              "Calls are pinned to this entity, apps and tier list.")
        return data


@router.get("/{session_id}")
def get_session(session_id: str, request: Request) -> dict[str, Any]:
    ws = _ws(request)
    with db() as s:
        row = s.scalar(select(AgentSession).where(AgentSession.id == session_id,
                                                  AgentSession.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Session not found")
        return session_public(row)


@router.post("/{session_id}/extend")
def extend_session(session_id: str, hours: int = 24, request: Request = None) -> dict[str, Any]:
    ws = _ws(request)
    with db() as s:
        row = s.scalar(select(AgentSession).where(AgentSession.id == session_id,
                                                  AgentSession.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Session not found")
        base = row.expires_at if row.expires_at and row.expires_at > datetime.now(timezone.utc) else datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        row.expires_at = base + timedelta(hours=max(1, min(int(hours), 24 * 30)))
        s.flush()
        return session_public(row)


@router.delete("/{session_id}")
def revoke_session(session_id: str, request: Request) -> dict[str, Any]:
    ws = _ws(request)
    with db() as s:
        row = s.scalar(select(AgentSession).where(AgentSession.id == session_id,
                                                  AgentSession.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Session not found")
        row.revoked = True
        s.flush()
        return {"ok": True, "id": session_id, "revoked": True}
