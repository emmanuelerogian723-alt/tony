"""One-click connect + the connected-accounts dashboard.

The rule this file enforces: an ordinary user never sees a client id, a secret
or a token. They press Connect, the provider asks for consent, they come back
connected, and the agent keeps working with their own account.
"""
from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .catalog import catalog
from .oauth import OAuthError, start_oauth
from .config import settings

router = APIRouter()

SAFE_NEXT = ("/playground", "/app", "/console", "/connections", "/")


def _safe_next(value: str) -> str:
    v = (value or "").strip()
    if v.startswith("/") and not v.startswith("//") and "\\" not in v:
        return v
    return "/playground"


def _workspace(request: Request) -> str:
    from .api import workspace_from_request

    ws, _ = workspace_from_request(request)
    return ws


@router.get("/connect/{app_slug}", include_in_schema=False)
async def one_click_connect(app_slug: str, request: Request, entity_id: str = "default",
                            next: str = "/playground", new_account: bool = False):
    """The link an agent hands a human: press it, sign in, come back connected."""
    from . import provider_registry as managed

    spec = catalog.resolve(app_slug) or catalog.get(app_slug)
    if spec is None:
        # not an app: this is one of Tony's shareable consent links
        from .connectlinks import consent
        return consent(app_slug)
    back = _safe_next(next)

    if spec.auth.type == "none":
        return RedirectResponse(f"{back}?connection=public&app={quote(spec.slug)}")

    if spec.auth.type != "oauth2":
        return RedirectResponse(f"/connections?app={quote(spec.slug)}&mode=key")

    ws = _workspace(request)
    try:
        _sid, url = await start_oauth(ws, entity_id, spec, back, new_account=new_account)
        return RedirectResponse(url)
    except OAuthError as exc:
        return HTMLResponse(setup_page(spec, str(exc)), status_code=200)


@router.get("/connections", response_class=HTMLResponse, include_in_schema=False)
def connections_page(request: Request):
    return HTMLResponse(dashboard_html())


def setup_page(spec: Any, reason: str) -> str:
    p = None
    try:
        from . import provider_registry as managed
        p = managed.provider_for(spec.slug)
    except Exception:  # noqa: BLE001
        pass
    env = " ".join(getattr(p, "env", ()) or ())
    name = html.escape(spec.name)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect {name} · Tony</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#faf9f6;
