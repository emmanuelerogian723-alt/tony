"""User-defined HTTP tools.

The gap every integration platform leaves: your own internal API. A custom tool
is a first-class action here, so it gets the same quota, approval gate, session
scoping, run log and tool-schema export as anything in the catalog.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .crypto import decrypt_json, encrypt_json
from .db import session
from .models import CustomTool

router = APIRouter(prefix="/v1/custom-tools", tags=["custom tools"])

SLUG_RE = re.compile(r"^[a-z0-9_]{2,40}$")
PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_]+)\}")
PRIVATE_HOST = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1|\[::1\]|"
    r"172\.(1[6-9]|2\d|3[01])\.|.*\.(internal|local|localhost)$)", re.IGNORECASE)


class CustomToolIn(BaseModel):
    slug: str
    name: str = ""
    description: str = ""
    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: str = ""
    secret: str = ""
    auth_style: str = "bearer"  # bearer|header|query|none
    auth_name: str = "Authorization"
    tier: str = "read"
    params: list[dict[str, Any]] = Field(default_factory=list)


def public(row: CustomTool) -> dict[str, Any]:
    return {
        "id": row.id, "slug": row.slug, "action": f"custom.{row.slug}",
        "name": row.name or row.slug, "description": row.description,
        "method": row.method, "url": row.url, "tier": row.tier,
        "auth_style": row.auth_style, "has_secret": bool(row.secret_enc),
        "headers": sorted(json.loads(row.headers_json or "{}").keys()),
        "body_template": row.body_template,
        "params": json.loads(row.params_json or "[]"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _validated(body: CustomToolIn) -> CustomToolIn:
    slug = (body.slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise HTTPException(400, detail="Slug must be 2-40 characters: lowercase letters, numbers, underscore")
    method = (body.method or "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
        raise HTTPException(400, detail="Unsupported HTTP method")
    url = (body.url or "").strip()
    if not url.startswith("https://") and not url.startswith("http://"):
        raise HTTPException(400, detail="URL must start with http:// or https://")
    host = url.split("://", 1)[1].split("/", 1)[0].split("@")[-1]
    if PRIVATE_HOST.match(host):
        raise HTTPException(400, detail="Private and local addresses are not allowed")
    tier = body.tier if body.tier in {"read", "write", "destructive"} else "read"
    style = body.auth_style if body.auth_style in {"bearer", "header", "query", "none"} else "bearer"
    return body.model_copy(update={"slug": slug, "method": method, "url": url[:600],
                                   "tier": tier, "auth_style": style})


@router.get("")
def list_tools(request: Request) -> dict[str, Any]:
    from .auth import workspace_from_request

    ws, _ = workspace_from_request(request)
    with session() as s:
        rows = s.scalars(select(CustomTool).where(CustomTool.workspace_id == ws)
                         .order_by(CustomTool.created_at.desc())).all()
        return {"tools": [public(r) for r in rows], "total": len(rows)}


@router.post("")
def create_tool(body: CustomToolIn, request: Request) -> dict[str, Any]:
    from .auth import workspace_from_request
    from .billing import check_capacity

    ws, _ = workspace_from_request(request)
    body = _validated(body)
    check_capacity(ws, "custom_tools")
    with session() as s:
        if s.scalar(select(CustomTool).where(CustomTool.workspace_id == ws, CustomTool.slug == body.slug)):
            raise HTTPException(409, detail="You already have a tool with that slug")
        row = CustomTool(
            workspace_id=ws, slug=body.slug, name=body.name[:120] or body.slug,
            description=body.description[:2000], method=body.method, url=body.url,
            headers_json=json.dumps(body.headers or {}), body_template=body.body_template[:20000],
            secret_enc=encrypt_json({"secret": body.secret}) if body.secret else "",
            auth_style=body.auth_style, auth_name=body.auth_name[:80], tier=body.tier,
            params_json=json.dumps(body.params or [])[:8000],
        )
        s.add(row)
        s.flush()
        return public(row)


@router.put("/{slug}")
def update_tool(slug: str, body: CustomToolIn, request: Request) -> dict[str, Any]:
    from .auth import workspace_from_request

    ws, _ = workspace_from_request(request)
    body = _validated(body.model_copy(update={"slug": slug}))
    with session() as s:
        row = s.scalar(select(CustomTool).where(CustomTool.workspace_id == ws, CustomTool.slug == slug))
        if row is None:
            raise HTTPException(404, detail="Tool not found")
        row.name = body.name[:120] or row.name
        row.description = body.description[:2000]
        row.method, row.url, row.tier = body.method, body.url, body.tier
        row.headers_json = json.dumps(body.headers or {})
        row.body_template = body.body_template[:20000]
        row.auth_style, row.auth_name = body.auth_style, body.auth_name[:80]
        row.params_json = json.dumps(body.params or [])[:8000]
        if body.secret:
            row.secret_enc = encrypt_json({"secret": body.secret})
        s.flush()
        return public(row)


@router.delete("/{slug}")
def delete_tool(slug: str, request: Request) -> dict[str, Any]:
    from .auth import workspace_from_request

    ws, _ = workspace_from_request(request)
    with session() as s:
        row = s.scalar(select(CustomTool).where(CustomTool.workspace_id == ws, CustomTool.slug == slug))
        if row is None:
            raise HTTPException(404, detail="Tool not found")
        s.delete(row)
    return {"ok": True, "slug": slug}


def find(ws: str, slug: str) -> CustomTool | None:
    with session() as s:
        return s.scalar(select(CustomTool).where(CustomTool.workspace_id == ws, CustomTool.slug == slug))


def _fill(template: str, args: dict[str, Any], quote_values: bool = True) -> str:
    def sub(m: re.Match) -> str:
        val = args.get(m.group(1), "")
        return quote(str(val), safe="") if quote_values else str(val)
    return PLACEHOLDER.sub(sub, template or "")


def _deep_fill(node: Any, args: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        return {k: _deep_fill(v, args) for k, v in node.items()}
    if isinstance(node, list):
        return [_deep_fill(v, args) for v in node]
    if isinstance(node, str):
        whole = PLACEHOLDER.fullmatch(node.strip())
        if whole and whole.group(1) in args:
            return args[whole.group(1)]
        return _fill(node, args, quote_values=False)
    return node


async def run(row: CustomTool, args: dict[str, Any]) -> dict[str, Any]:
    url = _fill(row.url, args)
    headers = _deep_fill(json.loads(row.headers_json or "{}"), args)
    headers = {str(k): str(v) for k, v in headers.items()}
    if row.secret_enc:
        secret = decrypt_json(row.secret_enc).get("secret", "")
        if row.auth_style == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        elif row.auth_style == "header":
            headers[row.auth_name or "X-API-Key"] = secret
        elif row.auth_style == "query":
            joiner = "&" if "?" in url else "?"
            url = f"{url}{joiner}{quote(row.auth_name or 'api_key')}={quote(secret)}"
    body: Any = None
    if row.body_template.strip():
        body = _deep_fill(json.loads(row.body_template), args)
    elif row.method in {"POST", "PUT", "PATCH"} and args:
        body = args
    started = time.time()
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        resp = await client.request(row.method, url, headers=headers, json=body)
    text = resp.text
    try:
        data: Any = resp.json()
    except ValueError:
        data = {"text": text[:4000]}
    return {"ok": resp.status_code < 400, "status": resp.status_code, "data": data,
            "latency_ms": int((time.time() - started) * 1000), "url": url}
