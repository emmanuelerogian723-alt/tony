import asyncio
import json

import pytest

from tony import syncs
from tony.executor import ExecResult
from tony.db import session
from tony.syncs import Sync, SyncRecord


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    def wipe():
        with session() as s:
            s.query(SyncRecord).delete()
            s.query(Sync).delete()
    wipe()
    monkeypatch.setattr(syncs, "credentials_for", lambda *a, **k: {"access_token": "test"})
    yield
    wipe()


def _fake(items):
    async def fake_execute(spec, action, args, creds, **kwargs):
        return ExecResult(True, 200, 5, {"items": items}, {})

    return fake_execute


def test_sync_upserts_and_dedupes(client, monkeypatch):
    items = [{"id": "1", "name": "Ada"}, {"id": "2", "name": "Grace"}]
    monkeypatch.setattr(syncs, "execute", _fake(items))

    created = client.post("/v1/syncs", json={"action": "github.list_repos",
                                            "args": {"per_page": 10},
                                            "interval_seconds": 600}).json()
    assert created["first_run"]["ok"] is True
    assert created["first_run"]["added"] == 2
    assert created["records_count"] == 2

    again = client.post(f"/v1/syncs/{created['id']}/run").json()
    assert again["added"] == 0 and again["updated"] == 0
    assert again["total"] == 2

    items[1]["name"] = "Grace H."
    monkeypatch.setattr(syncs, "execute", _fake(items))
    changed = client.post(f"/v1/syncs/{created['id']}/run").json()
    assert changed["updated"] == 1 and changed["added"] == 0

    records = client.get(f"/v1/syncs/{created['id']}/records").json()
    assert records["total"] == 2
    assert any(r["data"]["name"] == "Grace H." for r in records["records"])


def test_cursor_is_passed_to_the_action(client, monkeypatch):
    seen = {}

    async def fake_execute(spec, action, args, creds, **kwargs):
        seen.update(args)
        return ExecResult(True, 200, 5, [], {})

    monkeypatch.setattr(syncs, "execute", fake_execute)
    created = client.post("/v1/syncs", json={"action": "github.list_repos",
                                            "args": {"since": "{{cursor}}"}}).json()
    assert created["first_run"]["ok"] is True
    assert seen["since"] and seen["since"] != "{{cursor}}"


def test_unknown_action_and_pause(client):
    assert client.post("/v1/syncs", json={"action": "nope.nothing"}).status_code == 404

    created = client.post("/v1/syncs", json={"action": "github.list_repos"}).json()
    paused = client.post(f"/v1/syncs/{created['id']}/pause").json()
    assert paused["status"] == "paused"
    resumed = client.post(f"/v1/syncs/{created['id']}/resume").json()
    assert resumed["status"] == "active"


def test_failure_records_the_reason(client, monkeypatch):
    async def failing(spec, action, args, creds, **kwargs):
        return ExecResult(False, 429, 5, None, {}, error="rate limit exceeded")

    monkeypatch.setattr(syncs, "execute", failing)
    created = client.post("/v1/syncs", json={"action": "github.list_repos"}).json()
    assert created["status"] == "error"
    assert "rate_limit" in created["last_error"]
