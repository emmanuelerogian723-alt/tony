"""The Tony Agent Playground page (Nango-style): ask -> trace -> connect -> result.

Pure HTML/CSS/JS served inline so it has no build step. It talks to the same public
API every developer uses: /v1/agent, /v1/apps, /v1/connections, /v1/connect-links.
"""
from __future__ import annotations

import json

LOGO = """<svg viewBox="0 0 64 64" width="{s}" height="{s}" aria-hidden="true">
<defs><linearGradient id="tb{u}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1A1A18"/><stop offset="1" stop-color="#0A0A09"/></linearGradient>
<linearGradient id="tr{u}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#CFCBC0"/></linearGradient>
<radialGradient id="td{u}" cx=".35" cy=".3" r=".9"><stop offset="0" stop-color="#FF8A5C"/><stop offset=".6" stop-color="#E2542B"/><stop offset="1" stop-color="#B53A17"/></radialGradient></defs>
<rect width="64" height="64" rx="16" fill="url(#tb{u})"/>
<path d="M15 20.5h22M26 20.5V43" stroke="url(#tr{u})" stroke-width="6" stroke-linecap="round" fill="none"/>
<circle cx="43.5" cy="38.5" r="9.5" fill="none" stroke="url(#tr{u})" stroke-width="5.2" stroke-dasharray="44 16" stroke-linecap="round" transform="rotate(-30 43.5 38.5)"/>
<circle cx="46" cy="36" r="3.6" fill="url(#td{u})"/></svg>"""


def logo(size: int = 28, uid: str = "a") -> str:
    return LOGO.format(s=size, u=uid)


