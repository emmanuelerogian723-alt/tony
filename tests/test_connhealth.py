"""Connection health: proactive refresh and monitoring."""
from datetime import datetime, timedelta, timezone

import pytest

from tony import connhealth
from tony.db import SessionLocal, init_db
from tony.models import ConnectedAccount, Workspace


def _account(ws_id: str, app="gmail", status="active", minutes=5) -> str:
    init_db()
    s = SessionLocal()
    try:
        acc = ConnectedAccount(
            workspace_id=ws_id, entity_id="default", app_slug=app,
            auth_type="oauth2", status=status, credentials_enc="{}",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        )
        s.add(acc)
        s.commit()
        return acc.id
    finally:
        s.close()


def _workspace(name="health") -> str:
    init_db()
    s = SessionLocal()
    try:
        ws = Workspace(name=name)
        s.add(ws)
        s.commit()
        return ws.id
    finally:
        s.close()


@pytest.mark.asyncio
async def test_sweep_refreshes_expiring_connections(monkeypatch):
    from tony import oauth
    ws = _workspace()
    _account(ws, minutes=2)
    seen = {"n": 0}

    async def fake_refresh(account, spec):
        seen["n"] += 1
        account.status = "active"

    monkeypatch.setattr(oauth, "refresh_if_needed", fake_refresh)
    out = await connhealth.sweep()
    assert out["checked"] >= 1
    assert seen["n"] >= 1
    assert out["errors"] == 0


@pytest.mark.asyncio
async def test_sweep_marks_expired_when_refresh_says_so(monkeypatch):
    from tony import oauth
    ws = _workspace("health2")
    _account(ws, status="expired", minutes=-30)

    async def fake_refresh(account, spec):
        account.status = "expired"

    monkeypatch.setattr(oauth, "refresh_if_needed", fake_refresh)
    out = await connhealth.sweep()
    assert out["needs_reauth"] >= 1


def test_summary_groups_by_app():
    ws = _workspace("health3")
    _account(ws, app="gmail")
    _account(ws, app="slack", status="expired")
    out = connhealth.summary(ws)
    assert out["accounts"] >= 2
    apps = {a["app"]: a for a in out["apps"]}
    assert apps["slack"]["expired"] >= 1
    assert "last_sweep" in out
