"""Secret handling: encryption at rest for connected-account credentials."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .config import DATA_DIR, settings


def _key_material() -> bytes:
    raw = settings.secret_key
    if not raw:
        # Deterministic dev fallback so restarts keep data readable.
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        f = DATA_DIR / ".tony-secret"
        if not f.exists():
            f.write_text(secrets.token_urlsafe(48))
            try:
                os.chmod(f, 0o600)
            except OSError:
                pass
        raw = f.read_text().strip()
    return raw.encode()


def _fernet() -> Fernet:
    digest = hashlib.sha256(_key_material()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_json(payload: dict[str, Any]) -> str:
    """Encrypt a credentials dict for storage."""
    return _fernet().encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()


def decrypt_json(token: str) -> dict[str, Any]:
    """Decrypt stored credentials. Raises ValueError on a bad key."""
    try:
        return json.loads(_fernet().decrypt(token.encode()).decode())
    except (InvalidToken, json.JSONDecodeError) as exc:  # pragma: no cover - key mismatch
        raise ValueError("Stored credentials could not be decrypted with this key") from exc


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    """Returns (plaintext, prefix, hash). Only the prefix + hash are stored."""
    raw = secrets.token_urlsafe(30)
    key = f"tk_live_{raw}"
    prefix = key[:16]
    return key, prefix, hash_api_key(key)


def sign_payload(secret: str, body: bytes, timestamp: int | None = None) -> str:
    ts = timestamp or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify_signature(secret: str, body: bytes, header: str) -> bool:
    try:
        parts = dict(item.split("=", 1) for item in header.split(","))
        ts = int(parts["t"])
        if abs(time.time() - ts) > 300:
            return False
        expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])
    except Exception:
        return False


# ── Tiny signed cookie helpers (dashboard session) ─────────────────────────
def sign_cookie(value: str) -> str:
    mac = hmac.new(_key_material(), value.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{value}.{mac}"


def verify_cookie(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    value, mac = token.rsplit(".", 1)
    expected = hmac.new(_key_material(), value.encode(), hashlib.sha256).hexdigest()[:32]
    return value if hmac.compare_digest(mac, expected) else None


def read_secret_file(path: str | Path) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""