_CSS = r"""
*{box-sizing:border-box;margin:0}
:root{--bg:#fff;--side:#fafaf9;--line:#ececea;--line2:#e2e1dd;--ink:#0d0d0c;--ink2:#3c3b37;--mut:#77756d;
--hot:#E2542B;--hot2:#FF8A5C;--ok:#16a34a;--warn:#d97706;--err:#dc2626;--r:14px}
html,body{height:100%}
body{font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;cursor:pointer}
.app{display:grid;grid-template-columns:232px 1fr;height:100vh;height:100dvh}
/* sidebar */
.side{background:var(--side);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:14px 10px}
.env{display:flex;align-items:center;gap:10px;padding:6px 8px 14px}
.env b{font-size:15px;letter-spacing:-.01em}.env small{display:block;color:var(--mut);font-size:11px;margin-top:-2px}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:9px;color:var(--ink2);text-decoration:none;font-size:13.5px}
.nav a:hover{background:#f0efec}.nav a.on{background:#ebeae6;color:var(--ink);font-weight:600}
.nav svg{width:16px;height:16px;flex:none;stroke:currentColor;fill:none;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.sp{flex:1}
.who{display:flex;align-items:center;gap:9px;padding:9px 10px;border:1px solid var(--line);border-radius:11px;background:#fff;font-size:12.5px}
.who i{width:24px;height:24px;border-radius:50%;background:var(--ink);color:#fff;display:grid;place-items:center;font:600 11px/1 inherit;font-style:normal}
.who span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* main */
.main{display:flex;flex-direction:column;min-width:0;height:100%;position:relative}
.top{display:flex;align-items:center;gap:10px;padding:12px 20px;border-bottom:1px solid var(--line);font-size:13px;color:var(--mut)}
.top b{color:var(--ink);font-weight:600}.top .grow{flex:1}
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:99px;border:1px solid var(--line2);font-size:12px;color:var(--ink2);background:#fff}
.pill i{width:7px;height:7px;border-radius:50%;background:var(--ok)}
.pill.off i{background:var(--warn)}
.btn-s{border:1px solid var(--line2);background:#fff;border-radius:9px;padding:6px 12px;font-size:12.5px}
.btn-s:hover{background:#f6f5f2}
.scroll{flex:1;overflow-y:auto;scroll-behavior:smooth}
.col{max-width:760px;margin:0 auto;padding:0 20px}
/* hero */
.hero{padding:7vh 0 20px;text-align:center}
.orbit{position:relative;width:200px;height:150px;margin:0 auto 18px}
.orbit .core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:54px;height:54px;border-radius:16px;background:#fff;border:1px solid var(--line2);display:grid;place-items:center;box-shadow:0 6px 24px rgba(13,13,12,.08)}
.orbit .sat{position:absolute;width:36px;height:36px;border-radius:11px;background:#fff;border:1px solid var(--line2);display:grid;place-items:center;box-shadow:0 3px 10px rgba(13,13,12,.06);animation:fl 5s ease-in-out infinite}
.orbit .sat img{width:20px;height:20px}
.orbit .s1{left:6px;top:8px}.orbit .s2{right:8px;top:2px;animation-delay:-1.2s}.orbit .s3{left:20px;bottom:6px;animation-delay:-2.4s}.orbit .s4{right:24px;bottom:10px;animation-delay:-3.4s}
.orbit svg.ln{position:absolute;inset:0;width:100%;height:100%}
@keyframes fl{50%{transform:translateY(-5px)}}
.hero h1{font-size:19px;font-weight:600;letter-spacing:-.015em}
.hero p{color:var(--mut);margin-top:4px;font-size:13.5px}
/* composer */
.comp{border:1px solid var(--line2);border-radius:var(--r);background:#fff;box-shadow:0 1px 2px rgba(13,13,12,.04),0 8px 28px rgba(13,13,12,.05);transition:border-color .15s,box-shadow .15s}
.comp:focus-within{border-color:#cfcdc6;box-shadow:0 1px 2px rgba(13,13,12,.05),0 10px 34px rgba(13,13,12,.09)}
.comp textarea{width:100%;border:0;outline:0;resize:none;background:transparent;padding:14px 16px 4px;font:inherit;font-size:14.5px;min-height:52px;max-height:160px;color:var(--ink)}
.comp textarea::placeholder{color:#a3a198}
.comp .bar{display:flex;align-items:center;gap:8px;padding:6px 10px 10px 14px;color:var(--mut);font-size:12px}
.comp .bar .grow{flex:1}
.chk{display:inline-flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
.chk input{accent-color:var(--hot)}
.send{width:32px;height:32px;border-radius:10px;border:0;background:var(--ink);color:#fff;display:grid;place-items:center}
.send:disabled{background:#d8d6d0;cursor:default}.send svg{width:15px;height:15px;stroke:#fff;fill:none;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
/* suggestions */
.sug{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px}
.sug button{display:flex;align-items:center;gap:10px;text-align:left;padding:11px 13px;border:1px solid var(--line);border-radius:12px;background:#fff;font-size:13px;color:var(--ink2)}
.sug button:hover{border-color:var(--line2);background:#fbfaf8;transform:translateY(-1px)}
.sug img{width:18px;height:18px;flex:none}
.sug span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.sug em{color:#b9b7ae;font-style:normal}
/* thread */
.thread{padding:22px 0 18px;display:flex;flex-direction:column;gap:18px}
.msg.user{align-self:flex-end;max-width:84%;background:var(--ink);color:#fff;padding:10px 14px;border-radius:14px 14px 4px 14px;white-space:pre-wrap;word-break:break-word}
.agent{display:flex;gap:12px}
.agent .av{flex:none;margin-top:1px}
.agent .body{flex:1;min-width:0;display:flex;flex-direction:column;gap:9px}
.trace{border:1px solid var(--line);border-radius:12px;background:#fcfcfb;overflow:hidden}
.tr{display:flex;align-items:center;gap:10px;padding:9px 13px;font-size:13px;border-top:1px solid var(--line)}
.tr:first-child{border-top:0}
.tr .ic{width:16px;height:16px;flex:none;display:grid;place-items:center}
.tr .t{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tr .m{color:var(--mut);font-size:12px;font-variant-numeric:tabular-nums}
.tr.ok .ic{color:var(--ok)}.tr.bad .ic{color:var(--err)}.tr.wait .ic{color:var(--warn)}
.tr code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;background:#f1f0ec;border-radius:6px;padding:1px 6px}
.spin{width:13px;height:13px;border:2px solid #dcdad3;border-top-color:var(--hot);border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.dots span{display:inline-block;width:5px;height:5px;margin-right:3px;border-radius:50%;background:#b9b7ae;animation:bl 1.1s infinite}
.dots span:nth-child(2){animation-delay:.15s}.dots span:nth-child(3){animation-delay:.3s}
@keyframes bl{50%{opacity:.25;transform:translateY(-2px)}}
.ans{white-space:pre-wrap;word-break:break-word;font-size:14.5px;line-height:1.6}
.ans b{font-weight:650}
.cc{border:1px solid var(--line2);border-radius:13px;background:#fff;padding:13px 14px;display:flex;align-items:center;gap:12px}
.cc img.lg,.cc .lg{width:34px;height:34px;border-radius:9px;flex:none;object-fit:contain}
.cc .tx{flex:1;min-width:0}.cc .tx b{display:block;font-size:13.5px}.cc .tx small{color:var(--mut);font-size:12px}
.btn{border:0;background:var(--ink);color:#fff;border-radius:10px;padding:8px 15px;font-weight:600;font-size:13px}
.btn:hover{background:#2a2a27}.btn.hot{background:var(--hot)}.btn.hot:hover{background:#cc4722}
.btn:disabled{opacity:.5;cursor:default}
.res{border:1px solid var(--line);border-radius:12px;background:#fff;overflow:hidden}
.res summary{padding:9px 13px;font-size:12.5px;color:var(--mut);cursor:pointer;list-style:none;display:flex;gap:8px;align-items:center}
.res summary::-webkit-details-marker{display:none}.res summary:before{content:"▸";font-size:10px;transition:transform .15s}
.res[open] summary:before{transform:rotate(90deg)}
.res pre{margin:0;padding:12px 14px;border-top:1px solid var(--line);background:#fafaf9;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;overflow:auto;max-height:300px;color:#33312c}
.items{display:flex;flex-direction:column}
.it{padding:9px 13px;border-top:1px solid var(--line);font-size:13px}.it:first-child{border-top:0}
.it small{display:block;color:var(--mut);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.foot{border-top:1px solid var(--line);padding:12px 0 calc(14px + env(safe-area-inset-bottom));background:linear-gradient(#fff0,#fff 30%)}
.foot .hint{text-align:center;color:#a3a198;font-size:11.5px;margin-top:8px}
/* modal */
.mask{position:fixed;inset:0;background:rgba(13,13,12,.45);backdrop-filter:blur(2px);display:none;align-items:center;justify-content:center;z-index:50;padding:16px}
.mask.on{display:flex;animation:fi .15s}
@keyframes fi{from{opacity:0}}
.modal{width:100%;max-width:400px;background:#fff;border-radius:18px;box-shadow:0 24px 80px rgba(13,13,12,.3);overflow:hidden;animation:pop .18s ease-out}
@keyframes pop{from{transform:translateY(8px) scale(.98);opacity:0}}
.modal .x{position:absolute;right:14px;top:12px;border:0;background:none;font-size:20px;color:var(--mut)}
.modal .in{position:relative;padding:30px 28px 22px;text-align:center}
.modal .big{width:52px;height:52px;margin:0 auto 14px;display:grid;place-items:center;border:1px solid var(--line);border-radius:14px;background:#fff}
.modal .big img{width:30px;height:30px}
.modal h3{font-size:16px;font-weight:650;letter-spacing:-.01em}
.modal p{color:var(--mut);font-size:13px;margin:8px 0 16px}
.modal .btn{width:100%;padding:11px;font-size:14px}
.modal .or{display:flex;align-items:center;gap:10px;color:#b0aea5;font-size:11.5px;margin:14px 0}
.modal .or:before,.modal .or:after{content:"";flex:1;height:1px;background:var(--line)}
.modal input{width:100%;border:1px solid var(--line2);border-radius:10px;padding:10px 12px;font:inherit;font-size:13.5px;outline:0;margin-bottom:8px}
.modal input:focus{border-color:var(--ink)}
.modal .err{color:var(--err);font-size:12.5px;margin:2px 0 8px;text-align:left}
.modal .sec{display:flex;justify-content:center;align-items:center;gap:7px;padding:12px;background:#fafaf9;border-top:1px solid var(--line);color:var(--mut);font-size:11.5px}
.modal .lnk{color:var(--mut);font-size:12px;text-decoration:underline;cursor:pointer;background:none;border:0}
/* mobile */
.menu{display:none}
@media(max-width:820px){
 .app{grid-template-columns:1fr}
 .side{position:fixed;inset:0 auto 0 0;width:250px;transform:translateX(-102%);transition:transform .2s;z-index:40;box-shadow:0 0 60px rgba(0,0,0,.2)}
 .side.on{transform:none}
 .menu{display:inline-grid;place-items:center;width:32px;height:32px;border:1px solid var(--line2);border-radius:9px;background:#fff}
 .top .hide-m{display:none}
 .sug{grid-template-columns:1fr}
 .hero{padding-top:4vh}
}
"""

