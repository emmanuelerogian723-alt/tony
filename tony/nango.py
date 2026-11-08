"""Nango adapter: managed OAuth credentials for apps Tony has no client for.

Tony owns the catalogue, the agent and the approval gate. Nango owns the part that
needs a human to register apps once: the provider client id/secret and the token
refresh. Everything stays optional: with NANGO_HOST and NANGO_SECRET_KEY unset,
Tony behaves exactly as before.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

import httpx
from sqlalchemy import select

from .catalog import AppSpec
from .crypto import encrypt_json
from .db import session
from .models import ConnectedAccount


def host() -> str:
    return (os.getenv("NANGO_HOST") or "").strip().rstrip("/")


def secret() -> str:
    return (os.getenv("NANGO_SECRET_KEY") or "").strip()


def configured() -> bool:
    return bool(host() and secret())


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {secret()}", "Content-Type": "application/json"}


async def create_session(app_slug: str, workspace_id: str, entity_id: str) -> dict[str, Any]:
    """Ask Nango for a hosted connect link. The user signs in there; Nango keeps the tokens."""
    payload = {
        "end_user": {"id": f"{workspace_id}:{entity_id}"},
        "allowed_integrations": [app_slug],
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{host()}/connect/sessions", json=payload, headers=_headers())
    if r.status_code >= 400:
        raise RuntimeError(f"Nango rejected the session ({r.status_code}): {r.text[:200]}")
    data = r.json().get("data") or r.json()
    link = data.get("connect_link") or data.get("url") or data.get("token")
    return {"url": link, "raw": data}


async def fetch_credentials(app_slug: str, connection_id: str) -> dict[str, Any] | None:
    """Pull the live token set for a finished connection."""
    url = f"{host()}/connection/{connection_id}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url, params={"provider_config_key": app_slug}, headers=_headers())
    if r.status_code >= 400:
        return None
    body = r.json()
    creds = body.get("credentials") or {}
    if not creds:
        return None
    token = creds.get("access_token") or creds.get("api_key") or creds.get("token") or ""
    out: dict[str, Any] = {"access_token": token, "token": token, "raw": creds}
    if creds.get("refresh_token"):
        out["refresh_token"] = creds["refresh_token"]
    if body.get("connection_config"):
        out["config"] = body["connection_config"]
    return out


def verify_webhook(body: bytes, signature: str, shared_secret: str = "") -> bool:
    """Nango signs webhook bodies with HMAC-SHA256 when a secret is configured."""
    key = (shared_secret or os.getenv("NANGO_WEBHOOK_SECRET") or secret()).encode()
    if not key or not signature:
        return False
    expected = hmac.new(key, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower().removeprefix("sha256="))


def store_connection(workspace_id: str, entity_id: str, spec: AppSpec, creds: dict[str, Any],
                     label: str = "nango") -> ConnectedAccount:
    """Save a Nango connection into Tony's own encrypted store."""
    with session() as s:
        row = s.scalar(select(ConnectedAccount).where(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.entity_id == entity_id,
            ConnectedAccount.app_slug == spec.slug,
        ))
        if row is None:
            row = ConnectedAccount(workspace_id=workspace_id, entity_id=entity_id, app_slug=spec.slug)
            s.add(row)
        row.auth_type = "oauth2"
        row.status = "active"
        row.label = label[:160]
        row.credentials_enc = encrypt_json(creds)
        row.meta_json = json.dumps({"source": "nango"})
        s.flush()
        s.commit()
        return row
