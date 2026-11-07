"""Console accounts: email+password, Google sign-in, sessions, profile, per-user workspaces."""
from __future__ import annotations

import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import rate_limit
from .config import settings
from .crypto import new_api_key
from .db import session
from .models import ApiKey, User, UserSession, Workspace

router = APIRouter(prefix="/v1/account", tags=["account"])

COOKIE = "tony_session"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs"
_jwks: dict[str, Any] = {"at": 0.0, "keys": None}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt(rounds=12)).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bool(hashed) and bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def public_user(u: User) -> dict[str, Any]:
    return {
        "id": u.id, "email": u.email, "name": u.name or u.email.split("@")[0],
        "picture": u.picture, "has_password": bool(u.password_hash),
        "google": bool(u.google_sub), "workspace_id": u.workspace_id,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _new_workspace(s, name: str) -> Workspace:
    ws = Workspace(name=(name or "Workspace")[:120], is_demo=False)
    s.add(ws)
    s.flush()
    return ws


def _start_session(s, user: User, request: Request, response: Response) -> None:
    token = secrets.token_urlsafe(40)
    exp = datetime.now(timezone.utc) + timedelta(days=settings.session_days)
    s.add(UserSession(user_id=user.id, token_hash=_hash_token(token), expires_at=exp,
                      user_agent=(request.headers.get("user-agent") or "")[:200]))
    user.last_login_at = datetime.now(timezone.utc)
    secure = (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, max_age=settings.session_days * 86400, httponly=True,
                        samesite="lax", secure=secure, path="/")


def current_user(request: Request) -> User | None:
    token = request.cookies.get(COOKIE, "")
    if not token:
        return None
    with session() as s:
        row = s.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
        if row is None:
            return None
        exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            s.delete(row)
            return None
        return s.get(User, row.user_id)


def require_user(request: Request) -> User:
    u = current_user(request)
    if u is None:
        raise HTTPException(401, detail="Sign in to continue")
    return u


# ── email + password ─────────────────────────────────────────────────────
class SignupIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    name: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(f"signup:{_client_ip(request)}", 8)
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, detail="Enter a valid email address")
    with session() as s:
        if s.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, detail="That email already has an account. Sign in instead.")
        name = body.name.strip()[:160] or email.split("@")[0]
        ws = _new_workspace(s, f"{name}'s workspace")
        user = User(email=email, name=name, password_hash=hash_password(body.password), workspace_id=ws.id)
        s.add(user)
        s.flush()
        _start_session(s, user, request, response)
        return {"user": public_user(user)}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(f"login:{_client_ip(request)}", 10)
    email = body.email.strip().lower()
    with session() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is None or not check_password(body.password, user.password_hash):
            if user is not None and not user.password_hash and user.google_sub:
                raise HTTPException(400, detail="This account uses Google. Use Continue with Google.")
            raise HTTPException(401, detail="Wrong email or password")
        _start_session(s, user, request, response)
        return {"user": public_user(user)}


# ── Google sign-in (Google Identity Services ID token) ───────────────────
class GoogleIn(BaseModel):
    credential: str


def _google_keys() -> dict[str, Any]:
    now = time.time()
    if _jwks["keys"] and now - _jwks["at"] < 3600:
        return _jwks["keys"]
    r = httpx.get(GOOGLE_CERTS, timeout=10)
    r.raise_for_status()
    keys = {k["kid"]: k for k in r.json()["keys"]}
    _jwks.update(at=now, keys=keys)
    return keys


