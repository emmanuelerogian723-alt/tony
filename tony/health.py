"""Integration health intelligence.

A connected app that silently stopped working is worse than one that never
connected. This probes each live connection with the cheapest read the app
exposes, classifies what came back, and remembers the verdict so the console can
show it without re-probing on every page load.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import select

from .auth import workspace_from_request
from .catalog import catalog
from .db import session
from .executor import execute
from .models import ConnectedAccount
from .crypto import decrypt_json

router = APIRouter(prefix="/v1/health", tags=["health"])

AUTH_BAD = {401, 403}


def _probe_action(spec) -> Any | None:
    """The cheapest action that proves the credential still works."""
    reads = [a for a in spec.actions if a.tier == "read" and a.method.upper() == "GET"]
    reads.sort(key=lambda a: (len(a.required or []), len(a.url or "")))
    return reads[0] if reads else None


def classify(status: int | None, error: str) -> tuple[str, str]:
    if error and status is None:
        low = error.lower()
        if "timeout" in low or "deadline" in low:
            return "slow", "The app did not answer in time"
        if "getaddrinfo" in low or "name or service" in low or "connect" in low:
            return "unreachable", "The app's host could not be reached"
        return "error", error[:200]
    if status in AUTH_BAD:
        return "auth_expired", "The credential was rejected, reconnect this app"
    if status == 404:
        return "schema_changed", "The endpoint the action expects is gone"
    if status == 429:
        return "rate_limited", "The app is rate limiting this workspace"
    if status and status >= 500:
        return "unhealthy", "The app is returning server errors"
    if status and status >= 400:
        return "error", f"The app answered {status}"
    return "healthy", ""


async def check_one(row: Any, timeout: float = 20.0) -> dict[str, Any]:
    """Probe one connection. Accepts a plain row dict so nothing is detached from its session."""
    spec = catalog.get(row["app_slug"])
    if spec is None:
        return {"slug": row["app_slug"], "state": "unknown", "detail": "App is no longer in the catalogue"}
    action = _probe_action(spec)
    if action is None:
        return {"slug": row["app_slug"], "state": "unknown", "detail": "No safe read action to probe"}
    creds = decrypt_json(row["credentials_enc"]) if row.get("credentials_enc") else None
    started = time.perf_counter()
    state, detail, status = "healthy", "", None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await execute(spec, action, {}, creds, client=client)
        status = res.status
        state, detail = classify(res.status, "" if res.ok else str(res.error or ""))
    except Exception as exc:  # noqa: BLE001
        state, detail = classify(None, str(exc))
    return {"slug": row["app_slug"], "state": state, "detail": detail, "status": status,
            "action": f"{row['app_slug']}.{action.slug}",
            "latency_ms": int((time.perf_counter() - started) * 1000)}


async def run_checks(ws: str, entity_id: str = "") -> dict[str, Any]:
    # Read what the probe needs while the session is open, so nothing is detached later.
    with session() as s:
        q = select(ConnectedAccount).where(ConnectedAccount.workspace_id == ws)
        if entity_id:
            q = q.where(ConnectedAccount.entity_id == entity_id)
        rows = [{"id": r.id, "app_slug": r.app_slug, "credentials_enc": r.credentials_enc,
                 "meta_json": r.meta_json or "{}", "status": r.status}
                for r in s.scalars(q).all()]

    results = []
    for row in rows:
        r = await check_one(row)
        results.append(r)

    with session() as s:
        for row, r in zip(rows, results):
            live = s.get(ConnectedAccount, row["id"])
            if live is None:
                continue
            try:
                meta = json.loads(live.meta_json or "{}")
            except Exception:  # noqa: BLE001
                meta = {}
            meta["health"] = {"state": r["state"], "detail": r["detail"],
                              "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "latency_ms": r.get("latency_ms", 0)}
            live.meta_json = json.dumps(meta)
            if r["state"] == "auth_expired":
                live.status = "expired"
            elif r["state"] in {"unreachable", "unhealthy", "error", "schema_changed"}:
                live.status = "error" if live.status != "expired" else live.status
            elif r["state"] == "healthy":
                live.status = "active"
        s.commit()

    counts: dict[str, int] = {}
    for r in results:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    return {"checked": len(results), "counts": counts, "results": results}


@router.post("/check")
async def check_all(request: Request, entity_id: str = "") -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    return await run_checks(ws, entity_id)


@router.get("")
def health_summary(request: Request) -> dict[str, Any]:
    """One health answer, not two.

    ``/health`` described the service while ``/v1/health`` described connections,
    so "the health endpoint" meant different things depending on the slash. The
    v1 answer now leads with the service and adds this workspace's connections.
    """
    from . import __version__
    from .catalog import catalog
    from .db import DB_STATUS

    base = {
        "status": "ok",
        "db": DB_STATUS.get("backend"),
        "db_error": (DB_STATUS.get("error") or "")[:300],
        "version": __version__,
        "apps": catalog.stats()["apps"],
        "actions": catalog.stats()["actions"],
    }
    try:
        ws, demo = workspace_from_request(request)
    except Exception:  # noqa: BLE001 - service health must not need a credential
        return {**base, "connections": [], "total": 0, "auth_required": True,
                "note": "Send an API key for connection health; the service block needs no credential."}
    with session() as s:
        rows = s.scalars(select(ConnectedAccount).where(ConnectedAccount.workspace_id == ws)).all()
    out = []
    for r in rows:
        try:
            meta = json.loads(r.meta_json or "{}")
        except Exception:  # noqa: BLE001
            meta = {}
        out.append({"app": r.app_slug, "status": r.status, "health": meta.get("health")})
    return {**base, "demo": demo, "workspace": ws, "connections": out, "total": len(out),
            "note": "POST /v1/health/check probes each connection and stores the verdict."}
