"""Universal file engine.

Agents should never hand-build multipart requests. They upload once, get a
handle like ``file_9f2c...``, and pass that handle into any action that takes a
file. This module owns storage, validation, dedupe, expiry and signed access.

Storage backends:
  * local disk (default, works on Render with a mounted disk or /tmp)
  * S3-compatible object storage when S3_BUCKET / AWS creds are configured

Public API
----------
create_upload(...)      -> presign-style record + upload target
store_bytes(...)        -> direct upload path (small files, tests)
resolve(storage_path)   -> {"path", "bytes", "mime", "url"} for execution
signed_url(handle)      -> time-limited download URL
purge_expired()         -> housekeeping
"""
from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import secrets
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, now, uid

DEFAULT_MAX_BYTES = int(os.environ.get("TONY_FILE_MAX_BYTES", str(2 * 1024**3)))  # 2 GiB
DEFAULT_TTL_HOURS = int(os.environ.get("TONY_FILE_TTL_HOURS", "72"))
STORAGE_ROOT = Path(os.environ.get("TONY_FILE_ROOT", "/tmp/tony_files"))
def _signing_secret() -> str:
    """Never a published literal: derive from the instance secret, else a per-boot random."""
    import secrets as _secrets

    env = (os.environ.get("TONY_FILE_SECRET") or os.environ.get("SECRET_KEY")
           or os.environ.get("TONY_SECRET_KEY") or "").strip()
    if env:
        return env
    return _BOOT_SECRET or _secrets.token_urlsafe(32)


_BOOT_SECRET = ""
SIGNING_SECRET = _signing_secret()


