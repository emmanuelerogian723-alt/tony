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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import workspace_from_request
from .catalog import catalog
from .db import session
from .models import ConnectLink, ResumeTask
from .connectbrand import PAIR_CSS, pair
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


_BASE_CSS = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f7f6f3;
color:#0d0d0c;font:15px/1.55 Inter,system-ui,-apple-system,Segoe UI,sans-serif;padding:20px;-webkit-font-smoothing:antialiased}
.card{width:100%;max-width:400px;background:#fff;border:1px solid rgba(13,13,12,.1);border-radius:22px;
padding:30px 26px 22px;box-shadow:0 24px 70px rgba(13,13,12,.12);text-align:center;
background-image:linear-gradient(180deg,rgba(255,138,92,.14),rgba(255,255,255,0) 130px)}
h1{font-size:19px;margin:0 0 6px;letter-spacing:-.01em;font-weight:650}
p{margin:0 0 14px;color:#55544d;font-size:14px}
ul{list-style:none;padding:0;margin:0 0 18px;text-align:left}
li{padding:10px 12px;border:1px solid rgba(13,13,12,.1);border-radius:12px;margin-bottom:8px;font-size:14px}
li b{display:block;font-size:13px}li span{color:#5f6875;font-size:12.5px}
.btn{display:block;width:100%;padding:13px;border-radius:12px;border:0;background:#0d0d0c;color:#fff;
font-weight:600;font-size:15px;text-align:center;text-decoration:none;cursor:pointer}
.btn[disabled]{background:#9a9892;cursor:default}
.btn.ghost{background:#fff;color:#0d0d0c;border:1px solid rgba(13,13,12,.16);margin-top:8px}
.foot{margin-top:16px;padding-top:14px;border-top:1px solid #f0efeb;font-size:12px;color:#8b8a82;text-align:center}
.ok{color:#047857}.bad{color:#b91c1c}
input.k{width:100%;border:1px solid rgba(13,13,12,.16);border-radius:12px;padding:12px;font:inherit;font-size:14px;margin:0 0 10px;outline:0}
input.k:focus{border-color:#0d0d0c}label.l{display:block;font-size:12.5px;color:#3b4451;margin:0 0 4px;text-align:left}
.err{color:#b91c1c;font-size:13px;margin:0 0 10px;text-align:center}.hint{font-size:12.5px;color:#5f6875;text-align:left;margin:-4px 0 12px}
"""


def _page(title: str, body: str, script: str = "") -> HTMLResponse:
    return HTMLResponse(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{html.escape(title)}</title><meta name="robots" content="noindex">'
        '<link rel="icon" href="/favicon.ico">'
        f'<style>{_BASE_CSS}{PAIR_CSS}</style></head><body><div class="card">{body}</div>{script}</body></html>')


def _mode(spec) -> str:
    """How this app signs a user in: google (Firebase consent), oauth, key, or none."""
    from . import provider_registry as pr

    if spec.auth.type == "none":
        return "none"
    prov = pr.provider_for(spec.slug)
    if prov and prov.slug in {"gmail", "google_drive", "google_calendar", "google_sheets"} and _firebase_ready():
        return "google"
    if spec.auth.type == "oauth2":
        from .oauth import provider_ready
        if provider_ready(spec.slug) or (prov and pr.ready(spec.slug)):
            return "oauth"
        if _firebase_ready() and prov and prov.authorize_url.startswith("https://accounts.google.com"):
            return "google"
        return "oauth-setup"
    return "key"


def _firebase_ready() -> bool:
    from . import firebase
    try:
        return bool(firebase.web_config().get("api_key"))
    except Exception:
        return False


def _key_fields(spec) -> list[dict[str, str]]:
    """The single secret a key app needs, labelled the way its own dashboard calls it."""
    from .executor import needs_base_url

    t = spec.auth.type
    label = {"bearer": "Access token", "basic": "API key", "path": "API key"}.get(t, "API key")
    where = f"{spec.name} dashboard → Settings → API"
    fields = [{"name": "token", "label": f"{spec.name} {label.lower()}", "type": "password", "hint": where}]
    if t == "basic":
        fields = [{"name": "username", "label": "Username or account ID", "type": "text", "hint": ""},
                  {"name": "password", "label": "Password or API secret", "type": "password", "hint": where}]
    if needs_base_url(spec):
        fields.append({"name": "base_url", "label": "API base URL", "type": "text",
                       "hint": "Example: https://api.yourcompany.com/v1"})
    return fields


def _head(spec, agent: str, done: bool = False) -> str:
    name = html.escape(spec.name)
    return (pair(spec.slug, done=done) +
            f'<h1>{agent} wants to connect to your {name}</h1>')


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
        return _page("Connected", pair(spec.slug, done=True) +
                     f'<h1 class="ok">{name} is connected</h1>'
                     f'<p>You can close this page. {agent} can now act within the access you approved.</p>'
                     '<div class="foot">Secured by Tony</div>')
    tiers = [t for t in row.tiers.split(",") if t]
    items = "".join(f'<li><b>{html.escape(TIER_WORDS.get(t, t))}</b><span>in your {name} account</span></li>' for t in tiers)
    mode = _mode(spec)
    tok = html.escape(token)
    if mode == "key":
        fields = _key_fields(spec)
        form = "".join(
            f'<label class="l" for="f_{f["name"]}">{html.escape(f["label"])}</label>'
            f'<input class="k" id="f_{f["name"]}" name="{f["name"]}" type="{f["type"]}" autocomplete="off" '
            f'placeholder="{html.escape(f["label"])}">' + (f'<div class="hint">{html.escape(f["hint"])}</div>' if f["hint"] else "")
            for f in fields)
        docs = (f'<a class="btn ghost" style="font-weight:500" href="{html.escape(spec.docs)}" target="_blank" rel="noopener">'
                f'Where do I find it? ↗</a>' if spec.docs else "")
        body = (_head(spec, agent) +
                f'<p>{name} does not offer a sign-in page, so you add your key here once. It goes straight to Tony\'s '
                f'encrypted vault and is never shown to {agent} or any AI model.</p><ul>{items}</ul>'
                f'<form id="kf">{form}<div class="err" id="err"></div>'
                f'<button class="btn" id="kb" type="submit">Connect {name}</button></form>{docs}'
                '<div class="foot">Secured by Tony · encrypted at rest · revoke any time</div>')
        script = ("<script>const T=" + __import__("json").dumps(token) + ";"
                  "document.getElementById('kf').onsubmit=async e=>{e.preventDefault();const b=document.getElementById('kb'),"
                  "er=document.getElementById('err');er.textContent='';const v={};"
                  "new FormData(e.target).forEach((x,k)=>v[k]=String(x).trim());"
                  "if(!Object.values(v).some(Boolean)){er.textContent='Enter your key to continue.';return}"
                  "b.disabled=true;b.textContent='Connecting…';"
                  "try{const r=await fetch('/connect/'+T+'/key',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({values:v})});"
                  "const j=await r.json();if(j.ok){location.href=j.next}else{er.textContent=j.detail||'That key did not work.';"
                  "b.disabled=false;b.textContent='Connect'}}catch(x){er.textContent='Network error. Try again.';b.disabled=false;b.textContent='Connect'}};</script>")
        return _page(f"Connect {spec.name}", body, script)
    if mode == "google":
        body = (_head(spec, agent) +
                f'<p>You will sign in with Google and approve the permissions on Google\'s own screen. Tony never sees your password.</p>'
                f'<ul>{items}</ul><button class="btn" id="gb">Continue with Google</button>'
                f'<a class="btn ghost" href="/connect/{tok}/deny">Cancel</a>'
                '<div class="err" id="err" style="margin-top:10px"></div>'
                '<div class="foot">Secured by Tony · encrypted at rest · revoke any time</div>')
        return _page(f"Connect {spec.name}", body, _google_script(token, spec))
    if mode == "oauth-setup":
        return _page(f"Connect {spec.name}", _head(spec, agent) +
                     f'<p>{name} sign-in is not switched on for this Tony deployment yet. The owner adds its OAuth app once, '
                     f'then everyone connects with one click. When it is on you sign in on {name}\'s own page, so {agent} '
                     f'never sees your password.</p><ul>{items}</ul><a class="btn ghost" href="/providers">Open provider setup</a>'
                     '<div class="foot">Secured by Tony</div>')
    if mode == "none":
        body = (_head(spec, agent) + f'<p>{name} is a public API, so no sign-in is needed and Tony never sees your password.</p><ul>{items}</ul>'
                f'<a class="btn" href="/connect/{tok}/go">Connect {name}</a>'
                '<div class="foot">Secured by Tony</div>')
        return _page(f"Connect {spec.name}", body)
    return _page(f"Connect {spec.name}", _head(spec, agent) +
                 f'<p>You will sign in on {name}\'s own page. Tony never sees your password.</p><ul>{items}</ul>'
                 f'<a class="btn" href="/connect/{tok}/go">Continue to {name}</a>'
                 f'<a class="btn ghost" href="/connect/{tok}/deny">Cancel</a>'
                 '<div class="foot">Secured by Tony · encrypted at rest · revoke any time</div>')


def _google_script(token: str, spec) -> str:
    import json as _j
    from . import firebase, provider_registry as pr

    cfg = _j.dumps(firebase.web_config())
    prov = pr.provider_for(spec.slug)
    scopes = _j.dumps(list(prov.scopes) if prov else [])
    return (
        '<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>'
        '<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js"></script>'
        f'<script>window.TONY_FB={cfg};</script><script src="/static/connect.js"></script>'
        f'<script>const T={_j.dumps(token)},SC={scopes};const b=document.getElementById("gb"),er=document.getElementById("err");'
        'async function fin(tk){b.disabled=true;b.textContent="Connecting…";'
        'const r=await fetch("/connect/"+T+"/google",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({access_token:tk})});'
        'const j=await r.json();if(j.ok){location.href=j.next}else{er.textContent=j.detail||"Google sign-in did not complete.";b.disabled=false;b.textContent="Continue with Google"}}'
        'b.onclick=async()=>{er.textContent="";b.disabled=true;b.textContent="Opening Google…";'
        'try{const tk=await TonyConnect.google(SC,"link");if(tk)await fin(tk)}catch(e){er.textContent=String((e&&(e.code||e.message))||"Sign-in failed").replace("auth/","");'
        'b.disabled=false;b.textContent="Continue with Google"}};'
        '(async()=>{try{const tk=await TonyConnect.finishRedirect();if(tk)await fin(tk)}catch(e){}})();</script>')


class _KeyBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class _GoogleBody(BaseModel):
    access_token: str


def _live_link(token: str) -> tuple[ConnectLink, Any]:
    row = _load(token)
    if row is None or _expired(row) or row.status in {"expired", "denied"}:
        raise HTTPException(410, detail="This link has expired. Ask for a new one.")
    spec = catalog.get(row.app_slug)
    if spec is None:
        raise HTTPException(404, detail="Unknown app")
    return row, spec


def _mark_connected(token: str) -> str:
    return f"/connect/{token}/done"


@router.post("/connect/{token}/key")
async def submit_key(token: str, body: _KeyBody):
    """A user pastes their key on Tony's own page. It is probed once, then stored encrypted."""
    from .api import normalise_base_url
    from .oauth import store_api_key

    row, spec = _live_link(token)
    if spec.auth.type in {"oauth2", "none"}:
        raise HTTPException(400, detail="This app does not use a key.")
    values = {k: v.strip() for k, v in body.values.items() if v and v.strip()}
    if "base_url" in values:
        values["base_url"] = normalise_base_url(values["base_url"])
    secret = {k: v for k, v in values.items() if k != "base_url"}
    if not secret:
        raise HTTPException(400, detail="Enter your key to continue.")
    if "token" in secret:
        values.setdefault("api_key", secret["token"])
        values.setdefault("access_token", secret["token"])
    store_api_key(row.workspace_id, row.entity_id, spec, values, "connected via Tony link")
    return {"ok": True, "next": _mark_connected(token)}


@router.post("/connect/{token}/google")
async def submit_google(token: str, body: _GoogleBody):
    """Google apps: the browser got a token through the Firebase project; verify and store it."""
    from . import authflow

    row, spec = _live_link(token)
    try:
        res = await authflow.store_google_token(row.workspace_id, row.entity_id, spec, body.access_token)
    except HTTPException as exc:
        return JSONResponse(status_code=200, content={"ok": False, "detail": exc.detail})
    return {"ok": bool(res), "next": _mark_connected(token)}


@router.get("/connect/{token}/go")
async def go(token: str, request: Request):
    row = _load(token)
    if row is None or _expired(row) or row.status in {"expired", "denied", "connected"}:
        return RedirectResponse(f"/connect/{token}")
    spec = catalog.get(row.app_slug)
    if spec is None:
        return RedirectResponse(f"/connect/{token}")
    if spec.auth.type == "none":
        from .models import ConnectedAccount
        with session() as s:
            s.add(ConnectedAccount(workspace_id=row.workspace_id, entity_id=row.entity_id, app_slug=spec.slug,
                                   auth_type="none", status="active", label="public access",
                                   credentials_enc="", scopes="", meta_json="{}"))
        return RedirectResponse(f"/connect/{token}/done")
    if spec.auth.type != "oauth2":
        return RedirectResponse(f"/connect/{token}")
    try:
        _sid, url = await start_oauth(row.workspace_id, row.entity_id, spec, f"/connect/{token}/done")
    except OAuthError as exc:
        return _page("Not ready", pair(spec.slug) + f'<h1>One-time setup needed</h1><p>{html.escape(str(exc))}</p>')
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
