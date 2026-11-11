"""OAuth2 (with PKCE), API keys and static credentials for connected accounts."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select

from .catalog import AppSpec
from .config import settings
from .crypto import decrypt_json, encrypt_json
from .db import session
from .models import AuthSession, ConnectedAccount


class OAuthError(Exception):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _client_creds(spec: AppSpec) -> tuple[str, str]:
    """Provider credentials: environment first, then the owner-registered store.

    The store is what makes one-click sign-in possible for users: the owner
    registers an OAuth app once and everyone else just clicks Connect.
    """
    cid = os.getenv(spec.auth.client_id_env or f"{spec.slug.upper()}_CLIENT_ID", "").strip()
    secret = os.getenv(spec.auth.client_secret_env or f"{spec.slug.upper()}_CLIENT_SECRET", "").strip()
    if cid and secret:
        return cid, secret
    stored = stored_provider(spec.slug)
    if stored:
        stored_cid = _real_cred(stored.get("client_id", ""))
        stored_secret = _real_cred(stored.get("client_secret", ""))
        if stored_cid:
            return stored_cid, stored_secret or secret
    return _real_cred(cid), secret


PLACEHOLDER_CREDS = {"cid_test", "test", "test_id", "changeme", "your_client_id", "your-client-id",
                     "client_id", "xxx", "todo", "none", "null", "demo"}


def _real_cred(value: str) -> str:
    """Reject placeholder ids so a stale test row can never hijack a real sign-in."""
    v = (value or "").strip()
    if not v or v.lower() in PLACEHOLDER_CREDS or v.lower().startswith("cid_test"):
        return ""
    return v


def stored_provider(app_slug: str) -> dict[str, str]:
    from .models import OAuthProvider

    with session() as s:
        row = s.scalar(select(OAuthProvider).where(OAuthProvider.app_slug == app_slug))
        if row is None:
            return {}
        secret = ""
        if row.secret_enc:
            try:
                secret = decrypt_json(row.secret_enc).get("v", "")
            except Exception:
                secret = ""
        return {"client_id": row.client_id or "", "client_secret": secret}


def save_provider(app_slug: str, client_id: str, client_secret: str, user_id: str = "") -> None:
    """Register (or rotate) the OAuth app used for one-click sign-in."""
    from .models import OAuthProvider

    with session() as s:
        row = s.scalar(select(OAuthProvider).where(OAuthProvider.app_slug == app_slug))
        if row is None:
            row = OAuthProvider(app_slug=app_slug)
            s.add(row)
        row.client_id = (client_id or "").strip()[:400]
        row.secret_enc = encrypt_json({"v": (client_secret or "").strip()[:1200]}) if client_secret else ""
        row.created_by = user_id
        s.flush()


def drop_provider(app_slug: str) -> None:
    from .models import OAuthProvider

    with session() as s:
        row = s.scalar(select(OAuthProvider).where(OAuthProvider.app_slug == app_slug))
        if row is not None:
            s.delete(row)


def provider_ready(slug: str) -> bool:
    from .catalog import catalog

    spec = catalog.get(slug)
    if spec is None:
        return False
    cid, secret = _client_creds(spec)
    return bool(cid and secret)


def _well_known(authorize_url: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(authorize_url)
    return f"{parts.scheme}://{parts.netloc}/.well-known/oauth-authorization-server"


async def dynamic_client(spec: AppSpec) -> tuple[str, str]:
    """Register a client automatically with providers that support DCR (RFC 7591).

    This is the keyless path: no client id, no secret, no trip to a dashboard.
    Many MCP servers and modern OAuth providers advertise it.
    """
    url = _well_known(spec.auth.authorize_url or "")
    try:
        meta_resp = await _fetch_meta(url)
    except Exception as exc:
        raise OAuthError(
            f"{spec.name} needs a one-time OAuth app registration. "
            f"Add its client id and secret once in Tony, then users just sign in."
        ) from exc
    if True:  # keep the flow linear after the fetch
        if meta_resp.status_code >= 400:
            raise OAuthError(
                f"{spec.name} needs a one-time OAuth app registration. "
                f"Add its client id and secret in Tony, then users just sign in."
            )
        meta = meta_resp.json()
        reg_endpoint = meta.get("registration_endpoint")
        if not reg_endpoint:
            raise OAuthError(f"{spec.name} does not support automatic client registration.")
        reg = await _post_registration(reg_endpoint, {
            "client_name": "Tony",
            "redirect_uris": [redirect_uri(spec)],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "client_secret_post",
        })
        if reg.status_code >= 400:
            raise OAuthError(f"Automatic client registration failed ({reg.status_code}).")
        data = reg.json()
        cid = data.get("client_id", "")
        secret = data.get("client_secret", "")
        if cid:
            save_provider(spec.slug, cid, secret)
        return cid, secret


def is_configured(spec: AppSpec) -> bool:
    if spec.auth.type == "none":
        return True
    if spec.auth.static_env:
        return bool(os.getenv(spec.auth.static_env, "").strip())
    if spec.auth.type == "oauth2":
        cid, secret = _client_creds(spec)
        return bool(cid and secret)
    # api_key / bearer / basic accounts are connectable with a key the user pastes
    return spec.auth.type in {"api_key", "bearer", "basic", "custom"}


def redirect_uri(spec: AppSpec) -> str:
    return f"{settings.base_url}/oauth/callback"


async def start_oauth(workspace_id: str, entity_id: str, spec: AppSpec, redirect_after: str = "/app") -> tuple[str, str]:
    """Create an auth session and return (session_id, authorization_url)."""
    cid, _secret = _client_creds(spec)
    if cid and not _secret and not spec.auth.pkce:
        # An id with no secret starts a sign-in that the provider then refuses at the token step,
        # which looks like a dead button. Refuse early and honestly instead.
        raise OAuthError(
            f"{spec.name} has a client id but no client secret on this server, so sign-in cannot finish. "
            "Add the secret once under One-time setup, or connect with a personal token.")
    if not cid:
        cid, _secret = await dynamic_client(spec)
    if not cid:
        raise OAuthError(f"{spec.name} is not ready for one-click sign-in yet.")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48) if spec.auth.pkce else ""
    with session() as s:
        row = AuthSession(
            state=state,
            workspace_id=workspace_id,
            entity_id=entity_id,
            app_slug=spec.slug,
            code_verifier=verifier,
            redirect_after=redirect_after or "/app",
        )
        s.add(row)
        s.flush()
        session_id = row.id

    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri(spec),
        "response_type": "code",
        "state": state,
        "scope": " ".join(spec.auth.scopes),
        **(spec.auth.authorize_params or {}),
    }
    if spec.auth.pkce:
        challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
        params.update({"code_challenge": challenge, "code_challenge_method": "S256"})
    query = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items() if v not in (None, ""))
    authorize_url = f"{spec.auth.authorize_url}?{query}"
    return session_id, authorize_url


async def complete_oauth(state: str, code: str) -> ConnectedAccount:
    from .catalog import catalog

    with session() as s:
        pending = s.scalar(select(AuthSession).where(AuthSession.state == state))
        if pending is None or pending.consumed:
            raise OAuthError("This authorization link is invalid or has already been used.")
        if datetime.now(timezone.utc) - pending.created_at.replace(tzinfo=pending.created_at.tzinfo or timezone.utc) > timedelta(minutes=20):
            raise OAuthError("This authorization link expired. Start the connection again.")
        spec = catalog.get(pending.app_slug)
        if spec is None:
            raise OAuthError("Unknown app in this authorization session.")
        cid, secret = _client_creds(spec)
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(spec),
            "client_id": cid,
            "client_secret": secret,
            **(spec.auth.token_params or {}),
        }
        if pending.code_verifier:
            payload["code_verifier"] = pending.code_verifier
        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(spec.auth.token_url, data=payload, headers=headers)
        if resp.status_code >= 400:
            raise OAuthError(f"Token exchange failed ({resp.status_code}): {resp.text[:200]}")
        try:
            token_data = resp.json()
        except ValueError:
            from urllib.parse import parse_qs
            token_data = {k: v[0] for k, v in parse_qs(resp.text).items()}
        if "access_token" not in token_data:
            raise OAuthError(f"Provider did not return an access token: {str(token_data)[:200]}")

        creds = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token", ""),
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scope", " ".join(spec.auth.scopes)),
            "raw": {k: v for k, v in token_data.items() if isinstance(v, (str, int, float))},
        }
        expires_at = None
        if token_data.get("expires_in"):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]) - 30)

        account = s.scalar(
            select(ConnectedAccount).where(
                ConnectedAccount.workspace_id == pending.workspace_id,
                ConnectedAccount.entity_id == pending.entity_id,
                ConnectedAccount.app_slug == spec.slug,
            )
        )
        if account is None:
            account = ConnectedAccount(
                workspace_id=pending.workspace_id,
                entity_id=pending.entity_id,
                app_slug=spec.slug,
            )
            s.add(account)
        account.auth_type = spec.auth.type
        account.status = "active"
        account.credentials_enc = encrypt_json(creds)
        account.scopes = str(creds["scope"] or "")
        account.expires_at = expires_at
        account.label = str(creds.get("scope") or "")[:120]
        pending.consumed = True
        s.flush()
        return account


def store_api_key(workspace_id: str, entity_id: str, spec: AppSpec, values: dict[str, Any], label: str = "") -> ConnectedAccount:
    """Store user-pasted credentials for api_key / bearer / basic apps."""
    with session() as s:
        account = s.scalar(
            select(ConnectedAccount).where(
                ConnectedAccount.workspace_id == workspace_id,
                ConnectedAccount.entity_id == entity_id,
                ConnectedAccount.app_slug == spec.slug,
            )
        )
        if account is None:
            account = ConnectedAccount(workspace_id=workspace_id, entity_id=entity_id, app_slug=spec.slug)
            s.add(account)
        account.auth_type = spec.auth.type
        account.status = "active"
        account.credentials_enc = encrypt_json(values)
        account.label = label or "api key"
        account.scopes = ""
        s.flush()
        return account


def credentials_for(workspace_id: str, entity_id: str, spec: AppSpec) -> dict[str, Any] | None:
    import os as _os

    with session() as s:
        account = s.scalar(
            select(ConnectedAccount).where(
                ConnectedAccount.workspace_id == workspace_id,
                ConnectedAccount.entity_id == entity_id,
                ConnectedAccount.app_slug == spec.slug,
                ConnectedAccount.status == "active",
            )
        )
        if account is None:
            if spec.auth.static_env:
                val = _os.getenv(spec.auth.static_env, "").strip()
                if val:
                    return {"api_key": val, "token": val, "access_token": val}
            return None
        try:
            return decrypt_json(account.credentials_enc)
        except ValueError:
            return None


async def refresh_if_needed(account: ConnectedAccount, spec: AppSpec) -> None:
    if not account.expires_at:
        return
    expires = account.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires - datetime.now(timezone.utc) > timedelta(seconds=60):
        return
    creds = decrypt_json(account.credentials_enc)
    refresh = creds.get("refresh_token")
    if not refresh or not spec.auth.token_url:
        account.status = "expired"
        return
    cid, secret = _client_creds(spec)
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": cid,
        "client_secret": secret,
    }
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.post(spec.auth.token_url, data=payload, headers={"Accept": "application/json"})
    if resp.status_code >= 400:
        account.status = "expired"
        return
    token_data = resp.json()
    creds["access_token"] = token_data.get("access_token", creds.get("access_token"))
    if token_data.get("refresh_token"):
        creds["refresh_token"] = token_data["refresh_token"]
    account.credentials_enc = encrypt_json(creds)
    account.status = "active"
    if token_data.get("expires_in"):
        account.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]) - 30)


def public_redact(account: ConnectedAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "app": account.app_slug,
        "entity_id": account.entity_id,
        "status": account.status,
        "label": account.label,
        "scopes": account.scopes.split() if account.scopes else [],
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "expires_at": account.expires_at.isoformat() if account.expires_at else None,
        "base_url": _safe_base_url(account),
    }


def _safe_base_url(account: ConnectedAccount) -> str:
    """Expose the user-supplied API host, never the secret material."""
    if not account.credentials_enc:
        return ""
    try:
        creds = decrypt_json(account.credentials_enc)
    except Exception:
        return ""
    value = creds.get("base_url") if isinstance(creds, dict) else None
    return str(value)[:300] if value else ""


async def _fetch_meta(url: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        return await client.get(url)


async def _post_registration(url: str, payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.post(url, json=payload)