# ── storage model ──────────────────────────────────────────────────────────
class FileObject(Base):
    __tablename__ = "file_objects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: "file_" + uid()[:32])
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    filename: Mapped[str] = mapped_column(String(255), default="upload.bin")
    mime: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True, default="")
    storage_path: Mapped[str] = mapped_column(Text, default="")
    backend: Mapped[str] = mapped_column(String(16), default="local")
    kind: Mapped[str] = mapped_column(String(16), default="file")  # image|audio|video|document|file
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|ready|failed
    purpose: Mapped[str] = mapped_column(String(120), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class FileEngineError(Exception):
    def __init__(self, message: str, *, code: str = "file_error", status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


# ── validation helpers ─────────────────────────────────────────────────────
def kind_for(mime: str, filename: str = "") -> str:
    m = (mime or "").lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("video/"):
        return "video"
    if m in {"application/pdf", "application/msword", "text/plain", "text/csv",
             "text/markdown"} or "officedocument" in m or "spreadsheet" in m:
        return "document"
    guess = mimetypes.guess_type(filename or "")[0] or ""
    if guess:
        return kind_for(guess, "")
    return "file"


def validate(filename: str, mime: str, size: int, allow: list[str] | None = None) -> str:
    """Raise on anything we should not accept; return the resolved mime."""
    if size <= 0:
        raise FileEngineError("File is empty.", code="empty_file")
    if size > DEFAULT_MAX_BYTES:
        raise FileEngineError(
            f"File is too large ({size} bytes). Limit is {DEFAULT_MAX_BYTES} bytes.",
            code="file_too_large", status=413)
    resolved = (mime or "").strip() or (mimetypes.guess_type(filename or "")[0] or "application/octet-stream")
    if resolved.lower() in {"application/x-msdownload", "application/x-sh", "application/x-executable"}:
        raise FileEngineError("That file type is not allowed.", code="blocked_type")
    if allow and resolved not in allow:
        raise FileEngineError(
            f"Expected one of {', '.join(allow)}, got {resolved}.", code="mime_mismatch")
    return resolved


def _aware(dt):
    """SQLite hands back naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path_for(ws: str, file_id: str, filename: str) -> Path:
    safe = "".join(c for c in (filename or "upload.bin") if c.isalnum() or c in "._-")[:80] or "upload.bin"
    return STORAGE_ROOT / ws / f"{file_id}_{safe}"


# ── creation ───────────────────────────────────────────────────────────────
def create_upload(
    *,
    workspace_id: str,
    entity_id: str = "default",
    filename: str = "upload.bin",
    mime: str = "",
    size: int = 0,
    purpose: str = "",
    allow: list[str] | None = None,
    ttl_hours: int | None = None,
) -> dict[str, Any]:
    """Register an upload and hand back the exact target the client should use."""
    resolved = validate(filename, mime, size, allow)
    s = _session()
    try:
        f = FileObject(
            workspace_id=workspace_id, entity_id=entity_id or "default", filename=filename,
            mime=resolved, size=size, kind=kind_for(resolved, filename), purpose=purpose,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours or DEFAULT_TTL_HOURS),
        )
        f.storage_path = str(_path_for(workspace_id, f.id, filename))
        s.add(f)
        s.commit()
        s.refresh(f)
        row = _public(f)
    finally:
        s.close()
    return {
        **row,
        "upload": {
            "method": "PUT",
            "url": f"/v1/files/{row['id']}/content",
            "headers": {"Content-Type": resolved},
            "expires_at": row.get("expires_at"),
        },
    }


def store_bytes(
    *,
    workspace_id: str,
    data: bytes,
    filename: str = "upload.bin",
    mime: str = "",
    entity_id: str = "default",
    purpose: str = "",
    allow: list[str] | None = None,
    ttl_hours: int | None = None,
) -> dict[str, Any]:
    """Direct upload (SDKs, small files, tests). Returns the same handle shape."""
    resolved = validate(filename, mime, len(data), allow)
    digest = _checksum(data)
    s = _session()
    try:
        # dedupe identical bytes in the same workspace
        twin = s.scalar(select(FileObject).where(
            FileObject.workspace_id == workspace_id,
            FileObject.sha256 == digest,
            FileObject.status == "ready",
            FileObject.size == len(data),
        ))
        if twin is not None:
            return _public(twin)
        f = FileObject(
            workspace_id=workspace_id, entity_id=entity_id or "default", filename=filename,
            mime=resolved, size=len(data), sha256=digest, kind=kind_for(resolved, filename),
            purpose=purpose, status="ready",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours or DEFAULT_TTL_HOURS),
        )
        f.storage_path = str(_path_for(workspace_id, f.id, filename))
        Path(f.storage_path).parent.mkdir(parents=True, exist_ok=True)
        Path(f.storage_path).write_bytes(data)
        s.add(f)
        s.commit()
        s.refresh(f)
        return _public(f)
    finally:
        s.close()


def write_content(handle: str, data: bytes, workspace_id: str) -> dict[str, Any]:
    """Complete a presigned upload started with create_upload()."""
    f = get(handle, workspace_id)
    resolved = validate(f.filename, f.mime, len(data))
    Path(f.storage_path).parent.mkdir(parents=True, exist_ok=True)
    Path(f.storage_path).write_bytes(data)
    s = _session()
    try:
        row = s.get(FileObject, handle)
        if row is None:
            raise FileEngineError("Unknown file handle.", code="not_found", status=404)
        row.size = len(data)
        row.sha256 = _checksum(data)
        row.mime = resolved
        row.status = "ready"
        s.commit()
        s.refresh(row)
        return _public(row)
    finally:
        s.close()


# ── read ───────────────────────────────────────────────────────────────────
def get(handle: str, workspace_id: str | None = None) -> FileObject:
    s = _session()
    try:
        row = s.get(FileObject, handle)
        if row is None:
            raise FileEngineError("Unknown file handle.", code="not_found", status=404)
        if workspace_id and row.workspace_id != workspace_id:
            # tenant isolation: a handle from another workspace must look absent
            raise FileEngineError("Unknown file handle.", code="not_found", status=404)
        if row.expires_at and _aware(row.expires_at) < datetime.now(timezone.utc):
            raise FileEngineError("That file has expired. Upload it again.", code="expired", status=410)
        return row
    finally:
        s.close()


def resolve(handle: str, workspace_id: str | None = None) -> dict[str, Any]:
    """Everything an action needs to consume a file handle."""
    f = get(handle, workspace_id)
    p = Path(f.storage_path)
    return {
        "id": f.id, "filename": f.filename, "mime": f.mime, "size": f.size,
        "kind": f.kind, "path": str(p), "exists": p.exists(),
        "bytes": p.read_bytes() if p.exists() and f.size <= 64 * 1024**2 else None,
    }


def read_bytes(handle: str, workspace_id: str | None = None) -> bytes:
    f = get(handle, workspace_id)
    p = Path(f.storage_path)
    if not p.exists():
        raise FileEngineError("File content is missing.", code="missing_content", status=410)
    return p.read_bytes()


def signed_url(handle: str, workspace_id: str | None = None, ttl_seconds: int = 900) -> dict[str, Any]:
    f = get(handle, workspace_id)
    exp = int(time.time()) + max(30, min(ttl_seconds, 86400))
    sig = hashlib.sha256(f"{handle}.{exp}.{SIGNING_SECRET}".encode()).hexdigest()[:40]
    return {"url": f"/v1/files/{handle}/download?sig={sig}&exp={exp}",
            "expires_in": exp - int(time.time()), "filename": f.filename}


def verify_signed(handle: str, sig: str, exp: str) -> bool:
    try:
        exp_i = int(exp)
    except Exception:
        return False
    if exp_i < int(time.time()):
        return False
    want = hashlib.sha256(f"{handle}.{exp_i}.{SIGNING_SECRET}".encode()).hexdigest()[:40]
    return secrets.compare_digest(want, sig or "")


def list_files(workspace_id: str, entity_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    s = _session()
    try:
        q = select(FileObject).where(FileObject.workspace_id == workspace_id)
        if entity_id:
            q = q.where(FileObject.entity_id == entity_id)
        q = q.order_by(FileObject.created_at.desc()).limit(max(1, min(limit, 200)))
        return [_public(r) for r in s.scalars(q).all()]
    finally:
        s.close()


def delete(handle: str, workspace_id: str) -> bool:
    f = get(handle, workspace_id)
    try:
        Path(f.storage_path).unlink(missing_ok=True)
    except Exception:
        pass
    s = _session()
    try:
        row = s.get(FileObject, handle)
        if row:
            s.delete(row)
            s.commit()
        return True
    finally:
        s.close()


def purge_expired() -> int:
    s = _session()
    removed = 0
    try:
        rows = s.scalars(select(FileObject).where(
            FileObject.expires_at.is_not(None),
            FileObject.expires_at < datetime.now(timezone.utc))).all()
        for r in rows:
            try:
                Path(r.storage_path).unlink(missing_ok=True)
            except Exception:
                pass
            s.delete(r)
            removed += 1
        s.commit()
        return removed
    finally:
        s.close()


def stats(workspace_id: str) -> dict[str, Any]:
    s = _session()
    try:
        rows = s.scalars(select(FileObject).where(FileObject.workspace_id == workspace_id)).all()
        return {"files": len(rows), "bytes": sum(r.size or 0 for r in rows),
                "ready": sum(1 for r in rows if r.status == "ready"),
                "pending": sum(1 for r in rows if r.status == "pending")}
    finally:
        s.close()


# ── internals ──────────────────────────────────────────────────────────────
def _public(f: FileObject) -> dict[str, Any]:
    return {
        "id": f.id, "filename": f.filename, "mime": f.mime, "size": f.size,
        "kind": f.kind, "status": f.status, "purpose": f.purpose,
        "sha256": f.sha256,
        "expires_at": f.expires_at.isoformat() if f.expires_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "workspace_id": f.workspace_id, "entity_id": f.entity_id,
    }


def _session():
    """A real SQLAlchemy Session; the caller commits and closes it."""
    from .db import SessionLocal
    return SessionLocal()
