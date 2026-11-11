"""Tony Shield: behavioural abuse detection for the API.

A plain rate limit stops a flood but not a careful bot. Shield scores *behaviour*:
credential stuffing, endpoint scanning, burst-then-rotate, scripted user agents,
and writes without prior reads. Scores decay, so a legitimate burst heals on its
own, while a persistent offender gets a timed block that doubles on repeat.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select

from .db import session
from .models import BlockedSubject, SecurityEvent

BLOCK_AT = 100          # score at which a subject is blocked
HALF_LIFE = 120.0       # seconds for a score to halve
BASE_BLOCK = 600        # first block lasts ten minutes, then doubles

# Genuine attack tooling. These earn points on their own.
BOT_UA = re.compile(
    r"(sqlmap|nikto|nmap|masscan|zgrab|gobuster|dirbuster|wpscan|acunetix|nessus|hydra|"
    r"libwww-perl|scrapy)", re.I)
# Scripted clients and headless browsers. Every developer tests with these, so they
# only score when the caller is also sweeping many endpoints, never for one request.
SOFT_UA = re.compile(
    r"(python-requests|python-urllib|^curl/|go-http-client|httpclient$|"
    r"headlesschrome|phantomjs|node-fetch|axios|okhttp)", re.I)

# Page views are always readable: only the API can be blocked for behaviour.
# Every other path is a screen a person loads in a browser, including the connect
# pages and /oauth/callback that a sign-in returns to, so they must never be blocked.
_API_PREFIXES = ("/v1", "/mcp", "/api")
PROBE_PATHS = re.compile(
    r"(/\.env|/\.git|/wp-admin|/wp-login|/phpmyadmin|/admin\.php|/xmlrpc|/etc/passwd|"
    r"/cgi-bin|/vendor/phpunit|\.\./|%2e%2e|/actuator|/server-status|/\.aws|/id_rsa)", re.I)

_score: dict[str, tuple[float, float]] = {}          # subject -> (score, last_update)
_recent_paths: dict[str, deque] = defaultdict(lambda: deque(maxlen=40))
_recent_fail: dict[str, deque] = defaultdict(lambda: deque(maxlen=30))
_block_cache: dict[str, float] = {}                  # subject -> expiry epoch


def _decayed(subject: str, now: float) -> float:
    score, at = _score.get(subject, (0.0, now))
    return score * (0.5 ** ((now - at) / HALF_LIFE))


def _add(subject: str, points: float, now: float) -> float:
    total = _decayed(subject, now) + points
    _score[subject] = (total, now)
    return total


def subject_of(request: Request) -> str:
    """The caller's address. Behind Render's proxy the *last* x-forwarded-for entry is the one the
    proxy itself appended; earlier entries are client-supplied and can be spoofed to frame someone."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[-1][:80]
    return (request.client.host if request.client else "unknown")[:80]


def _record(subject: str, kind: str, detail: str, score: int, blocked: bool) -> None:
    try:
        with session() as s:
            s.add(SecurityEvent(subject=subject[:120], kind=kind, detail=detail[:300],
                                score=int(score), blocked=blocked))
    except Exception:  # noqa: BLE001  logging must never break a request
        pass


