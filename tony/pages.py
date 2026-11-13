"""The four surfaces behind the playground sidebar: Catalog, Integrations,
Connections and Logs.

They are real pages, not anchors. Before this, "Catalog" pointed at /#catalog (the
marketing page), "Logs" at /app (a redirect), and "Integrations" at the owner-only
provider console, so every click felt like being thrown out of the product.
All four share one shell, one nav order, and the same public API the playground
uses, so what you see is what the API actually returns.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .playground_page import _CSS, _I, logo

router = APIRouter(include_in_schema=False)

ENTITY = "playground"

# One order, used by every page and by the playground itself.
NAV = [
    ("play", "Playground", "/playground"),
    ("cat", "Catalog", "/catalog"),
    ("plug", "Integrations", "/integrations"),
    ("key", "Connections", "/connections"),
    ("log", "Logs", "/logs"),
    ("book", "Docs", "/sdk"),
]

_PAGE_CSS = r"""
.wrap{max-width:1080px;margin:0 auto;padding:22px 22px 60px}
.head{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap;margin-bottom:6px}
.head h1{font-size:21px;letter-spacing:-.02em;font-weight:650}
.head p{color:var(--mut);font-size:13px}
.tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:16px 0 14px}
.srch{flex:1;min-width:220px;display:flex;align-items:center;gap:8px;border:1px solid var(--line2);border-radius:11px;padding:9px 12px;background:#fff}
.srch input{border:0;outline:0;flex:1;font:inherit;font-size:13.5px;background:transparent}
.srch svg{width:15px;height:15px;stroke:#9c9a92;fill:none;stroke-width:1.8}
select.f{border:1px solid var(--line2);border-radius:10px;padding:9px 10px;font:inherit;font-size:13px;background:#fff;color:var(--ink2)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(232px,1fr));gap:10px}
.card{border:1px solid var(--line);border-radius:13px;background:#fff;padding:13px;display:flex;flex-direction:column;gap:9px;transition:border-color .12s,transform .12s}
.card:hover{border-color:var(--line2);transform:translateY(-1px)}
.card .row{display:flex;align-items:center;gap:10px;min-width:0}
.card .ico{width:34px;height:34px;border-radius:9px;flex:none;background:#f6f5f2;object-fit:contain;display:grid;place-items:center}
.card b{font-size:13.5px;font-weight:600;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card small{color:var(--mut);font-size:11.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card .meta{display:flex;gap:6px;flex-wrap:wrap}
.tag{font-size:10.5px;letter-spacing:.02em;text-transform:uppercase;color:#6b6a63;background:#f4f3ef;border-radius:6px;padding:2px 6px}
.tag.ok{background:#e9f7ee;color:#15803d}.tag.warn{background:#fdf3e3;color:#b45309}.tag.err{background:#fdecec;color:#b91c1c}
.card .act{margin-top:auto;display:flex;gap:6px}
.card .act a,.card .act button{flex:1;text-align:center;text-decoration:none;border:1px solid var(--line2);border-radius:9px;padding:6px 8px;font-size:12px;background:#fff;color:var(--ink2)}
.card .act a.pri{background:var(--ink);color:#fff;border-color:var(--ink)}
.sect{margin:22px 0 10px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}
.empty{border:1px dashed var(--line2);border-radius:13px;padding:26px;text-align:center;color:var(--mut);font-size:13px}
.sk{height:96px;border-radius:13px;background:linear-gradient(90deg,#f6f5f2,#eeedea,#f6f5f2);background-size:200% 100%;animation:sh 1.2s infinite}
@keyframes sh{to{background-position:-200% 0}}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{text-align:left;font-weight:600;color:var(--mut);font-size:11px;letter-spacing:.05em;text-transform:uppercase;padding:8px 10px;border-bottom:1px solid var(--line)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
.tbl tr:hover td{background:#fbfaf8}
.tbl .mono{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#4a4842}
.tabs{display:flex;gap:6px;margin:14px 0}
.tabs button{border:1px solid var(--line2);background:#fff;border-radius:99px;padding:5px 12px;font-size:12.5px;color:var(--ink2)}
.tabs button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.copy{font:11.5px ui-monospace,Menlo,monospace;background:#f4f3ef;border:1px solid var(--line);border-radius:6px;padding:2px 6px;color:#4a4842}
@media(max-width:760px){.app{grid-template-columns:1fr}.side{display:none}.wrap{padding:16px 14px 60px}}
"""


def _nav(active: str) -> str:
    return "".join(
        f'<a href="{href}" class="{"on" if key == active else ""}" data-n="{key}">{_I[key]}{label}</a>'
        for key, label, href in NAV)


def shell(active: str, title: str, subtitle: str, body: str, script: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title} · Tony</title><meta name="theme-color" content="#ffffff">
<link rel="icon" href="/favicon.ico"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>{_CSS}{_PAGE_CSS}</style></head><body>
<div class="app">
 <aside class="side">
  <div class="env">{logo(30, 's')}<div><b>Tony</b><small>dev environment</small></div></div>
  <nav class="nav">{_nav(active)}</nav><div class="sp"></div>
  <div class="who"><i>T</i><span>Public demo workspace</span></div>
 </aside>
 <section class="main">
  <div class="top"><b>{title}</b><span class="hide-m">· {subtitle}</span><span class="grow"></span>
   <span class="pill" id="stats"><i></i>Tony</span>
   <a class="btn-s" href="/playground" style="text-decoration:none">Open playground</a></div>
  <div class="scroll"><div class="wrap">{body}</div></div>
 </section>
</div>
<script>{script}</script></body></html>"""


# ── shared JS ────────────────────────────────────────────────────────────
_COMMON = r"""
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const ENTITY='__ENTITY__';
function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function api(u,o){try{const r=await fetch(u,o||{});const t=await r.text();let j;try{j=JSON.parse(t)}catch(e){j={raw:t}}return j}catch(e){return{error:String(e)}}}
function ico(slug,size){size=size||34;return '<img class="ico" loading="lazy" width="'+size+'" height="'+size+'" alt="" src="/v1/icon/'+encodeURIComponent(slug)+'" onerror="this.onerror=null;this.src=\'/v1/icon-tile/'+encodeURIComponent(slug)+'\'">'}
(async()=>{const h=await api('/health');if(h&&h.apps)$('#stats').innerHTML='<i></i>'+(h.apps||0).toLocaleString()+' apps · '+(h.actions||0).toLocaleString()+' actions'})();
""".replace("__ENTITY__", ENTITY)


# ── Catalog ──────────────────────────────────────────────────────────────
def catalog_page() -> str:
    body = f"""
<div class="head"><div><h1>Catalog</h1><p>Every app Tony can act on, with its real action count and auth type.</p></div></div>
<div class="tools">
  <label class="srch"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m16.5 16.5 4 4"/></svg>
   <input id="q" placeholder="Search the catalogue — github, stripe, notion…" autocomplete="off"></label>
  <select class="f" id="cat"><option value="">All categories</option></select>
  <select class="f" id="tier"><option value="">Any access</option><option value="read">Read</option><option value="write">Write</option><option value="destructive">Destructive</option></select>
</div>
<div id="count" class="sect">Loading…</div>
<div class="grid" id="grid">{'<div class="sk"></div>' * 8}</div>"""
    script = _COMMON + r"""
let cats=0;
async function load(){
  const q=$('#q').value.trim(), c=$('#cat').value, t=$('#tier').value;
  const r=await api('/v1/apps?limit=60&search='+encodeURIComponent(q)+'&category='+encodeURIComponent(c)+'&tier='+encodeURIComponent(t));
  if(!cats&&r.categories){cats=1;$('#cat').innerHTML='<option value="">All categories</option>'+r.categories.map(x=>'<option>'+esc(x)+'</option>').join('')}
  const apps=r.apps||[];
  $('#count').textContent=(r.total||0).toLocaleString()+' apps'+(q?' matching “'+q+'”':'')+(c?' in '+c:'');
  $('#grid').innerHTML=apps.length?apps.map(a=>
    '<div class="card"><div class="row">'+ico(a.slug)+
    '<div style="min-width:0"><b>'+esc(a.name)+'</b><small>'+esc(a.category||'')+'</small></div></div>'+
    '<div class="meta"><span class="tag">'+(a.actions_count||0)+' actions</span>'+
    '<span class="tag">'+esc((a.auth||{}).type||'none')+'</span>'+
    (a.verified?'<span class="tag ok">verified</span>':'')+'</div>'+
    '<div class="act"><a href="/integrations?app='+encodeURIComponent(a.slug)+'">Connect</a>'+
    '<a class="pri" href="/playground?goal='+encodeURIComponent('use '+a.name+' to ')+'">Use it</a></div></div>').join('')
    :'<div class="empty">No app matches that search. Try a shorter word.</div>';
}
let tmr; $('#q').oninput=()=>{clearTimeout(tmr);tmr=setTimeout(load,220)};
$('#cat').onchange=load; $('#tier').onchange=load; load();
"""
    return shell("cat", "Catalog", "every app, one port", body, script)


# ── Integrations ─────────────────────────────────────────────────────────
def integrations_page() -> str:
    body = """
<div class="head"><div><h1>Integrations</h1><p>The connectors people actually use. Connecting takes one click and one approval.</p></div></div>
<div class="tools">
  <label class="srch"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m16.5 16.5 4 4"/></svg>
   <input id="q" placeholder="Search connectors…" autocomplete="off"></label>
  <select class="f" id="cat"><option value="">All categories</option></select>
</div>
<div id="out"><div class="grid">""" + ('<div class="sk"></div>' * 9) + """</div></div>"""
    script = _COMMON + r"""
let connected={};
async function conns(){
  const r=await api('/v1/connections');
  (r.connections||[]).forEach(c=>{connected[c.app]=c});
  return r;
}
function card(a){
  const c=connected[a.slug];
  const state=c?('<span class="tag ok">connected</span>'):'';
  const act=c
    ? '<a href="/connections">Manage</a><a class="pri" href="/playground?app='+encodeURIComponent(a.slug)+'">Use it</a>'
    : '<a href="/playground?app='+encodeURIComponent(a.slug)+'">Try it</a><a class="pri" href="/connect/'+encodeURIComponent(a.slug)+'?entity_id='+ENTITY+'&redirect_after=%2Fintegrations">Connect</a>';
  return '<div class="card"><div class="row">'+ico(a.slug)+
    '<div style="min-width:0"><b>'+esc(a.name)+'</b><small>'+esc((a.auth||{}).type||'none')+' · '+(a.actions_count||0)+' actions</small></div></div>'+
    '<div class="meta">'+state+'<span class="tag">'+esc(a.category||'')+'</span></div>'+
    '<div class="act">'+act+'</div></div>';
}
async function load(){
  await conns();
  const q=$('#q').value.trim(), cat=$('#cat').value;
  const r=await api('/v1/apps?limit=48&search='+encodeURIComponent(q)+'&category='+encodeURIComponent(cat));
  if(!$('#cat').dataset.done&&r.categories){$('#cat').dataset.done=1;$('#cat').innerHTML='<option value="">All categories</option>'+r.categories.map(x=>'<option>'+esc(x)+'</option>').join('')}
  const apps=(r.apps||[]).slice();
  const pin=['github','gmail','slack','notion','stripe','google_calendar','google_sheets','googledrive','linear','vercel','shopify','discord','whatsapp','telegram','paystack','hubspot','airtable','figma'];
  apps.sort((a,b)=> (connected[b.slug]?1:0)-(connected[a.slug]?1:0) || (pin.indexOf(a.slug)+1||99)-(pin.indexOf(b.slug)+1||99) || a.name.localeCompare(b.name));
  $('#out').innerHTML='<div class="grid">'+apps.map(card).join('')+'</div>';
}
let tmr;$('#q').oninput=()=>{clearTimeout(tmr);tmr=setTimeout(load,220)};
$('#cat').onchange=load;load();
"""
    return shell("plug", "Integrations", "connect once, act forever", body, script)


# ── Connections ──────────────────────────────────────────────────────────
def connections_page() -> str:
    body = """
<div class="head"><div><h1>Connections</h1><p>Real accounts Tony holds for this workspace. Tokens are encrypted and never returned.</p></div></div>
<div class="tools"><span class="pill" id="n"><i></i>0 connected</span>
 <span class="grow" style="flex:1"></span>
 <a class="btn-s" href="/integrations" style="text-decoration:none">Connect another app</a></div>
<div id="out"><div class="grid"><div class="sk"></div><div class="sk"></div><div class="sk"></div></div></div>"""
    script = _COMMON + r"""
const HEALTH={healthy:'ok',active:'ok',expired:'warn','rate-limited':'warn',revoked:'err',error:'err',gone:'err'};
function card(c){
  const st=HEALTH[c.status]||'';
  const when=c.updated_at?new Date(c.updated_at).toLocaleDateString():'';
  return '<div class="card"><div class="row">'+ico(c.app)+
    '<div style="min-width:0"><b>'+esc(c.display_name||c.app)+'</b><small>'+esc(c.identity||c.label||c.auth_type||'')+'</small></div></div>'+
    '<div class="meta"><span class="tag '+st+'">'+esc(c.status||'active')+'</span>'+
    (c.auth_type?'<span class="tag">'+esc(c.auth_type)+'</span>':'')+
    (c.is_default?'<span class="tag">default</span>':'')+
    '<span class="tag">'+esc(c.entity_id||'default')+'</span></div>'+
    (c.scopes&&c.scopes.length?'<small style="color:#77756d;font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(c.scopes.slice(0,4).join(' · '))+'</small>':'')+
    '<div class="act"><button data-rm="'+esc(c.id)+'">Disconnect</button>'+
    '<a class="pri" href="/playground?app='+encodeURIComponent(c.app)+'">Use it</a></div>'+
    '<small style="color:#a3a198;font-size:11px">'+(when?'updated '+when:'')+'</small></div>';
}
async function load(){
  const r=await api('/v1/connections');
  const rows=(r.connections||[]).slice();
  const rank=c=>({ok:0,warn:1,err:2}[HEALTH[c.status]]??0);
  rows.sort((a,b)=>rank(a)-rank(b)||String(a.app).localeCompare(String(b.app)));
  $('#n').innerHTML='<i></i>'+rows.length+' connected';
  $('#out').innerHTML=rows.length?'<div class="grid">'+rows.map(card).join('')+'</div>'
    :'<div class="empty">Nothing connected yet. <a href="/integrations">Pick an app</a> and approve it — it will appear here in seconds.</div>';
  $$('#out [data-rm]').forEach(b=>b.onclick=async()=>{
    b.disabled=true;b.textContent='Removing…';
    await api('/v1/connections/id/'+encodeURIComponent(b.dataset.rm),{method:'DELETE'});
    load();
  });
}
load();
"""
    return shell("key", "Connections", "accounts Tony holds", body, script)


# ── Logs ─────────────────────────────────────────────────────────────────
def logs_page() -> str:
    body = """
<div class="head"><div><h1>Logs</h1><p>Every action, inbound event and durable flow, newest first.</p></div></div>
<div class="tabs"><button class="on" data-f="all">All</button><button data-f="run">Runs</button>
 <button data-f="event">Events</button><button data-f="flow">Flows</button></div>
<div id="out"><div class="sk"></div></div>"""
    script = _COMMON + r"""
let DATA=[], FILTER='all';
function ago(iso){if(!iso)return '';const d=(Date.now()-new Date(iso).getTime())/1000;
  if(d<60)return Math.round(d)+'s ago';if(d<3600)return Math.round(d/60)+'m ago';
  if(d<86400)return Math.round(d/3600)+'h ago';return new Date(iso).toLocaleDateString()}
async function load(){
  const [runs,evs,flows]=await Promise.all([api('/v1/runs?limit=60'),api('/v1/events?limit=60'),api('/v1/flows?limit=60')]);
  DATA=[];
  (runs.runs||[]).forEach(r=>DATA.push({kind:'run',at:r.created_at,app:r.app,label:r.app+'.'+r.action,
    status:r.status,ms:r.latency_ms,detail:'HTTP '+(r.status_code||'')+(r.error?' · '+r.error:'')}));
  (evs.events||[]).forEach(e=>DATA.push({kind:'event',at:e.at,app:e.source,label:e.type,
    status:e.status==='routed'?'routed':e.status||'',detail:(e.routed||0)+' subscription(s) fired'}));
  (flows.flows||[]).forEach(f=>DATA.push({kind:'flow',at:f.created_at,app:'flow',label:f.name,
    status:f.status,ms:null,detail:f.last_error||('step '+(f.current_step||0))}));
  DATA.sort((a,b)=>String(b.at||'').localeCompare(String(a.at||'')));
  render();
}
function render(){
  const rows=DATA.filter(d=>FILTER==='all'||d.kind===FILTER);
  if(!rows.length){$('#out').innerHTML='<div class="empty">Nothing yet. Run something in the <a href="/playground">playground</a>.</div>';return}
  $('#out').innerHTML='<table class="tbl"><thead><tr><th>When</th><th>Type</th><th>What</th><th>Status</th><th>Detail</th></tr></thead><tbody>'+
   rows.slice(0,120).map(d=>{
     const tone=/succe|ok|routed|active/i.test(d.status)?'ok':/dead|error|fail|denied|revoked/i.test(d.status)?'err':/wait|pending|approval/i.test(d.status)?'warn':'';
     return '<tr><td class="mono">'+esc(ago(d.at))+'</td><td><span class="tag">'+esc(d.kind)+'</span></td>'+
       '<td>'+ico(d.app,20).replace('class="ico"','class="ico" style="width:20px;height:20px;display:inline-grid;vertical-align:-5px;margin-right:7px"')+
       esc(d.label)+'</td><td><span class="tag '+tone+'">'+esc(d.status||'')+'</span></td>'+
       '<td class="mono" style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(d.detail||'')+(d.ms?' · '+d.ms+'ms':'')+'</td></tr>';
   }).join('')+'</tbody></table>';
}
$$('.tabs button').forEach(b=>b.onclick=()=>{FILTER=b.dataset.f;$$('.tabs button').forEach(x=>x.classList.toggle('on',x===b));render()});
load();
"""
    return shell("log", "Logs", "runs, events and flows", body, script)


@router.get("/catalog", response_class=HTMLResponse, include_in_schema=False)
def catalog_surface() -> Any:
    return HTMLResponse(catalog_page())


@router.get("/integrations", response_class=HTMLResponse, include_in_schema=False)
def integrations_surface() -> Any:
    return HTMLResponse(integrations_page())


@router.get("/logs", response_class=HTMLResponse, include_in_schema=False)
def logs_surface() -> Any:
    return HTMLResponse(logs_page())


@router.get("/connections", response_class=HTMLResponse, include_in_schema=False)
def connections_surface() -> Any:
    return HTMLResponse(connections_page())
