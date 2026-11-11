"""Hosted connect links: the way an agent gets a user to grant access without any keys.

Flow, the same shape Composio uses:
  1. The agent calls POST /v1/connect-links for an app and gets back a short-lived URL.
  2. It hands that URL to its end user.
  3. The user opens it, sees exactly which agent wants which access, and presses Connect.
  4. They sign in on the provider's own page (GitHub, Google, Slack ...) and approve.
  5. Tony stores the token encrypted and the agent can act, within the tiers it asked for.
The user never pastes a key, a client id or a secret.
"""
from __future__ import annotations

import hashlib
import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import workspace_from_request
from .catalog import catalog
from .db import session
from .models import ConnectLink, ResumeTask
from .oauth import OAuthError, start_oauth

router = APIRouter(tags=["connect-links"])
TTL_MINUTES = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _base(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _safe_redirect(url: str) -> str:
    """Only http(s) destinations, so a link cannot be turned into a javascript: redirect."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    return url.strip() if parts.scheme in {"http", "https"} and parts.netloc else ""


class LinkIn(BaseModel):
    app: str
    entity_id: str = "default"
    agent_name: str = Field(default="An agent", max_length=120)
    tiers: list[str] = Field(default_factory=lambda: ["read"])
    redirect_url: str = ""
    ttl_minutes: int = Field(default=TTL_MINUTES, ge=1, le=1440)
    resume_goal: str = Field(default="", max_length=600,
                             description="What the agent was doing; it resumes this once the user approves.")


@router.post("/v1/connect-links")
def create_link(body: LinkIn, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    spec = catalog.get(body.app)
    if spec is None:
        raise HTTPException(404, detail="Unknown app")
    allowed = {"read", "write", "destructive"}
    tiers = [t for t in body.tiers if t in allowed] or ["read"]
    token = "tcl_" + secrets.token_urlsafe(30)
    exp = datetime.now(timezone.utc) + timedelta(minutes=body.ttl_minutes)
    goal = (body.resume_goal or "").strip()
    with session() as s:
        s.add(ConnectLink(token_hash=_hash(token), workspace_id=ws, entity_id=body.entity_id[:160],
                          app_slug=spec.slug, agent_name=html.escape(body.agent_name.strip())[:120] or "An agent",
                          tiers=",".join(tiers), redirect_url=_safe_redirect(body.redirect_url),
                          expires_at=exp))
        if goal:
            s.add(ResumeTask(link_hash=_hash(token), workspace_id=ws, entity_id=body.entity_id[:160],
                             app_slug=spec.slug, goal=goal))
    return {"url": f"{_base(request)}/connect/{token}", "app": spec.slug, "tiers": tiers,
            "expires_at": exp.isoformat(timespec="seconds"), "resumes_task": bool(goal),
            "note": "Give this URL to your user. They sign in on the provider's own page; no keys are shared."}


def _load(token: str) -> ConnectLink | None:
    with session() as s:
        row = s.scalar(select(ConnectLink).where(ConnectLink.token_hash == _hash(token)))
        if row is None:
            return None
        s.expunge(row)
        return row


def _expired(row: ConnectLink) -> bool:
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    return exp <= datetime.now(timezone.utc)


TIER_WORDS = {"read": "View data", "write": "Create and change things", "destructive": "Delete things"}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<meta name="robots" content="noindex"><style>
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f7f8fa;
color:#0a0c11;font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif;padding:20px}}
.card{{width:100%;max-width:400px;background:#fff;border:1px solid rgba(10,12,17,.1);border-radius:20px;
padding:28px 24px;box-shadow:0 20px 60px rgba(10,12,17,.08)}}
.pair{{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:18px}}
.logo{{width:52px;height:52px;border-radius:14px;border:1px solid rgba(10,12,17,.1);display:grid;place-items:center;
font-weight:700;font-size:20px;background:#fff}}
.logo.t{{background:#0a0c11;color:#fff}}.line{{width:26px;height:2px;background:#0ea5e9;border-radius:2px}}
h1{{font-size:19px;margin:0 0 6px;text-align:center;letter-spacing:-.01em}}
p{{margin:0 0 14px;color:#3b4451;text-align:center;font-size:14px}}
ul{{list-style:none;padding:0;margin:0 0 18px}}
li{{padding:10px 12px;border:1px solid rgba(10,12,17,.1);border-radius:12px;margin-bottom:8px;font-size:14px}}
li b{{display:block;font-size:13px}}li span{{color:#5f6875;font-size:12.5px}}
.btn{{display:block;width:100%;padding:13px;border-radius:12px;border:0;background:#0a0c11;color:#fff;
font-weight:600;font-size:15px;text-align:center;text-decoration:none;cursor:pointer}}
.btn.ghost{{background:#fff;color:#0a0c11;border:1px solid rgba(10,12,17,.16);margin-top:8px}}
.foot{{margin-top:16px;font-size:12px;color:#8b939f;text-align:center}}
.ok{{color:#047857}}.bad{{color:#b91c1c}}</style></head><body><div class="card">{body}</div></body></html>""")


