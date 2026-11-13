"""Console accounts: email+password, Google sign-in, sessions, profile, per-user workspaces."""
from __future__ import annotations

import hashlib
import os
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

from .billing import check_capacity, ensure_subscription, summary
from . import auth0
from . import firebase
from .auth import rate_limit
from .config import settings
from .crypto import hash_api_key, new_api_key
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
    # The first element is whatever the caller typed. Behind Render's proxy the
    # last element is the hop the edge appended, which is the same rule the
    # firewall uses - one subject everywhere, so throttles cannot be dodged by
    # inventing a header, and an innocent IP cannot be framed into a block.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[-1][:80]
    return request.client.host if request.client else "?"


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
        # No browser session: a workspace key is still a credential, and it names
        # its owner. This is what makes the key "universal" across the API.
        return _user_from_api_key(request)
    with session() as s:
        row = s.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
        if row is None:
            return None
        exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            s.delete(row)
            return None
        return s.get(User, row.user_id)


def _user_from_api_key(request: Request) -> User | None:
    """A workspace key minted in the console carries its owner.

    Account endpoints used to answer "Sign in to continue" to a perfectly valid
    ``tk_live_`` key, which made the key look broken on exactly the pages that
    prove who it belongs to. The key is verified here (prefix + hash) before the
    user is trusted, so a forged key still fails.
    """
    raw = (request.headers.get("x-api-key") or "").strip()
    if not raw:
        auth = (request.headers.get("authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            raw = auth.split(" ", 1)[1].strip()
    if not raw.startswith("tk_"):
        return None
    try:
        with session() as s:
            row = s.scalar(select(ApiKey).where(ApiKey.prefix == raw[:16], ApiKey.revoked.is_(False)))
            if row is None or row.key_hash != hash_api_key(raw) or not row.user_id:
                return None
            return s.get(User, row.user_id)
    except Exception:  # noqa: BLE001 - a broken lookup must not crash a page
        return None


def is_instance_owner(user: User) -> bool:
    """The first account on this deployment owns it, unless TONY_OWNER_EMAIL says otherwise.

    Provider credentials are deployment-wide: one registered OAuth app serves every
    user. So only the owner may register or replace them, never any signed-in user.
    """
    import os as _os

    raw = ",".join(x for x in ((_os.getenv("TONY_OWNER_EMAIL") or ""),
                               (_os.getenv("TONY_ADMIN_EMAILS") or "")) if x)
    allow = [e.strip().lower() for e in raw.split(",") if e.strip()]
    if allow:
        return (user.email or "").lower() in allow
    with session() as s:
        first = s.scalar(select(User).order_by(User.created_at.asc()).limit(1))
        return bool(first is not None and first.id == user.id)


def require_owner(request: Request) -> User:
    user = require_user(request)
    if not is_instance_owner(user):
        raise HTTPException(403, detail="Only the workspace owner can register provider credentials. "
                                        "Set TONY_OWNER_EMAIL to the account that should manage them.")
    return user


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
    code: str = ""


@router.post("/signup")
def signup(body: SignupIn, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(f"signup:{_client_ip(request)}", int(os.getenv("TONY_SIGNUP_RATE", "12")))
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
        ensure_subscription(s, user)
        _start_session(s, user, request, response)
        return {"user": public_user(user), "plan": "trial"}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(f"login:{_client_ip(request)}", 10)
    email = body.email.strip().lower()
    with session() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is not None and check_password(body.password, user.password_hash):
            from . import totp
            from .models import UserTotp
            from .crypto import decrypt_text

            factor = s.scalar(select(UserTotp).where(UserTotp.user_id == user.id))
            if factor is not None and factor.confirmed:
                secret = decrypt_text(factor.secret_enc)
                if not totp.verify(secret, body.code or ""):
                    raise HTTPException(401, detail="Enter the 6-digit code from your authenticator app")
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
            ensure_subscription(s, user)
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
    """Only sign-in methods this deployment can actually finish.

    Auth0 used to be advertised here (and its route answered 503) while being
    unconfigured, so a client could pick a door with no room behind it.
    """
    return {"google_client_id": settings.google_client_id,
            "demo_open": settings.demo_open,
            "auth0": auth0.configured(),
            "firebase": firebase.enabled()}


# ── session + profile ────────────────────────────────────────────────────
@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    u = current_user(request)
    if u is None:
        return {"user": None}
    return {"user": public_user(u), "billing": summary(u.workspace_id)}


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
                          "owner": u.email, "owner_id": k.user_id or u.id,
                          "created_at": k.created_at.isoformat() if k.created_at else None,
                          "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None}
                         for k in rows]}


class KeyNameIn(BaseModel):
    name: str = "default"


@router.post("/keys")
def create_key(body: KeyNameIn, request: Request) -> dict[str, Any]:
    u = require_user(request)
    plain, prefix, hashed = new_api_key()
    check_capacity(u.workspace_id, "keys")
    with session() as s:
        k = ApiKey(workspace_id=u.workspace_id, name=(body.name or "key")[:120],
                   prefix=prefix, key_hash=hashed, user_id=u.id)
        s.add(k)
        s.flush()
        return {"key": plain, "id": k.id, "name": k.name, "prefix": prefix,
                "owner": u.email, "workspace_id": u.workspace_id,
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


class ProviderIn(BaseModel):
    client_id: str
    client_secret: str = ""


@router.get("/providers")
def list_providers(request: Request) -> dict[str, Any]:
    """Which OAuth apps are ready, so users can just click Connect."""
    require_owner(request)
    from .catalog import catalog
    from .oauth import provider_ready
    from . import provider_registry as _pr

    rows = []
    for spec in catalog.apps.values():
        if spec.auth.type != "oauth2":
            continue
        prov = _pr.provider_for(spec.slug)
        rows.append({"slug": spec.slug, "name": spec.name, "category": spec.category,
                     "ready": provider_ready(spec.slug),
                     "scopes": spec.auth.scopes,
                     "docs": getattr(prov, "docs", "") or "",
                     "env": list(getattr(prov, "env", ()) or ()),
                     "callback": f"/oauth/callback"})
    rows.sort(key=lambda r: (not r["ready"], r["name"].lower()))
    return {"providers": rows, "ready": sum(1 for r in rows if r["ready"]), "total": len(rows)}


_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _check_secret_looks_right(slug: str, secret: str) -> None:
    """Catch the common mix-up where a public key is pasted instead of a client secret."""
    if not secret:
        return
    if slug in {"discord", "slack", "twitter", "tiktok"} and _HEX64.match(secret):
        raise HTTPException(400, detail=(
            "That looks like a public key, not the client secret. "
            "Open the provider's OAuth page and copy (or reset) the client secret."))


@router.post("/providers/{app_slug}")
def set_provider(app_slug: str, body: ProviderIn, request: Request) -> dict[str, Any]:
    u = require_owner(request)
    from .catalog import catalog
    from .oauth import save_provider

    spec = catalog.get(app_slug)
    if spec is None:
        raise HTTPException(404, detail="Unknown app")
    if spec.auth.type != "oauth2":
        raise HTTPException(400, detail="This app does not use OAuth sign-in")
    if not body.client_id.strip():
        raise HTTPException(400, detail="Client id is required")
    _check_secret_looks_right(app_slug, body.client_secret.strip())
    save_provider(app_slug, body.client_id, body.client_secret, u.id)
    return {"ok": True, "slug": app_slug, "ready": True}


@router.delete("/providers/{app_slug}")
def remove_provider(app_slug: str, request: Request) -> dict[str, Any]:
    require_owner(request)
    from .oauth import drop_provider

    drop_provider(app_slug)
    return {"ok": True}


# ── Auth0 (OIDC authorization code) ───────────────────────────────────────
def _redirect_uri(request: Request) -> str:
    base = (settings.base_url or str(request.base_url)).rstrip("/")
    return f"{base}/v1/account/auth0/callback"


@router.get("/auth0/login", include_in_schema=False)
def auth0_login(request: Request, next: str = "/account", connection: str = ""):
    from fastapi.responses import RedirectResponse

    if not auth0.configured():
        # Not a broken endpoint, just one this deployment never enabled: say 404
        # rather than advertising a 503 as if something were down.
        raise HTTPException(404, detail="Auth0 sign-in is not enabled on this deployment. "
                                        "Use email, Google or the demo instead.")
    state = auth0.make_state(next)
    return RedirectResponse(auth0.authorize_url(_redirect_uri(request), state, connection))


@router.get("/auth0/callback")
async def auth0_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    from fastapi.responses import RedirectResponse

    if error:
        return RedirectResponse(f"/account?auth_error={error}")
    next_path = auth0.check_state(state)
    if not next_path:
        return RedirectResponse("/account?auth_error=bad_state")
    if not code:
        return RedirectResponse("/account?auth_error=missing_code")
    try:
        claims = await auth0.exchange(code, _redirect_uri(request))
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(f"/account?auth_error={type(exc).__name__}")

    from fastapi import Response

    response = Response()
    email = claims["email"]
    with session() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is None:
            ws = _new_workspace(s, f"{claims['name']}'s workspace")
            user = User(email=email, name=claims["name"], password_hash="", workspace_id=ws.id)
            s.add(user)
            s.flush()
            ensure_subscription(s, user)
        _start_session(s, user, request, response)
        s.commit()

    redirect = RedirectResponse(next_path if next_path.startswith("/") else "/account")
    for header, value in response.headers.items():
        if header.lower() == "set-cookie":
            redirect.headers.append("set-cookie", value)
    return redirect


# ── authenticator-app two-factor ──────────────────────────────────────────
class CodeIn(BaseModel):
    code: str


@router.get("/2fa")
def two_factor_status(request: Request) -> dict[str, Any]:
    from .models import UserTotp

    user = require_user(request)
    with session() as s:
        row = s.scalar(select(UserTotp).where(UserTotp.user_id == user.id))
        return {"enabled": bool(row and row.confirmed), "pending": bool(row and not row.confirmed)}


@router.post("/2fa/start")
def two_factor_start(request: Request) -> dict[str, Any]:
    from . import totp
    from .crypto import encrypt_text
    from .models import UserTotp

    user = require_user(request)
    secret = totp.new_secret()
    with session() as s:
        row = s.scalar(select(UserTotp).where(UserTotp.user_id == user.id))
        if row is None:
            row = UserTotp(user_id=user.id)
            s.add(row)
        row.secret_enc = encrypt_text(secret)
        row.confirmed = False
        s.commit()
    return {"secret": secret, "otpauth_url": totp.provisioning_uri(secret, user.email),
            "next": "Scan the QR with Google Authenticator or 1Password, then POST /v1/account/2fa/enable with a code."}


@router.post("/2fa/enable")
def two_factor_enable(body: CodeIn, request: Request) -> dict[str, Any]:
    from . import totp
    from .crypto import decrypt_text
    from .models import UserTotp

    user = require_user(request)
    with session() as s:
        row = s.scalar(select(UserTotp).where(UserTotp.user_id == user.id))
        if row is None:
            raise HTTPException(400, detail="Start setup first")
        if not totp.verify(decrypt_text(row.secret_enc), body.code):
            raise HTTPException(400, detail="That code did not match. Try the next one.")
        row.confirmed = True
        s.commit()
    return {"enabled": True}


@router.post("/2fa/disable")
def two_factor_disable(body: CodeIn, request: Request) -> dict[str, Any]:
    from . import totp
    from .crypto import decrypt_text
    from .models import UserTotp

    user = require_user(request)
    with session() as s:
        row = s.scalar(select(UserTotp).where(UserTotp.user_id == user.id))
        if row is None or not row.confirmed:
            return {"enabled": False}
        if not totp.verify(decrypt_text(row.secret_enc), body.code):
            raise HTTPException(400, detail="Code did not match")
        s.delete(row)
        s.commit()
    return {"enabled": False}


# ── Firebase identity (email or Google, verified by Google's own keys) ────
class FirebaseIn(BaseModel):
    id_token: str


@router.post("/firebase")
def firebase_login(body: FirebaseIn, request: Request, response: Response) -> dict[str, Any]:
    rate_limit(f"firebase:{_client_ip(request)}", 20)
    if not firebase.enabled():
        raise HTTPException(503, detail="Firebase sign-in is not configured on this server")
    try:
        claims = firebase.verify(body.id_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(401, detail=f"Firebase sign-in failed: {exc}") from exc
    email = claims["email"]
    with session() as s:
        user = s.scalar(select(User).where(User.email == email))
        if user is None:
            ws = _new_workspace(s, f"{claims['name']}'s workspace")
            user = User(email=email, name=claims["name"], picture=claims.get("picture", ""),
                        workspace_id=ws.id)
            s.add(user)
            s.flush()
            ensure_subscription(s, user)
        _start_session(s, user, request, response)
        return {"user": public_user(user), "provider": claims["provider"]}


@router.get("/firebase/status")
def firebase_status() -> dict[str, Any]:
    return {"enabled": firebase.enabled(), "project": firebase.project_id()}
