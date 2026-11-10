"""Tony console: signed-in workspace app (apps, connections, runs, keys, profile)."""
from __future__ import annotations

import os
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
.ask-fab{position:fixed;right:22px;bottom:92px;z-index:70;display:flex;align-items:center;gap:8px;
  background:var(--ink);color:var(--paper);border:1px solid var(--ink);border-radius:999px;
  padding:11px 16px;font-size:13px;font-weight:600;box-shadow:0 12px 30px rgba(9,9,11,.22);
  transition:transform .2s var(--ease),box-shadow .2s var(--ease)}
.ask-fab:hover{transform:translateY(-2px);box-shadow:0 18px 40px rgba(9,9,11,.28)}
.ask-fab svg{width:17px;height:17px}
.ask{position:fixed;right:22px;bottom:92px;width:min(380px,calc(100vw - 32px));height:min(560px,calc(100vh - 140px));
  z-index:80;background:var(--paper);border:1px solid var(--line-2);border-radius:16px;display:none;
  flex-direction:column;overflow:hidden;box-shadow:0 30px 70px rgba(9,9,11,.26)}
.ask.on{display:flex}
.ask-h{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--line)}
.ask-h b{display:block;font-size:13.5px}
.ask-h span{display:block;font-size:11px;color:var(--muted)}
.ask-dot{width:8px;height:8px;border-radius:50%;background:#1a7f4b;box-shadow:0 0 0 3px rgba(26,127,75,.14)}
.ask-x{margin-left:auto;font-size:20px;line-height:1;color:var(--muted);padding:2px 6px}
.ask-body{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:9px;background:var(--paper-2)}
.ask-msg{font-size:13px;line-height:1.55;padding:10px 12px;border-radius:12px;max-width:92%;white-space:pre-wrap}
.ask-msg.bot{background:var(--paper);border:1px solid var(--line);align-self:flex-start}
.ask-msg.me{background:var(--ink);color:var(--paper);align-self:flex-end}
.ask-msg.think{background:transparent;border:1px dashed var(--line-2);color:var(--muted);font-style:italic}
.ask-quick{display:flex;gap:6px;padding:8px 12px;border-top:1px solid var(--line);overflow-x:auto;flex:none}
.ask-quick button{font-size:11.5px;padding:5px 10px;border:1px solid var(--line-2);border-radius:999px;
  white-space:nowrap;color:var(--muted)}
.ask-quick button:hover{border-color:var(--ink);color:var(--ink)}
.ask-in{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--line);background:var(--paper)}
.ask-in input{flex:1;height:38px;border:1px solid var(--line-2);border-radius:9px;padding:0 11px;
  font-size:13px;font-family:inherit;background:var(--paper)}
.ask-in button{width:38px;height:38px;border-radius:9px;background:var(--ink);color:var(--paper);display:grid;place-items:center}
.ask-in button svg{width:16px;height:16px}
.ec-row{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}
.ec-row:last-child{border-bottom:0}
.ec-bar{height:4px;border-radius:2px;background:var(--line);flex:1;overflow:hidden}
.ec-bar i{display:block;height:100%;background:var(--ink);border-radius:2px}
@media (max-width:760px){.ask-fab{bottom:78px;right:14px}.ask{right:8px;left:8px;width:auto;bottom:74px}}
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

/* ── billing + sessions ─────────────────────────────────── */
.hero{display:flex;align-items:center;gap:18px;flex-wrap:wrap;padding:18px 20px;border-radius:var(--r-lg);
  background:linear-gradient(135deg,#12110F,#2C2A25);color:var(--paper);box-shadow:var(--shadow-lift);margin-bottom:14px}
.hero .amt{font-family:var(--serif);font-size:32px;line-height:1;letter-spacing:-.03em}
.hero .lbl{font-size:10.5px;text-transform:uppercase;letter-spacing:.1em;opacity:.62}
.hero .badge{background:rgba(244,239,231,.14);border-color:rgba(244,239,231,.26);color:var(--paper)}
.hero .note{font-size:12.5px;opacity:.72;max-width:44ch}
.meters{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-bottom:16px}
.mtr{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:12px 13px;box-shadow:var(--shadow)}
.mtr .k{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--mut);font-weight:600}
.mtr .v{font-family:var(--serif);font-size:19px;letter-spacing:-.02em;margin-top:3px;font-variant-numeric:tabular-nums}
.mtr .v small{font-family:var(--sans);font-size:11px;color:var(--mut);letter-spacing:0}
.bar{height:5px;border-radius:999px;background:rgba(18,17,15,.08);margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--ink);border-radius:999px}
.bar.w i{background:var(--warn)}
.bar.b i{background:var(--bad)}
.plans{display:grid;gap:12px;grid-template-columns:1fr;margin-bottom:16px}
@media(min-width:760px){.plans{grid-template-columns:repeat(3,1fr)}}
.plan{display:flex;flex-direction:column;gap:9px;background:var(--card);border:1px solid var(--line);
  border-radius:var(--r-lg);padding:16px;box-shadow:var(--shadow);position:relative}