_I = {
 "play": '<svg viewBox="0 0 24 24"><path d="M6 4l14 8-14 8z"/></svg>',
 "cat": '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
 "plug": '<svg viewBox="0 0 24 24"><path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/></svg>',
 "log": '<svg viewBox="0 0 24 24"><path d="M4 6h16M4 12h16M4 18h10"/></svg>',
 "key": '<svg viewBox="0 0 24 24"><circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/></svg>',
 "book": '<svg viewBox="0 0 24 24"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 19V5"/></svg>',
 "send": '<svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
 "menu": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
 "lock": '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
}

_JS = r"""
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ENTITY='playground';
const logoOf=slug=>'https://cdn.simpleicons.org/'+encodeURIComponent((slug||'').replace(/_/g,''))+'/0d0d0c';
const SUGG=[
 {t:"What's on my Google Calendar today?",a:'google_calendar',l:'googlecalendar'},
 {t:"Summarize my 3 latest emails in Gmail",a:'gmail',l:'gmail'},
 {t:"Star Tony's GitHub repo",a:'github',l:'github'},
 {t:'Send me "Hello, world!" on Slack',a:'slack',l:'slack'},
 {t:"Top 5 stories on Hacker News right now",a:'hackernews',l:'ycombinator'},
 {t:"What is the price of Bitcoin?",a:'coingecko',l:'coingecko'},
];
let history=[], busy=false, pendingConn=null;

// suggestions
$('#sug').innerHTML=SUGG.map((s,i)=>`<button data-i="${i}"><img alt="" src="https://cdn.simpleicons.org/${s.l}" onerror="this.style.visibility='hidden'"><span>${esc(s.t)}</span><em>→</em></button>`).join('');
$$('#sug button').forEach(b=>b.onclick=()=>{$('#q').value=SUGG[+b.dataset.i].t;send()});

// composer
const q=$('#q');
q.addEventListener('input',()=>{q.style.height='auto';q.style.height=Math.min(160,q.scrollHeight)+'px';$('#go').disabled=!q.value.trim()||busy});
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
$('#go').onclick=send;
$('#menu').onclick=()=>$('#side').classList.toggle('on');
$('#new').onclick=()=>{history=[];$('#thread').innerHTML='';$('#hero').style.display='';$('#sugw').style.display='';q.value='';q.focus()};

async function api(url,opt){
  const r=await fetch(url,opt); const t=await r.text(); let j; try{j=JSON.parse(t)}catch(e){j={raw:t}}
  j._status=r.status; return j;
}
function scrollEnd(){const s=$('#scroll');s.scrollTop=s.scrollHeight}
function row(kind,icon,text,meta){
  const ic={ok:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
   bad:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
   wait:'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 2"/></svg>',
   run:'<span class="spin"></span>'}[icon];
  return `<div class="tr ${kind}"><span class="ic">${ic}</span><span class="t">${text}</span><span class="m">${meta||''}</span></div>`;
}
function pretty(o){try{return JSON.stringify(o,null,2).slice(0,6000)}catch(e){return String(o)}}
function itemsOf(step){
  const d=step&&(step.data!==undefined?step.data:step.result);
  let arr=Array.isArray(d)?d:(d&&typeof d==='object'?(d.items||d.results||d.data||d.events||d.messages||d.stories||null):null);
  if(!Array.isArray(arr))return[];
  return arr.slice(0,6).map(x=>{
    if(x==null||typeof x!=='object')return {h:String(x),s:''};
    const h=x.title||x.name||x.subject||x.summary||x.full_name||x.text||x.id||Object.values(x)[0];
    const s=x.url||x.html_url||x.snippet||x.description||x.from||x.start||'';
    return {h:String(h).slice(0,120),s:typeof s==='object'?'':String(s).slice(0,140)};
  });
}

async function send(){
  const text=q.value.trim(); if(!text||busy)return;
  busy=true; $('#go').disabled=true; q.value=''; q.style.height='auto';
  $('#hero').style.display='none'; $('#sugw').style.display='none';
  const th=$('#thread');
  th.insertAdjacentHTML('beforeend',`<div class="msg user">${esc(text)}</div>`);
  const id='a'+Date.now();
  th.insertAdjacentHTML('beforeend',`<div class="agent" id="${id}"><div class="av">${LOGO28}</div><div class="body"><div class="trace" id="${id}t"></div><div id="${id}x"></div></div></div>`);
  const tr=$('#'+id+'t'), box=$('#'+id+'x');
  const t0=performance.now();
  tr.innerHTML=row('','run','Reading your request…');scrollEnd();
  // 1) match
  let m={};
  try{m=await api('/v1/queries',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text,source:'playground'})})}catch(e){}
  let h=row('ok','ok','Understood the goal','');
  if(m.action){h+=row('ok','ok',`Picked <code>${esc(m.action)}</code>${m.app?' in '+esc(m.app.name):''}`,m.confidence+'%')}
  else{h+=row('ok','ok','No single app needed. Thinking it through','')}
  tr.innerHTML=h+row('','run','Running with your connections…');scrollEnd();
  // 2) run the agent
  const dry=$('#dry').checked;
  let r;
  try{
    r=await api('/v1/agent',{method:'POST',headers:{'content-type':'application/json'},
      body:JSON.stringify({goal:text,entity_id:ENTITY,history:history.slice(-6),dry_run:dry,approve_writes:!dry})});
  }catch(e){r={error:String(e)}}
  const ms=Math.round(performance.now()-t0);
  h=row('ok','ok','Understood the goal','');
  if(m.action)h+=row('ok','ok',`Picked <code>${esc(m.action)}</code>${m.app?' in '+esc(m.app.name):''}`,m.confidence+'%');
  let need=null, approvals=[];
  (r.steps||[]).forEach(s=>{
    const nm=`<code>${esc((s.app||'')+(s.action?'.'+s.action:''))}</code>`;
    if(s.needs_connection){need=s.needs_connection;h+=row('wait','wait',`${nm||'App'} needs a connection`,'')}
    else if(s.status==='pending_approval'){approvals.push(s.run_id||'');h+=row('wait','wait',`${nm} needs your approval`,'')}
    else if(s.ok){h+=row('ok','ok',`Ran ${nm}`,s.elapsed_ms?s.elapsed_ms+' ms':'')}
    else{h+=row('bad','bad',`${nm} failed: ${esc((s.error||'error').slice(0,110))}`,'')}
  });
  if(!(r.steps||[]).length&&!r.error)h+=row('ok','ok','Answered directly','');
  h+=row(r.error||r._status>=400?'bad':'ok',r.error||r._status>=400?'bad':'ok',r.error||r._status>=400?'Request failed':'Done',ms+' ms');
  tr.innerHTML=h;
  let out='';
  const answer=r.answer||(r.detail?('⚠ '+(typeof r.detail==='string'?r.detail:pretty(r.detail))):'')||(r.error?('⚠ '+r.error):'');
  if(answer)out+=`<div class="ans">${esc(answer)}</div>`;
  (r.steps||[]).forEach(s=>{
    const its=s.ok?itemsOf(s):[];
    if(its.length)out+=`<div class="res"><div class="items">${its.map(i=>`<div class="it">${esc(i.h)}${i.s?`<small>${esc(i.s)}</small>`:''}</div>`).join('')}</div></div>`;
  });
  approvals.filter(Boolean).forEach(rid=>{out+=`<div class="cc"><div class="tx"><b>Approve a write</b><small>Tony stopped before changing anything.</small></div><button class="btn" data-approve="${esc(rid)}">Approve and run</button></div>`});
  if(need){out+=`<div class="cc" id="${id}c"><div class="lg" style="display:grid;place-items:center;background:#fff;border:1px solid var(--line)"><img id="${id}i" alt="" style="width:22px;height:22px" src="${logoOf(need)}" onerror="this.style.visibility='hidden'"></div><div class="tx"><b>Connect ${esc(prettyName(need))}</b><small>Sign in once so Tony can act on your account.</small></div><button class="btn hot" data-app="${esc(need)}" data-goal="${esc(text)}">Connect</button></div>`}
  if((r.steps||[]).length||r.error)out+=`<details class="res"><summary>Raw response · ${r.engine||'api'} · ${ms} ms</summary><pre>${esc(pretty(r))}</pre></details>`;
  box.innerHTML=out;
  $$('#'+id+'x .btn[data-app]').forEach(b=>b.onclick=()=>openConnect(b.dataset.app,b.dataset.goal));
  if(need){api('/v1/apps/'+encodeURIComponent(need)).then(a=>{const im=$('#'+id+'i');if(im&&a&&a.logo)im.src=a.logo});}
  $$('#'+id+'x .btn[data-approve]').forEach(b=>b.onclick=async()=>{
    const rid=b.dataset.approve; b.disabled=true; b.textContent='Approving…';
    const a=await api('/v1/runs/'+rid+'/approve',{method:'POST'});
    b.textContent=a.ok?'Approved':'Not approved';
    if(a.ok)box.insertAdjacentHTML('beforeend',`<div class="res"><summary>Approved · ${esc(a.status||'ran')}</summary><pre>${esc(pretty(a))}</pre></div>`);
  });
  history.push({role:'user',content:text});
  if(r.answer)history.push({role:'assistant',content:r.answer});
  busy=false; $('#go').disabled=!q.value.trim(); scrollEnd(); q.focus();
}
function prettyName(s){return String(s).replace(/[_-]/g,' ').replace(/\b\w/g,c=>c.toUpperCase())}

// ── connect modal ──
async function openConnect(slug,goal){
  pendingConn={slug,goal};
  const app=await api('/v1/apps/'+encodeURIComponent(slug));
  const name=app.name||prettyName(slug);
  const isOauth=app.auth&&app.auth.type==='oauth2';
  const needsBase=!!app.needs_base_url, needsToken=app.needs_token!==false;
  if(!needsToken&&!needsBase){
    $('#mask').classList.remove('on');
    const c=await api('/v1/connections/'+encodeURIComponent(slug)+'/start?entity_id='+ENTITY,{method:'POST'});
    if(c.connection||c.mode==='public'){await refreshConn();if(goal){q.value=goal;send()}}
    else $('#mErr').textContent=(c.detail||'Could not connect this app.');
    return;
  }
  $('#mApp').innerHTML=`<img alt="" src="${logoOf(slug)}" onerror="this.style.visibility='hidden'">`;
  $('#mTitle').textContent='Link '+name+' Account';
  $('#mErr').textContent=''; $('#mTok').value=''; $('#mBase').value='';
  $('#mBase').style.display=(needsBase||!needsToken)?'':'none';
  $('#mBase').placeholder=needsBase?'API base URL, e.g. https://api.vendor.com/v1':'API base URL (optional)';
  $('#mDocs').href=app.docs||'#'; $('#mDocs').style.display=app.docs?'':'none';
  $('#mOauth').style.display=isOauth?'':'none';
  $('#mOr').style.display=isOauth?'':'none';
  $('#mSub').textContent=isOauth?`We'll connect you to ${name}. A pop-up will open, please make sure your browser doesn't block pop-ups.`:`${name} connects with an API key or token. It is encrypted before it is stored.`;
  $('#mTokWrap').style.display=(isOauth&&needsToken)?'none':'';
  $('#mTokLink').style.display=(isOauth&&needsToken)?'':'none';
  $('#mOauth').style.display=(isOauth&&needsToken)?'':'none';
  $('#mOr').style.display=(isOauth&&needsToken)?'':'none';
  if(needsBase&&!needsToken){$('#mSave').textContent='Save and connect'}
  $('#mask').classList.add('on');
}
function closeConnect(){$('#mask').classList.remove('on');pendingConn=null}
$('#mX').onclick=closeConnect; $('#mask').addEventListener('click',e=>{if(e.target.id==='mask')closeConnect()});
$('#mTokLink').onclick=()=>{$('#mTokWrap').style.display='';$('#mTokLink').style.display='none';$('#mTok').focus()};
$('#mOauth').onclick=async()=>{
  if(!pendingConn)return; const b=$('#mOauth'); b.disabled=true; b.textContent='Opening…';
  const slug=pendingConn.slug;
  // open synchronously-ish to avoid popup blockers
  const w=window.open('about:blank','tony_oauth','width=520,height=700');
  const r=await api('/v1/connections/'+slug+'/start?entity_id='+ENTITY+'&redirect_after=/playground');
  b.disabled=false; b.textContent='Connect';
  if(r.authorization_url){ if(w)w.location=r.authorization_url; else location.href=r.authorization_url; watchConn(slug); }
  else{ if(w)w.close();
    $('#mErr').textContent=(r.detail||'Could not start sign-in.')+' You can connect with a token instead.';
    $('#mTokWrap').style.display='';$('#mTokLink').style.display='none'; }
};
$('#mSave').onclick=async()=>{
  if(!pendingConn)return; const v=$('#mTok').value.trim(); if(!v){$('#mErr').textContent='Paste a token first.';return}
  const vals={token:v,api_key:v,access_token:v}; const bu=$('#mBase').value.trim(); if(bu)vals.base_url=bu;
  $('#mSave').disabled=true; $('#mSave').textContent='Saving…';
  const r=await api('/v1/connections/'+pendingConn.slug+'/key',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({entity_id:ENTITY,values:vals,label:'playground'})});
  $('#mSave').disabled=false; $('#mSave').textContent='Save and connect';
  if(r.connection){const g=pendingConn.goal; closeConnect(); refreshConn(); if(g){q.value=g;send()}}
  else{$('#mErr').textContent=(typeof r.detail==='string'?r.detail:'Could not save that token.')}
};
function watchConn(slug){
  let n=0; const t=setInterval(async()=>{
    n++; const c=await api('/v1/connections?entity_id='+ENTITY);
    if((c.connections||[]).some(x=>x.app===slug&&x.status==='active')){clearInterval(t);const g=pendingConn&&pendingConn.goal;closeConnect();refreshConn();if(g){q.value=g;send()}}
    if(n>90)clearInterval(t);
  },2000);
}
async function refreshConn(){
  const c=await api('/v1/connections?entity_id='+ENTITY);
  const n=(c.connections||[]).filter(x=>x.status==='active').length;
  $('#connN').textContent=n+' connected';
}
refreshConn();
(async()=>{const h=await api('/health');if(h&&h.apps)$('#appN').textContent=h.apps.toLocaleString()+' apps · '+(h.actions||0).toLocaleString()+' actions'})();
q.focus();
"""


