"""Failure classification and safe-retry policy."""
import asyncio

import pytest

from tony import runtime as rt


@pytest.mark.parametrize("status,message,kind", [
    (401, "unauthorized", rt.AUTH),
    (403, "insufficient scope", rt.PERMISSION),
    (404, "not found", rt.NOT_FOUND),
    (422, "invalid argument", rt.INVALID_ARGUMENT),
    (429, "rate limit", rt.RATE_LIMIT),
    (503, "unavailable", rt.PROVIDER_ERROR),
    (0, "connection reset", rt.NETWORK),
])
def test_classify(status, message, kind):
    assert rt.classify(status, message) == kind


def test_writes_are_not_retried_without_idempotency():
    assert not rt.is_retryable(rt.NETWORK, method="POST", idempotent=False)
    assert rt.is_retryable(rt.NETWORK, method="POST", idempotent=True)
    assert rt.is_retryable(rt.NETWORK, method="POST", idempotency_key="k1")
    assert rt.is_retryable(rt.NETWORK, method="GET")


def test_auth_never_retries():
    assert not rt.is_retryable(rt.AUTH, method="GET")


def test_run_with_policy_retries_then_succeeds():
    calls = {"n": 0}

    async def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            return False, 503, None, "provider down"
        return True, 200, {"ok": 1}, ""

    out = asyncio.run(rt.run_with_policy(fn, method="GET", max_attempts=4))
    assert out.ok and out.attempts == 3 and out.value == {"ok": 1}


def test_run_with_policy_gives_up_on_auth():
    async def fn():
        return False, 401, None, "token expired"

    out = asyncio.run(rt.run_with_policy(fn, method="GET", max_attempts=4))
    assert not out.ok and out.kind == rt.AUTH and out.attempts == 1
    assert "Reconnect" in out.as_dict()["hint"]


def test_idempotency_claims_and_replays(ws):
    key = "test-key-123"
    first = rt.claim(key, ws, "gmail.send_email", {"to": "a@b.com"})
    assert not first.replayed
    rt.settle(key, ws, ok=True, status=200, payload={"message_id": "abc"})
    second = rt.claim(key, ws, "gmail.send_email", {"to": "a@b.com"})
    assert second.replayed and second.previous["message_id"] == "abc"


def test_idempotency_conflict_on_different_args(ws):
    key = "test-key-456"
    rt.claim(key, ws, "gmail.send_email", {"to": "a@b.com"})
    other = rt.claim(key, ws, "gmail.send_email", {"to": "z@b.com"})
    assert other.conflict
