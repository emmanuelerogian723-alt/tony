"""Workspace API-key auth, demo quota and small helpers."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from fastapi import Header, HTTPException, Request
from sqlalchemy import select

from .config import settings
from .crypto import hash_api_key
from .db import session
from .models import ApiKey

_WINDOW = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)


_MAX_BUCKETS = 20_000


# The request being served, so a limiter deep in the call stack can publish the
# caller's remaining budget without every call site passing the request along.
_CURRENT: ContextVar[Any] = ContextVar("tony_request", default=None)


def bind_request(request: Any) -> Any:
    return _CURRENT.set(request)


def unbind_request(token: Any) -> None:
    _CURRENT.reset(token)


def rate_limit(bucket: str, limit: int, window: float = _WINDOW,
               request: Any = None) -> None:
    now = time.time()
    # Evict before growing: this map is keyed by caller address, and an address can
    # be invented per request, so without a ceiling it is a cheap memory DoS.
    if len(_hits) > _MAX_BUCKETS:
        cutoff = now - window
        for k in [k for k, q in _hits.items() if not q or q[-1] < cutoff][: _MAX_BUCKETS // 4]:
            _hits.pop(k, None)
    q = _hits[bucket]
    while q and now - q[0] > window:
        q.popleft()
    req = request or _CURRENT.get()
    used = len(q)
    if used >= limit:
        retry = max(1, int(round(window - (now - q[0]))) if q else int(window))
        _publish(req, limit, 0, retry)
        raise HTTPException(429, detail=f"Rate limit reached ({limit}/min). Slow down or use an API key.",
                            headers={"Retry-After": str(retry),
                                     "X-RateLimit-Limit": str(limit),
                                     "X-RateLimit-Remaining": "0",
                                     "X-RateLimit-Reset": str(retry)})
    q.append(now)
    _publish(req, limit, max(0, limit - (used + 1)), max(1, int(round(window - (now - q[0])))))


def _publish(req: Any, limit: int, remaining: int, retry_after: int) -> None:
    """Leave the caller's budget on the request for the header middleware."""
    if req is None:
        return
    try:
        req.state.rate = {"limit": limit, "remaining": remaining, "retry_after": retry_after}
    except Exception:  # pragma: no cover - an object with no state
        pass


def _extract_key(authorization: str | None, x_api_key: str | None) -> str:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return ""


def key_row(key: str) -> dict | None:
    """The live key's workspace, id and scope. Also stamps last_used_at."""
    if not key or not key.startswith("tk_"):
        return None
    digest = hash_api_key(key)
    prefix = key[:16]
    with session() as s:
        row = s.scalar(select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked.is_(False)))
        if row is None or row.key_hash != digest:
            return None
        row.last_used_at = datetime.now(timezone.utc)
        apps = [a.strip().lower() for a in (getattr(row, "scope_apps", "") or "").split(",") if a.strip()]
        mode = getattr(row, "mode", "full") or "full"
        return {"workspace_id": row.workspace_id, "key_id": row.id, "name": row.name,
                "apps": apps, "mode": mode, "read_only": mode == "read_only"}


def workspace_from_key(key: str) -> str | None:
    found = key_row(key)
    return found["workspace_id"] if found else None


def scope_for_request(request: Request) -> dict:
    """The calling key's restrictions. Empty means the whole workspace."""
    return getattr(request.state, "key_scope", None) or {}


def enforce_key_scope(request: Request, app_slug: str, tier: str) -> None:
    """Apply a key's app allowlist and read-only flag to one action."""
    scope = scope_for_request(request)
    if not scope:
        return
    apps = scope.get("apps") or []
    if apps and (app_slug or "").lower() not in apps:
        raise HTTPException(403, detail=(
            f"This API key is limited to {', '.join(sorted(apps))}. Create an unscoped key "
            "in the dashboard, or add this app to the key's scope."))
    if scope.get("read_only") and (tier or "read") != "read":
        raise HTTPException(403, detail=(
            f"This API key is read-only, so {app_slug}.{tier} actions are refused. "
            "Use a key with write access to run them."))


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
        found = key_row(key)
        if found:
            request.state.key_scope = found
            return found["workspace_id"], False
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
        # A demo is private per visitor: the shared "demo workspace" meant every
        # anonymous caller read every other caller's runs and connections. Each
        # visitor now gets an empty room of their own, proven by a signed token.
        from . import demo

        info = demo.current(request) or demo.provision(request)
        return info["workspace_id"], True
    raise HTTPException(401, detail="Missing API key (send Authorization: Bearer tk_live_...)")


async def require_workspace(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    ws, is_demo = workspace_from_request(request)
    if is_demo:
        # Per room, not per address: on shared carrier NAT one visitor's traffic
        # used to consume everyone else's budget.
        rate_limit(f"demo:{ws}", settings.demo_rate_limit)
    return ws
