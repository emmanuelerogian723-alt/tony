"""Encryption, hashing, signature, session and SSRF helpers."""
import time

import httpx
import pytest

from tony.crypto import (
    decrypt_json,
    encrypt_json,
    hash_api_key,
    new_api_key,
    sign_cookie,
    sign_payload,
    verify_cookie,
    verify_signature,
)
from tony.executor import ExecutionError, _guarded_request


def test_credentials_roundtrip():
    creds = {"access_token": "secret-token", "refresh_token": "r2", "scope": "a b"}
    token = encrypt_json(creds)
    assert "secret-token" not in token
    assert decrypt_json(token) == creds


def test_api_key_only_prefix_and_hash_are_stored():
    key, prefix, hashed = new_api_key()
    assert key.startswith("tk_live_")
    assert key.startswith(prefix)
    assert hashed == hash_api_key(key)
    assert key not in prefix


def test_webhook_signature_roundtrip():
    body = b'{"hello":"world"}'
    header = sign_payload("whsec", body)
    assert verify_signature("whsec", body, header)
    assert not verify_signature("wrong", body, header)


def test_webhook_signature_rejects_replay():
    body = b"{}"
    old = sign_payload("whsec", body, timestamp=int(time.time()) - 3600)
    assert not verify_signature("whsec", body, old)


def test_signed_cookie():
    tok = sign_cookie("workspace-1")
    assert verify_cookie(tok) == "workspace-1"
    assert verify_cookie(tok + "x") is None
    assert verify_cookie("forged.deadbeef") is None


class _RedirectTransport(httpx.AsyncBaseTransport):
    """First hop redirects into the metadata service; the guard must refuse."""

    async def handle_async_request(self, request):
        if str(request.url).startswith("https://example.com"):
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return httpx.Response(200, json={"leaked": True})


@pytest.mark.asyncio
async def test_redirect_into_metadata_service_is_blocked():
    transport = _RedirectTransport()
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ExecutionError):
            await _guarded_request(client, "GET", "https://example.com/", headers={})
