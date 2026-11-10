"""Auth0 sign-in: standard OIDC authorization-code flow.

Tony stays the system of record for workspaces; Auth0 only proves who the person
is. State is signed with Tony's own secret so the callback cannot be forged, and
the ID token is verified against Auth0's published keys before any account is
touched.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any
from urllib.parse import urlencode

import httpx

PREFIX = "tony_state_"


def domain() -> str:
    return (os.getenv("AUTH0_DOMAIN") or "").strip().rstrip("/").removeprefix("https://")


def client_id() -> str:
    return (os.getenv("AUTH0_CLIENT_ID") or "").strip()


def client_secret() -> str:
    return (os.getenv("AUTH0_CLIENT_SECRET") or "").strip()


def configured() -> bool:
    return bool(domain() and client_id() and client_secret())


def _secret() -> bytes:
    raw = (os.getenv("TONY_TOKEN_SECRET") or "").strip()
    if raw:
        return raw.encode()
    return hashlib.sha256(b"tony-auth0-state:" + (os.getenv("DATABASE_URL") or "dev").encode()).digest()


def make_state(next_path: str = "/account") -> str:
    payload = f"{int(time.time())}:{next_path[:120]}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{PREFIX}{sig}:{payload}"


def check_state(state: str, max_age: int = 900) -> str | None:
    """Return the next path if the state is ours and fresh, else None."""
    if not state or not state.startswith(PREFIX):
        return None
    try:
        sig, _, payload = state[len(PREFIX):].partition(":")
        if not hmac.compare_digest(sig, hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()[:32]):
            return None
        ts, _, next_path = payload.partition(":")
        if int(ts) + max_age < int(time.time()):
            return None
        return next_path or "/account"
    except Exception:  # noqa: BLE001
        return None


def authorize_url(redirect_uri: str, state: str, connection: str = "") -> str:
    params = {
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
    }
    if connection:
        params["connection"] = connection
    return f"https://{domain()}/authorize?{urlencode(params)}"


async def exchange(code: str, redirect_uri: str) -> dict[str, Any]:
    """Trade the code for an ID token and return its verified claims."""
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(f"https://{domain()}/oauth/token", json={
            "grant_type": "authorization_code",
            "client_id": client_id(),
            "client_secret": client_secret(),
            "code": code,
            "redirect_uri": redirect_uri,
        })
    if r.status_code >= 400:
        raise RuntimeError(f"Auth0 rejected the code ({r.status_code}): {r.text[:160]}")
    body = r.json()
    id_token = body.get("id_token") or ""
    if not id_token:
        raise RuntimeError("Auth0 returned no id_token")
    return verify_id_token(id_token)


def verify_id_token(id_token: str) -> dict[str, Any]:
    import jwt
    from jwt import PyJWKClient

    jwks = PyJWKClient(f"https://{domain()}/.well-known/jwks.json")
    key = jwks.get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token, key=key, algorithms=["RS256"],
        audience=client_id(), issuer=f"https://{domain()}/",
        options={"verify_aud": True, "verify_iss": True},
    )
    email = str(claims.get("email") or "").strip().lower()
    if not email or not claims.get("email_verified", True):
        raise RuntimeError("Auth0 account has no verified email")
    return {"email": email, "sub": str(claims.get("sub") or ""),
            "name": str(claims.get("name") or claims.get("nickname") or email.split("@")[0])[:160],
            "picture": claims.get("picture") or ""}
