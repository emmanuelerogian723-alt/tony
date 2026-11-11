"""Durable syncs: keep a local, deduplicated copy of what matters.

Nango's sync primitive is why agents using it work from fresh context instead of
re-reading a provider on every call. Tony synced nothing, so every step paid
latency and quota for data it had already fetched. This module fixes that:

  * a sync is a definition (app, action, args, interval) plus a row store
  * records are keyed and upserted, never duplicated
  * incremental runs pass the last successful run time as {{cursor}}
  * a failed run keeps the previous data and records why
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from .auth import workspace_from_request
from .billing import PLANS, plan_id_for_workspace
from .catalog import catalog
from .db import session
from .executor import ExecutionError, execute
from .models import Base, now, uid
from .oauth import credentials_for
from .runtime import classify

router = APIRouter(prefix="/v1", tags=["syncs"])
log = logging.getLogger("tony.syncs")

ITEM_KEYS = ("items", "data", "results", "records", "values", "rows", "nodes")


class Sync(Base):
    __tablename__ = "syncs"
    __table_args__ = (Index("ix_sync_ws", "workspace_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), default="default")
    app_slug: Mapped[str] = mapped_column(String(80), default="")
    action_slug: Mapped[str] = mapped_column(String(120), default="")
    name: Mapped[str] = mapped_column(String(160), default="sync")
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=900)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|paused|error
    records_count: Mapped[int] = mapped_column(Integer, default=0)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SyncRecord(Base):
    __tablename__ = "sync_records"
    __table_args__ = (
        UniqueConstraint("sync_id", "key", name="uq_sync_record_key"),
        Index("ix_syncrec", "sync_id", "updated_at"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    sync_id: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(200), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def _items(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ITEM_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        # a single object is still a record
        return [data]
    return []


def _key_of(item: Any, index: int) -> str:
    if isinstance(item, dict):
        for field in ("id", "key", "uuid", "slug", "name", "url"):
            value = item.get(field)
            if isinstance(value, (str, int)) and str(value):
                return str(value)[:200]
    blob = json.dumps(item, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:40]


async def run_sync(sync_id: str) -> dict[str, Any]:
    """One sync pass: fetch, flatten, upsert, remember the cursor."""
    with session() as s:
        row = s.scalar(select(Sync).where(Sync.id == sync_id))
        if row is None or row.status == "paused":
            return {"ok": False, "skipped": True}
        ws, entity = row.workspace_id, row.entity_id
        action_name, args_raw = row.action_slug, json.loads(row.args_json or "{}")
        last = row.last_run_at
        name = row.name
    resolved = catalog.find_action(action_name)
    if not resolved:
        _mark(sync_id, f"Unknown action '{action_name}'")
        return {"ok": False, "error": "unknown action"}
    spec, action = resolved
    args: dict[str, Any] = {}
    cursor = (last or (datetime.now(timezone.utc) - timedelta(days=30))).isoformat()
    for key, value in (args_raw or {}).items():
        if isinstance(value, str):
            args[key] = value.replace("{{cursor}}", cursor)
        else:
            args[key] = value
    creds = credentials_for(ws, entity, spec)
    if spec.auth.type != "none" and creds is None and not action.public:
        _mark(sync_id, f"No {spec.name} account connected for '{entity}'")
        return {"ok": False, "error": "no credentials"}
    try:
        result = await execute(spec, action, args, creds)
    except ExecutionError as exc:
        _mark(sync_id, str(exc)[:500])
        return {"ok": False, "error": str(exc)}
    if not result.ok:
        _mark(sync_id, f"{classify(result.status, result.error)}: {result.error}"[:500])
        return {"ok": False, "error": result.error}

    items = _items(result.data)
    added = updated = 0
    stamp = datetime.now(timezone.utc)
    with session() as s:
        for index, item in enumerate(items):
            key = _key_of(item, index)
            blob = json.dumps(item, default=str)[:100000]
            digest = hashlib.sha256(blob.encode()).hexdigest()
            existing = s.scalar(select(SyncRecord).where(SyncRecord.sync_id == sync_id,
                                                          SyncRecord.key == key))
            if existing is None:
                s.add(SyncRecord(sync_id=sync_id, key=key, hash=digest, data_json=blob))
                added += 1
            elif existing.hash != digest:
                existing.data_json = blob
                existing.hash = digest
                existing.updated_at = stamp
                updated += 1
        total = len(s.scalars(select(SyncRecord).where(SyncRecord.sync_id == sync_id)).all())
        row = s.get(Sync, sync_id)
        row.records_count = total
        row.runs = (row.runs or 0) + 1
        row.last_run_at = stamp
        row.next_run_at = stamp + timedelta(seconds=max(60, row.interval_seconds))
        row.last_error = ""
        if row.status == "error":
            row.status = "active"
    return {"ok": True, "sync": name, "fetched": len(items), "added": added,
            "updated": updated, "total": total}


def _mark(sync_id: str, error: str) -> None:
    with session() as s:
        row = s.get(Sync, sync_id)
        if row is None:
            return
        row.last_error = error
        row.status = "error"
        row.last_run_at = datetime.now(timezone.utc)
        row.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=max(60, row.interval_seconds))


async def runner() -> None:
    """Drive due syncs. Same shape as the flow runner: cheap, resumable, quiet."""
    every = 20
    log.info("Sync runner started (every %ss)", every)
    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            with session() as s:
                rows = s.scalars(select(Sync).where(Sync.status.in_(("active", "error")))
                                 .limit(50)).all()
                due = []
                for r in rows:
                    nxt = r.next_run_at
                    if nxt is not None and nxt.tzinfo is None:
                        nxt = nxt.replace(tzinfo=timezone.utc)
                    if r.status == "active" and (nxt is None or nxt <= now_utc):
                        due.append(r.id)
            for sync_id in due:
                try:
                    await run_sync(sync_id)
                except Exception:  # noqa: BLE001
                    log.exception("sync %s crashed", sync_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover
            log.exception("sync runner tick failed")
        await asyncio.sleep(every)


# ── API ──────────────────────────────────────────────────────────────────
class SyncIn(BaseModel):
    action: str = Field(..., max_length=120)
    args: dict[str, Any] = Field(default_factory=dict)
    interval_seconds: int = Field(default=900, ge=60, le=2_592_000)
    entity_id: str = Field(default="default", max_length=160)
    name: str = Field(default="", max_length=160)


def sync_public(row: Sync) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "action": row.action_slug,
        "entity_id": row.entity_id,
        "interval_seconds": row.interval_seconds,
        "status": row.status,
        "records_count": row.records_count,
        "runs": row.runs,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_error": row.last_error,
    }


def _enforce_sync_limit(ws: str) -> None:
    plan_id, _sub, _user = plan_id_for_workspace(ws)
    limit = int(PLANS[plan_id].get("triggers", 3))
    with session() as s:
        used = len(s.scalars(select(Sync).where(Sync.workspace_id == ws)).all())
    if used >= limit:
        raise HTTPException(402, detail=(
            f"The {plan_id} plan allows {limit} triggers, syncs and subscriptions. "
            "Upgrade to add more."))


@router.post("/syncs")
async def create_sync(body: SyncIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    if not catalog.find_action(body.action):
        raise HTTPException(404, detail=f"Unknown action '{body.action}'")
    _enforce_sync_limit(ws)
    with session() as s:
        row = Sync(workspace_id=ws, entity_id=body.entity_id or "default",
                   app_slug=body.action.split(".")[0], action_slug=body.action,
                   name=body.name or body.action, args_json=json.dumps(body.args or {}),
                   interval_seconds=body.interval_seconds,
                   next_run_at=datetime.now(timezone.utc))
        s.add(row)
        s.flush()
        sync_id = row.id
    result = await run_sync(sync_id)
    with session() as s:
        row = s.get(Sync, sync_id)
        return {**sync_public(row), "first_run": result}


@router.get("/syncs")
def list_syncs(request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(Sync).where(Sync.workspace_id == ws)
                         .order_by(Sync.created_at.desc())).all()
        return {"syncs": [sync_public(r) for r in rows]}


@router.get("/syncs/{sync_id}")
def get_sync(sync_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(Sync).where(Sync.id == sync_id, Sync.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown sync")
        return sync_public(row)


@router.post("/syncs/{sync_id}/run")
async def trigger_sync(sync_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(Sync).where(Sync.id == sync_id, Sync.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown sync")
    return await run_sync(sync_id)


@router.post("/syncs/{sync_id}/pause")
def pause_sync(sync_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(Sync).where(Sync.id == sync_id, Sync.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown sync")
        row.status = "paused"
        return sync_public(row)


@router.post("/syncs/{sync_id}/resume")
def resume_sync(sync_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(Sync).where(Sync.id == sync_id, Sync.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown sync")
        row.status = "active"
        row.next_run_at = datetime.now(timezone.utc)
        return sync_public(row)


@router.get("/syncs/{sync_id}/records")
def sync_records(sync_id: str, request: Request, limit: int = 50, skip: int = 0) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    limit = max(1, min(limit, 500))
    with session() as s:
        row = s.scalar(select(Sync).where(Sync.id == sync_id, Sync.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown sync")
        total = len(s.scalars(select(SyncRecord).where(SyncRecord.sync_id == sync_id)).all())
        rows = s.scalars(select(SyncRecord).where(SyncRecord.sync_id == sync_id)
                         .order_by(SyncRecord.updated_at.desc())
                         .limit(limit).offset(max(0, skip))).all()
        return {"total": total, "records": [
            {"key": r.key, "updated_at": r.updated_at.isoformat(),
             "data": json.loads(r.data_json or "{}")} for r in rows]}


@router.delete("/syncs/{sync_id}")
def delete_sync(sync_id: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(Sync).where(Sync.id == sync_id, Sync.workspace_id == ws))
        if row is None:
            raise HTTPException(404, detail="Unknown sync")
        for rec in s.scalars(select(SyncRecord).where(SyncRecord.sync_id == sync_id)).all():
            s.delete(rec)
        s.delete(row)
    return {"ok": True}
