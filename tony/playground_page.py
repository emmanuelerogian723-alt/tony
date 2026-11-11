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

/* app icons */
.ico{width:100%;height:100%;object-fit:contain;display:block}
.tile{display:grid;place-items:center;flex:none;background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.tile.s24{width:24px;height:24px;border-radius:7px}.tile.s34{width:34px;height:34px}.tile.s52{width:52px;height:52px;border-radius:14px}
.tile img{width:70%;height:70%;object-fit:contain}
.tile.fill img{width:100%;height:100%}
/* timeline */
.tl{display:flex;flex-direction:column;gap:2px}
.ev{display:flex;align-items:center;gap:10px;padding:7px 2px;font-size:13px;color:var(--ink2)}
.ev .lead{width:18px;height:18px;flex:none;display:grid;place-items:center}
.ev .lead img{width:16px;height:16px}
.ev .t{flex:1;min-width:0}
.ev .t b{font-weight:600;color:var(--ink)}
.ev .chip{font:11.5px ui-monospace,Menlo,monospace;color:var(--mut);background:#f4f3ef;border:1px solid var(--line);border-radius:7px;padding:2px 8px;white-space:nowrap}
.ev .m{color:var(--mut);font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.ev.ok .ck{color:var(--ok)}.ev.bad .ck{color:var(--err)}.ev.wait .ck{color:var(--warn)}
.ev button.mini{border:1px solid var(--line2);background:#fff;border-radius:8px;padding:4px 10px;font-size:12px}
.ev button.mini:hover{background:#f6f5f2}
.ev-detail{margin:0 0 6px 28px;border:1px solid var(--line);border-radius:10px;background:#fafaf9;font:11.5px/1.55 ui-monospace,Menlo,monospace;padding:9px 12px;overflow:auto;max-height:220px;white-space:pre-wrap;word-break:break-word;color:#33312c;display:none}
.ev-detail.on{display:block}
/* connect card (inline, like Nango) */
.cc{border:1px solid var(--line2);border-radius:13px;background:#fff;padding:12px 14px;display:flex;align-items:center;gap:12px;box-shadow:0 1px 2px rgba(13,13,12,.04)}
.cc.done{background:#f6fbf7;border-color:#cfe8d6}
.cc .tx b{display:block;font-size:13.5px}.cc .tx small{color:var(--mut);font-size:12px}
.btn.go{background:var(--hot);display:inline-flex;align-items:center;gap:6px}
.btn.go:hover{background:#cc4722}
/* answer card */
.ans{border:1px solid var(--line);border-radius:13px;background:#fff;padding:14px 16px;font-size:14.5px;line-height:1.65}
.ans p{margin:0 0 8px}.ans p:last-child{margin:0}
.ans ol,.ans ul{margin:4px 0 8px;padding-left:20px}.ans li{margin:3px 0}
.ans code{font:12.5px ui-monospace,Menlo,monospace;background:#f1f0ec;border-radius:6px;padding:1px 6px}
.ans a{color:#1d4ed8}
/* modal polish */
.modal .big{width:64px;height:64px;border-radius:16px;box-shadow:0 4px 16px rgba(13,13,12,.08)}
.modal .big .tile{width:100%;height:100%;border:0;border-radius:16px}
.modal .btn.hot{background:var(--hot)}
.modal .row2{display:flex;gap:8px;align-items:center;justify-content:center;margin-top:10px}
.modal .ok{color:var(--ok);font-size:13px;margin:6px 0}
/* connections drawer */
.drawer{position:fixed;top:0;right:0;bottom:0;width:340px;max-width:92vw;background:#fff;border-left:1px solid var(--line);box-shadow:-20px 0 60px rgba(13,13,12,.12);transform:translateX(104%);transition:transform .2s;z-index:45;display:flex;flex-direction:column}
.drawer.on{transform:none}
.drawer h4{padding:16px 18px;font-size:14px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}
.drawer .list{flex:1;overflow:auto;padding:8px}
.drawer .row{display:flex;align-items:center;gap:11px;padding:10px;border-radius:11px}
.drawer .row:hover{background:#f7f6f3}
.drawer .row .nm{flex:1;min-width:0;font-size:13.5px;font-weight:550}.drawer .row .nm small{display:block;color:var(--mut);font-weight:400;font-size:11.5px}
.drawer .empty{color:var(--mut);text-align:center;padding:40px 20px;font-size:13px}
.drawer .search{margin:8px;padding:9px 12px;border:1px solid var(--line2);border-radius:10px;font:inherit;font-size:13px;outline:0;width:calc(100% - 16px)}
.dot-on{width:8px;height:8px;border-radius:50%;background:var(--ok)}

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
const pretty=o=>{try{return JSON.stringify(o,null,2).slice(0,6000)}catch(e){return String(o)}};
const prettyName=s=>String(s||'').replace(/[_-]/g,' ').replace(/\b\w/g,c=>c.toUpperCase());

/* ── app icons: real logo -> favicon -> colored letter tile, never a broken image ── */
function tile(slug,size,fill){
  const sl=encodeURIComponent(slug||'app');
  return `<span class="tile s${size||34}${fill?' fill':''}"><img alt="" loading="lazy" src="/v1/icon/${sl}" onerror="if(!this.dataset.f){this.dataset.f=1;this.src='/v1/icon-tile/${sl}';this.parentNode.classList.add('fill')}"></span>`;
}
const SUGG=[
 {t:"What's on my Google Calendar today?",a:'google_calendar'},
 {t:"Summarize my 3 latest emails in Gmail",a:'gmail'},
 {t:"Create an issue on GitHub",a:'github'},
 {t:'Send "Hello, world!" on Slack',a:'slack'},
 {t:"Top 5 stories on Hacker News right now",a:'hackernews'},
 {t:"What is the price of Bitcoin?",a:'coingecko'},
];
let history=[], busy=false, pendingConn=null, connected=new Set(), lastGoal='';

$('#sug').innerHTML=SUGG.map((s,i)=>`<button data-i="${i}">${tile(s.a,24)}<span>${esc(s.t)}</span><em>→</em></button>`).join('');
$$('#sug button').forEach(b=>b.onclick=()=>{q.value=SUGG[+b.dataset.i].t;send()});

const q=$('#q');
q.addEventListener('input',()=>{q.style.height='auto';q.style.height=Math.min(160,q.scrollHeight)+'px';$('#go').disabled=!q.value.trim()||busy});
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
$('#go').onclick=send;
$('#menu').onclick=()=>$('#side').classList.toggle('on');
$('#new').onclick=()=>{history=[];$('#thread').innerHTML='';$('#hero').style.display='';$('#sugw').style.display='';q.value='';q.focus()};

async function api(url,opt){
  const ctl=new AbortController(); const to=setTimeout(()=>ctl.abort(),(opt&&opt.timeout)||90000);
  try{
    const r=await fetch(url,Object.assign({signal:ctl.signal},opt||{})); const t=await r.text(); let j; try{j=JSON.parse(t)}catch(e){j={raw:t}}
    if(j===null||typeof j!=='object')j={raw:j}; j._status=r.status; return j;
  }catch(e){return {error:e.name==='AbortError'?'The request timed out. Try again.':String(e),_status:0}}
  finally{clearTimeout(to)}
}
const scrollEnd=()=>{const s=$('#scroll');s.scrollTop=s.scrollHeight};

/* markdown-lite for agent answers */
function md(t){
  let h=esc(t||'');
  h=h.replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>').replace(/`([^`\n]+)`/g,'<code>$1</code>');
  h=h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
  const lines=h.split(/\n/); let out='',list=null;
  for(const ln of lines){
    const m=ln.match(/^\s*(\d+)[.)]\s+(.*)/), b=ln.match(/^\s*[-*•]\s+(.*)/);
    if(m||b){const tag=m?'ol':'ul'; if(list!==tag){if(list)out+=`</${list}>`;out+=`<${tag}>`;list=tag} out+=`<li>${(m?m[2]:b[1])}</li>`}
    else{if(list){out+=`</${list}>`;list=null} if(ln.trim())out+=`<p>${ln}</p>`}
  }
  if(list)out+=`</${list}>`; return out;
}
const CHK='<svg class="ck" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
const BAD='<svg class="ck" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
const WAIT='<svg class="ck" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 2"/></svg>';
function ev(kind,lead,text,chip,meta,detail){
  const l=lead==='spin'?'<span class="spin"></span>':lead;
  const id='d'+Math.random().toString(36).slice(2,8);
  return `<div class="ev ${kind}"><span class="lead">${l}</span><span class="t">${text}</span>${chip?`<span class="chip">${chip}</span>`:''}${meta?`<span class="m">${meta}</span>`:''}${detail?`<button class="mini" data-d="${id}">details</button>`:''}</div>${detail?`<div class="ev-detail" id="${id}">${esc(detail)}</div>`:''}`;
}
function itemsOf(step){
  const d=step&&step.data&&step.data.data!==undefined?step.data.data:(step&&step.data);
  let arr=Array.isArray(d)?d:(d&&typeof d==='object'?(d.items||d.results||d.data||d.events||d.messages||d.stories||null):null);
  if(!Array.isArray(arr))return[];
  return arr.slice(0,6).map(x=>{
    if(x==null||typeof x!=='object')return {h:String(x),s:''};
    const h=x.title||x.name||x.subject||x.summary||x.full_name||x.text||x.id||Object.values(x)[0];
    const s=x.url||x.html_url||x.snippet||x.description||x.from||x.start||'';
    return {h:String(h).slice(0,120),s:typeof s==='object'?'':String(s).slice(0,140)};
  });
}

async function send(textOverride){
  const text=(typeof textOverride==='string'?textOverride:q.value).trim(); if(!text||busy)return;
  busy=true; $('#go').disabled=true; q.value=''; q.style.height='auto'; lastGoal=text;
  $('#hero').style.display='none'; $('#sugw').style.display='none';
  const th=$('#thread');
  th.insertAdjacentHTML('beforeend',`<div class="msg user">${esc(text)}</div>`);
  const id='a'+Date.now();
  th.insertAdjacentHTML('beforeend',`<div class="agent" id="${id}"><div class="av">${LOGO28}</div><div class="body"><div class="tl" id="${id}t"></div><div id="${id}x" style="display:flex;flex-direction:column;gap:9px"></div></div></div>`);
  const tl=$('#'+id+'t'), box=$('#'+id+'x'); const t0=performance.now();
  tl.innerHTML=ev('','spin','Starting an agent session…');scrollEnd();
  const m=await api('/v1/queries',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text,source:'playground'}),timeout:30000});
  let head=ev('ok',CHK,'Started an agent session','','');
  if(m.app) head+=ev('ok',tile(m.app.slug,24,0).replace('tile s24','tile s24'),`Searching the right tool <b>"${esc(text.slice(0,48))}"</b>`,m.action?esc(m.action):'',m.confidence?m.confidence+'%':'');
  tl.innerHTML=head+ev('','spin','Running with your connections…');scrollEnd();

  const dry=$('#dry').checked;
  const r=await api('/v1/agent',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({goal:text,entity_id:ENTITY,history:history.slice(-6),dry_run:dry,approve_writes:!dry}),timeout:120000});
  const ms=Math.round(performance.now()-t0);
  let h=head, need=null, approvals=[], items=[];
  (r.steps||[]).forEach(s=>{
    const nm=esc(prettyName(s.app||'')+(s.action?' · '+s.action:''));
    const lead=tile(s.app||'app',24,0);
    if(s.needs_connection){need=s.needs_connection;h+=ev('wait',lead,`<b>${esc(prettyName(s.app||s.needs_connection))}</b> needs access`,'','')}
    else if(s.status==='pending_approval'){approvals.push(s.run_id||'');h+=ev('wait',lead,`${nm} needs your approval`,'','')}
    else if(s.ok){h+=ev('ok',lead,`Ran <b>${nm}</b>`,esc(s.tier||''),s.latency_ms?s.latency_ms+' ms':'',pretty(s.data))}
    else{h+=ev('bad',lead,`${nm} failed: ${esc(String(s.error||'error').slice(0,120))}`,'','')}
  });
  if(!(r.steps||[]).length&&!r.error)h+=ev('ok',CHK,'Answered directly','','');
  const failed=r.error||r._status>=400||r._status===0;
  h+=ev(failed?'bad':'ok',failed?BAD:CHK,failed?'Request failed':'Done','',ms+' ms');
  tl.innerHTML=h;
  $$('#'+id+'t .mini').forEach(b=>b.onclick=()=>{const d=document.getElementById(b.dataset.d);d.classList.toggle('on');b.textContent=d.classList.contains('on')?'hide':'details';scrollEnd()});

  let out='';
  const answer=r.answer||(r.detail?('⚠ '+(typeof r.detail==='string'?r.detail:pretty(r.detail))):'')||(r.error?('⚠ '+r.error):'');
  if(answer)out+=`<div class="ans">${md(answer)}</div>`;
  (r.steps||[]).forEach(s=>{const its=s.ok?itemsOf(s):[];
    if(its.length)out+=`<div class="res"><div class="items">${its.map(i=>`<div class="it">${esc(i.h)}${i.s?`<small>${esc(i.s)}</small>`:''}</div>`).join('')}</div></div>`});
  approvals.filter(Boolean).forEach(rid=>{out+=`<div class="cc"><span class="tile s34">${WAIT}</span><div class="tx"><b>Approve a write</b><small>Tony stopped before changing anything.</small></div><button class="btn" data-approve="${esc(rid)}">Approve and run</button></div>`});
  if(need){out+=`<div class="cc" data-card="${esc(need)}">${tile(need,34)}<div class="tx"><b>Connect ${esc(prettyName(need))}</b><small>The agent needs access to continue.</small></div><button class="btn go" data-app="${esc(need)}">Connect <span>→</span></button></div>`}
  if((r.steps||[]).length||r.error)out+=`<details class="res"><summary>Raw response · ${esc(r.engine||'api')} · ${ms} ms</summary><pre>${esc(pretty(r))}</pre></details>`;
  box.innerHTML=out;
  $$('#'+id+'x .btn[data-app]').forEach(b=>b.onclick=()=>openConnect(b.dataset.app,text));
  $$('#'+id+'x .btn[data-approve]').forEach(b=>b.onclick=async()=>{
    const rid=b.dataset.approve; b.disabled=true; b.textContent='Approving…';
    const a=await api('/v1/runs/'+rid+'/approve',{method:'POST'});
    b.textContent=a.ok?'Done':'Failed';
    box.insertAdjacentHTML('beforeend',`<details class="res" open><summary>${a.ok?'Approved and ran':'Not approved'}</summary><pre>${esc(pretty(a))}</pre></details>`);scrollEnd();
  });
  history.push({role:'user',content:text}); if(r.answer)history.push({role:'assistant',content:r.answer});
  busy=false; $('#go').disabled=!q.value.trim(); scrollEnd(); q.focus();
}

/* ── connect modal (Link <App> Account) ── */
let PROVIDERS={};
async function loadProviders(){
  const r=await api('/v1/providers');
  (r.providers||[]).forEach(p=>PROVIDERS[p.app]=p);
}

function canGoogle(app){
  const prov=PROVIDERS[app.slug]||PROVIDERS[(app.slug||'').replace(/-/g,'_')]||{};
  const isGoogle=prov.google===true||/^google|^gmail|^youtube|^googleapis/.test(app.slug||'');
  return !!(window.TonyConnect&&TonyConnect.config&&TonyConnect.config.api_key&&isGoogle);
}
function openGoogleModal(app,name){
  pendingConn.mode='google';
  $('#mApp').innerHTML=tile(app.slug,52,0);
  $('#mTitle').textContent='Connect '+name;
  $('#mSub').textContent='Sign in with your Google account to let Tony use your own '+name+'. You approve the permissions on the Google consent screen, and Tony never sees your password.';
  $('#mErr').textContent=''; $('#mTok').value='';
  $('#mTokWrap').style.display='none'; $('#mTokLink').style.display='none'; $('#mOr').style.display='none';
  $('#mSave').style.display='none';
  $('#mOauth').style.display=''; $('#mOauth').textContent='Continue with Google'; $('#mOauth').disabled=false;
  $('#mDocs').style.display='none';
  $('#mask').classList.add('on');
}
function openSetupModal(app,name){
  pendingConn.mode='setup';
  $('#mApp').innerHTML=tile(app.slug,52,0);
  $('#mTitle').textContent='Connect '+name;
  $('#mSub').textContent='This app needs Tony\'s one-time provider setup before anyone can sign in. No keys needed from you.';
  $('#mTokWrap').style.display='none'; $('#mTokLink').style.display='none'; $('#mOr').style.display='none';
  $('#mSave').style.display='none'; $('#mOauth').style.display='none';
  $('#mErr').textContent='';
  $('#mDocs').href='/providers'; $('#mDocs').style.display=''; $('#mDocs').textContent='Open provider setup';
  $('#mask').classList.add('on');
}
async function runGoogle(slug){
  const app=await api('/v1/apps/'+encodeURIComponent(slug));
  const prov=PROVIDERS[slug]||PROVIDERS[(slug||'').replace(/-/g,'_')]||{};
  const scopes=prov.scopes||(app.auth&&app.auth.scopes)||[];
  $('#mOauth').disabled=true; $('#mOauth').textContent='Opening Google…'; $('#mErr').textContent='';
  try{
    sessionStorage.setItem('tony_pending_conn',JSON.stringify({slug,goal:(pendingConn&&pendingConn.goal)||''}));
    const token=await TonyConnect.google(scopes,slug);
    if(!token) return;                       // redirect flow: finished after reload
    await postGoogle(slug,token);
  }catch(e){
    const code=String((e&&(e.code||e.message))||'Google sign-in failed').replace('auth/','');
    $('#mErr').textContent=code==='popup-closed-by-user'?'Sign-in was cancelled.':code;
    $('#mOauth').disabled=false; $('#mOauth').textContent='Continue with Google';
    sessionStorage.removeItem('tony_pending_conn');
  }
}
async function postGoogle(slug,token){
  const r=await api('/v1/connections/'+encodeURIComponent(slug)+'/firebase-token?entity_id='+ENTITY,
    {method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({access_token:token})});
  if(r.connection){ sessionStorage.removeItem('tony_pending_conn'); await afterConnected(slug,r.identity||prettyName(slug)); return true }
  const msg=(typeof r.detail==='string'?r.detail:'Google sign-in did not complete.');
  if($('#mErr'))$('#mErr').textContent=msg;
  if($('#mOauth')){$('#mOauth').disabled=false;$('#mOauth').textContent='Continue with Google'}
  return false;
}
async function openConnect(slug,goal){
  pendingConn={slug,goal};
  const app=await api('/v1/apps/'+encodeURIComponent(slug));
  if(app._status===404||!app.slug){pendingConn=null;alert('Tony does not know an app called "'+slug+'".');return}
  pendingConn.real=app.slug; const name=app.name||prettyName(slug);
  const isOauth=app.auth&&app.auth.type==='oauth2';
  const needsBase=!!app.needs_base_url, needsToken=app.needs_token!==false;
  const prov=PROVIDERS[app.slug]||PROVIDERS[(app.slug||'').replace(/-/g,'_')];
  if(isOauth){
    if(prov&&prov.ready){
      // managed OAuth: one click, straight to the provider, no key form at all
      const w=window.open('about:blank','tony_oauth','width=540,height=720');
      const r=await api('/v1/connections/'+encodeURIComponent(app.slug)+'/start?entity_id='+ENTITY+'&redirect_after=/playground',{method:'POST'});
      if(r.authorization_url){ if(w)w.location=r.authorization_url; else location.href=r.authorization_url; watchConn(app.slug); }
      else { if(w)w.close(); alert(r.detail||'Could not start sign-in.'); }
      return;
    }
    if(canGoogle(app)){ openGoogleModal(app,name); return; }
    openSetupModal(app,name); return;
  }
  $('#mSave').style.display='';$('#mDocs').textContent='Open the API docs →';
  if(!needsToken&&!needsBase){
    const c=await api('/v1/connections/'+encodeURIComponent(app.slug)+'/start?entity_id='+ENTITY,{method:'POST'});
    if(c.connection||c.mode==='public'){await afterConnected(app.slug,name)}
    return;
  }
  $('#mApp').innerHTML=tile(app.slug,52,0);
  $('#mTitle').textContent='Link '+name+' Account';
  $('#mErr').textContent=''; $('#mTok').value=''; $('#mBase').value='';
  $('#mBase').style.display=(needsBase)?'':'none';
  $('#mBase').placeholder='API base URL, e.g. https://api.vendor.com/v1';
  $('#mDocs').href=app.docs||'#'; $('#mDocs').style.display=app.docs?'':'none';
  $('#mSub').textContent=isOauth?`We'll connect you to ${name}. A pop-up will open, please make sure your browser doesn't block pop-ups.`:`${name} connects with an API key or token. It is encrypted before it is stored.`;
  const oauthFirst=isOauth&&needsToken;
  $('#mOauth').style.display=oauthFirst?'':'none';
  $('#mOr').style.display=oauthFirst?'':'none';
  $('#mTokLink').style.display=oauthFirst?'':'none';
  $('#mTokWrap').style.display=oauthFirst?'none':'';
  $('#mSave').textContent=needsToken?'Save and connect':'Save and connect';
  $('#mask').classList.add('on');
}
function closeConnect(){$('#mask').classList.remove('on');pendingConn=null}
$('#mX').onclick=closeConnect; $('#mask').addEventListener('click',e=>{if(e.target.id==='mask')closeConnect()});
$('#mTokLink').onclick=()=>{$('#mTokWrap').style.display='';$('#mTokLink').style.display='none';$('#mTok').focus()};
$('#mOauth').onclick=async()=>{
  if(!pendingConn)return;
  if(pendingConn.mode==='google')return runGoogle(pendingConn.real||pendingConn.slug);
  const b=$('#mOauth'); b.disabled=true; b.textContent='Opening…';
  const slug=pendingConn.real||pendingConn.slug;
  const w=window.open('about:blank','tony_oauth','width=520,height=700');
  const r=await api('/v1/connections/'+slug+'/start?entity_id='+ENTITY+'&redirect_after=/playground');
  b.disabled=false; b.textContent='Connect';
  if(r.authorization_url){ if(w)w.location=r.authorization_url; else location.href=r.authorization_url; watchConn(slug); }
  else{ if(w)w.close();
    $('#mErr').textContent=(typeof r.detail==='string'?r.detail:'Could not start sign-in.')+' You can connect with a token instead.';
    $('#mTokWrap').style.display='';$('#mTokLink').style.display='none'; }
};
$('#mSave').onclick=async()=>{
  if(!pendingConn)return; const v=$('#mTok').value.trim(); const bu=$('#mBase').value.trim();
  if(!v&&$('#mTok').offsetParent!==null){$('#mErr').textContent='Paste a key or token first.';return}
  const vals={}; if(v){vals.token=v;vals.api_key=v;vals.access_token=v} if(bu)vals.base_url=bu;
  $('#mSave').disabled=true; $('#mSave').textContent='Connecting…';
  const slug=pendingConn.real||pendingConn.slug;
  const r=await api('/v1/connections/'+slug+'/key',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({entity_id:ENTITY,values:vals,label:'playground'})});
  $('#mSave').disabled=false; $('#mSave').textContent='Save and connect';
  if(r.connection){const nm=$('#mTitle').textContent.replace(/^Link | Account$/g,''); await afterConnected(slug,nm)}
  else{$('#mErr').textContent=(typeof r.detail==='string'?r.detail:'Could not save that. Check the key and try again.')}
};
function watchConn(slug){
  let n=0; const t=setInterval(async()=>{
    n++; const c=await api('/v1/connections?entity_id='+ENTITY);
    if((c.connections||[]).some(x=>x.app===slug&&x.status==='active')){clearInterval(t);await afterConnected(slug,prettyName(slug))}
    if(n>90||!pendingConn)clearInterval(t);
  },2000);
}
async function afterConnected(slug,name){
  const goal=pendingConn&&pendingConn.goal;
  closeConnect(); await refreshConn();
  $$('.cc[data-card="'+slug+'"], .cc[data-card]').forEach(c=>{ if(c.dataset.card===slug||c.dataset.card.replace(/[-_]/g,'')===slug.replace(/[-_]/g,'')){
    c.classList.add('done'); c.innerHTML=`${tile(slug,34)}<div class="tx"><b>${esc(name)} connected</b><small>Resuming your request…</small></div><span class="dot-on"></span>`}});
  if(goal){history=history.slice(0,-2);busy=false;send(goal)}
}

/* ── connections drawer ── */
async function refreshConn(){
  const c=await api('/v1/connections?entity_id='+ENTITY);
  const act=(c.connections||[]).filter(x=>x.status==='active');
  connected=new Set(act.map(x=>x.app));
  $('#connN').textContent=act.length+' connected'; $('#connN').classList.toggle('off',!act.length);
  $('#dList').innerHTML=act.length?act.map(x=>`<div class="row">${tile(x.app,34)}<div class="nm">${esc(prettyName(x.app))}<small>${esc(x.identity||x.label||'connected')}${x.is_default?' · default':''}</small></div><span class="dot-on"></span><button class="btn-s" data-rm="${esc(x.id)}">Remove</button></div>`).join(''):'<div class="empty">No apps connected yet.<br>Ask the agent for something and Tony will offer to connect the app it needs.</div>';
  $$('#dList [data-rm]').forEach(b=>b.onclick=async()=>{b.disabled=true;await api('/v1/connections/id/'+b.dataset.rm,{method:'DELETE'});refreshConn()});
}
$('#connN').onclick=()=>{$('#drawer').classList.add('on');refreshConn()};
$('#dX').onclick=()=>$('#drawer').classList.remove('on');
let st; $('#dSearch').addEventListener('input',()=>{clearTimeout(st);st=setTimeout(async()=>{
  const v=$('#dSearch').value.trim(); if(!v){$('#dRes').innerHTML='';return}
  const r=await api('/v1/apps?search='+encodeURIComponent(v)+'&limit=8&dedupe=true');
  $('#dRes').innerHTML=(r.apps||[]).map(a=>`<div class="row">${tile(a.slug,34)}<div class="nm">${esc(a.name)}<small>${esc(a.category||'')} · ${esc((a.auth&&a.auth.type)||'')}</small></div>${connected.has(a.slug)?'<span class="dot-on"></span>':`<button class="btn go" data-add="${esc(a.slug)}">Connect</button>`}</div>`).join('')||'<div class="empty">No matching apps.</div>';
  $$('#dRes [data-add]').forEach(b=>b.onclick=()=>{$('#drawer').classList.remove('on');openConnect(b.dataset.add,'')});
},250)});

loadProviders();
refreshConn();
(async()=>{ try{
  if(!window.TonyConnect) return;
  const t=await TonyConnect.finishRedirect();
  if(!t) return;
  const p=JSON.parse(sessionStorage.getItem('tony_pending_conn')||'{}');
  if(!p.slug) return;
  const ok=await postGoogle(p.slug,t);
  if(ok&&p.goal){ busy=false; send(p.goal); }
}catch(e){} })();
(async()=>{const h=await api('/health');if(h&&h.apps)$('#appN').textContent=h.apps.toLocaleString()+' apps · '+(h.actions||0).toLocaleString()+' actions'})();
q.focus();
"""


def _firebase_bits() -> tuple[str, str]:
    import json as _json
    import os as _os
    from . import firebase

    cfg = firebase.web_config()
    script = ""
    if cfg["api_key"]:
        script = ('<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>'
                  '<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js"></script>'
                  '<script src="/static/connect.js"></script>')
    return _json.dumps(cfg), script


def playground_page() -> str:
    _fb_cfg, _fb_js = _firebase_bits()
    nav = [("play", "Playground", "/playground", True), ("cat", "Catalog", "/#catalog", False),
           ("plug", "Integrations", "/providers", False), ("key", "Connections", "/account", False),
           ("log", "Logs", "/app", False), ("book", "Docs", "/sdk", False)]
    nav_html = "".join(f'<a href="{h}" class="{"on" if on else ""}">{_I[i]}{t}</a>' for i, t, h, on in nav)
    sats = ("".join(f'<span class="sat s{n}"><img alt="" src="/v1/icon/{s}"></span>'
                    for n, s in ((1, "slack"), (2, "github"), (3, "google_calendar"), (4, "notion"))))
    lines = ('<svg class="ln" viewBox="0 0 200 150" fill="none" stroke="#e2e1dd" stroke-width="1.2" stroke-dasharray="3 4">'
             '<path d="M24 26L100 75M178 20L100 75M38 126L100 75M162 118L100 75"/></svg>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Playground · Tony</title><meta name="theme-color" content="#ffffff">
<link rel="icon" href="/favicon.ico"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>{_CSS}</style>
<script>window.TONY_FB={_fb_cfg};</script>{_fb_js}</head><body>
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
   <button class="pill off" id="connN" style="cursor:pointer"><i></i>0 connected</button>
   <button class="btn-s" id="new">New chat</button></div>
  <div class="scroll" id="scroll"><div class="col">
   <div class="hero" id="hero"><div class="orbit">{lines}{sats}<div class="core">{logo(34, 'c')}</div></div>
    <h1>Explore how Tony works with an agent</h1><p>Ask in plain words. Tony picks the tool, connects the account, and runs it for real.</p></div>
   <div class="thread" id="thread"></div>
  </div></div>
  <div class="foot"><div class="col">
   <div class="comp"><textarea id="q" rows="1" placeholder="Ask the agent to do something…" autocomplete="off"></textarea>
    <div class="bar"><label class="chk"><input type="checkbox" id="dry"> Safe mode (no writes)</label><span class="grow"></span>
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
<aside class="drawer" id="drawer"><h4>Connections<button class="btn-s" id="dX">Close</button></h4>
 <a href="/connections" style="display:block;margin:8px 12px 0;font-size:12.5px;color:#6b6a63;text-decoration:none">Manage all accounts and permissions →</a>
 <input class="search" id="dSearch" placeholder="Search 7,900 apps to connect…" autocomplete="off">
 <div class="list"><div id="dRes"></div><div id="dList"></div></div></aside>
<script>const LOGO28={json.dumps(logo(28,'m'))};{_JS}</script></body></html>"""
