"""Firebase Authentication: Google-backed identity using the project key already on the server.

No console trip and no client secret. Tony verifies the ID token Firebase issues
against Google's published keys, then keeps its own session and workspace.
"""
from __future__ import annotations

import os
from typing import Any

JWKS = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"


def project_id() -> str:
    for name in ("FIREBASE_PROJECT_ID", "FIREBASE_AUTH_DOMAIN"):
        raw = (os.getenv(name) or "").strip()
        if raw:
            return raw.replace(".firebaseapp.com", "").replace(".web.app", "")
    # Derived from the API key's project when unset.
    return (os.getenv("FIREBASE_PROJECT_FALLBACK") or "ominiassist-ai").strip()


def web_config() -> dict[str, str]:
    """Public Firebase web settings. The API key is a public identifier, not a secret."""
    project = project_id()
    return {
        "api_key": (os.getenv("FIREBASE_API_KEY") or "").strip(),
        "auth_domain": (os.getenv("FIREBASE_AUTH_DOMAIN") or f"{project}.firebaseapp.com").strip(),
        "project_id": project,
    }


def enabled() -> bool:
    return bool(os.getenv("FIREBASE_API_KEY") or os.getenv("FIREBASE_PROJECT_ID"))


def verify(id_token: str) -> dict[str, Any]:
    import jwt
    from jwt import PyJWKClient

    if not id_token:
        raise ValueError("Missing Firebase token")
    client = PyJWKClient(JWKS)
    key = client.get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(
        id_token, key=key, algorithms=["RS256"],
        audience=project_id(), issuer=f"https://securetoken.google.com/{project_id()}",
        options={"require": ["exp", "iat", "aud", "iss", "sub"]},
    )
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise ValueError("This Firebase account has no email address")
    provider = str(claims.get("firebase", {}).get("sign_in_provider") or "password")
    if provider not in {"password", "google.com"}:
        raise ValueError(f"Unsupported Firebase provider: {provider}")
    return {
        "sub": str(claims.get("sub") or claims.get("user_id") or ""),
        "email": email,
        "name": str(claims.get("name") or email.split("@")[0])[:160],
        "picture": str(claims.get("picture") or ""),
        "provider": provider,
    }
