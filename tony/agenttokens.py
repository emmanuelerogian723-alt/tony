"""Scoped agent tokens: hand a narrow slice of Tony to any AI, not your whole account.

A token carries its own workspace, its allowed apps, its allowed tiers and an
expiry, signed with HMAC so Tony can verify it without a database lookup or a
schema migration. That is the difference between "an agent can do everything I
can" and "this agent may read Hacker News for seven days".
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

PREFIX = "tony_at_"
TIERS = ("read", "write", "destructive")


def _secret() -> bytes:
    raw = (os.getenv("TONY_TOKEN_SECRET") or "").strip()
    if raw:
        return raw.encode()
    # Stable fallback so tokens survive restarts even when the secret is unset.
    seed = (os.getenv("DATABASE_URL") or "tony-local-dev").encode()
    return hashlib.sha256(b"tony-agent-token-v1:" + seed).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str) -> str:
    return hmac.new(_secret(), payload_b64.encode(), hashlib.sha256).hexdigest()[:40]


def issue(workspace_id: str, name: str = "agent", apps: list[str] | None = None,
          tiers: list[str] | None = None, ttl_days: int = 7) -> dict[str, Any]:
    """Mint a token. apps=None means every app, tiers default to read-only."""
    tiers = [t for t in (tiers or ["read"]) if t in TIERS] or ["read"]
    now = int(time.time())
    payload = {
        "ws": workspace_id,
        "name": (name or "agent")[:60],
        "apps": [a.strip() for a in (apps or []) if a.strip()],
        "tiers": tiers,
        "iat": now,
        "exp": now + max(1, min(ttl_days, 365)) * 86400,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    return {"token": f"{PREFIX}{body}.{_sign(body)}", "payload": payload,
            "scopes": {"apps": payload["apps"] or ["*"], "tiers": tiers},
            "expires_in_days": max(1, min(ttl_days, 365))}


def verify(token: str) -> dict[str, Any] | None:
    """Return the payload for a valid token, else None. Never raises."""
    if not token or not token.startswith(PREFIX):
        return None
    try:
        body, _, sig = token[len(PREFIX):].partition(".")
        if not body or not sig or not hmac.compare_digest(sig, _sign(body)):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        if not payload.get("ws"):
            return None
        return payload
    except Exception:  # noqa: BLE001 - a malformed token is simply invalid
        return None


def allows(payload: dict[str, Any] | None, app_slug: str, tier: str) -> bool:
    """Is this app and tier inside the token's grant?"""
    if not payload:
        return True  # not an agent token: normal workspace auth rules apply
    apps = payload.get("apps") or []
    tiers = payload.get("tiers") or ["read"]
    app_ok = not apps or app_slug in apps
    tier_ok = tier in tiers
    return app_ok and tier_ok


def describe(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    apps = ", ".join(payload.get("apps") or ["all apps"])
    return f"{payload.get('name', 'agent')} ({apps}; {', '.join(payload.get('tiers') or ['read'])})"