.plan.mid{border-color:var(--ink);box-shadow:var(--shadow-lift)}
.plan h3{font-size:16px}
.plan .price{font-family:var(--serif);font-size:24px;letter-spacing:-.03em;line-height:1.1}
.plan .price small{font-family:var(--sans);font-size:11px;color:var(--mut);letter-spacing:0;font-weight:500}
.plan ul{margin:0;padding:0;list-style:none;display:grid;gap:6px}
.plan li{font-size:12.3px;color:var(--ink-2);padding-left:16px;position:relative}
.plan li:before{content:"✓";position:absolute;left:0;color:var(--ok);font-weight:700}
.plan .cur{position:absolute;right:12px;top:12px}
.ses{display:flex;gap:10px;align-items:center;padding:11px 0;border-bottom:1px solid var(--line);flex-wrap:wrap}
.ses:last-child{border-bottom:none}
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
  if(!r.ok){ const e = new Error(d.detail || d.error || ('HTTP '+r.status)); e.status=r.status; e.body=d; throw e }
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
function mountFirebaseGoogle(){
  const fb = CFG.firebase || {};
  if(!fb.api_key){ return false }
  el('g-wrap').innerHTML = '<button id="fb-google" style="width:100%;padding:11px 14px;border-radius:9px;'+
    'border:1px solid var(--line-2);background:#fff;color:#111;font-weight:600;cursor:pointer">'+
    'Continue with Google</button>';
  el('fb-google').onclick = async function(){
    authMsg('');
    try{
      if(!window.firebase || !firebase.auth) throw new Error('Firebase is still loading. Try again in a second.');
      if(!firebase.apps.length){
        firebase.initializeApp({apiKey:fb.api_key, authDomain:fb.auth_domain, projectId:fb.project_id});
      }
      const provider = new firebase.auth.GoogleAuthProvider();
      const cred = await firebase.auth().signInWithPopup(provider);
      const token = await cred.user.getIdToken();
      const d = await api('/v1/account/firebase', {method:'POST', body:{id_token:token}});
      S.user = d.user; location.hash = '#overview'; showApp(); toast('Signed in as ' + d.user.email);
    }catch(e){
      const code = (e && (e.code || e.message)) || 'Google sign-in failed';
      authMsg(String(code).replace('auth/',''));
    }
  };
  return true;
}
function mountGoogle(){
  if(CFG.firebase && CFG.firebase.api_key && mountFirebaseGoogle()) return;
  if(!CFG.google_client_id){
    if(!mountFirebaseGoogle()) el('g-wrap').innerHTML='<span class="tiny muted" style="padding:10px">Google sign-in is not configured on this server</span>';
    return }
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
             ['agent','Agent','M12 3v3m0 12v3M3 12h3m12 0h3M12 8.5a3.5 3.5 0 100 7 3.5 3.5 0 000-7z'],
             ['apps','Apps','M4 5h7v7H4zM13 5h7v7h-7zM4 14h7v6H4zM13 14h7v6h-7z'],
             ['connections','Connections','M9 15l6-6M7.5 4.5 6 6a4 4 0 105.7 5.7M16.5 19.5 18 18a4 4 0 10-5.7-5.7'],
             ['runs','Activity','M3 12h4l2.5-7 4 14L16 12h5'],
             ['keys','API keys','M14 7a4 4 0 10-3.5 4L4 17.5V21h3.5l6.5-6.5A4 4 0 0014 7z'],
             ['sessions','Sessions','M12 3a9 9 0 100 18 9 9 0 000-18zm0 4v5l3.5 2'],
             ['billing','Billing','M3 7h18M3 7l0 11a1 1 0 001 1h16a1 1 0 001-1V7M7 13h4'],
             ['ecosystem','Ecosystem','M4 17V7m5 10V4m5 13v-7m5 7V9'],
             ['profile','Profile','M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0']];
const MOBILE = ['apps','runs','sessions','billing','profile'];

