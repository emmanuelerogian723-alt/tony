"""Signup intent capture, the post-signup query page and the Agent Playground.

Three related surfaces, all additive:

* ``Query`` rows record what a user says they want Tony to do (the post-signup
  page, and the playground). This is product telemetry the owner can read back.
* ``/query``  - the page a user lands on after signup: Tony icon, one question,
  and a record of what they asked for.
* ``/playground`` - a Nango-style loop: ask -> Tony finds the tool -> connect the
  account if needed -> run it -> see the real result.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from . import catalog
from .db import session
from .models import Base, now, uid

router = APIRouter(include_in_schema=False)


# ── storage ───────────────────────────────────────────────────────────────────

class Query(Base):
    """One thing a person wants done. These answers drive product decisions."""

    __tablename__ = "queries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    user_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(24), default="signup")  # signup|playground|survey
    matched_action: Mapped[str] = mapped_column(String(120), default="")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    ran: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SurveyIn(BaseModel):
    how_found: str = ""
    goal: str = ""


class QueryIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    source: str = "playground"


# ── helpers ───────────────────────────────────────────────────────────────────

def _who(request: Request) -> dict[str, str]:
    """Best-effort identity: the signed-in user when present, the demo workspace otherwise."""
    from .accounts import current_user

    user = None
    try:
        user = current_user(request)
    except Exception:
        user = None
    if user:
        return {"ws": user.workspace_id or "", "user": user.id, "email": user.email, "name": user.name}
    return {"ws": "", "user": "", "email": "", "name": ""}


def best_action(text: str) -> tuple[str, int]:
    """The action Tony would pick for this sentence, plus a 0-100 confidence."""
    try:
        from .toolsearch import search_actions

        hits = search_actions(catalog.catalog, text, limit=3)
    except Exception:
        return "", 0
    if not hits:
        return "", 0
    top = hits[0]
    name = top.get("action") or ""
    score = float(top.get("score") or 0)
    # Below this the "match" is noise (a shared word, not an intent). Saying
    # nothing is far better than sending the wrong action.
    if score < 5.0:
        return "", 0
    # The scorer is unbounded; squash it into something a human reads as confidence.
    conf = int(min(97, max(1, round(100 * (1 - 2.718 ** (-max(score, 0.01) / 3.2))))))
    return name, conf


def record_query(request: Request, text: str, source: str, matched: str = "",
                 confidence: int = 0, connected: bool = False, ran: bool = False) -> str:
    who = _who(request)
    row = Query(workspace_id=who["ws"], user_id=who["user"], email=who["email"],
                text=text.strip()[:1000], source=source, matched_action=matched or "",
                confidence=int(confidence or 0), connected=connected, ran=ran)
    with session() as s:
        s.add(row)
        s.flush()
        return row.id


# ── API ───────────────────────────────────────────────────────────────────────

@router.post("/v1/queries")
def create_query(body: QueryIn, request: Request) -> dict[str, Any]:
    matched, conf = best_action(body.text)
    qid = record_query(request, body.text, body.source, matched, conf)
    spec_slug = matched.split(".")[0] if "." in matched else ""
    spec = catalog.catalog.get(spec_slug) if spec_slug else None
    app = {"slug": spec.slug, "name": spec.name, "logo": spec.logo,
           "auth": spec.auth.type, "category": spec.category} if spec else None
    return {"id": qid, "query": body.text, "action": matched or None,
            "confidence": conf, "app": app,
            "needs_connection": bool(spec and spec.auth.type not in ("none", ""))}


@router.get("/v1/queries")
def list_queries(request: Request, limit: int = 100) -> dict[str, Any]:
    """What people are asking for - read this to decide what Tony should do next."""
    who = _who(request)
    with session() as s:
        q = select(Query)
        if who["ws"] and request.query_params.get("all") != "1":
            q = q.where(Query.workspace_id == who["ws"])
        rows = s.scalars(q.order_by(Query.created_at.desc()).limit(min(limit, 500))).all()
        out = [{"id": r.id, "text": r.text, "source": r.source, "action": r.matched_action,
                "confidence": r.confidence, "connected": r.connected, "ran": r.ran,
                "email": r.email, "at": r.created_at.isoformat()[:16]} for r in rows]
    return {"queries": out, "total": len(out)}


@router.post("/v1/survey")
def save_survey(body: SurveyIn, request: Request) -> dict[str, Any]:
    who = _who(request)
    with session() as s:
        s.add(Query(workspace_id=who["ws"], user_id=who["user"], email=who["email"],
                    text=f"[survey] found via: {body.how_found or 'skipped'} | goal: {body.goal or '-'}",
                    source="survey"))
    return {"ok": True}


# ── pages ─────────────────────────────────────────────────────────────────────

_ICON = """<svg viewBox="0 0 32 32" width="{s}" height="{s}" aria-hidden="true">
<defs><linearGradient id="tg" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#F2D06B"/><stop offset=".55" stop-color="#D4AF37"/>
<stop offset="1" stop-color="#A67C12"/></linearGradient></defs>
<rect width="32" height="32" rx="9" fill="#0A0A0C"/>
<path d="M8 22V10l8 8 8-8v12" fill="none" stroke="url(#tg)" stroke-width="2.4"
stroke-linecap="round" stroke-linejoin="round"/></svg>"""

_SHELL = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
*{{box-sizing:border-box}}
body{{margin:0;background:#0A0A0C;color:#F6F3EA;font:15px/1.55 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:28px 20px 64px}}
.brand{{display:flex;align-items:center;gap:12px;margin-bottom:26px}}
.brand b{{font-size:17px;letter-spacing:-.01em}}
.brand span{{color:#8b8778;font-size:13px}}
h1{{font-size:26px;line-height:1.2;letter-spacing:-.02em;margin:0 0 6px}}
p.sub{{color:#a29c8c;margin:0 0 22px}}
.card{{background:#121216;border:1px solid #232329;border-radius:16px;padding:18px}}
textarea,input{{width:100%;background:#0f0f13;border:1px solid #2a2a31;border-radius:11px;color:#F6F3EA;
padding:12px 13px;font:inherit;outline:none}}
textarea{{min-height:96px;resize:vertical}}
textarea:focus,input:focus{{border-color:#D4AF37}}
.btn{{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(180deg,#E8C765,#D4AF37);
color:#141008;border:0;border-radius:11px;padding:11px 18px;font-weight:650;cursor:pointer;font:inherit}}
.btn[disabled]{{opacity:.55;cursor:default}}
.btn.ghost{{background:#17171c;color:#F6F3EA;border:1px solid #2a2a31}}
.row{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}}
.chip{{display:inline-flex;align-items:center;gap:7px;background:#17171c;border:1px solid #2a2a31;
border-radius:999px;padding:6px 12px;font-size:13px;color:#cdc7b8;cursor:pointer}}
.chip.on{{border-color:#D4AF37;color:#F2D06B}}
.muted{{color:#8b8778;font-size:13px}}
.out{{margin-top:16px;display:grid;gap:10px}}
.step{{display:flex;gap:11px;align-items:flex-start;background:#101015;border:1px solid #232329;
border-radius:12px;padding:12px}}
.step b{{color:#F2D06B;font-weight:600}}
pre{{background:#0d0d11;border:1px solid #232329;border-radius:11px;padding:12px;overflow:auto;
max-height:340px;font-size:12.5px;color:#cfc9ba}}
a{{color:#F2D06B}}
</style></head><body><div class="wrap">{body}</div>{script}</body></html>"""