def _block(subject: str, reason: str, now: float) -> None:
    with session() as s:
        row = s.scalar(select(BlockedSubject).where(BlockedSubject.subject == subject))
        prior = 0
        if row is not None:
            prior = max(0, int((row.expires_at - row.created_at).total_seconds() // BASE_BLOCK).bit_length() - 1)
            s.delete(row)
            s.flush()
        seconds = BASE_BLOCK * (2 ** min(prior + 1, 6)) if row is not None else BASE_BLOCK
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        s.add(BlockedSubject(subject=subject, reason=reason[:200], expires_at=until))
    _block_cache[subject] = now + seconds


def is_blocked(subject: str) -> bool:
    now = time.time()
    cached = _block_cache.get(subject)
    if cached is not None:
        if cached > now:
            return True
        _block_cache.pop(subject, None)
    try:
        with session() as s:
            row = s.scalar(select(BlockedSubject).where(BlockedSubject.subject == subject))
            if row is None:
                return False
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if exp <= datetime.now(timezone.utc):
                s.delete(row)
                return False
            _block_cache[subject] = exp.timestamp()
            return True
    except Exception:  # noqa: BLE001
        return False


def inspect(request: Request) -> None:
    """Call on every API request. Raises 403 when the caller is blocked or has just earned a block."""
    path = request.url.path
    if path in {"/health", "/favicon.ico"} or path.startswith("/static"):
        return
    # Provider webhooks arrive in bursts, from shared provider IPs, signed and
    # deduplicated. Behavioural scoring would frame them for their neighbours.
    if path.startswith("/v1/hooks/"):
        return
    page_view = request.method in {"GET", "HEAD"} and not path.startswith(_API_PREFIXES)
    probed = bool(PROBE_PATHS.search(path) or PROBE_PATHS.search(request.url.query or ""))
    # A visitor reading pages is never scored or blocked. Probing for /.env still is.
    if page_view and not probed:
        return
    subject = subject_of(request)
    if is_blocked(subject):
        raise HTTPException(403, detail="Blocked for suspicious activity. This clears on its own; "
                                         "contact the workspace owner if you think it is a mistake.")
    now = time.time()
    ua = request.headers.get("user-agent", "")
    is_write = request.method not in {"GET", "HEAD", "OPTIONS"}
    points, reasons = 0.0, []

    if PROBE_PATHS.search(path) or PROBE_PATHS.search(request.url.query or ""):
        points += 60; reasons.append("probe_path")
    if BOT_UA.search(ua) and not page_view:
        points += 35; reasons.append("scanner_ua")
    if not ua and path.startswith("/v1/"):
        points += 4; reasons.append("no_ua")

    paths = _recent_paths[subject]
    paths.append((now, path))
    window = [p for t, p in paths if now - t < 20]
    distinct = len(set(window))
    # Reading is not abuse: an app screen legitimately fires a dozen GETs at once,
    # and a headless browser rendering it looks identical to a user. Writes earn
    # sweep and burst points; a scripted client only reading gets a light nudge.
    if is_write:
        if SOFT_UA.search(ua) and distinct >= 8:
            points += 20; reasons.append("scripted_sweep")  # a script walking many routes
        if len(window) >= 18 and distinct >= 15:
            points += 30; reasons.append("endpoint_sweep")  # walking many routes fast
        if len(window) >= 30:
            points += 12; reasons.append("burst")
    elif SOFT_UA.search(ua) and distinct >= 8:
        points += 4; reasons.append("scripted_reads")

    if not points:
        return
    total = _add(subject, points, now)
    blocked = total >= BLOCK_AT
    _record(subject, ",".join(reasons), f"{request.method} {path[:120]}", total, blocked)
    if blocked:
        _block(subject, ",".join(reasons), now)
        raise HTTPException(403, detail="Blocked for suspicious activity.")


def note_auth_failure(request: Request, kind: str = "bad_key") -> None:
    """Call when a credential is rejected. Repeated failures are credential stuffing."""
    subject = subject_of(request)
    now = time.time()
    fails = _recent_fail[subject]
    fails.append(now)
    recent = [t for t in fails if now - t < 300]
    points = 8 + max(0, len(recent) - 3) * 6
    total = _add(subject, points, now)
    blocked = total >= BLOCK_AT
    _record(subject, kind, f"{len(recent)} failed credentials in 5 min", total, blocked)
    if blocked:
        _block(subject, f"credential_stuffing:{len(recent)}", now)
        raise HTTPException(403, detail="Too many rejected credentials. Try again later.")


def reset() -> None:
    _score.clear(); _recent_paths.clear(); _recent_fail.clear(); _block_cache.clear()


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    with session() as s:
        rows = s.scalars(select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(limit)).all()
        return [{"at": r.created_at.isoformat(timespec="seconds"), "subject": r.subject, "kind": r.kind,
                 "detail": r.detail, "score": r.score, "blocked": r.blocked} for r in rows]
