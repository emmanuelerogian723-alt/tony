"""Authenticator-app two-factor (RFC 6238), so a password alone is not enough.

Independent of any third-party provider: the secret lives encrypted in Tony's own
database, and codes are checked with a one-step drift tolerance.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def code_at(secret: str, when: float | None = None) -> str:
    return _code(secret, int((when or time.time()) // 30))


def verify(secret: str, code: str, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not secret or len(code) != 6 or not code.isdigit():
        return False
    step = int(time.time() // 30)
    return any(hmac.compare_digest(code, _code(secret, step + drift))
               for drift in range(-window, window + 1))


def provisioning_uri(secret: str, email: str, issuer: str = "Tony") -> str:
    from urllib.parse import quote
    label = quote(f"{issuer}:{email}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits=6&period=30")