def _brand(sub: str) -> str:
    return f'<div class="brand">{_ICON.format(s=34)}<div><b>Tony</b><br><span>{sub}</span></div></div>'


def query_page_html(name: str = "") -> str:
    hello = f"Welcome, {name.split()[0]}." if name else "Welcome."
    body = f"""
{_brand('the integration layer for your AI agents')}
<h1>{hello} What do you want Tony to do?</h1>
<p class="sub">Say it in plain words. Tony finds the app, connects your account, and runs it.</p>
<div class="card">
  <textarea id="q" placeholder="e.g. Send an email to my customer about their invoice"></textarea>
  <div class="row"><button class="btn" id="go">Find what I need</button>
  <span class="muted" id="hint">One line is enough. You can change it later.</span></div>
</div>
<div class="out" id="out"></div>"""
    script = """<script>
const $=s=>document.querySelector(s);
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'content-type':'application/json'},
body:JSON.stringify(b||{})});return r.json()}
$('#go').onclick=async()=>{
  const text=$('#q').value.trim(); if(!text){$('#q').focus();return}
  $('#go').disabled=true; $('#hint').textContent='Tony is thinking…';
  const d=await post('/v1/queries',{text,source:'signup'});
  let html='<div class="step"><b>1</b><div>Got it. Searching 7,900 apps for the right action…</div></div>';
  if(d.action){html+='<div class="step"><b>2</b><div>Best match: <b>'+d.action+'</b> '
    +(d.app?'in '+d.app.name+' ':'')+'<span class="muted">('+d.confidence+'% confident)</span></div></div>'}
  else{html+='<div class="step"><b>2</b><div>Nothing certain yet. Tony will keep this on record and keep looking.</div></div>'}
  if(d.needs_connection){html+='<div class="step"><b>3</b><div>Next: connect '+(d.app?d.app.name:'the app')
    +' so it can run. <a href="/app">Open the console</a></div></div>'}
  $('#out').innerHTML=html; $('#hint').textContent='Saved. Opening your console…';
  setTimeout(()=>location.href='/app',1400);
};
$('#q').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey))$('#go').click()});
</script>"""
    return _SHELL.format(title="What do you want Tony to do?", body=body, script=script)


