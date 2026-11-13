"""Files API: presigned uploads, handles, download, listing."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import files as engine
from .auth import workspace_from_request

router = APIRouter(prefix="/v1/files", tags=["files"])


class FileCreateIn(BaseModel):
    filename: str = "upload.bin"
    mime: str = ""
    size: int = 0
    purpose: str = ""
    entity_id: str = "default"
    allow: list[str] = Field(default_factory=list)
    ttl_hours: int | None = None


class FileUploadIn(BaseModel):
    filename: str = "upload.bin"
    mime: str = ""
    entity_id: str = "default"
    purpose: str = ""
    data_base64: str


@router.post("")
def create_file(body: FileCreateIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    try:
        return engine.create_upload(
            workspace_id=ws, entity_id=body.entity_id, filename=body.filename, mime=body.mime,
            size=body.size, purpose=body.purpose, allow=body.allow or None, ttl_hours=body.ttl_hours)
    except engine.FileEngineError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@router.post("/upload")
def upload_file(body: FileUploadIn, request: Request) -> dict[str, Any]:
    """Direct upload for SDKs and small files."""
    import base64
    ws, _ = workspace_from_request(request)
    try:
        raw = base64.b64decode(body.data_base64 or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, detail="data_base64 is not valid base64") from exc
    try:
        return engine.store_bytes(workspace_id=ws, data=raw, filename=body.filename,
                                  mime=body.mime, entity_id=body.entity_id, purpose=body.purpose)
    except engine.FileEngineError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@router.put("/{handle}/content")
async def put_content(handle: str, request: Request) -> dict[str, Any]:
    """Complete a presigned upload: raw bytes in the body."""
    ws, _ = workspace_from_request(request)
    data = await request.body()
    try:
        return engine.write_content(handle, data, ws)
    except engine.FileEngineError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc


@router.get("")
def list_files(request: Request, entity_id: str = "", limit: int = 50) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    return {"files": engine.list_files(ws, entity_id or None, limit),
            "stats": engine.stats(ws)}


@router.get("/{handle}")
def get_file(handle: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    try:
        f = engine.get(handle, ws)
    except engine.FileEngineError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
    return {**engine._public(f), "signed_url": engine.signed_url(handle, ws)["url"]}


@router.get("/{handle}/download")
def download(handle: str, request: Request, sig: str = "", exp: str = "") -> Response:
    ws, _ = workspace_from_request(request)
    if sig and exp and not engine.verify_signed(handle, sig, exp):
        raise HTTPException(403, detail="Invalid or expired signature")
    try:
        data = engine.read_bytes(handle, ws)
        f = engine.get(handle, ws)
    except engine.FileEngineError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
    # A filename is attacker-controlled text; unquoted it could inject header syntax.
    from urllib.parse import quote

    name = (f.filename or "download").replace('"', "").replace("\\", "").replace("\r", "").replace("\n", "")
    ascii_name = name.encode("ascii", "ignore").decode() or "download"
    return Response(content=data, media_type=f.mime,
                    headers={"Content-Disposition":
                             f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}'})


@router.delete("/{handle}")
def delete_file(handle: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    try:
        return {"ok": engine.delete(handle, ws)}
    except engine.FileEngineError as exc:
        raise HTTPException(exc.status, detail={"code": exc.code, "message": exc.message}) from exc