@router.get("/connect/{token}", response_class=HTMLResponse)
def consent(token: str):
    row = _load(token)
    if row is None:
        return _page("Link not found", '<h1>This link is not valid</h1><p>Ask the app that sent it for a new one.</p>')
    if _expired(row) or row.status in {"expired", "denied"}:
        return _page("Link expired", '<h1>This link has expired</h1><p>Ask the app that sent it for a fresh one.</p>')
    spec = catalog.get(row.app_slug)
    if spec is None:
        return _page("Unknown app", '<h1>This app is no longer available</h1>')
    name = html.escape(spec.name)
    agent = html.escape(row.agent_name)
    if row.status == "connected":
        return _page("Connected", f'<div class="pair"><div class="logo t">T</div><div class="line"></div>'
                                   f'<div class="logo">{name[:1]}</div></div><h1 class="ok">{name} is connected</h1>'
                                   f'<p>You can close this page. {agent} can now act within the access you approved.</p>')
    tiers = [t for t in row.tiers.split(",") if t]
    items = "".join(f'<li><b>{html.escape(TIER_WORDS.get(t, t))}</b><span>in your {name} account</span></li>' for t in tiers)
    return _page(f"Connect {spec.name}", f"""
<div class="pair"><div class="logo t">T</div><div class="line"></div><div class="logo">{name[:1]}</div></div>
<h1>{agent} wants to connect to your {name}</h1>
<p>You will sign in on {name}'s own page. Tony never sees your password.</p>
<ul>{items}</ul>
<a class="btn" href="/connect/{html.escape(token)}/go">Continue to {name}</a>
<a class="btn ghost" href="/connect/{html.escape(token)}/deny">Cancel</a>
<div class="foot">Secured by Tony. You can revoke access any time.</div>""")


@router.get("/connect/{token}/go")
async def go(token: str, request: Request):
    row = _load(token)
    if row is None or _expired(row) or row.status in {"expired", "denied", "connected"}:
        return RedirectResponse(f"/connect/{token}")
    spec = catalog.get(row.app_slug)
    if spec is None:
        return RedirectResponse(f"/connect/{token}")
    if spec.auth.type != "oauth2":
        return _page("Needs a key", f'<h1>{html.escape(spec.name)} uses a key</h1>'
                                    f'<p>This app does not offer a sign-in page, so the owner needs to add its key in the console.</p>')
    try:
        _sid, url = await start_oauth(row.workspace_id, row.entity_id, spec, f"/connect/{token}/done")
    except OAuthError as exc:
        return _page("Not ready", f'<h1>One-time setup needed</h1><p>{html.escape(str(exc))}</p>')
    with session() as s:
        live = s.scalar(select(ConnectLink).where(ConnectLink.token_hash == _hash(token)))
        if live is not None:
            live.status = "opened"
    return RedirectResponse(url)


@router.get("/connect/{token}/deny")
def deny(token: str):
    with session() as s:
        live = s.scalar(select(ConnectLink).where(ConnectLink.token_hash == _hash(token)))
        if live is not None and live.status != "connected":
            live.status = "denied"
    return _page("Cancelled", '<h1>No access was granted</h1><p>You can close this page.</p>')


async def _resume(task_id: str) -> None:
    """Pick the agent's original job back up now that the app is connected."""
    from .power import AgentIn, run_agent

    with session() as s:
        task = s.get(ResumeTask, task_id)
        if task is None or task.status != "queued":
            return
        task.status = "running"
        ws, entity, goal = task.workspace_id, task.entity_id, task.goal
        s.commit()
    try:
        out = await run_agent(ws, AgentIn(goal=goal, entity_id=entity))
        result, status = (out.get("answer") or ""), "done"
    except Exception as exc:  # noqa: BLE001 - the user still gets their connection
        result, status = f"Resume failed: {exc}"[:2000], "failed"
    with session() as s:
        task = s.get(ResumeTask, task_id)
        if task is not None:
            task.status, task.result = status, result
            task.finished_at = datetime.now(timezone.utc)


@router.get("/connect/{token}/done")
async def done(token: str):
    queued = ""
    with session() as s:
        live = s.scalar(select(ConnectLink).where(ConnectLink.token_hash == _hash(token)))
        if live is None:
            return RedirectResponse("/")
        live.status = "connected"
        live.connected_at = datetime.now(timezone.utc)
        target = live.redirect_url
        task = s.scalar(select(ResumeTask).where(ResumeTask.link_hash == _hash(token),
                                                 ResumeTask.status == "queued"))
        if task is not None:
            queued = task.id
    if queued:
        import asyncio

        asyncio.create_task(_resume(queued))
    return RedirectResponse(target) if target else RedirectResponse(f"/connect/{token}")


@router.get("/v1/resume/{token}")
def resume_status(token: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    with session() as s:
        task = s.scalar(select(ResumeTask).where(ResumeTask.link_hash == _hash(token),
                                                 ResumeTask.workspace_id == ws))
        if task is None:
            raise HTTPException(404, detail="No task was queued for this link")
        return {"status": task.status, "goal": task.goal, "result": task.result,
                "app": task.app_slug}


@router.get("/v1/connect-links/{token}")
def link_status(token: str, request: Request) -> dict[str, Any]:
    ws, _ = workspace_from_request(request)
    row = _load(token)
    if row is None or row.workspace_id != ws:
        raise HTTPException(404, detail="Unknown link")
    state = "expired" if _expired(row) and row.status in {"pending", "opened"} else row.status
    return {"status": state, "app": row.app_slug, "entity_id": row.entity_id,
            "connected": row.status == "connected"}