def playground_html() -> str:
    body = f"""
{_brand('Agent Playground · test a connection end to end')}
<h1>Agent Playground</h1>
<p class="sub">Ask in plain words. Tony picks the tool, checks the connection, and shows the real output.</p>
<div class="card">
  <textarea id="q" placeholder="e.g. Summarise my 3 latest emails"></textarea>
  <div class="row">
    <button class="btn" id="find">Find tool</button>
    <button class="btn ghost" id="run" disabled>Run it</button>
    <label class="chip" id="dry"><input type="checkbox" id="dryin" checked style="width:auto;margin-right:6px">dry run</label>
  </div>
</div>
<div class="out" id="out"></div>"""
    script = """<script>
const $=s=>document.querySelector(s);
let picked=null, entity='default';
const steps=(h)=>{$('#out').innerHTML=h};
async function j(u,o){const r=await fetch(u,o);const t=await r.text();
try{return JSON.parse(t)}catch(e){return {raw:t}}}
$('#find').onclick=async()=>{
  const text=$('#q').value.trim(); if(!text)return;
  $('#find').disabled=true; steps('<div class="step"><b>1</b><div>Searching…</div></div>');
  const res=await j('/v1/actions?search='+encodeURIComponent(text.split(' ').slice(0,4).join(' '))+'&limit=5');
  const q=await j('/v1/queries',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({text,source:'playground'})});
  let h='<div class="step"><b>1</b><div>You asked: <b>'+text.replace(/</g,'&lt;')+'</b></div></div>';
  if(q.action) h+='<div class="step"><b>2</b><div>Tony picked <b>'+q.action+'</b> '
     +'<span class="muted">('+q.confidence+'%)</span>'+(q.app?' in '+q.app.name:'')+'</div></div>';
  h+='<div class="step"><b>3</b><div>Connection: '+(q.needs_connection
     ?'needs linking <a href="/v1/connections/'+(q.app?q.app.slug:'')+'/start">connect now</a>':'not required')+'</div></div>';
  steps(h);
  picked=q.action; $('#run').disabled=!picked; $('#find').disabled=false;
  window._cands=(res.actions||[]).map(a=>a.tool_name||(a.app+'.'+a.slug));
};
$('#run').onclick=async()=>{
  if(!picked)return;
  $('#run').disabled=true;
  const dry=$('#dryin').checked;
  const r=await j('/v1/execute',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({action:picked,args:{},approved:!dry,dry_run:dry,source:'playground'})});
  const pretty=JSON.stringify(r,null,2).slice(0,4000);
  $('#out').insertAdjacentHTML('beforeend','<div class="step"><b>4</b><div>Result'
    +'</div></div><pre>'+pretty.replace(/</g,'&lt;')+'</pre>');
  $('#run').disabled=false;
};
</script>"""
    return _SHELL.format(title="Tony Agent Playground", body=body, script=script)


def survey_html() -> str:
    opts = ["My team is already using Tony", "Recommended by someone I know",
            "Search engine (Google, etc.)", "LLM search (ChatGPT, Claude, etc.)",
            "Social media (LinkedIn, Hackernews, etc.)", "Don't remember",
            "Other (no details required)"]
    chips = "".join(f'<div class="chip" data-v="{o}">{o}</div>' for o in opts)
    body = f"""
{_brand('one quick question')}
<h1>How did you hear about Tony?</h1>
<p class="sub">This helps us know what's working. Pick one, or skip.</p>
<div class="card"><div class="row" id="opts">{chips}</div>
<div class="row"><button class="btn" id="next" disabled>Continue</button>
<button class="btn ghost" id="skip">Skip for now</button></div></div>"""
    script = """<script>
const $=s=>document.querySelector(s); let val='';
document.querySelectorAll('#opts .chip').forEach(c=>c.onclick=()=>{
  document.querySelectorAll('#opts .chip').forEach(x=>x.classList.remove('on'));
  c.classList.add('on'); val=c.dataset.v; $('#next').disabled=false;});
async function send(){await fetch('/v1/survey',{method:'POST',headers:{'content-type':'application/json'},
  body:JSON.stringify({how_found:val})});location.href='/query'}
$('#next').onclick=send; $('#skip').onclick=()=>{val='skipped';send()};
</script>"""
    return _SHELL.format(title="How did you hear about Tony?", body=body, script=script)


@router.get("/query", response_class=HTMLResponse)
def query_page(request: Request) -> Any:
    who = _who(request)
    return HTMLResponse(query_page_html(who.get("name", "")))


@router.get("/playground", response_class=HTMLResponse)
def playground_page() -> Any:
    return HTMLResponse(playground_html())


@router.get("/welcome", response_class=HTMLResponse)
def survey_page() -> Any:
    return HTMLResponse(survey_html())
