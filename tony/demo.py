"""Private demo sessions.

The demo used to be one shared workspace: every anonymous visitor read the same
runs, the same connections and the same key, so one person's test was another
person's data. A demo must be a *room of one's own*.

Each visitor now gets a workspace of their own, proven by a signed cookie (or an
``X-Tony-Demo-Session`` header for clients without a cookie jar). The signature
covers the workspace id and its key, so a visitor cannot point the cookie at
someone else's room. Sessions expire: the cookie in ``demo_ttl_hours`` and the
workspace in ``demo_gc_hours``, so an abandoned demo does not live forever.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request, Response
from sqlalchemy import select

from .config import settings
from .crypto import new_api_key
from .db import session
from .models import ApiKey, Workspace

COOKIE = "tony_demo"
HEADER = "x-tony-demo-session"
_PREFIX = "d1"
_WS_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")
_KEY_RE = re.compile(r"^tk_[A-Za-z0-9_\-]{8,120}$")
_DEMO_NAME = "Demo session"


def ttl_hours() -> float:
    try:
        return max(1.0, float(settings.demo_ttl_hours))
    except (TypeError, ValueError):
        return 24.0


def gc_hours() -> float:
    try:
        return max(ttl_hours(), float(settings.demo_gc_hours))
    except (TypeError, ValueError):
        return 168.0


def _secret() -> bytes:
    raw = (settings.secret_key or "").strip()
    if raw:
        return hashlib.sha256(("tony-demo:" + raw).encode()).digest()
    # No configured secret: derive a stable one from the deployment identity so
    # sessions survive a restart but are useless anywhere else.
    basis = (settings.database_url or settings.base_url or "tony-local").encode()
    return hashlib.sha256(b"tony-demo:" + basis).digest()


def _sign(body: str) -> str:
    return hmac.new(_secret(), body.encode(), hashlib.sha256).hexdigest()[:40]


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes | None:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except Exception:  # noqa: BLE001
        return None


def mint_token(workspace_id: str, api_key: str) -> str:
    body = _b64(f"{workspace_id}.{api_key}".encode())
    return f"{_PREFIX}.{body}.{_sign(body)}"


def parse_token(token: str) -> tuple[str, str] | None:
    """Return (workspace_id, api_key) when the token is ours and untampered."""
    if not token or not token.startswith(_PREFIX + "."):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    _, body, sig = parts
    if not hmac.compare_digest(_sign(body), sig):
        return None
    decoded = _unb64(body)
    if decoded is None:
        return None
    try:
        workspace_id, api_key = decoded.decode().split(".", 1)
    except ValueError:
        return None
    if not _WS_RE.match(workspace_id) or not _KEY_RE.match(api_key):
        return None
    return workspace_id, api_key


def _token_from_request(request: Request) -> str:
    header = request.headers.get(HEADER, "")
    if header:
        return header.strip()
    return (request.cookies.get(COOKIE) or "").strip()


def _workspace_exists(workspace_id: str) -> bool:
    with session() as s:
        row = s.get(Workspace, workspace_id)
        return bool(row and row.is_demo)


def _create() -> tuple[str, str]:
    """A brand-new, empty room with its own key."""
    with session() as s:
        ws = Workspace(name=_DEMO_NAME, is_demo=True)
        s.add(ws)
        s.flush()
        plain, prefix, hashed = new_api_key()
        s.add(ApiKey(workspace_id=ws.id, name="demo", prefix=prefix, key_hash=hashed))
        s.commit()
        return ws.id, plain


def provision(request: Request) -> dict[str, Any]:
    """The caller's own demo room, created on first sight. Cached per request."""
    cached = getattr(request.state, "demo_session", None)
    if isinstance(cached, dict):
        return cached

    token = _token_from_request(request)
    parsed = parse_token(token)
    fresh = False
    workspace_id = api_key = ""
    if parsed and _workspace_exists(parsed[0]):
        workspace_id, api_key = parsed
    else:
        workspace_id, api_key = _create()
        token = mint_token(workspace_id, api_key)
        fresh = True

    info = {
        "workspace_id": workspace_id,
        "api_key": api_key,
        "token": token,
        "fresh": fresh,
        "expires_in": int(ttl_hours() * 3600),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=ttl_hours())).isoformat(timespec="seconds"),
    }
    request.state.demo_session = info
    if fresh:
        _housekeeping()
    return info


def current(request: Request) -> dict[str, Any] | None:
    """The caller's demo room if they already have one, without creating it."""
    cached = getattr(request.state, "demo_session", None)
    if isinstance(cached, dict):
        return cached
    parsed = parse_token(_token_from_request(request))
    if not parsed or not _workspace_exists(parsed[0]):
        return None
    info = {"workspace_id": parsed[0], "api_key": parsed[1],
            "token": _token_from_request(request), "fresh": False,
            "expires_in": int(ttl_hours() * 3600)}
    request.state.demo_session = info
    return info


def attach(request: Request, response: Response) -> dict[str, Any] | None:
    """Set the signed cookie and the header when this request minted a room."""
    info = getattr(request.state, "demo_session", None)
    if not isinstance(info, dict):
        return None
    response.headers[HEADER] = info["token"]
    if info.get("fresh") and settings.demo_open:
        response.set_cookie(
            COOKIE, info["token"],
            max_age=int(ttl_hours() * 3600),
            httponly=True,
            samesite="lax",
            secure=settings.base_url.startswith("https"),
            path="/",
        )
        info["fresh"] = False
    return info


def _housekeeping() -> None:
    """Drop old, empty demo rooms. Never touch a room that still holds work."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=gc_hours())
    try:
        with session() as s:
            rows = s.scalars(select(Workspace).where(Workspace.is_demo.is_(True))).all()
            for ws in rows:
                created = ws.created_at if ws.created_at.tzinfo else ws.created_at.replace(tzinfo=timezone.utc)
                if created > cutoff or ws.name != _DEMO_NAME:
                    continue
                if s.scalar(select(ApiKey).where(ApiKey.workspace_id == ws.id, ApiKey.last_used_at.isnot(None))):
                    continue
                for key in s.scalars(select(ApiKey).where(ApiKey.workspace_id == ws.id)).all():
                    s.delete(key)
                s.delete(ws)
            s.commit()
    except Exception:  # noqa: BLE001 - housekeeping must never break a request
        pass
