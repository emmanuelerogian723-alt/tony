"""Tony console: signed-in workspace app (apps, connections, runs, keys, profile)."""
from __future__ import annotations

from typing import Any

from .config import settings


def _initials(name: str) -> str:
    parts = [p for p in str(name or "").replace("@", " ").replace(".", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


CONSOLE_CSS = """
*{box-sizing:border-box}
:root{
  --paper:#F4EFE7; --card:#FFFDF9; --card-2:#FBF7F0; --ink:#12110F; --ink-2:#3B3934;
  --mut:#6E6C63; --line:rgba(18,17,15,.13); --line-2:rgba(18,17,15,.22);
  --accent:#E2542B; --accent-soft:#FBE7DF; --ok:#0E7A47; --ok-soft:#E4F3EA;
  --warn:#9A5B0B; --bad:#A32217;
  --r:12px; --r-lg:18px; --r-xl:26px;
  --shadow:0 1px 0 rgba(18,17,15,.06), 3px 3px 0 rgba(18,17,15,.055);
  --shadow-lift:0 1px 0 rgba(18,17,15,.07), 6px 6px 0 rgba(18,17,15,.07);
  --sans:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",system-ui,sans-serif;
  --serif:"Fraunces",Georgia,"Times New Roman",serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
}
html,body{margin:0;height:100%}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
body:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.5;
  background-image:radial-gradient(rgba(18,17,15,.055) 1px,transparent 1px);background-size:3px 3px}
a{color:inherit;text-decoration:none}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
input,select,textarea{font:inherit;color:inherit}
::selection{background:var(--ink);color:var(--paper)}
h1,h2,h3{font-family:var(--serif);font-weight:600;letter-spacing:-.02em;margin:0}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}

/* ── shell ─────────────────────────────────────────────── */
#shell{position:relative;z-index:1;display:grid;min-height:100vh;grid-template-columns:1fr}
@media(min-width:920px){#shell{grid-template-columns:250px 1fr}}
.rail{display:none}
@media(min-width:920px){
  .rail{display:flex;flex-direction:column;gap:6px;border-right:1px solid var(--line);
    padding:22px 14px 18px;position:sticky;top:0;height:100vh;background:rgba(255,253,249,.6)}
}
.brand{display:flex;align-items:center;gap:10px;padding:4px 8px 16px}
.brand svg{width:30px;height:30px;flex:none}
.brand b{font-family:var(--serif);font-size:19px;letter-spacing:-.02em}
.brand i{font-style:normal;font-family:var(--mono);font-size:10px;color:var(--mut);
  border:1px solid var(--line);border-radius:5px;padding:1px 5px}
.nav{display:flex;align-items:center;gap:10px;padding:10px 11px;border-radius:10px;font-size:14px;
  font-weight:520;color:var(--ink-2);width:100%;text-align:left;transition:background .16s,color .16s}
.nav svg{width:17px;height:17px;flex:none;opacity:.75}
.nav:hover{background:rgba(18,17,15,.05)}
.nav.on{background:var(--ink);color:var(--paper)}
.nav.on svg{opacity:1}
.nav .n{margin-left:auto;font-family:var(--mono);font-size:11px;opacity:.6}
.rail-foot{margin-top:auto;border-top:1px solid var(--line);padding-top:12px}
.who{display:flex;align-items:center;gap:10px;width:100%;padding:8px;border-radius:10px;text-align:left}
.who:hover{background:rgba(18,17,15,.05)}
.who .nm{font-size:13px;font-weight:560;line-height:1.2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.who .em{font-size:11px;color:var(--mut);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:12px;padding:12px 16px;
  background:rgba(244,239,231,.88);backdrop-filter:saturate(180%) blur(14px);border-bottom:1px solid var(--line)}
@media(min-width:920px){.top{display:none}}
.top .mark{display:flex;align-items:center;gap:9px}
.top .mark svg{width:26px;height:26px}
.top .mark b{font-family:var(--serif);font-size:17px}
.top .sp{flex:1}

main{padding:18px 16px 96px;min-width:0}
@media(min-width:920px){main{padding:30px 34px 60px;max-width:1180px}}

.tabbar{position:fixed;left:0;right:0;bottom:0;z-index:30;display:grid;grid-template-columns:repeat(5,1fr);
  gap:2px;padding:8px 6px calc(8px + env(safe-area-inset-bottom));background:rgba(255,253,249,.96);
  backdrop-filter:blur(14px);border-top:1px solid var(--line)}
@media(min-width:920px){.tabbar{display:none}}
.tab{display:flex;flex-direction:column;align-items:center;gap:3px;padding:5px 2px;border-radius:10px;
  font-size:10.5px;font-weight:560;color:var(--mut);letter-spacing:.01em}
.tab svg{width:20px;height:20px}
.tab.on{color:var(--ink);background:rgba(18,17,15,.06)}

/* ── primitives ────────────────────────────────────────── */
.pg{display:none}
.pg.on{display:block;animation:up .28s cubic-bezier(.2,.8,.2,1) both}
@keyframes up{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
.hd{display:flex;align-items:flex-end;justify-content:space-between;gap:14px;margin-bottom:18px;flex-wrap:wrap}
.hd h1{font-size:27px;line-height:1.1}
@media(min-width:920px){.hd h1{font-size:34px}}
.hd p{margin:6px 0 0;color:var(--mut);font-size:13.5px;max-width:52ch}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:40px;padding:0 16px;
  border-radius:9px;background:var(--ink);color:var(--paper);font-weight:560;font-size:13.5px;
  border:1px solid var(--ink);transition:transform .14s,box-shadow .14s;box-shadow:2px 2px 0 rgba(18,17,15,.18)}
.btn:hover{transform:translate(-1px,-1px);box-shadow:3px 3px 0 rgba(18,17,15,.2)}
.btn:active{transform:translate(1px,1px);box-shadow:none}
.btn[disabled]{opacity:.5;pointer-events:none}
.btn.acc{background:var(--accent);border-color:var(--accent);box-shadow:2px 2px 0 rgba(226,84,43,.28)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line-2);box-shadow:none}
.btn.ghost:hover{background:rgba(18,17,15,.05);transform:none}
.btn.sm{height:32px;padding:0 11px;font-size:12.5px;border-radius:8px;box-shadow:none}
.btn.wide{width:100%}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--shadow)}
.pad{padding:16px}
@media(min-width:920px){.pad{padding:20px}}
.muted{color:var(--mut)}
.tiny{font-size:12px}
.mono{font-family:var(--mono)}
.row{display:flex;align-items:center;gap:10px}
.wrap{flex-wrap:wrap}
.sp{flex:1}
.grid{display:grid;gap:12px}
.g4{grid-template-columns:repeat(2,1fr)}
@media(min-width:760px){.g4{grid-template-columns:repeat(4,1fr)}}
.stat{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:13px 14px;box-shadow:var(--shadow)}
.stat b{display:block;font-family:var(--serif);font-size:23px;line-height:1.1;letter-spacing:-.02em}
.stat span{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut)}
.field{display:flex;flex-direction:column;gap:5px;margin-bottom:11px}
.field label{font-size:12px;font-weight:600;letter-spacing:.02em}
.field .hint{font-weight:400;color:var(--mut);margin-left:6px;text-transform:none;letter-spacing:0}
.inp{height:40px;width:100%;padding:0 11px;border-radius:9px;border:1px solid var(--line-2);
  background:var(--card);outline:none;transition:border-color .16s,box-shadow .16s}
.inp:focus{border-color:var(--ink);box-shadow:0 0 0 3px rgba(18,17,15,.08)}
textarea.inp{height:auto;min-height:80px;padding:10px 11px;font-family:var(--mono);font-size:12.5px}
.badge{display:inline-flex;align-items:center;gap:5px;height:21px;padding:0 7px;border-radius:5px;
  font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.06em;
  border:1px solid var(--line);color:var(--ink-2);background:var(--card-2);white-space:nowrap}
.badge.ok{background:var(--ok-soft);border-color:rgba(14,122,71,.28);color:var(--ok)}
.badge.acc{background:var(--accent-soft);border-color:rgba(226,84,43,.3);color:#A83C18}
.badge.bad{background:#FCE9E7;border-color:rgba(163,34,23,.28);color:var(--bad)}
.empty{padding:34px 18px;text-align:center;color:var(--mut);font-size:13.5px;border:1px dashed var(--line-2);
  border-radius:var(--r);background:rgba(255,253,249,.5)}
.divider{height:1px;background:var(--line);margin:16px 0}
.ico{position:relative;display:inline-flex;flex:none}
.ico img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;border-radius:7px;background:var(--card)}
.mono-b{display:inline-flex;align-items:center;justify-content:center;flex:none;border-radius:7px;
  font-family:var(--mono);font-weight:600;color:#fff;letter-spacing:.02em}

/* options (filter chips) */
.opts{display:flex;gap:6px;overflow-x:auto;padding-bottom:2px;scrollbar-width:none}
.opts::-webkit-scrollbar{display:none}
.opt{flex:none;height:30px;padding:0 11px;border-radius:999px;border:1px solid var(--line-2);
  background:var(--card);font-size:12.5px;font-weight:520;color:var(--ink-2);white-space:nowrap}
.opt.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}

/* app list */
.apps{display:grid;gap:10px;grid-template-columns:1fr}
@media(min-width:640px){.apps{grid-template-columns:repeat(2,1fr)}}
@media(min-width:1080px){.apps{grid-template-columns:repeat(3,1fr)}}
.app{display:flex;flex-direction:column;gap:9px;padding:13px;border-radius:var(--r);background:var(--card);
  border:1px solid var(--line);box-shadow:var(--shadow);text-align:left;transition:transform .16s,box-shadow .16s}
.app:hover{transform:translate(-1px,-1px);box-shadow:var(--shadow-lift)}
.app .nm{font-size:13.5px;font-weight:600;letter-spacing:-.01em;line-height:1.2;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.app .cat{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.06em}
.app .ds{font-size:12.5px;color:var(--ink-2);margin:0;display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden;line-height:1.45}
.app .ft{display:flex;gap:5px;flex-wrap:wrap;margin-top:auto}

/* sheet */
.sheet{position:fixed;inset:0;z-index:60;display:none;background:rgba(18,17,15,.34);backdrop-filter:blur(3px)}
.sheet.on{display:block}
.sheet-b{position:absolute;right:0;top:0;bottom:0;width:min(560px,100%);background:var(--paper);
  border-left:1px solid var(--line);display:flex;flex-direction:column;animation:slide .3s cubic-bezier(.2,.8,.2,1) both}
@media(max-width:640px){
  .sheet-b{left:0;right:0;top:auto;bottom:0;height:92vh;width:auto;border-left:none;
    border-top:1px solid var(--line);border-radius:20px 20px 0 0;animation:up .3s cubic-bezier(.2,.8,.2,1) both}
}
@keyframes slide{from{transform:translateX(24px);opacity:.6}to{transform:none;opacity:1}}
.sheet-h{display:flex;align-items:flex-start;gap:12px;padding:16px 18px;border-bottom:1px solid var(--line)}
.sheet-bd{overflow:auto;padding:16px 18px 28px;flex:1}
.x{width:32px;height:32px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;
  border:1px solid var(--line);background:var(--card)}
.tabs{display:flex;gap:4px;padding:0 18px;border-bottom:1px solid var(--line);background:var(--paper)}
.tabs button{padding:11px 2px;margin-right:16px;font-size:13px;font-weight:560;color:var(--mut);
  border-bottom:2px solid transparent}
.tabs button.on{color:var(--ink);border-bottom-color:var(--accent)}
.acts{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}
.act{display:flex;align-items:center;gap:9px;padding:10px 11px;border-radius:9px;border:1px solid var(--line);
  background:var(--card);text-align:left}
.act.on{border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.act .an{font-size:13px;font-weight:560}
.act .as{font-family:var(--mono);font-size:11px;color:var(--mut)}
pre.out{margin:0;padding:13px;border-radius:10px;background:#151412;color:#EDE8DE;font-family:var(--mono);
  font-size:11.5px;line-height:1.55;overflow:auto;max-height:340px;white-space:pre-wrap;word-break:break-word}

/* auth */
#auth{position:relative;z-index:1;min-height:100vh;display:grid;grid-template-columns:1fr}
@media(min-width:980px){#auth{grid-template-columns:1.05fr .95fr}}
.auth-l{display:none;padding:44px;border-right:1px solid var(--line);background:
  radial-gradient(120% 80% at 100% 0%,rgba(226,84,43,.10),transparent 60%),var(--paper)}
@media(min-width:980px){.auth-l{display:flex;flex-direction:column}}
.auth-l h1{font-size:44px;line-height:1.04;margin-top:auto}
.auth-l p{color:var(--ink-2);max-width:36ch;font-size:15px}
.auth-l .lst{margin:18px 0 0;padding:0;list-style:none;display:grid;gap:9px;color:var(--ink-2);font-size:13.5px}
.auth-l .lst li{display:flex;gap:9px;align-items:flex-start}
.auth-l .lst svg{width:15px;height:15px;margin-top:3px;flex:none;color:var(--accent)}
.auth-r{display:flex;align-items:center;justify-content:center;padding:26px 18px 40px}
.auth-c{width:100%;max-width:392px}
.auth-c .card{padding:22px}
.auth-c h2{font-size:24px;margin-bottom:4px}
.seg{display:grid;grid-template-columns:1fr 1fr;gap:4px;padding:4px;background:rgba(18,17,15,.06);
  border-radius:10px;margin:16px 0}
.seg button{height:32px;border-radius:7px;font-size:13px;font-weight:560;color:var(--mut)}
.seg button.on{background:var(--card);color:var(--ink);box-shadow:0 1px 2px rgba(18,17,15,.12)}
#g-btn{display:flex;justify-content:center;min-height:0}
#g-wrap{border:1px solid var(--line-2);border-radius:9px;overflow:hidden;min-height:44px;
  display:flex;align-items:center;justify-content:center;background:var(--card)}
.or{display:flex;align-items:center;gap:10px;color:var(--mut);font-size:11.5px;margin:14px 0;
  text-transform:uppercase;letter-spacing:.08em}
.or:before,.or:after{content:"";height:1px;background:var(--line);flex:1}
.msg{margin:12px 0 0;padding:9px 11px;border-radius:8px;font-size:12.5px;display:none}
.msg.on{display:block}
.msg.err{background:#FCE9E7;color:var(--bad);border:1px solid rgba(163,34,23,.25)}
.msg.info{background:var(--ok-soft);color:var(--ok);border:1px solid rgba(14,122,71,.22)}

/* toast */
#toast{position:fixed;left:50%;bottom:78px;transform:translate(-50%,14px);z-index:90;background:var(--ink);
  color:var(--paper);padding:10px 15px;border-radius:9px;font-size:13px;opacity:0;pointer-events:none;
  transition:opacity .2s,transform .2s;max-width:88vw;text-align:center}
@media(min-width:920px){#toast{bottom:26px}}
#toast.on{opacity:1;transform:translate(-50%,0)}
.pk{display:flex;align-items:center;gap:10px;padding:11px 12px;border:1px solid var(--line);
  border-radius:9px;background:var(--card);margin-bottom:8px}
.pk code{font-family:var(--mono);font-size:12px}
"""

CONSOLE_JS = r"""
const CFG = __CFG__;
const ME = __ME__;
const S = { user: ME, page: 'overview', apps: [], total: 0, offset: 0, q: '', tier: '', cat: '',
            conns: [], keys: [], cur: null, act: null, loaded: {} };

function el(id){return document.getElementById(id)}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function toast(m){const t=el('toast');t.textContent=m;t.classList.add('on');
  clearTimeout(t._x);t._x=setTimeout(()=>t.classList.remove('on'),2600)}
function n(x){return Number(x||0).toLocaleString()}
function initials(name){const w=String(name||'').replace(/[^A-Za-z0-9 ]/g,' ').trim().split(/\s+/).filter(Boolean);
  if(!w.length) return '?'; return (w.length===1?w[0].slice(0,2):w[0][0]+w[1][0]).toUpperCase()}
function hue(s){let x=0;for(const ch of String(s||''))x=(x*31+ch.charCodeAt(0))%360;return x}

async function api(path, opts){
  opts = opts || {};
  const init = {credentials:'same-origin', method:opts.method||'GET', headers:{'Content-Type':'application/json'}};
  if(opts.body !== undefined) init.body = JSON.stringify(opts.body);
  const r = await fetch(path, init);
  let d = {}; const txt = await r.text();
  try{ d = txt ? JSON.parse(txt) : {} }catch(e){ d = {raw:txt} }
  if(r.status === 401){ showAuth(); throw new Error('Sign in to continue') }
  if(!r.ok){ const e = new Error(d.detail || d.error || ('HTTP '+r.status)); e.status=r.status; throw e }
  return d;
}

/* ── auth ───────────────────────────────────────────────── */
function showAuth(){ el('auth').style.display='grid'; el('shell').style.display='none'; mountGoogle() }
function showApp(){ el('auth').style.display='none'; el('shell').style.display='grid'; boot() }
function authMode(mode){
  el('mode-login').classList.toggle('on', mode==='login');
  el('mode-signup').classList.toggle('on', mode==='signup');
  el('form-login').style.display = mode==='login' ? 'block':'none';
  el('form-signup').style.display = mode==='signup' ? 'block':'none';
  authMsg('');
}
function authMsg(text, kind){
  const m = el('auth-msg'); m.className = 'msg' + (text ? ' on ' + (kind||'err') : ''); m.textContent = text||'';
}
let _gisTries = 0;
function mountGoogle(){
  if(!CFG.google_client_id){ el('g-wrap').innerHTML='<span class="tiny muted" style="padding:10px">Google sign-in is not configured on this server</span>'; return }
  if(!window.google || !google.accounts){
    if(_gisTries++ < 40) return setTimeout(mountGoogle, 350);
    el('g-wrap').innerHTML='<span class="tiny muted" style="padding:10px">Could not load Google. Use email below.</span>'; return;
  }
  google.accounts.id.initialize({ client_id: CFG.google_client_id, callback: onGoogle, ux_mode:'popup', auto_select:false });
  el('g-btn').innerHTML = '';
  google.accounts.id.renderButton(el('g-btn'), {type:'standard', theme:'outline', size:'large',
    text:'continue_with', shape:'rectangular', logo_alignment:'left', width:320});
}
async function onGoogle(resp){
  if(!resp || !resp.credential){ authMsg('Google did not return a credential. Try again.'); return }
  try{
    const d = await api('/v1/account/google', {method:'POST', body:{credential:resp.credential}});
    S.user = d.user; location.hash = '#overview'; showApp(); toast('Signed in as ' + d.user.email);
  }catch(e){ authMsg(e.message) }
}
async function doLogin(ev){
  ev.preventDefault(); authMsg('');
  const email = el('li-email').value.trim(), password = el('li-pass').value;
  const b = ev.target.querySelector('button[type=submit]'); b.disabled = true; b.textContent = 'Signing in…';
  try{
    const d = await api('/v1/account/login', {method:'POST', body:{email, password}});
    S.user = d.user; location.hash='#overview'; showApp(); toast('Welcome back, ' + (d.user.name||d.user.email));
  }catch(e){ authMsg(e.message) } finally { b.disabled=false; b.textContent='Sign in' }
}
async function doSignup(ev){
  ev.preventDefault(); authMsg('');
  const name = el('su-name').value.trim(), email = el('su-email').value.trim(), password = el('su-pass').value;
  if(password.length < 8){ authMsg('Use at least 8 characters for the password.'); return }
  const b = ev.target.querySelector('button[type=submit]'); b.disabled = true; b.textContent='Creating…';
  try{
    const d = await api('/v1/account/signup', {method:'POST', body:{name, email, password}});
    authMode('login'); el('li-email').value = (d.email || email); el('li-pass').value = '';
    authMsg('Account created. Sign in to open your workspace.', 'info');
    el('li-pass').focus();
  }catch(e){ authMsg(e.message) } finally { b.disabled=false; b.textContent='Create account' }
}
async function signOut(){
  try{ await api('/v1/account/logout', {method:'POST'}) }catch(e){}
  S.user=null; location.hash=''; showAuth(); toast('Signed out');
}

/* ── routing ────────────────────────────────────────────── */
const NAV = [['overview','Overview','M3 10.5 12 3l9 7.5M5 9.5V21h14V9.5'],
             ['apps','Apps','M4 5h7v7H4zM13 5h7v7h-7zM4 14h7v6H4zM13 14h7v6h-7z'],
             ['connections','Connections','M9 15l6-6M7.5 4.5 6 6a4 4 0 105.7 5.7M16.5 19.5 18 18a4 4 0 10-5.7-5.7'],
             ['runs','Activity','M3 12h4l2.5-7 4 14L16 12h5'],
             ['keys','API keys','M14 7a4 4 0 10-3.5 4L4 17.5V21h3.5l6.5-6.5A4 4 0 0014 7z'],
             ['profile','Profile','M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0']];
const MOBILE = ['apps','connections','runs','keys','profile'];

function iconNav(d){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="'+d+'"/></svg>'}
function buildNav(){
  el('rail-nav').innerHTML = NAV.map(([id,label,d])=>
    '<button class="nav" data-p="'+id+'">'+iconNav(d)+'<span>'+label+'</span></button>').join('');
  el('rail-nav').querySelectorAll('.nav').forEach(b=>b.onclick=()=>go(b.dataset.p));
  const labels = {apps:'Apps', connections:'Links', runs:'Activity', keys:'Keys', profile:'You'};
  const icons = Object.fromEntries(NAV.map(([id,l,d])=>[id,d]));
  el('tabbar').innerHTML = MOBILE.map(id=>
    '<button class="tab" data-p="'+id+'">'+iconNav(icons[id])+'<span>'+labels[id]+'</span></button>').join('');
  el('tabbar').querySelectorAll('.tab').forEach(b=>b.onclick=()=>go(b.dataset.p));
}
function go(page){
  S.page = page; location.hash = '#' + page;
  document.querySelectorAll('.pg').forEach(p=>p.classList.toggle('on', p.id==='p-'+page));
  document.querySelectorAll('.nav,.tab').forEach(b=>b.classList.toggle('on', b.dataset.p===page));
  window.scrollTo({top:0, behavior:'instant'});
  if(page==='apps'){ if(!S.loaded.apps){ S.loaded.apps=1; loadApps(true) } else { renderApps() } }
  if(page==='connections'){ loadConns() }
  if(page==='runs'){ loadRuns() }
  if(page==='keys'){ loadKeys() }
  if(page==='profile'){ renderProfile() }
  if(page==='overview'){ loadOverview() }
}

/* ── boot ───────────────────────────────────────────────── */
async function boot(){
  renderWho(); buildNav();
  const h = (location.hash||'#overview').slice(1);
  go(['overview','apps','connections','runs','keys','profile'].includes(h) ? h : 'overview');
}
function renderWho(){
  const u = S.user || {};
  const pic = u.picture ? '<img src="'+esc(u.picture)+'" alt="" style="width:32px;height:32px;border-radius:50%;object-fit:cover;border:1px solid var(--line)">'
    : '<span class="mono-b" style="width:32px;height:32px;font-size:12px;background:hsl('+hue(u.email)+',45%,38%)">'+esc(initials(u.name||u.email))+'</span>';
  el('who').innerHTML = pic + '<span style="min-width:0"><span class="nm">'+esc(u.name||'You')+'</span><span class="em">'+esc(u.email||'')+'</span></span>';
  el('top-av').innerHTML = pic;
}

/* ── overview ───────────────────────────────────────────── */
async function loadOverview(){
  try{
    const [st, runs, conns] = await Promise.all([api('/v1/stats'), api('/v1/runs?limit=6'), api('/v1/connections')]);
    S.conns = conns.connections||[];
    el('st-apps').textContent = n(st.apps);
    el('st-acts').textContent = n(st.actions);
    el('st-conn').textContent = n(conns.total);
    el('st-runs').textContent = n(runs.runs.length ? runs.runs.length : 0);
    el('st-runs-l').textContent = 'recent calls';
    const rr = runs.runs||[];
    el('ov-runs').innerHTML = rr.length ? rr.map(runLine).join('')
      : '<div class="empty">No calls yet. Open an app and run a read action.</div>';
    el('ov-conns').innerHTML = S.conns.length ? S.conns.slice(0,4).map(c=>
      '<div class="row" style="padding:9px 0;border-bottom:1px solid var(--line)"><span class="mono" style="font-size:12.5px">'+esc(c.app)+'</span>'+
      '<span class="sp"></span><span class="badge ok">live</span></div>').join('')
      : '<div class="empty" style="padding:20px">Nothing connected yet.</div>';
  }catch(e){ toast(e.message) }
}
function runLine(r){
  const ok = r.status==='success';
  const when = (r.created_at||'').slice(11,19);
  return '<div class="row" style="padding:9px 0;border-bottom:1px solid var(--line);gap:8px">'+
    '<span class="mono muted tiny" style="width:58px">'+esc(when)+'</span>'+
    '<span class="mono" style="font-size:12.5px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(r.app)+'.'+esc(r.action)+'</span>'+
    '<span class="sp"></span>'+
    '<span class="badge '+(ok?'ok':'bad')+'">'+(ok?'ok':esc(r.status))+'</span>'+
    '<span class="mono muted tiny">'+(r.latency_ms||0)+'ms</span></div>';
}

/* ── apps ───────────────────────────────────────────────── */
const PAGE = 48;
async function loadApps(reset){
  if(reset){ S.offset=0; S.apps=[]; el('app-grid').innerHTML='<div class="empty">Loading catalogue…</div>' }
  const q = new URLSearchParams({limit:PAGE, offset:S.offset, search:S.q, tier:S.tier, category:S.cat});
  try{
    const d = await api('/v1/apps?'+q.toString());
    S.apps = S.apps.concat(d.apps||[]); S.total = d.total||0; S.offset = S.apps.length;
    el('app-count').textContent = n(S.total)+' apps';
    renderCats(d.categories||[]);
    renderApps();
  }catch(e){ el('app-grid').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
}
function renderCats(cats){
  if(!cats.length || el('tier-opts').childElementCount) return;
  el('tier-opts').innerHTML = [['','All'],['actions','Built-in'],['proxy','Proxy'],['directory','Directory']]
    .map(([v,l])=>'<button class="opt'+(S.tier===v?' on':'')+'" data-t="'+v+'">'+l+'</button>').join('');
  el('tier-opts').querySelectorAll('.opt').forEach(b=>b.onclick=()=>{S.tier=b.dataset.t;loadApps(true)});
}
function iconHTML(a, size){
  const s = size||30;
  const mono = '<span class="mono-b" style="width:'+s+'px;height:'+s+'px;font-size:'+Math.round(s*0.37)+'px;background:hsl('+hue(a.slug)+',45%,38%)">'+esc(initials(a.name))+'</span>';
  if(!a.logo) return '<span class="ico" style="width:'+s+'px;height:'+s+'px">'+mono+'</span>';
  return '<span class="ico" style="width:'+s+'px;height:'+s+'px">'+mono+
    '<img src="'+esc(a.logo)+'" alt="" loading="lazy" decoding="async" onload="this.previousElementSibling.style.display=\'none\'" onerror="this.remove()"></span>';
}
function renderApps(){
  const grid = el('app-grid');
  if(!S.apps.length){ grid.innerHTML='<div class="empty">No app matches that search.</div>'; el('more').style.display='none'; return }
  grid.innerHTML = S.apps.map(a=>{
    const c = S.conns.find(x=>x.app===a.slug && x.status==='active');
    return '<button class="app" data-s="'+esc(a.slug)+'">'+
      '<span class="row"><span class="ico-wrap">'+iconHTML(a,30)+'</span><span style="min-width:0">'+
      '<span class="nm" style="display:block">'+esc(a.name)+'</span><span class="cat">'+esc(a.category||'')+'</span></span></span>'+
      '<span class="ds">'+esc(a.description||'')+'</span>'+
      '<span class="ft">'+(c?'<span class="badge ok">connected</span>':'')+
      '<span class="badge">'+n(a.actions_count)+' act</span>'+
      '<span class="badge '+(a.tier==='directory'?'':'acc')+'">'+esc(a.tier==='actions'?'built-in':a.tier)+'</span></span></button>';
  }).join('');
  grid.querySelectorAll('.app').forEach(b=>b.onclick=()=>openApp(b.dataset.s));
  el('more').style.display = S.offset < S.total ? 'inline-flex' : 'none';
  el('more').textContent = 'Load more · '+n(S.offset)+' of '+n(S.total);
}
let _qt;
function wireSearch(){
  el('q').addEventListener('input', e=>{
    clearTimeout(_qt);
    _qt = setTimeout(()=>{ S.q = e.target.value.trim(); loadApps(true) }, 220);
  });
}

/* ── app sheet ──────────────────────────────────────────── */
async function openApp(slug){
  el('sheet').classList.add('on');
  el('sheet-bd').innerHTML = '<div class="empty">Loading…</div>';
  try{
    const d = await api('/v1/apps/'+encodeURIComponent(slug));
    S.cur = d;
    const conn = S.conns.find(x=>x.app===slug && x.status==='active');
    el('sh-ico').innerHTML = iconHTML(d, 40);
    el('sh-name').textContent = d.name;
    el('sh-cat').innerHTML = esc(d.category||'') + ' · ' + n(d.actions_count) + ' actions' +
      (conn ? ' · <span style="color:var(--ok)">connected</span>' : '');
    sheetTab('actions');
  }catch(e){ el('sheet-bd').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
}
function sheetTab(tab){
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on', b.dataset.t===tab));
  if(tab==='connect'){ el('sheet-bd').innerHTML = connectHTML(); wireConnect(); return }
  if(tab==='code'){ el('sheet-bd').innerHTML = codeHTML(); wireCode(); return }
  el('sheet-bd').innerHTML = actionsHTML();
  el('act-list').querySelectorAll('.act').forEach(b=>b.onclick=()=>pickAction(+b.dataset.i));
  pickAction(0);
}
function actionsHTML(){
  const acts = S.cur.actions||[];
  return '<div class="acts" id="act-list">'+ acts.map((a,i)=>
    '<button class="act'+(i===0?' on':'')+'" data-i="'+i+'"><span style="flex:1;min-width:0">'+
    '<span class="an">'+esc(a.name)+'</span><br><span class="as">'+esc(a.slug)+'</span></span>'+
    '<span class="badge '+(a.tier==='read'?'ok':'acc')+'">'+esc(a.tier)+'</span></button>').join('')+'</div>'+
    '<div id="p-fields"></div>'+
    '<div class="row" style="margin:14px 0 10px"><b style="font-size:13px">Result</b><span class="sp"></span>'+
    '<span class="tiny muted" id="p-meta"></span></div>'+
    '<pre class="out" id="p-out">Pick an action.</pre>'+
    '<div class="row" style="margin-top:12px;gap:8px"><button class="btn acc" id="runbtn" style="flex:1" disabled>Run action</button>'+
    '<label class="row tiny" style="gap:6px"><input type="checkbox" id="p-dry"> dry run</label></div>'+
    '<div id="approve-box" class="card pad" style="display:none;margin-top:12px;border-color:rgba(163,34,23,.35);background:#FDF3F1">'+
    '<b style="font-size:13.5px">This writes to '+esc((S.cur&&S.cur.name)||'the app')+'</b>'+
    '<p class="tiny" style="margin:6px 0 10px;color:var(--ink-2)" id="approve-msg"></p>'+
    '<button class="btn sm" id="approve-btn" style="background:var(--bad);border-color:var(--bad)">Approve and run once</button></div>';
}
function pickAction(i){
  const a = S.cur.actions[i]; S.act = a;
  document.querySelectorAll('#act-list .act').forEach(b=>b.classList.toggle('on', +b.dataset.i===i));
  const req = a.required||[];
  const fields = Object.entries(a.params||{}).map(([k,v])=>{
    const typ = v.type||'string';
    let input;
    if(v.enum) input = '<select class="inp" data-arg="'+esc(k)+'">'+v.enum.map(o=>'<option>'+esc(o)+'</option>').join('')+'</select>';
    else if(typ==='boolean') input = '<select class="inp" data-arg="'+esc(k)+'"><option value="true">true</option><option value="false">false</option></select>';
    else if(typ==='object') input = '<textarea class="inp" data-arg="'+esc(k)+'" data-type="object" placeholder="{ }"></textarea>';
    else input = '<input class="inp" data-arg="'+esc(k)+'" type="'+(typ==='integer'||typ==='number'?'number':'text')+'"'+
      (v.default!==undefined?' value="'+esc(v.default)+'"':'')+'>';
    return '<div class="field"><label>'+esc(k)+(req.includes(k)?' *':'')+
      '<span class="hint">'+esc(typ)+'</span></label>'+input+
      (v.description?'<span class="tiny muted">'+esc(v.description)+'</span>':'')+'</div>';
  }).join('');
  el('p-fields').innerHTML = fields || '<div class="tiny muted" style="margin-bottom:8px">This action takes no arguments.</div>';
  el('runbtn').disabled = false;
  el('runbtn').onclick = runAction;
  el('p-out').textContent = 'Ready.';
  el('p-meta').textContent = '';
}
async function runAction(){
  const a = S.act; if(!a) return;
  const args = {};
  document.querySelectorAll('#p-fields [data-arg]').forEach(inp=>{
    let v = inp.value; if(v==='') return;
    const spec = (a.params||{})[inp.dataset.arg]||{};
    if(inp.dataset.type==='object'){ try{ v = JSON.parse(v) }catch(e){ throw new Error(inp.dataset.arg+' is not valid JSON') } }
    else if(spec.type==='integer') v = parseInt(v,10);
    else if(spec.type==='number') v = parseFloat(v);
    else if(spec.type==='boolean') v = v==='true';
    else if(spec.type==='array') v = v.split(',').map(x=>x.trim()).filter(Boolean);
    args[inp.dataset.arg] = v;
  });
  const out = el('p-out'), meta = el('p-meta'), btn = el('runbtn');
  btn.disabled = true; out.textContent = 'Running…'; meta.textContent='';
  el('approve-box').style.display = 'none';
  const t0 = performance.now();
  try{
    const d = await api('/v1/execute', {method:'POST', body:{action:S.cur.slug+'.'+a.slug, entity_id:'default',
      args, approved:false, dry_run: el('p-dry').checked}});
    meta.textContent = (d.status==='pending_approval' ? 'needs approval' : (d.status||'')) + ' · ' +
      Math.round(performance.now()-t0) + 'ms';
    out.textContent = JSON.stringify(d, null, 2);
    if(d.status === 'pending_approval'){ showApproval(d, args);
      el('approve-box').scrollIntoView({behavior:'smooth', block:'center'}) }
    else if(el('p-out')) el('p-out').scrollIntoView({behavior:'smooth', block:'nearest'});
  }catch(e){ out.textContent = 'Error: ' + e.message; meta.textContent = '' }
  btn.disabled = false;
}
function showApproval(d, args){
  const box = el('approve-box'); box.style.display='block';
  el('approve-msg').textContent = (d.tier==='destructive' ? 'Destructive action. ' : 'Write action. ') +
    'Tony paused it before touching ' + ((S.cur&&S.cur.name)||'the app') + '. Approve to send this exact request once.';
  el('approve-btn').onclick = async()=>{
    const btn = el('approve-btn'); btn.disabled = true; btn.textContent='Approving…';
    try{
      const r = await api('/v1/runs/'+encodeURIComponent(d.run_id)+'/approve', {method:'POST'});
      el('p-out').textContent = JSON.stringify(r, null, 2);
      el('p-meta').textContent = r.ok ? 'approved · ' + (r.latency_ms||0) + 'ms' : 'approved · failed';
      if(r.ok){ box.style.display='none'; toast('Ran with write access') }
    }catch(e){ toast(e.message) } finally { btn.disabled=false; btn.textContent='Approve and run once' }
  };
}

/* code tab */
function codeHTML(){
  const d = S.cur, a = (S.cur.actions||[])[0] || {slug:'list'};
  const action = d.slug + '.' + a.slug;
  const base = CFG.public_url || location.origin;
  const key = 'tk_live_YOUR_KEY';
  const curl = 'curl -X POST ' + base + '/v1/execute \\\n  -H "Authorization: Bearer ' + key + '" \\\n  -H "Content-Type: application/json" \\\n  -d \'{"action":"' + action + '","entity_id":"default","args":{}}\'';
  const py = 'import httpx\n\nr = httpx.post(\n    "' + base + '/v1/execute",\n    headers={"Authorization": "Bearer ' + key + '"},\n    json={"action": "' + action + '", "entity_id": "default", "args": {}},\n    timeout=60,\n)\nprint(r.json()["data"])';
  const js = "const r = await fetch('" + base + "/v1/execute', {\n  method: 'POST',\n  headers: { 'Authorization': 'Bearer " + key + "', 'Content-Type': 'application/json' },\n  body: JSON.stringify({ action: '" + action + "', entity_id: 'default', args: {} }),\n});\nconst out = await r.json();\nconsole.log(out.data);";
  const mcp = JSON.stringify({ mcpServers: { tony: { type:'http', url: base + '/mcp',
      headers: { Authorization: 'Bearer ' + key } } } }, null, 2);
  const tool = JSON.stringify({ name: action.replace('.', '__'), description: a.name,
      input_schema: { type:'object', properties: a.params||{}, required: a.required||[] } }, null, 2);
  const block = (label, code, id)=>'<div class="row" style="margin:14px 0 6px"><b style="font-size:12.5px">'+label+
    '</b><span class="sp"></span><button class="btn ghost sm" data-copy="'+id+'">Copy</button></div>'+
    '<pre class="out" id="'+id+'">'+esc(code)+'</pre>';
  return '<p class="tiny muted" style="margin:0 0 4px">Every action in this app is callable from your own agent. '+
    'Create a key in <b>API keys</b>, then paste these.</p>'+
    block('curl', curl, 'cs-curl') + block('Python', py, 'cs-py') + block('JavaScript', js, 'cs-js') +
    block('MCP client (Claude, Cursor, any agent)', mcp, 'cs-mcp') + block('Tool schema for an LLM', tool, 'cs-tool');
}
function wireCode(){
  document.querySelectorAll('[data-copy]').forEach(b=>b.onclick=async()=>{
    const t = el(b.dataset.copy).textContent;
    try{ await navigator.clipboard.writeText(t); b.textContent='Copied'; setTimeout(()=>b.textContent='Copy',1400) }
    catch(e){ toast('Select and copy manually') }
  });
}

/* connect tab */
function connectHTML(){
  const d = S.cur, conn = S.conns.find(x=>x.app===d.slug && x.status==='active');
  if(conn){
    return '<div class="card pad"><b>Connected</b>'+
      (conn.base_url?'<p class="mono tiny" style="margin:8px 0 0;word-break:break-all">'+esc(conn.base_url)+'</p>':'')+
      '<p class="tiny muted" style="margin:8px 0 14px">'+(conn.scopes&&conn.scopes.length?'Scopes: '+esc(conn.scopes.join(' ')):'Credentials are stored encrypted on this server.')+'</p>'+
      '<button class="btn ghost sm" id="btn-disc">Disconnect</button></div>';
  }
  if(d.auth.type==='oauth2'){
    const ready = d.configured;
    return '<div class="card pad"><b>Sign in with '+esc(d.name)+'</b>'+
      '<p class="tiny muted" style="margin:6px 0 14px">Tony sends you to '+esc(d.name)+' and stores the tokens encrypted here.</p>'+
      (ready?'<button class="btn sm" id="btn-oauth">Connect '+esc(d.name)+'</button>'
        :'<pre class="out">Set '+esc(d.auth.client_id_env||'CLIENT_ID')+' and '+esc(d.auth.client_secret_env||'CLIENT_SECRET')+' in the environment, then restart Tony.</pre>')+
      '</div>';
  }
  const base = !!d.needs_base_url, token = d.auth.type!=='none';
  return '<div class="card pad"><b>'+(base?'Point Tony at ':'Add your ')+esc(d.name)+'</b>'+
    '<p class="tiny muted" style="margin:6px 0 14px">'+esc(base
      ? 'This app ships documented paths but no fixed host. Paths get appended to the base URL you paste here.'
      : 'Stored encrypted on this server and never shown again.')+'</p>'+
    (base?'<div class="field"><label>API base URL *<span class="hint">https</span></label><input class="inp" id="c-base" placeholder="https://api.vendor.com/v1" autocomplete="off"></div>':'')+
    (token?'<div class="field"><label>Token / API key *</label><input class="inp" id="c-key" type="password" placeholder="paste the key" autocomplete="off"></div>':'')+
    '<button class="btn acc sm" id="btn-save">Save connection</button>'+
    (d.docs?'<p class="tiny muted" style="margin:12px 0 0">Vendor docs: <a href="'+esc(d.docs)+'" target="_blank" rel="noopener" style="text-decoration:underline">'+esc(d.docs)+'</a></p>':'')+
    '</div>';
}
function wireConnect(){
  const d = S.cur;
  const save = el('btn-save'), oauth = el('btn-oauth'), disc = el('btn-disc');
  if(disc) disc.onclick = async()=>{
    await api('/v1/connections/'+encodeURIComponent(d.slug)+'?entity_id=default', {method:'DELETE'});
    toast('Disconnected'); loadConns(); openApp(d.slug);
  };
  if(oauth) oauth.onclick = async()=>{
    try{
      const r = await api('/v1/connections/'+encodeURIComponent(d.slug)+'/start?entity_id=default', {method:'POST'});
      if(r.authorization_url) location.href = r.authorization_url; else toast('Could not start');
    }catch(e){ toast(e.message) }
  };
  if(save) save.onclick = async()=>{
    const values = {};
    const b = el('c-base'), k = el('c-key');
    if(b){ if(!b.value.trim()){ toast('Paste the API base URL'); return } values.base_url = b.value.trim() }
    if(k && k.value.trim()){ values.api_key = k.value.trim(); values.token = k.value.trim(); values.access_token = k.value.trim() }
    if(d.auth.type!=='none' && !values.api_key){ toast('Paste the token as well'); return }
    save.disabled = true;
    try{
      await api('/v1/connections/'+encodeURIComponent(d.slug)+'/key', {method:'POST', body:{entity_id:'default', values, label:'console'}});
      toast('Connected'); await loadConns(); openApp(d.slug);
    }catch(e){ toast(e.message) } finally { save.disabled = false }
  };
}
function closeSheet(){ el('sheet').classList.remove('on') }

/* ── connections ────────────────────────────────────────── */
async function loadConns(){
  try{
    const d = await api('/v1/connections');
    S.conns = d.connections||[];
    const box = el('conn-list');
    if(!S.conns.length){ box.innerHTML='<div class="empty">No connections yet. Connect an app from the Apps tab.</div>'; return }
    box.innerHTML = S.conns.map(c=>
      '<div class="card pad" style="margin-bottom:10px"><div class="row wrap" style="gap:8px">'+
      '<b style="font-size:14px">'+esc(c.app)+'</b><span class="badge ok">'+esc(c.status)+'</span>'+
      '<span class="sp"></span><button class="btn ghost sm" data-d="'+esc(c.app)+'">Disconnect</button></div>'+
      (c.base_url?'<p class="mono tiny" style="margin:8px 0 0;word-break:break-all;color:var(--mut)">'+esc(c.base_url)+'</p>':'')+
      '<p class="tiny muted" style="margin:6px 0 0">entity '+esc(c.entity_id)+' · '+esc(c.label||'no label')+'</p></div>').join('');
    box.querySelectorAll('[data-d]').forEach(b=>b.onclick=async()=>{
      await api('/v1/connections/'+encodeURIComponent(b.dataset.d)+'?entity_id=default', {method:'DELETE'});
      toast('Disconnected'); loadConns();
    });
  }catch(e){ el('conn-list').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
}

/* ── activity ───────────────────────────────────────────── */
async function loadRuns(){
  try{
    const d = await api('/v1/runs?limit=60');
    const runs = d.runs||[];
    const ok = runs.filter(r=>r.status==='success').length;
    el('run-stats').innerHTML =
      '<div class="stat"><b>'+n(runs.length)+'</b><span>calls</span></div>'+
      '<div class="stat"><b>'+n(ok)+'</b><span>succeeded</span></div>'+
      '<div class="stat"><b>'+n(runs.reduce((s,r)=>s+(r.chars||0),0))+'</b><span>chars back</span></div>';
    el('run-list').innerHTML = runs.length ? runs.map(runLine).join('') : '<div class="empty">Nothing yet.</div>';
  }catch(e){ el('run-list').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
}

/* ── keys ───────────────────────────────────────────────── */
async function loadKeys(){
  try{
    const d = await api('/v1/account/keys');
    S.keys = d.keys||[];
    el('key-list').innerHTML = S.keys.length ? S.keys.map(k=>
      '<div class="pk"><code>'+esc(k.prefix)+'…</code><span class="tiny muted">'+esc(k.name)+'</span><span class="sp"></span>'+
      '<button class="btn ghost sm" data-r="'+esc(k.id)+'">Revoke</button></div>').join('')
      : '<div class="empty">No keys yet. Create one to call Tony from your own code.</div>';
    el('key-list').querySelectorAll('[data-r]').forEach(b=>b.onclick=async()=>{
      await api('/v1/account/keys/'+b.dataset.r, {method:'DELETE'}); toast('Key revoked'); loadKeys();
    });
  }catch(e){ el('key-list').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
}
async function newKey(){
  const field = el('key-name');
  const name = (field.value || 'server').trim() || 'server';
  try{
    const d = await api('/v1/account/keys', {method:'POST', body:{name}});
    el('new-key-box').style.display='block';
    el('new-key-val').textContent = d.key;
    if(field) field.value = '';
    toast('Copy the key now'); loadKeys();
  }catch(e){ toast(e.message) }
}

/* ── profile ────────────────────────────────────────────── */
function renderProfile(){
  const u = S.user||{};
  const pic = u.picture ? '<img src="'+esc(u.picture)+'" alt="" style="width:64px;height:64px;border-radius:50%;object-fit:cover;border:1px solid var(--line)">'
    : '<span class="mono-b" style="width:64px;height:64px;font-size:22px;border-radius:50%;background:hsl('+hue(u.email)+',45%,38%)">'+esc(initials(u.name||u.email))+'</span>';
  el('pf-head').innerHTML = pic + '<div style="min-width:0"><b style="font-family:var(--serif);font-size:20px;display:block">'+esc(u.name||'You')+'</b>'+
    '<span class="tiny muted">'+esc(u.email)+'</span><div class="row" style="gap:5px;margin-top:6px">'+
    (u.google?'<span class="badge">Google</span>':'')+(u.has_password?'<span class="badge">password</span>':'')+
    '<span class="badge ok">active</span></div></div>';
  el('pf-name').value = u.name||'';
  el('pf-pw-hint').textContent = u.has_password ? 'Change your password.' : 'You signed in with Google. Set a password so you can also sign in by email.';
}

async function saveProfile(){
  try{
    const d = await api('/v1/account/profile', {method:'PATCH', body:{name: el('pf-name').value.trim()}});
    S.user = Object.assign({}, S.user, d.user); renderWho(); renderProfile(); toast('Profile saved');
  }catch(e){ toast(e.message) }
}
async function savePassword(){
  const cur = el('pf-cur').value, nw = el('pf-new').value;
  if(nw.length<8){ toast('New password needs 8+ characters'); return }
  try{
    await api('/v1/account/password', {method:'POST', body:{current:cur, new:nw}});
    el('pf-cur').value=''; el('pf-new').value=''; renderProfile(); toast('Password updated');
  }catch(e){ toast(e.message) }
}
async function deleteAccount(){
  if(!confirm('Delete your Tony account and workspace? This cannot be undone.')) return;
  try{ await api('/v1/account/', {method:'DELETE'}); S.user=null; location.hash=''; showAuth(); toast('Account deleted') }
  catch(e){ toast(e.message) }
}

/* ── start ──────────────────────────────────────────────── */
wireSearch();
el('more').onclick = ()=>loadApps(false);
if(S.user){ showApp() } else { showAuth() }
if(location.hash) { /* keep */ }
el('sheet').addEventListener('click', e=>{ if(e.target.id==='sheet') closeSheet() });
document.addEventListener('keydown', e=>{ if(e.key==='Escape') closeSheet() });
"""


def _google_script(client_id: str) -> str:
    if not client_id:
        return ""
    return ('<script src="https://accounts.google.com/gsi/client" async defer></script>')


def console_html(user: Any = None) -> str:
    import json

    cfg = {"google_client_id": settings.google_client_id, "demo_open": settings.demo_open,
           "public_url": (settings.base_url or "").rstrip("/")}
    me = None
    if user is not None:
        from .accounts import public_user

        me = public_user(user)

    js = CONSOLE_JS.replace("__CFG__", json.dumps(cfg)).replace("__ME__", json.dumps(me))
    name = (me or {}).get("name") or ""
    mark = (
        '<svg viewBox="0 0 64 64" aria-hidden="true">'
        '<rect width="64" height="64" rx="15" fill="#0E0E0C"/>'
        '<path d="M11.5 32h6.5" stroke="#F3F0E9" stroke-width="5" stroke-linecap="round"/>'
        '<circle cx="32" cy="32" r="13" fill="none" stroke="#F3F0E9" stroke-width="5" '
        'stroke-dasharray="62 19.7" stroke-linecap="round" transform="rotate(45 32 32)"/>'
        '<circle cx="33.5" cy="30.5" r="4.6" fill="#E2542B"/></svg>'
    )
    from .catalog import catalog as _cat

    _st = _cat.stats()
    apps = f"{_st['apps']:,}"
    acts = f"{_st['actions']:,}"
    nav = ""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#F4EFE7">
<title>Tony — console</title>
<link rel="icon" href="/static/brand/tony-mark.svg">
<link rel="apple-touch-icon" href="/static/brand/tony-mark-192.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&display=swap" rel="stylesheet">
<style>{CONSOLE_CSS}</style>
</head><body>

<div id="auth">
  <div class="auth-l">
    <div class="brand" style="padding:0">{mark}<b style="font-family:var(--serif);font-size:20px">Tony</b><i>v0.2</i></div>
    <h1>Every app.<br>One port.</h1>
    <p>The console for your integration gateway: {apps} apps, {acts} actions, OAuth in the browser, keys sealed on this server, and a human gate on anything that writes.</p>
    <ul class="lst">
      <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12.5 9 17.5 20 6.5"/></svg>Your workspace, your keys, no vendor cloud</li>
      <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12.5 9 17.5 20 6.5"/></svg>Run, dry-run and inspect every call</li>
      <li><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12.5 9 17.5 20 6.5"/></svg>API keys for your own agents</li>
    </ul>
  </div>
  <div class="auth-r"><div class="auth-c">
    <div class="brand" style="justify-content:center;padding:0 0 16px">{mark}<b style="font-family:var(--serif);font-size:20px">Tony</b></div>
    <div class="card">
      <h2>Sign in</h2>
      <p class="tiny muted" style="margin:4px 0 0">One workspace per account. Nothing shared, nothing public.</p>
      <div id="g-wrap" style="margin-top:16px"><div id="g-btn"></div></div>
      <div class="or">or use email</div>
      <div class="seg">
        <button id="mode-login" class="on" onclick="authMode('login')">Sign in</button>
        <button id="mode-signup" onclick="authMode('signup')">Create account</button>
      </div>
      <form id="form-login" onsubmit="doLogin(event)">
        <div class="field"><label>Email</label><input class="inp" id="li-email" type="email" required autocomplete="email" placeholder="you@studio.com"></div>
        <div class="field"><label>Password</label><input class="inp" id="li-pass" type="password" required autocomplete="current-password" placeholder="••••••••"></div>
        <button class="btn wide" type="submit">Sign in</button>
      </form>
      <form id="form-signup" style="display:none" onsubmit="doSignup(event)">
        <div class="field"><label>Name</label><input class="inp" id="su-name" autocomplete="name" placeholder="Your name"></div>
        <div class="field"><label>Email</label><input class="inp" id="su-email" type="email" required autocomplete="email" placeholder="you@studio.com"></div>
        <div class="field"><label>Password<span class="hint">8+ characters</span></label><input class="inp" id="su-pass" type="password" required minlength="8" autocomplete="new-password"></div>
        <button class="btn wide" type="submit">Create account</button>
      </form>
      <div class="msg" id="auth-msg"></div>
    </div>
    <p class="tiny muted" style="text-align:center;margin:14px 0 0">Self-hosted · MIT · your data stays on your instance</p>
  </div></div>
</div>

<div id="shell" style="display:none">
  <aside class="rail">
    <div class="brand">{mark}<b>Tony</b><i>v0.2</i></div>
    <nav id="rail-nav" style="display:grid;gap:3px"></nav>
    <div class="rail-foot">
      <button class="who" id="who" onclick="go('profile')"></button>
      <button class="nav" onclick="signOut()" style="margin-top:4px"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M15 12H4m0 0 3.5-3.5M4 12l3.5 3.5M13 4h5a2 2 0 012 2v12a2 2 0 01-2 2h-5"/></svg><span>Sign out</span></button>
    </div>
  </aside>

  <div style="min-width:0">
    <header class="top">
      <button class="mark" onclick="go('overview')" style="gap:9px">{mark}<b>Tony</b></button>
      <span class="sp"></span>
      <button class="x" id="top-av" onclick="go('profile')" style="border:none;background:none;padding:0"></button>
    </header>

    <main>
      <!-- overview -->
      <section class="pg on" id="p-overview">
        <div class="hd"><div><h1>Overview</h1><p>Your gateway at a glance. Everything below is live from this workspace.</p></div>
          <button class="btn acc" onclick="go('apps')">Open catalogue</button></div>
        <div class="grid g4" style="margin-bottom:16px">
          <div class="stat"><b id="st-apps">—</b><span>apps</span></div>
          <div class="stat"><b id="st-acts">—</b><span>actions</span></div>
          <div class="stat"><b id="st-conn">—</b><span>connections</span></div>
          <div class="stat"><b id="st-runs">—</b><span id="st-runs-l">recent calls</span></div>
        </div>
        <div class="grid" style="grid-template-columns:1fr;gap:12px">
          <div class="card pad"><div class="row" style="margin-bottom:6px"><b style="font-size:14px">Recent activity</b>
            <span class="sp"></span><button class="btn ghost sm" onclick="go('runs')">All</button></div>
            <div id="ov-runs"></div></div>
          <div class="card pad"><div class="row" style="margin-bottom:6px"><b style="font-size:14px">Connected apps</b>
            <span class="sp"></span><button class="btn ghost sm" onclick="go('connections')">Manage</button></div>
            <div id="ov-conns"></div></div>
        </div>
      </section>

      <!-- apps -->
      <section class="pg" id="p-apps">
        <div class="hd"><div><h1>Catalogue</h1><p>Every app is queryable right now. Search hits the live registry.</p></div>
          <span class="badge" id="app-count">…</span></div>
        <input class="inp" id="q" placeholder="Search apps and actions — github, invoice, whatsapp…" style="margin-bottom:10px" autocomplete="off">
        <div class="opts" id="tier-opts" style="margin-bottom:14px"></div>
        <div class="apps" id="app-grid"></div>
        <div style="text-align:center;margin-top:16px"><button class="btn ghost" id="more" style="display:none">Load more</button></div>
      </section>

      <!-- connections -->
      <section class="pg" id="p-connections">
        <div class="hd"><div><h1>Connections</h1><p>Accounts your agents can act through. Credentials stay encrypted here.</p></div>
          <button class="btn" onclick="go('apps')">Add a connection</button></div>
        <div id="conn-list"></div>
      </section>

      <!-- activity -->
      <section class="pg" id="p-runs">
        <div class="hd"><div><h1>Activity</h1><p>Every call Tony made for this workspace, newest first.</p></div></div>
        <div class="grid g4" id="run-stats" style="margin-bottom:16px;grid-template-columns:repeat(3,1fr)"></div>
        <div class="card pad"><div id="run-list"></div></div>
      </section>

      <!-- keys -->
      <section class="pg" id="p-keys">
        <div class="hd"><div><h1>API keys</h1><p>Use these from your own backend, MCP client or SDK.</p></div></div>
        <div class="card pad" style="margin-bottom:12px">
          <div class="row wrap" style="gap:8px;align-items:flex-end">
            <div class="field" style="flex:1;min-width:180px;margin:0"><label>Key name</label>
              <input class="inp" id="key-name" placeholder="production" autocomplete="off"></div>
            <button class="btn acc" onclick="newKey()">Create key</button>
          </div>
        </div>
        <div class="card pad">
          <div id="new-key-box" style="display:none;margin-bottom:14px">
            <p class="tiny muted" style="margin:0 0 6px">Copy this now. It is not shown again.</p>
            <pre class="out" id="new-key-val" style="color:#EDE8DE"></pre>
          </div>
          <div id="key-list"></div>
          <div class="divider"></div>
          <p class="tiny muted" style="margin:0">Example<br><code class="mono">curl -H "Authorization: Bearer tony_sk_…" https://tony-7su0.onrender.com/v1/apps?limit=3</code></p>
        </div>
      </section>

      <!-- profile -->
      <section class="pg" id="p-profile">
        <div class="hd"><div><h1>Profile</h1><p>Your account, password and workspace.</p></div></div>
        <div class="card pad" style="margin-bottom:12px"><div class="row" style="gap:14px;align-items:flex-start" id="pf-head"></div></div>
        <div class="card pad" style="margin-bottom:12px">
          <b style="font-size:14px">Name</b>
          <div class="field" style="margin-top:10px"><label>Display name</label><input class="inp" id="pf-name"></div>
          <button class="btn sm" onclick="saveProfile()">Save</button>
        </div>
        <div class="card pad" style="margin-bottom:12px">
          <b style="font-size:14px">Password</b>
          <p class="tiny muted" id="pf-pw-hint" style="margin:6px 0 10px"></p>
          <div class="field"><label>Current password<span class="hint">leave blank if none</span></label><input class="inp" id="pf-cur" type="password" autocomplete="current-password"></div>
          <div class="field"><label>New password</label><input class="inp" id="pf-new" type="password" autocomplete="new-password" minlength="8"></div>
          <button class="btn sm" onclick="savePassword()">Update password</button>
        </div>
        <div class="card pad">
          <div class="row wrap"><button class="btn ghost sm" onclick="signOut()">Sign out</button>
            <span class="sp"></span><button class="btn ghost sm" style="color:var(--bad);border-color:rgba(163,34,23,.3)" onclick="deleteAccount()">Delete account</button></div>
        </div>
      </section>
    </main>
  </div>

  <nav class="tabbar" id="tabbar"></nav>
</div>

<div class="sheet" id="sheet"><div class="sheet-b">
  <div class="sheet-h">
    <span id="sh-ico"></span>
    <div style="flex:1;min-width:0"><b id="sh-name" style="font-family:var(--serif);font-size:18px"></b>
      <div class="tiny muted" id="sh-cat"></div></div>
    <button class="x" onclick="closeSheet()" aria-label="Close">✕</button>
  </div>
  <div class="tabs">
    <button data-t="actions" class="on" onclick="sheetTab('actions')">Actions</button>
    <button data-t="connect" onclick="sheetTab('connect')">Connect</button>
    <button data-t="code" onclick="sheetTab('code')">Code</button>
  </div>
  <div class="sheet-bd" id="sheet-bd" tabindex="0"></div>
</div></div>

<div id="toast"></div>
{_google_script(settings.google_client_id)}
<script>{js}</script>
</body></html>"""
