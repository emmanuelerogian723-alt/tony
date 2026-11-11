"""Connection health: proactive token refresh and failure monitoring.

Nango's most important lesson is that a connection must never be discovered to
be broken at execution time. This module sweeps connected accounts ahead of
expiry, refreshes them, records a health signal and reports per-app status so
a broken integration is visible before an agent tries to use it.

Nothing here changes existing behaviour: `execute()` still refreshes on demand.
This is the background safety net on top of it.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from .catalog import catalog
from .models import ConnectedAccount

# Refresh anything expiring inside this window.
REFRESH_WINDOW = timedelta(minutes=10)
# Never hammer a provider: at most this many refreshes per sweep.
MAX_PER_SWEEP = 40

_last_sweep: dict[str, Any] = {"at": 0.0, "checked": 0, "refreshed": 0, "expired": 0, "errors": 0}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _session():
    from .db import SessionLocal

    return SessionLocal()


async def sweep(limit: int = MAX_PER_SWEEP) -> dict[str, Any]:
    """Refresh every connection that is expired or about to expire."""
    from .oauth import refresh_if_needed

    started = time.perf_counter()
    checked = refreshed = expired = errors = 0
    horizon = datetime.now(timezone.utc) + REFRESH_WINDOW

    s = _session()
    try:
        rows = (
            s.query(ConnectedAccount)
            .filter(ConnectedAccount.auth_type == "oauth2")
            .filter(ConnectedAccount.status.in_(("active", "expired")))
            .filter(
                (ConnectedAccount.expires_at.is_(None))
                | (ConnectedAccount.expires_at <= horizon)
            )
            .limit(limit)
            .all()
        )
        ids = [r.id for r in rows]
    finally:
        s.close()

    for account_id in ids:
        s = _session()
        try:
            account = s.query(ConnectedAccount).filter(ConnectedAccount.id == account_id).first()
            if account is None:
                continue
            spec = catalog.get(account.app_slug)
            if spec is None or spec.auth.type != "oauth2":
                continue
            checked += 1
            before = account.status
            try:
                await refresh_if_needed(account, spec)
            except Exception:
                errors += 1
                account.status = "error"
            if account.status == "active" and before != "active":
                refreshed += 1
            elif account.status in ("expired", "error"):
                expired += 1
            s.commit()
        finally:
            s.close()

    took = round((time.perf_counter() - started) * 1000)
    result = {"checked": checked, "refreshed": refreshed, "needs_reauth": expired,
              "errors": errors, "ms": took, "at": datetime.now(timezone.utc).isoformat()}
    _last_sweep.update(result)
    return result


def last_sweep() -> dict[str, Any]:
    return dict(_last_sweep)


def summary(workspace_id: str | None = None) -> dict[str, Any]:
    """Per-app connection health for one workspace (or all, for admins)."""
    s = _session()
    try:
        q = s.query(ConnectedAccount)
        if workspace_id:
            q = q.filter(ConnectedAccount.workspace_id == workspace_id)
        rows = q.all()
        by_status: dict[str, int] = {}
        per_app: dict[str, dict[str, Any]] = {}
        now = datetime.now(timezone.utc)
        for r in rows:
            by_status[r.status] = by_status.get(r.status, 0) + 1
            slot = per_app.setdefault(
                r.app_slug, {"app": r.app_slug, "active": 0, "expired": 0, "error": 0,
                             "revoked": 0, "total": 0, "expiring_soon": 0}
            )
            slot["total"] += 1
            if r.status in slot:
                slot[r.status] += 1
            exp = _aware(r.expires_at)
            if exp and exp - now <= REFRESH_WINDOW:
                slot["expiring_soon"] += 1
        return {
            "accounts": len(rows),
            "by_status": by_status,
            "apps": sorted(per_app.values(), key=lambda x: -x["total"]),
            "last_sweep": last_sweep(),
        }
    finally:
        s.close()


async def watch(interval_seconds: int = 900) -> None:
    """Background loop used by the app lifespan."""
    import asyncio

    while True:
        try:
            await sweep()
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)