def playground_page() -> str:
    nav = [("play", "Playground", "/playground", True), ("cat", "Catalog", "/#catalog", False),
           ("plug", "Integrations", "/providers", False), ("key", "Connections", "/account", False),
           ("log", "Logs", "/app", False), ("book", "Docs", "/sdk", False)]
    nav_html = "".join(f'<a href="{h}" class="{"on" if on else ""}">{_I[i]}{t}</a>' for i, t, h, on in nav)
    sats = ("".join(f'<span class="sat s{n}"><img alt="" src="https://cdn.simpleicons.org/{s}"></span>'
                    for n, s in ((1, "slack"), (2, "github"), (3, "googlecalendar"), (4, "notion"))))
    lines = ('<svg class="ln" viewBox="0 0 200 150" fill="none" stroke="#e2e1dd" stroke-width="1.2" stroke-dasharray="3 4">'
             '<path d="M24 26L100 75M178 20L100 75M38 126L100 75M162 118L100 75"/></svg>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Playground · Tony</title><meta name="theme-color" content="#ffffff">
<link rel="icon" href="/favicon.ico"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>{_CSS}</style></head><body>
<div class="app">
 <aside class="side" id="side">
  <div class="env">{logo(30, 's')}<div><b>Tony</b><small>dev environment</small></div></div>
  <nav class="nav">{nav_html}</nav><div class="sp"></div>
  <div class="who"><i>T</i><span>Public demo workspace</span></div>
 </aside>
 <section class="main">
  <div class="top"><button class="menu" id="menu" aria-label="Menu">{_I["menu"]}</button>
   <b>Agent Playground</b><span class="hide-m">· test Tony end to end</span><span class="grow"></span>
   <span class="pill hide-m" id="appN"><i></i>Tony</span>
   <span class="pill off" id="connN"><i></i>0 connected</span>
   <button class="btn-s" id="new">New chat</button></div>
  <div class="scroll" id="scroll"><div class="col">
   <div class="hero" id="hero"><div class="orbit">{lines}{sats}<div class="core">{logo(34, 'c')}</div></div>
    <h1>Explore how Tony works with an agent</h1><p>Ask in plain words. Tony picks the tool, connects the account, and runs it for real.</p></div>
   <div class="thread" id="thread"></div>
  </div></div>
  <div class="foot"><div class="col">
   <div class="comp"><textarea id="q" rows="1" placeholder="Ask the agent to do something…" autocomplete="off"></textarea>
    <div class="bar"><label class="chk"><input type="checkbox" id="dry" checked> Safe mode (no writes)</label><span class="grow"></span>
     <span>Tony agent</span><button class="send" id="go" disabled aria-label="Send">{_I["send"]}</button></div></div>
   <div id="sugw"><div class="sug" id="sug"></div></div>
   <div class="hint">Tony runs real API calls on your connected accounts. Writes need Safe mode off.</div>
  </div></div>
 </section>
</div>
<div class="mask" id="mask"><div class="modal"><div class="in"><button class="x" id="mX" aria-label="Close">×</button>
 <div class="big" id="mApp"></div><h3 id="mTitle">Link Account</h3><p id="mSub"></p>
 <button class="btn" id="mOauth">Connect</button>
 <div class="or" id="mOr">or use a token</div>
 <button class="lnk" id="mTokLink">Paste an API key / token instead</button>
 <div id="mTokWrap" style="display:none;text-align:left"><input id="mTok" type="password" placeholder="API key or access token" autocomplete="off">
  <input id="mBase" placeholder="API base URL (https://api.example.com)" style="display:none">
  <div class="err" id="mErr"></div><button class="btn" id="mSave">Save and connect</button>
  <a class="lnk" id="mDocs" href="#" target="_blank" rel="noopener" style="display:none">Open the API docs ↗</a></div>
 </div><div class="sec">{_I["lock"]} Secured by Tony · encrypted at rest</div></div></div>
<script>const LOGO28={json.dumps(logo(28,'m'))};{_JS}</script></body></html>"""