function iconNav(d){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="'+d+'"/></svg>'}
function buildNav(){
  el('rail-nav').innerHTML = NAV.map(([id,label,d])=>
    '<button class="nav" data-p="'+id+'">'+iconNav(d)+'<span>'+label+'</span></button>').join('');
  el('rail-nav').querySelectorAll('.nav').forEach(b=>b.onclick=()=>go(b.dataset.p));
  const labels = {apps:'Apps', connections:'Links', runs:'Activity', keys:'Keys', sessions:'Sessions', billing:'Billing', profile:'You'};
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
  if(page==='billing'){ loadBilling() }
  if(page==='sessions'){ loadSessions() }
  if(page==='ecosystem'){ loadEcosystem() }
  if(page==='agent'){ mountAgent() }
}

/* ── agent ──────────────────────────────────────────────── */
let AG = {writes:false, on:false};
const AG_EX = ['summarise the top hacker news stories right now',
               'look up a random wikipedia article and summarise it',
               'find the newest stories on the front page and pick the best one',
               'what is trending in tech today'];
function mountAgent(){
  if(AG.on) return; AG.on = true;
  const box = el('ag-goal'), runBtn = el('ag-run');
  el('ag-example').onclick = ()=>{ box.value = AG_EX[Math.floor(Math.random()*AG_EX.length)]; };
  el('ag-writes').onclick = ()=>{
    AG.writes = !AG.writes;
    el('ag-writes').textContent = AG.writes ? 'Writes allowed' : 'Allow writes';
    el('ag-mode').textContent = AG.writes ? 'writes on' : 'writes off';
    el('ag-mode').style.borderColor = AG.writes ? 'var(--ink)' : '';
  };
  runBtn.onclick = runAgent;
  box.addEventListener('keydown', e=>{ if((e.metaKey||e.ctrlKey)&&e.key==='Enter') runAgent(); });
}
async function runAgent(){
  const goal = (el('ag-goal').value||'').trim();
  if(!goal){ toast('Describe the outcome first'); return; }
  const btn = el('ag-run'), out = el('ag-answer'), steps = el('ag-steps');
  btn.disabled = true; btn.textContent = 'Working…';
  el('ag-meta').textContent = '';
  out.innerHTML = '<span class="muted">Choosing apps and planning…</span>';
  steps.innerHTML = '<div class="empty">Running…</div>';
  try{
    const d = await api('/v1/agent', {method:'POST',
      body: {goal, max_steps: 4, approve_writes: AG.writes}});
    el('ag-meta').textContent = (d.engine||'') + ' · ' + (d.elapsed_ms||0) + ' ms';
    out.textContent = d.answer || 'No answer came back.';
    const rows = (d.steps||[]).map(st=>{
      const good = st.ok;
      return '<div class="row" style="align-items:flex-start;gap:10px;padding:9px 0;border-top:1px solid var(--line)">'+
        '<span class="mono-b" style="color:'+(good?'#12724a':'#a33')+'">'+(good?'OK':'FAIL')+'</span>'+
        '<div style="flex:1;min-width:0"><div class="mono-b">'+esc(st.app||'-')+'.'+esc(st.action||'-')+'</div>'+
        '<div class="tiny muted" style="margin-top:2px">'+esc((st.error||'').slice(0,200) || ((st.latency_ms||0)+' ms'))+'</div></div></div>';
    }).join('');
    steps.innerHTML = rows || '<div class="empty">The model answered without calling a tool.</div>';
  }catch(e){
    out.textContent = 'That run failed: ' + e.message;
    steps.innerHTML = '<div class="empty">No calls recorded.</div>';
  }finally{ btn.disabled = false; btn.textContent = 'Run'; }
}

/* ── boot ───────────────────────────────────────────────── */
async function boot(){
  renderWho(); buildNav(); checkBillingReturn();
  const h = (location.hash||'#overview').slice(1);
  go(['overview','agent','apps','connections','runs','keys','sessions','billing','ecosystem','profile'].includes(h) ? h : 'overview');
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
  const notice = d._notice ? '<div class="card pad" style="margin-bottom:10px;border-color:var(--warn,#b45309)">'+
    '<b class="tiny" style="letter-spacing:.02em">One-time setup</b>'+
    '<p class="tiny muted" style="margin:6px 0 0">'+esc(d._notice)+'</p></div>' : '';
  if(conn){
    return '<div class="card pad"><b>Connected</b>'+
      (conn.base_url?'<p class="mono tiny" style="margin:8px 0 0;word-break:break-all">'+esc(conn.base_url)+'</p>':'')+
      '<p class="tiny muted" style="margin:8px 0 14px">'+(conn.scopes&&conn.scopes.length?'Scopes: '+esc(conn.scopes.join(' ')):'Credentials are stored encrypted on this server.')+'</p>'+
      '<button class="btn ghost sm" id="btn-disc">Disconnect</button></div>';
  }
  if(d.auth.type==='oauth2'){
    const ready = d.configured;
    return notice+'<div class="card pad"><b>Sign in with '+esc(d.name)+'</b>'+
      '<p class="tiny muted" style="margin:6px 0 14px">You never paste an API key. Tony opens '+esc(d.name)+
      '\u2019s own sign-in page, you log in, and the account comes back connected. Tokens stay encrypted on this server.</p>'+
      '<button class="btn sm" id="btn-oauth">Connect '+esc(d.name)+'</button>'+
      (ready?'<p class="tiny" style="margin:12px 0 0;color:var(--ok)">OAuth app ready \u00b7 users just sign in</p>'
        :'<details style="margin-top:14px"><summary class="tiny" style="cursor:pointer">One-time setup: register the OAuth app</summary>'+
         '<p class="tiny muted" style="margin:10px 0">Do this once for this provider. After that, every user clicks Connect and signs in \u2014 no keys handed around. Callback URL: <span class="mono">'+
         esc(CFG.public_url)+'/oauth/callback</span></p>'+
         '<div class="field"><label>Client id</label><input class="inp" id="prov-id" autocomplete="off" placeholder="from the provider\u2019s developer console"></div>'+
         '<div class="field"><label>Client secret</label><input class="inp" id="prov-secret" type="password" autocomplete="off" placeholder="stored encrypted"></div>'+
         '<button class="btn ghost sm" id="btn-prov">Save OAuth app</button></details>')+
      '</div>';
  }
  const base = !!d.needs_base_url, token = d.auth.type!=='none';
  return notice+'<div class="card pad"><b>'+(base?'Point Tony at ':'Add your ')+esc(d.name)+'</b>'+
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
    oauth.disabled = true; oauth.textContent = 'Opening sign-in\u2026';
    try{
      const r = await api('/v1/connections/'+encodeURIComponent(d.slug)+'/start?entity_id=default', {method:'POST'});
      if(r.authorization_url) location.href = r.authorization_url;
      else { toast('Could not start'); oauth.disabled=false; oauth.textContent='Connect '+d.name }
    }catch(e){
      oauth.disabled=false; oauth.textContent='Connect '+d.name;
      if(e.status===409 && e.body){
        const b = e.body;
        S.cur = Object.assign({}, d, {auth: Object.assign({}, d.auth, {type:'key'}), _notice: b.setup_hint || b.detail});
        openApp(d.slug);
        toast(b.mode==='oauth' ? 'One-time setup needed \u2014 paste a token or let the owner register the app' : 'Paste your key to connect');
      } else { toast(e.message) }
    }
  };
  const prov = el('btn-prov');
  if(prov) prov.onclick = async()=>{
    const cid = (el('prov-id')||{}).value||'', sec = (el('prov-secret')||{}).value||'';
    if(!cid.trim()) return toast('Client id required');
    try{
      await api('/v1/account/providers/'+encodeURIComponent(d.slug), {method:'POST', body:JSON.stringify({client_id:cid.trim(), client_secret:sec.trim()})});
      toast('OAuth app saved \u2014 users can sign in now'); openApp(d.slug);
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
      '<div class="pk"><code>'+esc(k.prefix)+'…</code><span class="tiny muted">'+esc(k.name)+(k.owner?' · '+esc(k.owner):'')+'</span><span class="sp"></span>'+
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


/* ── billing ─────────────────────────────────────────────── */
const LIMIT_LABEL = {runs:'runs', connected_accounts:'accounts', entities:'identities',
                     keys:'keys', triggers:'triggers', sessions:'sessions', custom_tools:'custom tools'};
async function loadBilling(){
  try{
    const [d, plans] = await Promise.all([api('/v1/billing/me'), api('/v1/billing/plans')]);
    S.billing = d; S.plans = plans;
    const p = d.plan, u = d.usage, lim = d.limits;
    const price = p.price_ngn ? '₦'+n(p.price_ngn) : 'Free';
    const sub = d.trial ? 'Pro trial · ' + (d.days_left||0) + ' days left'
      : (p.price_ngn ? 'Renews in ' + (d.days_left||0) + ' days' : 'No card needed, ever');
    el('bl-hero').innerHTML =
      '<div class="hero"><div><div class="lbl">Current plan</div><div class="amt">'+esc(p.name)+'</div>'+
      '<div class="note">'+esc(price)+(p.price_ngn?' / month':'')+' · '+esc(sub)+'</div></div>'+
      '<span class="sp"></span>'+
      '<div style="text-align:right"><span class="badge">'+esc(d.status)+'</span>'+
      (d.cancel_at_period_end?'<div class="note" style="margin-top:6px">Cancels at period end</div>':'')+'</div></div>';
    el('bl-meters').innerHTML = Object.keys(LIMIT_LABEL).map(k=>{
      const used = u[k]||0, cap = lim[k]||0;
      if(!cap) return '';
      const pct = Math.min(100, Math.round(used/cap*100));
      const cls = pct>=90?'b':(pct>=70?'w':'');
      return '<div class="mtr"><div class="k">'+LIMIT_LABEL[k]+'</div>'+
        '<div class="v">'+n(used)+' <small>/ '+n(cap)+'</small></div>'+
        '<div class="bar '+cls+'"><i style="width:'+pct+'%"></i></div></div>';
    }).join('') +
      '<div class="mtr"><div class="k">requests / min</div><div class="v">'+n(lim.rate_per_min)+'</div>'+
      '<div class="bar"><i style="width:100%"></i></div></div>'+
      '<div class="mtr"><div class="k">history</div><div class="v">'+n(lim.retention_days)+' <small>days</small></div>'+
      '<div class="bar"><i style="width:100%"></i></div></div>';
    el('bl-plans').innerHTML = (plans.plans||[]).map(p=>{
      const cur = p.id===d.plan_id;
      const mid = p.id==='pro' ? ' mid':'';
      const price = p.price_ngn ? '₦'+n(p.price_ngn)+' <small>/month</small>' : 'Free <small>forever</small>';
      const cta = cur ? '<button class="btn ghost sm" disabled>Current plan</button>'
        : (p.id==='free' ? '<button class="btn ghost sm" onclick="toast(\'Paid time simply stops renewing; your data stays.\')">Included</button>'
        : '<button class="btn '+(p.id==='pro'?'acc':'ghost')+' sm" onclick="upgrade(\''+p.id+'\')">Choose '+esc(p.name)+'</button>');
      return '<div class="plan'+mid+'">'+(cur?'<span class="badge acc cur">now</span>':'')+
        '<h3>'+esc(p.name)+'</h3><p class="tiny muted" style="margin:0">'+esc(p.tagline)+'</p>'+
        '<div class="price">'+price+'</div><ul>'+(p.highlights||[]).map(h=>'<li>'+esc(h)+'</li>').join('')+'</ul>'+
        '<span class="sp"></span>'+cta+'</div>';
    }).join('');
    const ready = plans.payments_ready;
    el('pay-note').textContent = ready
      ? 'Card payments run through Paystack. Annual billing gives you two months free.'
      : 'No payment key on this server yet, so checkout is off. Everything else works, and a pass code unlocks a tier instantly. Owner: add PAYSTACK_SECRET_KEY in Render → Environment.';
    el('pay-actions').innerHTML = (d.plan_id!=='free' && !d.cancel_at_period_end)
      ? '<button class="btn ghost sm" onclick="cancelPlan()">Cancel at period end</button>'
      : (d.cancel_at_period_end ? '<button class="btn ghost sm" onclick="resumePlan()">Resume plan</button>' : '');
  }catch(e){ el('bl-hero').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
}
async function upgrade(plan, months){
  months = months || 1;
  try{
    const d = await api('/v1/billing/checkout', {method:'POST', body:{plan, months}});
    if(d.authorization_url){ location.href = d.authorization_url; return }
    toast('Checkout opened');
  }catch(e){
    if(e.status===503){
      let msg = e.message;
      try{ const d = JSON.parse(e.message); msg = d.error || msg }catch(_){}
      toast(msg);
    } else toast(e.message);
  }
}
async function redeemPasscode(){
  const code = (el('pc-code').value||'').trim();
  if(!code){ toast('Enter a pass code'); return }
  try{
    const d = await api('/v1/billing/passcode', {method:'POST', body:{code}});
    toast('Unlocked '+d.plan+' for '+d.days+' days'); el('pc-code').value=''; loadBilling();
  }catch(e){ toast(e.message) }
}
async function cancelPlan(){
  try{ await api('/v1/billing/cancel', {method:'POST'}); toast('Cancels at period end'); loadBilling() }
  catch(e){ toast(e.message) }
}
async function resumePlan(){
  try{ await api('/v1/billing/resume', {method:'POST'}); toast('Plan resumed'); loadBilling() }
  catch(e){ toast(e.message) }
}
async function checkBillingReturn(){
  const q = new URLSearchParams(location.search);
  if(q.get('billing')!=='verify') return;
  const ref = q.get('reference');
  if(!ref) return;
  try{
    const d = await api('/v1/billing/verify?reference='+encodeURIComponent(ref));
    toast(d.ok ? ('Payment confirmed. You are on '+d.plan+'.') : 'Payment not confirmed yet');
    if(d.ok) loadBilling();
  }catch(e){ toast(e.message) }
  history.replaceState({}, '', location.pathname + location.hash);
}

/* ── sessions ────────────────────────────────────────────── */
async function loadSessions(){
  try{
    const d = await api('/v1/sessions');
    const rows = d.sessions||[];
    el('se-count').textContent = rows.length ? rows.length + ' total' : '';
    el('se-list').innerHTML = rows.length ? rows.map(x=>{
      const dead = x.revoked || x.expired;
      const apps = (x.apps||[]).join(', ');
      const budget = x.run_limit ? (x.runs_used+'/'+x.run_limit) : 'plan';
      return '<div class="ses"><div style="min-width:0;flex:1">'+
        '<div class="row" style="gap:6px"><code class="mono tiny">'+esc(x.id)+'</code>'+
        '<span class="badge '+(dead?'bad':'ok')+'">'+(x.revoked?'revoked':(x.expired?'expired':'live'))+'</span></div>'+
        '<div class="tiny muted" style="margin-top:3px">'+esc(x.entity_id)+(x.label?' · '+esc(x.label):'')+
        ' · apps: '+esc(apps||'all')+' · tiers: '+esc((x.tiers||[]).join(', '))+' · runs: '+esc(budget)+'</div></div>'+
        '<button class="btn ghost sm" data-c="'+esc(x.id)+'">Copy id</button>'+
        (dead?'':'<button class="btn ghost sm" data-x="'+esc(x.id)+'">Revoke</button>')+'</div>';
    }).join('') : '<div class="empty">No sessions yet. Create one to scope an agent to a single end-user.</div>';
    el('se-list').querySelectorAll('[data-c]').forEach(b=>b.onclick=()=>{
      navigator.clipboard.writeText(b.dataset.c).then(()=>{ b.textContent='Copied'; setTimeout(()=>b.textContent='Copy id',1400) });
    });
    el('se-list').querySelectorAll('[data-x]').forEach(b=>b.onclick=async()=>{
      await api('/v1/sessions/'+b.dataset.x, {method:'DELETE'}); toast('Session revoked'); loadSessions();
    });
  }catch(e){ el('se-list').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
}
async function createSession(){
  const tiers = [];
  if(el('se-t-read').checked) tiers.push('read');
  if(el('se-t-write').checked) tiers.push('write');
  if(el('se-t-dest').checked) tiers.push('destructive');
  if(!tiers.length){ toast('Pick at least one tier'); return }
  const body = {entity_id:(el('se-entity').value||'default').trim(), label:el('se-label').value.trim(),
                apps:(el('se-apps').value||'').split(',').map(s=>s.trim()).filter(Boolean),
                tiers, ttl_hours:parseInt(el('se-ttl').value||'24',10),
                run_limit:parseInt(el('se-limit').value||'0',10)};
  try{
    const d = await api('/v1/sessions', {method:'POST', body});
    toast('Session ready'); el('se-entity').value=''; el('se-label').value=''; el('se-apps').value='';
    loadSessions();
    if(d.how_to_use) setTimeout(()=>toast('Attach X-Tony-Session: '+d.id), 1200);
  }catch(e){ toast(e.message) }
}


/* ── Tony assistant ─────────────────────────────────────── */
let ASK_HISTORY = [];
function toggleAsk(force){
  const a = el('ask'), open = force===undefined ? !a.classList.contains('on') : force;
  a.classList.toggle('on', open); a.setAttribute('aria-hidden', String(!open));
  el('ask-fab').style.display = open ? 'none' : 'flex';
  if(open) setTimeout(()=>el('ask-q').focus(), 60);
}
function askBubble(role, text){
  const d = document.createElement('div');
  d.className = 'ask-msg ' + role; d.textContent = text;
  el('ask-body').appendChild(d); el('ask-body').scrollTop = el('ask-body').scrollHeight;
  return d;
}
async function askTony(text){
  text = (text||'').trim(); if(!text) return;
  if(!el('ask').classList.contains('on')) toggleAsk(true);
  askBubble('me', text); ASK_HISTORY.push({role:'user', content:text});
  const t = askBubble('think', 'Reading your workspace…');
  try{
    const d = await api('/v1/assistant', {method:'POST', body:{message:text, history:ASK_HISTORY.slice(-6)}});
    t.remove();
    askBubble('bot', d.answer); ASK_HISTORY.push({role:'assistant', content:d.answer});
    el('ask-quick').innerHTML = (d.suggestions||[]).map(q=>'<button></button>').join('');
    el('ask-quick').querySelectorAll('button').forEach((b,i)=>{b.textContent=(d.suggestions||[])[i];b.onclick=()=>askTony(b.textContent)});
  }catch(e){ t.textContent = 'That request failed: ' + e.message; t.className='ask-msg bot' }
}
function sendAsk(ev){
  ev.preventDefault(); const q = el('ask-q'); const v = q.value; q.value=''; askTony(v); return false;
}

/* ── ecosystem ──────────────────────────────────────────── */
async function loadEcosystem(){
  try{
    const [sum, use, rat, rev] = await Promise.all([
      api('/v1/ecosystem/summary'), api('/v1/stats/usage?days=30'),
      api('/v1/ratings'), api('/v1/revenue')]);
    el('ec-meters').innerHTML =
      '<div class="mtr"><div class="k">apps</div><div class="v">'+n(sum.apps)+'</div><div class="bar"><i style="width:100%"></i></div></div>'+
      '<div class="mtr"><div class="k">actions</div><div class="v">'+n(sum.actions)+'</div><div class="bar"><i style="width:100%"></i></div></div>'+
      '<div class="mtr"><div class="k">avg rating</div><div class="v">'+(sum.ratings.average||0)+' <small>/ 5</small></div><div class="bar"><i style="width:'+Math.round((sum.ratings.average||0)/5*100)+'%"></i></div></div>'+
      '<div class="mtr"><div class="k">runs all time</div><div class="v">'+n(sum.runs_all_time)+'</div><div class="bar"><i style="width:100%"></i></div></div>';

    const top = (use.by_app||[]).slice(0,6);
    const max = Math.max(1, ...top.map(r=>r.runs));
    el('ec-usage').innerHTML = top.length ? top.map(r=>
      '<div class="ec-row"><span class="mono" style="min-width:110px">'+esc(r.app)+'</span>'+
      '<span class="ec-bar"><i style="width:'+Math.round(r.runs/max*100)+'%"></i></span>'+
      '<b style="font-size:12px">'+n(r.runs)+'</b><span class="tiny muted">'+r.avg_latency_ms+'ms</span></div>'
    ).join('') : '<div class="empty">Send your first call and this fills in.</div>';

    const apps = (rat.apps||[]).slice(0,6);
    el('ec-ratings').innerHTML = apps.length ? apps.map(a=>
      '<div class="ec-row"><span class="mono" style="min-width:110px">'+esc(a.app)+'</span>'+
      '<span class="ec-bar"><i style="width:'+Math.round(a.average/5*100)+'%"></i></span>'+
      '<b style="font-size:12px">'+a.average.toFixed(1)+'</b><span class="tiny muted">'+a.ratings+' votes</span></div>'
    ).join('') : '<div class="empty">No ratings yet.</div>';

    el('ec-rev-state').textContent = rev.eligible ? 'eligible' : 'not eligible';
    const st = rev.statements||[];
    el('ec-revenue').innerHTML =
      '<div class="ec-row"><span class="mono">pending</span><span class="sp"></span><b>₦'+n(rev.pending_ngn)+'</b></div>'+
      '<div class="ec-row"><span class="mono">paid</span><span class="sp"></span><b>₦'+n(rev.paid_ngn)+'</b></div>'+
      (st.length ? st.map(x=>'<div class="ec-row">'+esc(x.period)+' · '+esc(x.app||'—')+
        '<span class="sp"></span><span class="badge">'+esc(x.status)+'</span></div>').join('')
        : '<p class="tiny muted" style="margin:8px 0 0">'+esc(rev.policy)+'</p>');

    el('ec-security').innerHTML =
      'Credentials: AES-256-GCM at rest, decrypted per call.<br>'+
      'API keys: stored as hashes, bound to your workspace.<br>'+
      'Writes: explicit approval with a preview and a full run log.<br>'+
      'Sessions: app allowlist, tier ceiling, TTL, own run budget.';
  }catch(e){ el('ec-meters').innerHTML='<div class="empty">'+esc(e.message)+'</div>' }
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


def _firebase_scripts() -> str:
    if not os.getenv("FIREBASE_API_KEY"):
        return ""
    return ('<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>'
            '<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js"></script>')


def _google_script(client_id: str) -> str:
    if not client_id:
        return ""
    return ('<script src="https://accounts.google.com/gsi/client" async defer></script>')


def console_html(user: Any = None) -> str:
    import json

    cfg = {"google_client_id": settings.google_client_id, "demo_open": settings.demo_open,
           "firebase": {"api_key": (os.getenv("FIREBASE_API_KEY") or ""),
                        "auth_domain": (os.getenv("FIREBASE_AUTH_DOMAIN") or f"{(os.getenv('FIREBASE_PROJECT_ID') or 'ominiassist-ai')}.firebaseapp.com"),
                        "project_id": (os.getenv("FIREBASE_PROJECT_ID") or "ominiassist-ai")},
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

      <!-- sessions -->
      <section class="pg" id="p-sessions">
        <div class="hd"><div><h1>Sessions</h1><p>One per end-user: pinned identity, app allowlist, tier limit, own run budget.</p></div></div>
        <div class="grid" style="grid-template-columns:1fr;gap:12px">
          <div class="card pad">
            <div class="row wrap" style="gap:8px;align-items:flex-end">
              <div class="field" style="flex:1;min-width:150px;margin:0"><label>End-user identity</label>
                <input class="inp" id="se-entity" placeholder="user_42" autocomplete="off"></div>
              <div class="field" style="flex:1;min-width:150px;margin:0"><label>Label</label>
                <input class="inp" id="se-label" placeholder="Support bot for Ada" autocomplete="off"></div>
            </div>
            <div class="field" style="margin-top:11px"><label>Allowed apps<span class="hint">comma separated, empty = every app</span></label>
              <input class="inp" id="se-apps" placeholder="gmail, slack" autocomplete="off"></div>
            <div class="row wrap" style="gap:14px;margin:2px 0 12px">
              <label class="tiny row" style="gap:6px"><input type="checkbox" id="se-t-read" checked> read</label>
              <label class="tiny row" style="gap:6px"><input type="checkbox" id="se-t-write" checked> write</label>
              <label class="tiny row" style="gap:6px"><input type="checkbox" id="se-t-dest"> destructive</label>
              <span class="sp"></span>
              <label class="tiny row" style="gap:6px">TTL <input class="inp" id="se-ttl" value="24" style="width:64px;height:32px"> h</label>
              <label class="tiny row" style="gap:6px">budget <input class="inp" id="se-limit" value="0" style="width:88px;height:32px"></label>
            </div>
            <button class="btn acc" onclick="createSession()">Create session</button>
            <p class="tiny muted" style="margin:10px 0 0">Send <code class="mono">X-Tony-Session: &lt;id&gt;</code> on any call. Your workspace key stays on your server.</p>
          </div>
          <div class="card pad"><div class="row" style="margin-bottom:8px"><b style="font-size:14px">Active</b>
            <span class="sp"></span><span class="tiny muted" id="se-count"></span></div>
            <div id="se-list"><div class="empty">Loading…</div></div></div>
        </div>
      </section>

      <!-- billing -->
      <section class="pg" id="p-billing">
        <div class="hd"><div><h1>Billing</h1><p>Free covers a real product. Upgrade only when volume says so.</p></div></div>
        <div id="bl-hero"></div>
        <div class="meters" id="bl-meters"></div>
        <div class="plans" id="bl-plans"></div>
        <div class="grid" style="grid-template-columns:1fr;gap:12px">
          <div class="card pad">
            <b style="font-size:14px">Pass code</b>
            <p class="tiny muted" style="margin:6px 0 10px">Owner-issued codes unlock a tier with no card.</p>
            <div class="row wrap" style="gap:8px">
              <input class="inp" id="pc-code" placeholder="TONY-…" style="flex:1;min-width:150px" autocomplete="off">
              <button class="btn sm" onclick="redeemPasscode()">Apply</button>
            </div>
          </div>
          <div class="card pad">
            <b style="font-size:14px">Payments</b>
            <p class="tiny muted" id="pay-note" style="margin:6px 0 10px">Checking…</p>
            <div class="row wrap" style="gap:8px" id="pay-actions"></div>
          </div>
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
      <section class="pg" id="p-agent">
        <div class="hd"><div><h1>Agent</h1><p>Describe the outcome. Tony plans across apps, runs the calls, and shows what each one returned.</p></div>
          <span class="pill" id="ag-mode">writes off</span></div>
        <div class="grid" style="grid-template-columns:1.1fr .9fr;gap:12px">
          <div class="card pad">
            <b style="font-size:14px">Goal</b>
            <textarea id="ag-goal" class="inp" rows="5" style="width:100%;margin-top:10px;resize:vertical;font-family:var(--mono);font-size:12.5px"
              placeholder="summarise the top hacker news stories right now"></textarea>
            <div class="row" style="margin-top:10px;gap:8px;flex-wrap:wrap">
              <button class="btn acc" id="ag-run">Run</button>
              <button class="btn" id="ag-writes">Allow writes</button>
              <button class="btn" id="ag-example">Try an example</button>
            </div>
            <p class="tiny muted" style="margin-top:10px">Every call is recorded in Activity, including failures.</p>
          </div>
          <div class="card pad">
            <div class="row"><b style="font-size:14px">Answer</b><span class="sp"></span><span class="tiny muted" id="ag-meta"></span></div>
            <div id="ag-answer" style="margin-top:10px;font-size:13.5px;line-height:1.6">Nothing has run yet.</div>
          </div>
        </div>
        <div class="card pad" style="margin-top:12px">
          <div class="row"><b style="font-size:14px">Steps</b><span class="sp"></span><span class="tiny muted">app.action · status · latency</span></div>
          <div id="ag-steps" style="margin-top:8px"><div class="empty">No calls yet.</div></div>
        </div>
      </section>
      <section class="pg" id="p-ecosystem">
        <div class="hd"><div><h1>Ecosystem</h1><p>Ratings, changelogs, security verdicts, usage and builder revenue. The parts a gateway normally hides.</p></div></div>
        <div class="meters" id="ec-meters"><div class="empty">Loading…</div></div>
        <div class="grid" style="grid-template-columns:1fr;gap:12px">
          <div class="card pad"><div class="row" style="margin-bottom:10px"><b style="font-size:14px">Most used apps</b>
            <span class="sp"></span><span class="tiny muted">last 30 days</span></div>
            <div id="ec-usage"><div class="empty">No runs yet.</div></div></div>
          <div class="card pad"><div class="row" style="margin-bottom:10px"><b style="font-size:14px">Community ratings</b>
            <span class="sp"></span><a class="tiny" href="/docs" style="color:var(--accent)">Rate an app</a></div>
            <div id="ec-ratings"><div class="empty">No ratings yet. Be the first.</div></div></div>
          <div class="card pad"><div class="row" style="margin-bottom:10px"><b style="font-size:14px">Builder revenue</b>
            <span class="sp"></span><span class="badge" id="ec-rev-state">—</span></div>
            <div id="ec-revenue"><div class="empty">Publish an integration to earn from its runs.</div></div></div>
          <div class="card pad"><div class="row" style="margin-bottom:10px"><b style="font-size:14px">Security posture</b>
            <span class="sp"></span><span class="tiny muted">encryption · approval gate</span></div>
            <div id="ec-security" class="tiny muted" style="line-height:1.7"></div></div>
        </div>
      </section>

    </main>
  </div>

  <button class="ask-fab" id="ask-fab" onclick="toggleAsk()" aria-label="Ask Tony">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 5h16v11H8l-4 4z"/><path d="M8.5 9.5h7M8.5 12.5h4"/></svg>
    <span>Ask Tony</span>
  </button>
  <aside class="ask" id="ask" aria-hidden="true">
    <div class="ask-h">
      <span class="ask-dot"></span>
      <div style="flex:1;min-width:0"><b>Tony assistant</b><span>Answers about Tony only</span></div>
      <button class="ask-x" onclick="toggleAsk(false)" aria-label="Close">×</button>
    </div>
    <div class="ask-body" id="ask-body">
      <div class="ask-msg bot">Ask me about plans, quotas, connecting an app, keys, sessions, custom tools, MCP, SDKs or an error code. I read your live usage, so the numbers are yours.</div>
    </div>
    <div class="ask-quick" id="ask-quick">
      <button onclick="askTony('How many runs do I have left?')">Runs left</button>
      <button onclick="askTony('How do I connect an app without an API key?')">Connect an app</button>
      <button onclick="askTony('What does Pro add?')">Plans</button>
      <button onclick="askTony('How do I use this in Claude?')">Claude / MCP</button>
    </div>
    <form class="ask-in" onsubmit="return sendAsk(event)">
      <input id="ask-q" placeholder="Ask about Tony…" autocomplete="off" maxlength="1200">
      <button type="submit" aria-label="Send">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 12h15M13 6l6 6-6 6"/></svg>
      </button>
    </form>
  </aside>

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
{_firebase_scripts()}
{_google_script(settings.google_client_id)}
<script>{js}</script>
</body></html>"""