def verify_google_credential(credential: str) -> dict[str, Any]:
    """Verify signature, audience, issuer and expiry of a Google ID token."""
    if not settings.google_client_id:
        raise HTTPException(503, detail="Google sign-in is not configured on this server")
    try:
        header = jwt.get_unverified_header(credential)
        jwk = _google_keys().get(header.get("kid"))
        if jwk is None:
            _jwks["keys"] = None
            jwk = _google_keys().get(header.get("kid"))
        if jwk is None:
            raise HTTPException(401, detail="Unknown Google signing key")
        claims = jwt.decode(credential, key=jwt.PyJWK(jwk).key, algorithms=["RS256"],
                            audience=settings.google_client_id, leeway=30,
                            options={"require": ["exp", "iss", "aud", "sub"]})
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(401, detail=f"Google sign-in failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, detail="Could not reach Google to verify the sign-in") from exc
    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise HTTPException(401, detail="Bad token issuer")
    if not claims.get("email") or not claims.get("email_verified"):
        raise HTTPException(401, detail="Your Google email is not verified")
    return claims


@router.post("/google")
def google_login(body: GoogleIn, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(f"google:{_client_ip(request)}", 20)
    claims = verify_google_credential(body.credential)
    email = str(claims["email"]).lower()
    with session() as s:
        user = s.scalar(select(User).where(User.google_sub == claims["sub"])) \
            or s.scalar(select(User).where(User.email == email))
        if user is None:
            name = claims.get("name") or email.split("@")[0]
            ws = _new_workspace(s, f"{name}'s workspace")
            user = User(email=email, name=name, picture=claims.get("picture", ""),
                        google_sub=claims["sub"], workspace_id=ws.id)
            s.add(user)
            s.flush()
        else:
            user.google_sub = user.google_sub or claims["sub"]
            user.picture = claims.get("picture") or user.picture
            user.name = user.name or claims.get("name", "")
            if not user.workspace_id:
                user.workspace_id = _new_workspace(s, f"{user.name}'s workspace").id
        _start_session(s, user, request, response)
        return {"user": public_user(user)}


@router.get("/config")
def public_config() -> dict[str, Any]:
    return {"google_client_id": settings.google_client_id, "demo_open": settings.demo_open}


# ── session + profile ────────────────────────────────────────────────────
@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    u = current_user(request)
    return {"user": public_user(u) if u else None}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    token = request.cookies.get(COOKIE, "")
    if token:
        with session() as s:
            row = s.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
            if row:
                s.delete(row)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)


@router.patch("/profile")
def update_profile(body: ProfileIn, request: Request) -> dict[str, Any]:
    u = require_user(request)
    with session() as s:
        row = s.get(User, u.id)
        row.name = body.name.strip()
        return {"user": public_user(row)}


class PasswordIn(BaseModel):
    current: str = ""
    new: str = Field(min_length=8, max_length=200)


@router.post("/password")
def change_password(body: PasswordIn, request: Request) -> dict[str, Any]:
    u = require_user(request)
    with session() as s:
        row = s.get(User, u.id)
        if row.password_hash and not check_password(body.current, row.password_hash):
            raise HTTPException(400, detail="Current password is wrong")
        row.password_hash = hash_password(body.new)
    return {"ok": True}


@router.delete("/")
def delete_account(request: Request, response: Response) -> dict[str, Any]:
    u = require_user(request)
    with session() as s:
        for row in s.scalars(select(UserSession).where(UserSession.user_id == u.id)).all():
            s.delete(row)
        row = s.get(User, u.id)
        ws = s.get(Workspace, row.workspace_id) if row and row.workspace_id else None
        if row:
            s.delete(row)
        if ws and not ws.is_demo:
            s.delete(ws)
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


# ── API keys for this user's workspace ───────────────────────────────────
@router.get("/keys")
def list_keys(request: Request) -> dict[str, Any]:
    u = require_user(request)
    with session() as s:
        rows = s.scalars(select(ApiKey).where(ApiKey.workspace_id == u.workspace_id,
                                              ApiKey.revoked.is_(False))).all()
        return {"keys": [{"id": k.id, "name": k.name, "prefix": k.prefix,
                          "created_at": k.created_at.isoformat() if k.created_at else None,
                          "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None}
                         for k in rows]}


class KeyNameIn(BaseModel):
    name: str = "default"


@router.post("/keys")
def create_key(body: KeyNameIn, request: Request) -> dict[str, Any]:
    u = require_user(request)
    plain, prefix, hashed = new_api_key()
    with session() as s:
        count = len(s.scalars(select(ApiKey).where(ApiKey.workspace_id == u.workspace_id,
                                                   ApiKey.revoked.is_(False))).all())
        if count >= 20:
            raise HTTPException(400, detail="You have 20 active keys. Revoke one first.")
        k = ApiKey(workspace_id=u.workspace_id, name=(body.name or "key")[:120],
                   prefix=prefix, key_hash=hashed)
        s.add(k)
        s.flush()
        return {"key": plain, "id": k.id, "name": k.name, "prefix": prefix,
                "note": "Copy it now. It is shown once."}


@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, request: Request) -> dict[str, Any]:
    u = require_user(request)
    with session() as s:
        k = s.get(ApiKey, key_id)
        if k is None or k.workspace_id != u.workspace_id:
            raise HTTPException(404, detail="Key not found")
        k.revoked = True
    return {"ok": True}
