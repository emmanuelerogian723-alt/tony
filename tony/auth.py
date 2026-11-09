"""Workspace API-key auth, demo quota and small helpers."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request
from sqlalchemy import select

from .config import settings
from .crypto import hash_api_key
from .db import session
from .models import ApiKey, Workspace

_WINDOW = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(bucket: str, limit: int, window: float = _WINDOW) -> None:
    now = time.time()
    q = _hits[bucket]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, detail=f"Rate limit reached ({limit}/min). Slow down or use an API key.")
    q.append(now)


def _extract_key(authorization: str | None, x_api_key: str | None) -> str:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return ""


def workspace_from_key(key: str) -> str | None:
    if not key.startswith("tk_"):
        return None
    digest = hash_api_key(key)
    prefix = key[:16]
    with session() as s:
        row = s.scalar(select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked.is_(False)))
        if row is None or row.key_hash != digest:
            return None
        row.last_used_at = datetime.now(timezone.utc)
        return row.workspace_id


def workspace_from_request(request: Request) -> tuple[str, bool]:
    """Returns (workspace_id, is_demo_session). Raises 401 when unavailable."""
    from . import agenttokens

    raw = _extract_key(request.headers.get("authorization"), request.headers.get("x-api-key"))
    scope = agenttokens.verify(raw) if raw else None
    if scope:
        request.state.agent_scope = scope
        return scope["ws"], False
    return _workspace_from_request_inner(request)


def _workspace_from_request_inner(request: Request) -> tuple[str, bool]:
    key = _extract_key(request.headers.get("authorization"), request.headers.get("x-api-key"))
    if key:
        ws = workspace_from_key(key)
        if ws:
            return ws, False
        raise HTTPException(401, detail="Invalid API key")
    # a signed-in console user acts as their own workspace
    try:
        from .accounts import current_user  # local import: accounts imports this module

        cookie_user = current_user(request)
        if cookie_user is not None and cookie_user.workspace_id:
            return cookie_user.workspace_id, False
    except Exception:  # pragma: no cover - never block the demo path on a session bug
        pass
    if settings.demo_open:
        with session() as s:
            ws = s.scalar(select(Workspace).where(Workspace.is_demo.is_(True)))
        if ws:
            return ws.id, True
    raise HTTPException(401, detail="Missing API key (send Authorization: Bearer tk_live_...)")


async def require_workspace(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    ws, is_demo = workspace_from_request(request)
    if is_demo:
        client = request.client.host if request.client else "unknown"
        rate_limit(f"demo:{client}", settings.demo_rate_limit)
    return ws
