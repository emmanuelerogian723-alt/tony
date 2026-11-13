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

BLOCK_AT = 100          # score at which a subject is blocked (hard signals only)
HALF_LIFE = 120.0       # seconds for a score to halve
BASE_BLOCK = 600        # a genuine probe stays blocked for ten minutes
SOFT_BLOCK = 240        # behaviour-only blocks are short: they exist to slow a bot, not jail a person
MAX_BLOCK = 3600        # no block outlives an hour, however noisy the caller

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

# A request carrying a credential the API will verify is never jailed for its
# traffic shape. Only an unmistakable attack signal (probing for secrets, attack
# tooling) can block it, because a valid key is the caller's identity.
_HARD_REASONS = {"probe_path", "scanner_ua"}
_SHIELD_EXEMPT = ("/health", "/favicon.ico", "/static", "/v1/icon", "/v1/hooks/",
                  "/v1/security/unblock", "/v1/security/status", "/v1/demo/session")

_score: dict[str, tuple[float, float]] = {}          # subject -> (score, last_update)
_recent_paths: dict[str, deque] = defaultdict(lambda: deque(maxlen=40))
_recent_fail: dict[str, deque] = defaultdict(lambda: deque(maxlen=30))
_block_cache: dict[str, float] = {}                  # subject -> expiry epoch
_MAX_SUBJECTS = 20_000