color:#14140f;font:15px/1.6 Inter,system-ui,-apple-system,sans-serif}}
.card{{max-width:520px;margin:24px;background:#fff;border:1px solid #e7e5df;border-radius:18px;
padding:32px;box-shadow:0 10px 40px rgba(13,13,12,.07)}}
h1{{font-size:19px;margin:0 0 6px;letter-spacing:-.01em}}
p{{color:#6b6a63;margin:0 0 14px}}
code{{background:#f4f3ef;border:1px solid #e7e5df;border-radius:7px;padding:3px 8px;
font:12.5px ui-monospace,Menlo,monospace}}
.btn{{display:inline-block;margin-top:8px;background:#14140f;color:#fff;text-decoration:none;
border-radius:10px;padding:10px 18px;font-weight:600;font-size:14px}}
.mut{{font-size:13px;color:#8a887f}}
</style></head><body><div class="card">
<h1>{name} needs a one-time setup</h1>
<p>{html.escape(reason)}</p>
<p>Tony signs every user in through one OAuth app owned by this deployment. That app is
registered once, by the workspace owner, in Tony's provider console. After that, every
user just clicks Connect.</p>
<p class="mut">Credentials are read from {('<code>'+html.escape(env)+'</code>') if env else 'the provider console'} and are never exposed to users or to the model.</p>
<a class="btn" href="/providers">Open provider setup</a>
<a class="btn" style="background:#ece9e2;color:#14140f;margin-left:8px" href="/connections">Back to accounts</a>
</div></body></html>"""


def dashboard_html() -> str:
    hot = "#E2542B"
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connected accounts · Tony</title>
<link rel="icon" href="/static/brand/tony-32.png">
<style>
:root{--ink:#14140f;--ink2:#3f3e38;--mut:#6b6a63;--line:#e7e5df;--line2:#d8d6ce;
--bg:#faf9f6;--card:#fff;--hot:#E2542B;--ok:#1a7f4b;--warn:#b45309;--err:#c0362c;--r:14px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:14.5px/1.55 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
a{color:inherit}
.top{position:sticky;top:0;z-index:20;background:rgba(250,249,246,.86);backdrop-filter:blur(14px);
border-bottom:1px solid var(--line)}
.top .in{max-width:1080px;margin:0 auto;padding:12px 20px;display:flex;align-items:center;gap:12px}
.logo{display:flex;align-items:center;gap:9px;font-weight:650;letter-spacing:-.01em;text-decoration:none}
.logo img{width:26px;height:26px;border-radius:8px}
.nav{margin-left:auto;display:flex;gap:8px;align-items:center}
.nav a{font-size:13px;color:var(--mut);text-decoration:none;padding:7px 11px;border-radius:9px}
.nav a:hover{background:#f0eee8;color:var(--ink)}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:24px;letter-spacing:-.02em;margin:0 0 4px}
.sub{color:var(--mut);margin:0 0 22px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:10px 14px;min-width:120px}
.stat b{display:block;font-size:19px;letter-spacing:-.02em}
.stat span{font-size:12px;color:var(--mut)}
.bar{display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.search{flex:1;min-width:220px;background:#fff;border:1px solid var(--line2);border-radius:11px;
padding:10px 14px;font:inherit;font-size:13.5px;outline:0}
.search:focus{border-color:var(--ink)}
.tab{background:#fff;border:1px solid var(--line2);border-radius:10px;padding:8px 13px;font-size:13px;cursor:pointer}
.tab.on{background:var(--ink);color:#fff;border-color:var(--ink)}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);margin:26px 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.app{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:15px;
display:flex;gap:12px;align-items:flex-start;transition:border-color .15s,box-shadow .15s}
.app:hover{border-color:var(--line2);box-shadow:0 6px 22px rgba(13,13,12,.05)}
.app.off{opacity:.92}
.ico{width:42px;height:42px;border-radius:11px;border:1px solid var(--line);background:#fff;
display:grid;place-items:center;flex:none;overflow:hidden}
.ico img{width:24px;height:24px;object-fit:contain}
.body{flex:1;min-width:0}
.nm{font-weight:600;font-size:14px;display:flex;align-items:center;gap:7px}
.who{font-size:12.5px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:2px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;border-radius:20px;
padding:3px 9px;border:1px solid var(--line);background:#faf9f6;color:var(--mut)}
.pill i{width:7px;height:7px;border-radius:50%;background:#c4c2b8;display:block}
.pill.on{color:var(--ok);border-color:#cfe8d6;background:#f3fbf6}
.pill.on i{background:var(--ok)}
.pill.warn{color:var(--warn);border-color:#f2e0c8;background:#fdf8ef}.pill.warn i{background:var(--warn)}
.act{display:flex;gap:7px;margin-top:10px;flex-wrap:wrap}
.btn{border:1px solid var(--line2);background:#fff;border-radius:9px;padding:6px 12px;
font-size:12.5px;font-weight:600;cursor:pointer;color:var(--ink)}
.btn:hover{background:#f6f5f1}
.btn.hot{background:var(--hot);border-color:var(--hot);color:#fff}
.btn.hot:hover{background:#cc4722}
.btn.ghost{color:var(--mut)}
.btn:disabled{opacity:.55;cursor:default}
.scopes{display:flex;gap:5px;flex-wrap:wrap;margin-top:9px}
.scope{font:11px ui-monospace,Menlo,monospace;color:var(--mut);background:#f4f3ef;
border:1px solid var(--line);border-radius:6px;padding:2px 6px}
.empty{grid-column:1/-1;text-align:center;color:var(--mut);padding:34px;border:1px dashed var(--line2);
border-radius:var(--r);background:#fff}
.mask{position:fixed;inset:0;background:rgba(13,13,12,.45);display:none;place-items:center;z-index:50;padding:16px}
.mask.on{display:grid}
.modal{background:#fff;border-radius:18px;max-width:400px;width:100%;padding:28px;text-align:center;
box-shadow:0 30px 90px rgba(13,13,12,.32);position:relative}
.modal .ico{width:58px;height:58px;border-radius:15px;margin:0 auto 14px}
.modal .ico img{width:32px;height:32px}
.modal h3{font-size:17px;margin:0 0 8px}
.modal p{color:var(--mut);font-size:13px;margin:0 0 16px}
.modal .btn{width:100%;padding:11px;font-size:14px;margin-top:8px}
.modal .x{position:absolute;right:14px;top:10px;border:0;background:none;font-size:22px;color:var(--mut);cursor:pointer}
.modal input{width:100%;border:1px solid var(--line2);border-radius:10px;padding:10px 12px;
font:inherit;font-size:13.5px;margin-bottom:8px;outline:0}
.err{color:var(--err);font-size:12.5px;text-align:left;margin-bottom:8px}
.or{display:flex;align-items:center;gap:10px;color:#b0aea5;font:12px/1 sans-serif;margin:12px 0}
.or:before,.or:after{content:"";flex:1;height:1px;background:var(--line)}
.ev{background:#fff;border:1px solid var(--line);border-radius:11px;padding:10px 13px;
display:flex;gap:10px;align-items:center;font-size:13px;margin-bottom:7px}
.ev .k{font:11px ui-monospace,Menlo,monospace;border-radius:6px;padding:2px 7px;
background:#f4f3ef;border:1px solid var(--line);color:var(--mut)}
.ev .t{margin-left:auto;color:var(--mut);font-size:12px;white-space:nowrap}
.note{font-size:12.5px;color:var(--mut);margin-top:14px}
</style></head><body>
<div class="top"><div class="in">
  <a class="logo" href="/playground"><img src="/static/brand/tony-mark.svg" alt="">Tony</a>
  <nav class="nav">
    <a href="/playground">Playground</a><a href="/console">Console</a>
    <a href="/connections" style="color:var(--ink);background:#f0eee8">Accounts</a>
    <a href="/docs">API</a>
  </nav>
</div></div>
<div class="wrap">
  <h1>Connected accounts</h1>
  <p class="sub">Sign in once. Tony uses your own authorized accounts, never a pasted key.</p>
  <div class="stats">
    <div class="stat"><b id="sConn">0</b><span>connected</span></div>
    <div class="stat"><b id="sApps">0</b><span>integrations ready</span></div>
    <div class="stat"><b id="sNeed">0</b><span>need attention</span></div>
  </div>
  <div class="bar">
    <input class="search" id="q" placeholder="Search integrations…" autocomplete="off">
    <button class="tab on" data-f="all">All</button>
    <button class="tab" data-f="connected">Connected</button>
    <button class="tab" data-f="available">Not connected</button>
  </div>
  <h2>Integrations</h2>
  <div class="grid" id="grid"></div>
  <h2>Other apps</h2>
  <div class="grid" id="other"></div>
  <h2>Recent authentication activity</h2>
  <div id="events"><div class="empty">No activity yet.</div></div>
  <p class="note">Tokens are encrypted at rest and never sent to the browser or to the model.
  Removing an account revokes it at the provider when the provider supports revocation.</p>
</div>
<div class="mask" id="mask"><div class="modal">
  <button class="x" id="mx">×</button>
  <div class="ico" id="mico"></div>
  <h3 id="mh">Connect</h3>
  <p id="mp"></p>
  <div class="err" id="merr"></div>
  <button class="btn hot" id="moauth">Continue to sign in</button>
  <div class="or" id="mor">or</div>
  <div id="mkey" style="display:none">
    <input id="mtok" placeholder="API key or token">
    <input id="mbase" placeholder="API base URL (only if this app needs one)" style="display:none">
    <button class="btn" id="msave">Save key</button>
  </div>
  <button class="btn ghost" id="mfallback" style="background:#fff">Use an API key instead</button>
</div></div>
<script>
const ENTITY=new URLSearchParams(location.search).get('entity_id')||'playground';
const $=s=>document.querySelector(s);
let providers=[],conns=[],filter='all',current=null,filterApp=new URLSearchParams(location.search).get('app');
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pname=s=>String(s||'').replace(/[_\\-]/g,' ').replace(/\\b\\w/g,c=>c.toUpperCase());
const icon=slug=>`<img alt="" src="/v1/icon/${encodeURIComponent(slug)}" onerror="this.onerror=null;this.src='/v1/icon-tile/${encodeURIComponent(slug)}'">`;
async function api(u,o){try{const r=await fetch(u,o);const t=await r.text();let j;try{j=JSON.parse(t)}catch(e){j={raw:t}}return j||{}}catch(e){return {error:String(e)}}}

function connFor(slug){return conns.filter(c=>c.app===slug&&c.status==='active')}
function card(p){
  const mine=connFor(p.app);
  const any=conns.filter(c=>c.app===p.app);
  const on=mine.length>0;
  const who=mine[0]?(mine[0].identity||mine[0].label||'connected'):'';
  const extra=mine.length>1?` +${mine.length-1}`:'';
  return `<div class="app ${on?'':'off'}">
    <div class="ico">${icon(p.app)}</div>
    <div class="body">
      <div class="nm">${esc(p.name)}
        ${on?`<span class="pill on"><i></i>Connected${extra}</span>`
            :(p.ready?`<span class="pill"><i></i>Not connected</span>`
                     :`<span class="pill warn"><i></i>Setup needed</span>`)}
      </div>
      <div class="who">${on?esc(who):(p.ready?'One click, no keys':'One-time provider setup by the owner')}</div>
      <div class="act">
        ${on?`<button class="btn ghost" data-reconnect="${esc(p.app)}" ${p.ready?'':'disabled'}>Reconnect</button>
              <button class="btn ghost" data-add="${esc(p.app)}" ${p.ready?'':'disabled'}>Add account</button>
              <button class="btn ghost" data-off="${esc(mine[0].id)}">Disconnect</button>`
            :`<button class="btn hot" data-connect="${esc(p.app)}" ${p.ready?'':'disabled'}>Connect</button>
              ${p.ready?'':`<a class="btn ghost" href="/providers">Set up</a>`}`}
      </div>
      ${p.scopes&&p.scopes.length?`<div class="scopes">${p.scopes.slice(0,4).map(s=>`<span class="scope">${esc(s.split('/').pop())}</span>`).join('')}${p.scopes.length>4?`<span class="scope">+${p.scopes.length-4}</span>`:''}</div>`:''}
    </div></div>`;
}
function render(){
  const q=($('#q').value||'').toLowerCase();
  let list=providers.filter(p=>!q||p.name.toLowerCase().includes(q));
  if(filter==='connected')list=list.filter(p=>connFor(p.app).length);
  if(filter==='available')list=list.filter(p=>!connFor(p.app).length);
  $('#grid').innerHTML=list.length?list.map(card).join(''):'<div class="empty">Nothing matches that search.</div>';
  const managed=new Set(providers.map(p=>p.app));
  const others={};
  conns.filter(c=>c.status==='active'&&!managed.has(c.app)).forEach(c=>{(others[c.app]=others[c.app]||[]).push(c)});
  const oks=Object.keys(others);
  $('#other').innerHTML=oks.length?oks.map(slug=>`<div class="app"><div class="ico">${icon(slug)}</div>
    <div class="body"><div class="nm">${esc(pname(slug))}<span class="pill on"><i></i>Connected</span></div>
    <div class="who">${esc(others[slug][0].identity||others[slug][0].label||'connected')}</div>
    <div class="act"><button class="btn ghost" data-off="${esc(others[slug][0].id)}">Disconnect</button></div></div></div>`).join('')
    :'<div class="empty">Apps outside the managed set show up here once connected.</div>';
  $('#sConn').textContent=conns.filter(c=>c.status==='active').length;
  $('#sApps').textContent=providers.filter(p=>p.ready).length;
  $('#sNeed').textContent=conns.filter(c=>c.status==='expired').length;
  bind();
}
function bind(){
  document.querySelectorAll('[data-connect]').forEach(b=>b.onclick=()=>start(b.dataset.connect,false));
  document.querySelectorAll('[data-reconnect]').forEach(b=>b.onclick=()=>start(b.dataset.reconnect,false));
  document.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>start(b.dataset.add,true));
  document.querySelectorAll('[data-off]').forEach(b=>b.onclick=async()=>{
    if(!confirm('Disconnect this account? Tony will lose access and the token is revoked.'))return;
    b.disabled=true;await api('/v1/connections/id/'+b.dataset.off,{method:'DELETE'});await load();});
}
async function start(slug,isNew){
  const p=providers.find(x=>x.app===slug)||{app:slug,name:pname(slug),ready:false};
  current={slug,isNew};
  $('#mico').innerHTML=icon(slug);$('#mh').textContent='Connect '+p.name;
  $('#mp').textContent='A pop-up will open on '+p.name+"'s own sign-in page. Approve access and you will come straight back.";
  $('#merr').textContent='';$('#mkey').style.display='none';$('#mbase').style.display='none';
  $('#moauth').style.display='';$('#mor').style.display='';$('#mfallback').style.display='';
  $('#mask').classList.add('on');
}
$('#moauth').onclick=async()=>{
  if(!current)return;
  const slug=current.slug,isNew=current.isNew;
  const w=window.open('about:blank','tony_auth','width=540,height=720');
  const r=await api(`/v1/connections/${slug}/start?entity_id=${ENTITY}&redirect_after=/connections&new_account=${isNew}`,{method:'POST'});
  if(r.authorization_url){if(w)w.location=r.authorization_url;else location.href=r.authorization_url;}
  else{if(w)w.close();
    $('#merr').textContent=r.detail||r.error||'Could not start sign-in.';
    $('#mkey').style.display='';$('#mbase').style.display='';$('#mf'+'allback').style.display='none';}
};
$('#mfallback').onclick=()=>{$('#mkey').style.display='';$('#mbase').style.display='';$('#merr').textContent=''};
$('#msave').onclick=async()=>{
  if(!current)return;const v=$('#mtok').value.trim();if(!v){$('#merr').textContent='Paste the key first.';return}
  const vals={token:v,api_key:v,access_token:v};
  const b=$('#mbase').value.trim();if(b)vals.base_url=b;
  const r=await api('/v1/connections/'+current.slug+'/key',{method:'POST',
    headers:{'content-type':'application/json'},body:JSON.stringify({entity_id:ENTITY,values:vals,label:'api key'})});
  if(r.connection){close();await load()}else $('#merr').textContent=r.detail||r.error||'Could not save that key.';
};
function close(){$('#mask').classList.remove('on');current=null}
$('#mx').onclick=close;$('#mask').onclick=e=>{if(e.target.id==='mask')close()};
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));t.classList.add('on');
  filter=t.dataset.f;render();});
$('#q').oninput=render;

async function load(){
  const [p,c]=await Promise.all([api('/v1/providers'),api('/v1/connections?entity_id='+ENTITY)]);
  providers=p.providers||[];conns=c.connections||[];
  render();
  const ev=await api('/v1/connections/events?limit=8');
  const rows=ev.events||[];
  $('#events').innerHTML=rows.length?rows.map(e=>`<div class="ev"><span class="k">${esc(e.kind)}</span>
    <b>${esc(pname(e.app))}</b><span style="color:var(--mut)">${esc(e.identity||e.detail||'')}</span>
    <span class="t">${esc((e.created_at||'').replace('T',' ').slice(0,16))}</span></div>`).join(''):'<div class="empty">No activity yet.</div>';
}
load();
setInterval(async()=>{ if(current){const c=await api('/v1/connections?entity_id='+ENTITY);
  const row=(c.connections||[]).find(x=>x.app===current.slug&&x.status==='active');
  if(row){close();await load()}}},2500);
if(filterApp){const p=providers.find(x=>x.app===filterApp);if(p)setTimeout(()=>start(filterApp,false),400)}
</script></body></html>"""
