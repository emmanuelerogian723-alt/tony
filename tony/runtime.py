"""Execution runtime: idempotency, failure classification and safe retries.

Composio-style platforms retry blindly and double-charge people. Tony's rule:
a retry is only allowed when the action is idempotent, or when the caller
supplied an idempotency key, or when we can prove the provider never accepted
the request. Everything else is surfaced as a classified failure instead.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, now, uid


# ── failure taxonomy ──────────────────────────────────────────────────────
AUTH = "auth"
PERMISSION = "permission"
INVALID_ARGUMENT = "invalid_argument"
RATE_LIMIT = "rate_limit"
PROVIDER_ERROR = "provider_error"
NETWORK = "network"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
UNKNOWN = "unknown"

RETRYABLE = {RATE_LIMIT, PROVIDER_ERROR, NETWORK, CONFLICT}

HINTS = {
    AUTH: "The connection's credentials were rejected. Reconnect the account.",
    PERMISSION: "The connected account lacks the required scope or permission.",
    INVALID_ARGUMENT: "The provider rejected the arguments. Check the action schema.",
    RATE_LIMIT: "Provider rate limit hit. Backing off and retrying is safe for reads.",
    PROVIDER_ERROR: "The provider is failing on its side. Retry later.",
    NETWORK: "Network problem reaching the provider. Safe to retry reads.",
    NOT_FOUND: "The thing you referenced does not exist (or the id is wrong).",
    CONFLICT: "The resource changed underneath us. Re-read, then retry.",
    UNKNOWN: "Unclassified failure. Inspect the provider message.",
}


def classify(status: int = 0, message: str = "", error: str = "") -> str:
    """Turn a provider response into one of the taxonomy values."""
    m = f"{message} {error}".lower()
    if status in (401,) or "unauthorized" in m or "invalid_grant" in m or "token expired" in m:
        return AUTH
    if status in (403,) or "forbidden" in m or "insufficient" in m or "scope" in m:
        return PERMISSION
    if status == 404 or "not found" in m:
        return NOT_FOUND
    if status == 409 or "conflict" in m:
        return CONFLICT
    if status in (400, 422) or "invalid" in m or "required" in m or "missing" in m:
        return INVALID_ARGUMENT
    if status == 429 or "rate limit" in m or "too many requests" in m:
        return RATE_LIMIT
    if status >= 500:
        return PROVIDER_ERROR
    if "timeout" in m or "timed out" in m or "connection" in m or "dns" in m:
        return NETWORK
    return UNKNOWN


def is_retryable(kind: str, *, method: str = "GET", idempotent: bool = False,
                 idempotency_key: str | None = None) -> bool:
    """Never blindly retry a non-idempotent write."""
    if kind not in RETRYABLE:
        return False
    safe = method.upper() in {"GET", "HEAD", "OPTIONS"} or idempotent or bool(idempotency_key)
    return safe


def backoff(attempt: int, retry_after: float | None = None) -> float:
    if retry_after and retry_after > 0:
        return min(retry_after, 30.0)
    return min(0.5 * (2 ** max(0, attempt - 1)), 8.0)


# ── idempotency store ─────────────────────────────────────────────────────
class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(120), default="")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    state: Mapped[str] = mapped_column(String(16), default="running")  # running|done|failed
    status: Mapped[int] = mapped_column(Integer, default=0)
    response: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=now)


def fingerprint(action: str, args: dict[str, Any] | None) -> str:
    blob = json.dumps({"a": action, "g": args or {}}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


@dataclass
class IdempotencyOutcome:
    replayed: bool = False
    conflict: bool = False
    previous: dict[str, Any] = field(default_factory=dict)




def claim(key: str, workspace_id: str, action: str, args: dict[str, Any] | None) -> IdempotencyOutcome:
    """Reserve the key. Replays return the stored outcome instead of re-executing."""
    if not key:
        return IdempotencyOutcome()
    fp = fingerprint(action, args)
    s = _session()
    try:
        row = s.get(IdempotencyRecord, key)
        if row is None:
            s.add(IdempotencyRecord(key=key, workspace_id=workspace_id, action=action,
                                    fingerprint=fp, state="running"))
            s.commit()
            return IdempotencyOutcome()
        if row.workspace_id != workspace_id:
            # another tenant's key: treat as a fresh key rather than leaking state
            return IdempotencyOutcome(conflict=True)
        if row.fingerprint != fp:
            return IdempotencyOutcome(conflict=True, previous={"action": row.action})
        if row.state == "done":
            try:
                payload = json.loads(row.response or "{}")
            except Exception:
                payload = {}
            return IdempotencyOutcome(replayed=True, previous=payload)
        return IdempotencyOutcome()
    finally:
        s.close()


def settle(key: str, workspace_id: str, *, ok: bool, status: int = 0,
           payload: dict[str, Any] | None = None) -> None:
    if not key:
        return
    s = _session()
    try:
        row = s.get(IdempotencyRecord, key)
        if row is None or row.workspace_id != workspace_id:
            return
        row.state = "done" if ok else "failed"
        row.status = status
        row.response = json.dumps(payload or {}, default=str)[:20000]
        s.commit()
    finally:
        s.close()


def release(key: str, workspace_id: str) -> None:
    """Drop a claim so a genuinely failed attempt can be retried by the caller."""
    if not key:
        return
    s = _session()
    try:
        row = s.get(IdempotencyRecord, key)
        if row is not None and row.workspace_id == workspace_id and row.state == "running":
            s.delete(row)
            s.commit()
    finally:
        s.close()


# ── concurrency guard ─────────────────────────────────────────────────────
class Limiter:
    """Per-provider concurrency so one slow API cannot starve the others."""

    def __init__(self, per_provider: int = 8) -> None:
        self.per_provider = per_provider
        self._sem: dict[str, asyncio.Semaphore] = {}

    def for_provider(self, slug: str) -> asyncio.Semaphore:
        sem = self._sem.get(slug)
        if sem is None:
            sem = asyncio.Semaphore(self.per_provider)
            self._sem[slug] = sem
        return sem


LIMITER = Limiter()


@dataclass
class Attempt:
    ok: bool
    status: int
    kind: str
    message: str
    value: Any = None
    attempts: int = 1
    elapsed_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "status": self.status, "failure": None if self.ok else self.kind,
                "message": self.message, "hint": None if self.ok else HINTS.get(self.kind, ""),
                "attempts": self.attempts, "elapsed_ms": self.elapsed_ms}


async def run_with_policy(
    fn: Callable[[], Awaitable[tuple[bool, int, Any, str]]],
    *,
    method: str = "GET",
    idempotent: bool = False,
    idempotency_key: str | None = None,
    max_attempts: int = 3,
    provider: str = "",
) -> Attempt:
    """Execute with classified retries. ``fn`` returns (ok, status, value, message)."""
    started = time.perf_counter()
    attempt_no = 0
    last_kind = UNKNOWN
    last_msg = ""
    sem = LIMITER.for_provider(provider or "default") if provider else None
    for attempt_no in range(1, max_attempts + 1):
        try:
            if sem is not None:
                async with sem:
                    ok, status, value, message = await fn()
            else:
                ok, status, value, message = await fn()
            elapsed = int((time.perf_counter() - started) * 1000)
            if ok:
                return Attempt(True, status, "", "", value, attempt_no, elapsed)
            last_kind = classify(status, message)
            last_msg = message or HINTS.get(last_kind, "")
            if not is_retryable(last_kind, method=method, idempotent=idempotent,
                                idempotency_key=idempotency_key):
                return Attempt(False, status, last_kind, last_msg, value, attempt_no, elapsed)
        except asyncio.TimeoutError:
            last_kind, last_msg = NETWORK, "Request timed out."
            elapsed = int((time.perf_counter() - started) * 1000)
            if not is_retryable(last_kind, method=method, idempotent=idempotent,
                                idempotency_key=idempotency_key):
                return Attempt(False, 0, last_kind, last_msg, None, attempt_no, elapsed)
        except Exception as exc:  # noqa: BLE001
            last_kind, last_msg = NETWORK, str(exc)[:300]
            elapsed = int((time.perf_counter() - started) * 1000)
            if not is_retryable(last_kind, method=method, idempotent=idempotent,
                                idempotency_key=idempotency_key):
                return Attempt(False, 0, last_kind, last_msg, None, attempt_no, elapsed)
        if attempt_no < max_attempts:
            await asyncio.sleep(backoff(attempt_no))
    return Attempt(False, 0, last_kind, last_msg, None, attempt_no,
                   int((time.perf_counter() - started) * 1000))


def _session():
    """A real SQLAlchemy Session; the caller commits and closes it."""
    from .db import SessionLocal
    return SessionLocal()