def _trim() -> None:
    """Keep the per-address maps bounded; the address is caller-controlled."""
    for store in (_score, _block_cache):
        if len(store) > _MAX_SUBJECTS:
            for k in list(store)[: _MAX_SUBJECTS // 4]:
                store.pop(k, None)
    for store in (_recent_paths, _recent_fail):
        if len(store) > _MAX_SUBJECTS:
            for k in list(store)[: _MAX_SUBJECTS // 4]:
                store.pop(k, None)


def _decayed(subject: str, now: float) -> float:
    score, at = _score.get(subject, (0.0, now))
    return score * (0.5 ** ((now - at) / HALF_LIFE))


def _add(subject: str, points: float, now: float) -> float:
    total = _decayed(subject, now) + points
    _trim()
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


def _block(subject: str, reason: str, now: float, hard: bool = True) -> int:
    """Record a block and return how many seconds it lasts.

    A soft block (bursts, sweeps) is deliberately short: on shared carrier NAT a
    twenty-minute block takes out every customer behind one address. A hard block
    (scanning for /.env, attack tooling) keeps the old escalator.
    """
    with session() as s:
        row = s.scalar(select(BlockedSubject).where(BlockedSubject.subject == subject))
        prior = 0
        if row is not None:
            prior = max(0, int((row.expires_at - row.created_at).total_seconds() // BASE_BLOCK).bit_length() - 1)
            s.delete(row)
            s.flush()
        if hard:
            seconds = BASE_BLOCK * (2 ** min(prior + 1, 6)) if row is not None else BASE_BLOCK
        else:
            seconds = SOFT_BLOCK
        seconds = min(seconds, MAX_BLOCK)
        until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        s.add(BlockedSubject(subject=subject, reason=reason[:200], expires_at=until))
    _trim()
    _block_cache[subject] = now + seconds
    return seconds


def _remaining(subject: str) -> int:
    """Seconds left on a block, reading the cache first and the table once."""
    cached = _block_cache.get(subject)
    if cached is not None:
        left = int(cached - time.time())
        if left > 0:
            return left
        _block_cache.pop(subject, None)
        return 0
    try:
        with session() as s:
            row = s.scalar(select(BlockedSubject).where(BlockedSubject.subject == subject))
            if row is None:
                return 0
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            left = int((exp - datetime.now(timezone.utc)).total_seconds())
            if left > 0:
                _block_cache[subject] = time.time() + left
                return left
            s.delete(row)
            return 0
    except Exception:  # noqa: BLE001 - the database cannot be the gate
        return 0


def block_remaining(subject: str) -> int:
    """Seconds left on a block, 0 when clear. Used by the status endpoint."""
    return _remaining(subject)


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


def has_credential(request: Request) -> bool:
    """Does this request present something the API can verify?"""
    if (request.headers.get("x-api-key") or "").strip():
        return True
    return (request.headers.get("authorization") or "").lower().startswith("bearer ")


def inspect(request: Request) -> None:
    """Call on every API request. Raises 403 when the caller has earned a block.

    Behavioural scoring is a defence against anonymous abuse, not a tax on
    developers. A caller presenting a credential is judged by that credential and
    is only blocked for an unmistakable attack (probing for secrets, scanner
    tooling). Reading is never scored. A burst of reads from a verification sweep
    used to earn 4 points per request until the whole address was locked out for
    twenty minutes, including callers holding a valid key.
    """
    path = request.url.path
    if path in {"/health", "/favicon.ico"} or path.startswith(_SHIELD_EXEMPT):
        return
    page_view = request.method in {"GET", "HEAD"} and not path.startswith(_API_PREFIXES)
    probed = bool(PROBE_PATHS.search(path) or PROBE_PATHS.search(request.url.query or ""))
    if page_view and not probed:
        return

    subject = subject_of(request)
    credentialed = has_credential(request)
    remaining = _remaining(subject)
    # A key holder is not serving a behaviour block: their key is the identity,
    # and blocking the address would also punish everyone sharing it.
    if remaining and not credentialed:
        raise HTTPException(403, detail=(
            f"Blocked for suspicious activity. Try again in {remaining} seconds, or call "
            "POST /v1/security/unblock to lift it now."), headers={"Retry-After": str(remaining)})

    now = time.time()
    ua = request.headers.get("user-agent", "")
    is_write = request.method not in {"GET", "HEAD", "OPTIONS"}
    points, reasons = 0.0, []

    if probed:
        points += 60; reasons.append("probe_path")
    if BOT_UA.search(ua):
        points += 35; reasons.append("scanner_ua")

    # Behaviour below the hard signals is only ever scored for anonymous
    # callers, and only on writes. A headless browser rendering the catalogue and
    # a scripted verification sweep both look like a "sweep" while doing nothing
    # wrong.
    if not credentialed:
        connect_flow = path.startswith("/v1/connections/") or path.startswith("/v1/account/providers")
        if is_write and not connect_flow:
            paths = _recent_paths[subject]
            paths.append((now, path))
            window = [p for t, p in paths if now - t < 20]
            distinct = len(set(window))
            if SOFT_UA.search(ua) and distinct >= 10:
                points += 15; reasons.append("scripted_sweep")
            if len(window) >= 45 and distinct >= 20:
                points += 25; reasons.append("endpoint_sweep")
            if len(window) >= 80:
                points += 10; reasons.append("burst")

    if not points:
        return
    total = _add(subject, points, now)
    hard = bool(_HARD_REASONS.intersection(reasons))
    blocked = total >= BLOCK_AT and (hard or not credentialed)
    _record(subject, ",".join(reasons), f"{request.method} {path[:120]}", total, blocked)
    if blocked:
        seconds = _block(subject, ",".join(reasons), now, hard=hard)
        raise HTTPException(403, detail=(
            f"Blocked for suspicious activity. Try again in {seconds} seconds, or call "
            "POST /v1/security/unblock to lift it now."), headers={"Retry-After": str(seconds)})


def note_auth_failure(request: Request, kind: str = "bad_key") -> None:
    """Call when a credential is rejected. Repeated failures are credential stuffing."""
    subject = subject_of(request)
    now = time.time()
    fails = _recent_fail[subject]
    fails.append(now)
    recent = [t for t in fails if now - t < 300]
    points = 6 + max(0, len(recent) - 8) * 4
    total = _add(subject, points, now)
    blocked = total >= BLOCK_AT or len(recent) >= 25
    _record(subject, kind, f"{len(recent)} failed credentials in 5 min", total, blocked)
    if blocked:
        seconds = _block(subject, f"credential_stuffing:{len(recent)}", now, hard=False)
        raise HTTPException(429, detail=(
            f"Too many rejected credentials. Try again in {seconds} seconds."),
            headers={"Retry-After": str(seconds)})


def reset() -> None:
    _score.clear(); _recent_paths.clear(); _recent_fail.clear(); _block_cache.clear()


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    with session() as s:
        rows = s.scalars(select(SecurityEvent).order_by(SecurityEvent.created_at.desc()).limit(limit)).all()
        return [{"at": r.created_at.isoformat(timespec="seconds"), "subject": r.subject, "kind": r.kind,
                 "detail": r.detail, "score": r.score, "blocked": r.blocked} for r in rows]
