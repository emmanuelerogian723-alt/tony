"""Tony's front door: an editorial, printed-plate landing page.

No framework, no build step. Everything below is a single HTML document plus
system/Google fonts, hand-drawn SVG and about 120 lines of vanilla JS.
"""
from __future__ import annotations

import math

LANDING_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700;1,9..144,600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root{
  --paper:#F3F0E9; --paper-2:#EAE6DB; --paper-3:#E2DDD0;
  --ink:#0E0E0C; --ink-2:#1B1B16; --muted:#6E6B61; --muted-2:#8C887C;
  --line:rgba(14,14,12,.13); --line-2:rgba(14,14,12,.26); --line-3:rgba(14,14,12,.5);
  --signal:#D9502A; --signal-ink:#B23F1F; --signal-soft:#F6DCD1;
  --max:1180px; --gut:clamp(18px,4vw,44px);
  --serif:'Fraunces',Georgia,'Times New Roman',serif;
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Inter,system-ui,sans-serif;
  --ease:cubic-bezier(.22,.68,.16,1);
}
*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;overflow-x:hidden;
}
/* paper grain: a real texture, not a gradient */
body::before{
  content:"";position:fixed;inset:0;z-index:9999;pointer-events:none;opacity:.42;
  mix-blend-mode:multiply;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.82' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='.14'/%3E%3C/svg%3E");
}
a{color:inherit;text-decoration:none}
img,svg{display:block;max-width:100%}
button{font:inherit;color:inherit;background:none;border:none;cursor:pointer}
::selection{background:var(--ink);color:var(--paper)}

.wrap{max-width:var(--max);margin:0 auto;padding:0 var(--gut)}
.mono{font-family:var(--mono);font-size:11.5px;letter-spacing:.16em;text-transform:uppercase}
.rule{height:1px;background:var(--line);width:100%}

/* ---------- nav ---------- */
.nav{position:sticky;top:0;z-index:60;background:rgba(243,240,233,.86);
  backdrop-filter:saturate(140%) blur(14px);border-bottom:1px solid var(--line)}
.nav-in{display:flex;align-items:center;gap:26px;height:64px}
.brand{display:flex;align-items:center;gap:10px}
.brand .mark{width:26px;height:26px;border-radius:8px;overflow:hidden;flex:none;
  box-shadow:0 1px 0 rgba(14,14,12,.18),0 2px 6px rgba(14,14,12,.12)}
.brand b{font-family:var(--serif);font-size:19px;font-weight:700;letter-spacing:-.02em}
.brand span{font-family:var(--mono);font-size:9.5px;letter-spacing:.18em;color:var(--muted);
  border:1px solid var(--line-2);border-radius:3px;padding:2px 5px;transform:translateY(-1px)}
.nav-links{display:flex;gap:22px;margin-left:auto}
.nav-links a{font-family:var(--mono);font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--ink-2);padding:6px 0;position:relative}
.nav-links a::after{content:"";position:absolute;left:0;right:100%;bottom:0;height:1px;background:var(--ink);
  transition:right .3s var(--ease)}
.nav-links a:hover::after{right:0}
.nav-cta{display:flex;align-items:center;gap:10px}

/* ---------- buttons ---------- */
.btn{display:inline-flex;align-items:center;gap:9px;height:42px;padding:0 20px;
  background:var(--ink);color:var(--paper);border:1px solid var(--ink);border-radius:2px;
  font-family:var(--mono);font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;
  transition:transform .25s var(--ease),box-shadow .25s var(--ease),background .25s var(--ease)}
.btn:hover{transform:translate(-2px,-2px);box-shadow:4px 4px 0 var(--signal)}
.btn.solid-signal:hover{box-shadow:4px 4px 0 var(--ink)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line-2)}
.btn.ghost:hover{background:var(--paper-2);box-shadow:4px 4px 0 rgba(14,14,12,.12)}
.btn.signal{background:var(--signal);border-color:var(--signal);color:#fff}
.btn.sm{height:34px;padding:0 14px;font-size:10.5px}

/* ---------- hero ---------- */
.hero{position:relative;padding:clamp(24px,4.6vw,68px) 0 0}
.hero-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:clamp(24px,4vw,56px);align-items:center}
.kicker{display:flex;align-items:center;gap:10px;color:var(--muted);margin-bottom:22px}
.kicker .bar{width:34px;height:1px;background:var(--line-3)}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(37px,7.4vw,104px);line-height:.95;
  letter-spacing:-.035em;margin:0 0 26px;font-variation-settings:"SOFT" 0,"WONK" 1}
h1 em{font-style:italic;color:var(--signal);font-weight:600}
h1 .thin{display:block;color:var(--muted-2);font-size:.44em;letter-spacing:-.01em;font-style:italic;
  margin-top:.22em}
.lede{font-size:clamp(15.5px,1.35vw,18px);line-height:1.6;color:var(--ink-2);max-width:33em;margin:0 0 clamp(20px,3vw,30px)}
.lede b{font-weight:640}
.cta-row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.cta-note{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;color:var(--muted);text-transform:uppercase}

/* live counters */
.counters{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--line-2);
  border-bottom:1px solid var(--line);margin-top:clamp(34px,4vw,52px)}
.counters div{padding:16px 14px 15px;border-right:1px solid var(--line)}
.counters div:last-child{border-right:0}
.counters b{font-family:var(--serif);font-size:clamp(24px,2.7vw,34px);font-weight:600;letter-spacing:-.03em;
  display:block;line-height:1;font-variant-numeric:tabular-nums}
.counters span{font-family:var(--mono);font-size:9.5px;letter-spacing:.15em;text-transform:uppercase;
  color:var(--muted);display:block;margin-top:8px}

/* the port diagram */
.port{position:relative;aspect-ratio:1/1;width:100%;max-width:520px;margin-inline:auto}
.port svg{width:100%;height:100%}
.port .ring-a{animation:spin 68s linear infinite;transform-origin:260px 260px}
.port .ring-b{animation:spin 44s linear infinite reverse;transform-origin:260px 260px}
.port .pulse{animation:portpulse 3.4s ease-in-out infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes portpulse{0%,100%{opacity:.25}50%{opacity:.85}}
.port .tick{stroke:var(--line-3)}
.port text{font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;fill:var(--muted);
  text-transform:uppercase}
.port .node{fill:var(--paper);stroke:var(--ink);stroke-width:1.2}
.port .live{fill:var(--signal)}

/* ---------- ticker ---------- */
.ticker{margin-top:clamp(30px,4vw,52px);border-top:1px solid var(--line-2);border-bottom:1px solid var(--line-2);
  overflow:hidden;background:var(--paper-2);position:relative}
.ticker::before,.ticker::after{content:"";position:absolute;top:0;bottom:0;width:80px;z-index:2;pointer-events:none}
.ticker::before{left:0;background:linear-gradient(90deg,var(--paper-2),transparent)}
.ticker::after{right:0;background:linear-gradient(270deg,var(--paper-2),transparent)}
.ticker-track{display:flex;gap:0;width:max-content;animation:slide 60s linear infinite}
.ticker:hover .ticker-track{animation-play-state:paused}
.ticker span{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);padding:11px 18px;border-right:1px solid var(--line);white-space:nowrap}
.ticker span.hot{color:var(--signal-ink)}
@keyframes slide{to{transform:translateX(-50%)}}

/* ---------- sections ---------- */
section{position:relative}
.sec{padding:clamp(44px,7vw,110px) 0}
.sec-head{display:grid;grid-template-columns:auto 1fr;gap:clamp(18px,3vw,40px);align-items:start;
  margin-bottom:clamp(30px,4vw,52px)}
.sec-num{font-family:var(--mono);font-size:11px;letter-spacing:.2em;color:var(--signal-ink);
  padding-top:10px;min-width:66px}
h2{font-family:var(--serif);font-weight:600;font-size:clamp(30px,4.3vw,54px);line-height:1.02;
  letter-spacing:-.03em;margin:0 0 14px;max-width:20em}
h2 em{font-style:italic;color:var(--signal)}
.sec-head p{margin:0;color:var(--muted);max-width:44em;font-size:15.5px}

/* problem plates */
.plates{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border:1px solid var(--line-2)}
.plate{padding:clamp(22px,2.6vw,34px);border-right:1px solid var(--line-2);position:relative;
  background:var(--paper);transition:background .3s var(--ease)}
.plate:last-child{border-right:0}
.plate:hover{background:var(--paper-2)}
.plate .n{font-family:var(--mono);font-size:10px;letter-spacing:.2em;color:var(--signal-ink)}
.plate h3{font-family:var(--serif);font-size:clamp(20px,2vw,26px);font-weight:600;letter-spacing:-.02em;
  margin:14px 0 10px}
.plate p{margin:0;color:var(--muted);font-size:14.5px;line-height:1.6}
.plate .glyph{position:absolute;top:20px;right:20px;opacity:.5}

/* catalogue search */
.search-shell{border:1px solid var(--line-2);background:var(--paper);box-shadow:8px 8px 0 var(--paper-3)}
.search-top{display:flex;align-items:center;gap:14px;padding:16px 18px;border-bottom:1px solid var(--line)}
.search-top svg{flex:none}
.search-top input{flex:1;border:0;background:transparent;font-family:var(--mono);font-size:14px;
  letter-spacing:.02em;outline:none;color:var(--ink);min-width:0}
.search-top input::placeholder{color:var(--muted-2)}
.search-meta{font-family:var(--mono);font-size:10px;letter-spacing:.13em;text-transform:uppercase;
  color:var(--muted);white-space:nowrap}
.results{max-height:398px;overflow:auto}
.row{display:grid;grid-template-columns:34px 1fr auto auto;gap:14px;align-items:center;
  padding:13px 18px;border-bottom:1px solid var(--line);transition:background .2s var(--ease)}
.row:last-child{border-bottom:0}
.row:hover{background:var(--paper-2)}
.row .ic{width:26px;height:26px;border-radius:6px;border:1px solid var(--line);display:grid;place-items:center;
  font-family:var(--mono);font-size:10px;font-weight:600;background:var(--paper-2);color:var(--ink-2)}
.row .nm{font-weight:600;font-size:14.5px;letter-spacing:-.01em}
.row .cat{font-family:var(--mono);font-size:9.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted)}
.tag{font-family:var(--mono);font-size:9px;letter-spacing:.13em;text-transform:uppercase;padding:4px 7px;
  border:1px solid var(--line-2);border-radius:2px;color:var(--ink-2);white-space:nowrap}
.tag.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.tag.act{background:var(--signal-soft);border-color:rgba(217,80,42,.35);color:var(--signal-ink)}
.row .acts{font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:.08em;white-space:nowrap}
.empty{padding:34px 18px;color:var(--muted);font-family:var(--mono);font-size:11.5px;letter-spacing:.1em;
  text-transform:uppercase}

/* layer bars */
.layers{border-top:1px solid var(--line-2)}
.layer{display:grid;grid-template-columns:150px 1fr 92px;gap:18px;align-items:center;padding:18px 0;
  border-bottom:1px solid var(--line)}
.layer .lname{font-weight:620;font-size:14.5px}
.layer .lname small{display:block;font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);margin-top:3px;font-weight:400}
.bar{height:26px;background:repeating-linear-gradient(90deg,var(--line) 0 1px,transparent 1px 9px);position:relative}
.bar i{position:absolute;left:0;top:0;bottom:0;background:var(--ink);width:0;
  transition:width 1.1s var(--ease)}
.bar i.signal{background:var(--signal)}
.bar i.grey{background:var(--ink-2);opacity:.55}
.layer .lval{font-family:var(--mono);font-size:12px;text-align:right;letter-spacing:.06em;color:var(--ink-2)}

/* protocol panel (dark) */
.dark{background:var(--ink);color:var(--paper);position:relative;overflow:hidden}
.dark::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;
  background-image:linear-gradient(rgba(243,240,233,.055) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(243,240,233,.055) 1px,transparent 1px);
  background-size:56px 56px}
.dark h2{color:var(--paper)}
.dark h2 em{color:#F0835C}
.dark .sec-head p{color:rgba(243,240,233,.62)}
.dark .sec-num{color:#F0835C}
.tabs{display:flex;gap:0;border-bottom:1px solid rgba(243,240,233,.16);flex-wrap:wrap}
.tabs button{font-family:var(--mono);font-size:10.5px;letter-spacing:.15em;text-transform:uppercase;
  color:rgba(243,240,233,.55);padding:12px 18px 13px;border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs button[aria-selected="true"]{color:var(--paper);border-bottom-color:var(--signal)}
.code{position:relative;background:#111110;border:1px solid rgba(243,240,233,.14);border-top:0}
.code pre{margin:0;padding:22px 20px;overflow:auto;font-family:var(--mono);font-size:12.5px;line-height:1.75;
  color:#D6D2C7;max-height:340px}
.code .k{color:#F0835C}
.code .s{color:#9BD1A8}
.code .c{color:#6E6B61}
.copy{position:absolute;top:10px;right:10px;font-family:var(--mono);font-size:9.5px;letter-spacing:.13em;
  text-transform:uppercase;color:rgba(243,240,233,.7);border:1px solid rgba(243,240,233,.2);padding:5px 9px;
  border-radius:2px;background:#111110}
.copy:hover{color:var(--paper);border-color:rgba(243,240,233,.5)}
.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin-top:34px;
  border:1px solid rgba(243,240,233,.16)}
.flow div{padding:20px 18px;border-right:1px solid rgba(243,240,233,.16);position:relative}
.flow div:last-child{border-right:0}
.flow b{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;
  color:#F0835C;margin-bottom:8px}
.flow p{margin:0;font-size:13.5px;color:rgba(243,240,233,.72);line-height:1.55}

/* comparison */
.cmp{width:100%;border-collapse:collapse;font-size:14.5px}
.cmp th,.cmp td{text-align:left;padding:15px 16px;border-bottom:1px solid var(--line);vertical-align:top}
.cmp thead th{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--muted);border-bottom:1px solid var(--line-2);padding-bottom:12px}
.cmp thead th.us{color:var(--ink);font-family:var(--serif);font-size:15px;letter-spacing:0;text-transform:none}
.cmp tbody th{font-weight:520;color:var(--muted);font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;
  text-transform:uppercase;width:23%}
.cmp td{color:var(--muted);width:38%}
.cmp td.us{color:var(--ink);font-weight:560;background:rgba(217,80,42,.045);
  border-left:1px solid rgba(217,80,42,.18);border-right:1px solid rgba(217,80,42,.18)}
.cmp tr:last-child td,.cmp tr:last-child th{border-bottom:0}

/* features */
.feats{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--line-2);
  border-left:1px solid var(--line)}
.feat{padding:24px 22px 26px;border-right:1px solid var(--line);border-bottom:1px solid var(--line);
  background:var(--paper);transition:background .3s var(--ease),transform .3s var(--ease)}
.feat:hover{background:var(--paper-2);transform:translateY(-2px)}
.feat .n{font-family:var(--mono);font-size:9.5px;letter-spacing:.18em;color:var(--signal-ink)}
.feat .g{margin:16px 0 14px;height:30px;color:var(--ink)}
.feat h3{font-size:15px;font-weight:640;letter-spacing:-.01em;margin:0 0 7px}
.feat p{margin:0;font-size:13.5px;color:var(--muted);line-height:1.55}

/* install */
.install{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--line-2)}
.install > div{padding:clamp(22px,3vw,34px)}
.install > div:first-child{border-right:1px solid var(--line-2);background:var(--paper-2)}
.cmd{display:flex;align-items:center;gap:12px;background:var(--ink);color:#EDE9E0;padding:13px 15px;
  font-family:var(--mono);font-size:12.5px;margin-bottom:10px;overflow:auto;white-space:nowrap}
.cmd i{color:#F0835C;font-style:normal}
.cmd b{color:#8C887C;font-weight:400}

/* footer */
.foot{border-top:1px solid var(--line-2);padding:clamp(34px,5vw,58px) 0 30px;background:var(--paper-2)}
.foot-top{display:flex;justify-content:space-between;gap:30px;flex-wrap:wrap;align-items:flex-end}
.wordmark{font-family:var(--serif);font-weight:600;font-size:clamp(56px,11vw,132px);line-height:.8;
  letter-spacing:-.05em;color:transparent;-webkit-text-stroke:1px rgba(14,14,12,.35)}
.foot-links{display:flex;gap:26px;flex-wrap:wrap}
.foot-links a{font-family:var(--mono);font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:var(--ink-2)}
.foot-links a:hover{color:var(--signal-ink)}
.foot-bot{display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;margin-top:26px;padding-top:18px;
  border-top:1px solid var(--line);font-family:var(--mono);font-size:10px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted)}

/* reveal */
.rise{opacity:0;transform:translateY(16px);transition:opacity .7s var(--ease),transform .7s var(--ease)}
.rise.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  .rise{opacity:1;transform:none}
  .ticker-track,.port .ring-a,.port .ring-b,.port .pulse{animation:none!important}
  html{scroll-behavior:auto}
}

@media (max-width:1080px){
  .nav-in{gap:18px}
  .nav-links{gap:16px}
}
@media (max-width:940px){
  .hero-grid{grid-template-columns:1fr;gap:clamp(22px,4vw,34px)}
  .port{max-width:min(360px,72vw);order:2;margin-top:4px}
  .plates{grid-template-columns:1fr}
  .plate{border-right:0;border-bottom:1px solid var(--line-2)}
  .plate:last-child{border-bottom:0}
  .feats{grid-template-columns:1fr 1fr}
  .flow{grid-template-columns:1fr 1fr}
  .flow div:nth-child(2){border-right:0}
  .flow div:nth-child(n+3){border-top:1px solid rgba(243,240,233,.16)}
  .install{grid-template-columns:1fr}
  .install > div:first-child{border-right:0;border-bottom:1px solid var(--line-2)}
  .nav-links{display:none}
  .layer{grid-template-columns:110px 1fr 74px}
  .cmp{font-size:13.5px}
}
@media (max-width:760px){
  .nav-in{height:58px;gap:12px}
  .brand b{font-size:17px}
  .nav-cta .btn.ghost{display:none}
  h1{font-size:clamp(34px,9.6vw,58px);line-height:.98}
  h1 .thin{font-size:.5em;margin-top:.5em}
  .hero{padding-top:20px}
  .hero-grid{gap:20px}
  .port{max-width:min(300px,64vw);order:2}
  .kicker{font-size:10px;letter-spacing:.14em}
  .lede{max-width:none}
  .cta-row{gap:10px}
  .cta-row .btn{flex:1 1 auto;justify-content:center}
  .cta-note{flex-basis:100%;text-align:center;margin-top:2px}
  .counters{grid-template-columns:1fr 1fr;margin-top:26px}
  .counters div:nth-child(2n){border-right:0}
  .counters div:nth-child(-n+2){border-bottom:1px solid var(--line)}
  .sec-head{grid-template-columns:1fr;margin-bottom:24px}
  .sec-num{padding-top:0}
  .feats{grid-template-columns:1fr}
  .feat{border-right:0}
  .flow{grid-template-columns:1fr}
  .flow div{border-right:0;border-bottom:1px solid rgba(243,240,233,.16)}
  .flow div:last-child{border-bottom:0}
  .layer{grid-template-columns:1fr auto;gap:8px 12px}
  .layer .lval{grid-column:2}
  .cmp thead th:first-child,.cmp tbody th{display:none}
  .cmp td{width:50%;padding:12px 10px}
  .search-top{padding:13px 14px;gap:10px}
  .row{grid-template-columns:26px 1fr auto;gap:10px;padding:12px 14px}
  .row .acts{display:none}
  .foot-links{flex-wrap:wrap;gap:10px 16px}
  .cmd{font-size:11.5px}
}
@media (max-width:430px){
  .wrap{padding:0 16px}
  h1{font-size:clamp(31px,10.4vw,44px)}
  .cta-row .btn{width:100%}
  .counters b{font-size:22px}
  .counters div{padding:13px 10px}
  .sec-num{min-width:0}
  .wordmark{font-size:clamp(44px,13vw,72px)}
  .ticker span{font-size:10px;padding:9px 13px}
}
@media (max-height:560px) and (orientation:landscape){
  .hero{padding-top:16px}
  .port{display:none}
  h1{font-size:clamp(28px,6vw,40px)}
}
"""


# ---------------------------------------------------------------- drawings

def _port_drawing() -> str:
    """A drafting-table 'port': rings, graduated ticks, three orbits, the mark."""
    import math as _m
    ticks = []
    for i in range(72):
        ang = _m.radians(i * 5)
        r1 = 236
        r2 = 248 if i % 6 == 0 else 242
        x1, y1 = 260 + r1 * _m.cos(ang), 260 + r1 * _m.sin(ang)
        x2, y2 = 260 + r2 * _m.cos(ang), 260 + r2 * _m.sin(ang)
        ticks.append(f'<line class="tick" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke-width="{1.2 if i%6==0 else .7}"/>')
    orbits = []
    for ang, label, hot in ((-58, "agents", True), (62, "apps", False), (168, "actions", False)):
        a = _m.radians(ang)
        x, y = 260 + 196 * _m.cos(a), 260 + 196 * _m.sin(a)
        orbits.append(f'<circle class="node{" live" if hot else ""}" cx="{x:.1f}" cy="{y:.1f}" r="5.5"/>')
        lx = 260 + 196 * _m.cos(a) + (12 if _m.cos(a) >= 0 else -12)
        anchor = "start" if _m.cos(a) >= 0 else "end"
        orbits.append(f'<text x="{lx:.1f}" y="{y + 24:.1f}" text-anchor="{anchor}">{label}</text>')
    return f"""
<svg viewBox="0 0 520 520" aria-hidden="true">
  <defs>
    <marker id="ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
      <path d="M0 0 L10 5 L0 10 z" fill="#8C887C"/>
    </marker>
  </defs>
  <circle class="pulse" cx="260" cy="260" r="168" fill="none" stroke="#D9502A" stroke-width="1" stroke-dasharray="2 10" opacity=".35"/>
  <g class="ring-a">{''.join(ticks)}</g>
  <circle cx="260" cy="260" r="214" fill="none" stroke="rgba(14,14,12,.18)" stroke-width="1"/>
  <circle cx="260" cy="260" r="196" fill="none" stroke="rgba(14,14,12,.10)" stroke-width="1" stroke-dasharray="1 7"/>
  <g class="ring-b">
    <circle cx="260" cy="260" r="150" fill="none" stroke="rgba(14,14,12,.30)" stroke-width="1"/>
  </g>
  <line x1="260" y1="26" x2="260" y2="70" stroke="rgba(14,14,12,.25)" stroke-width="1"/>
  <line x1="260" y1="450" x2="260" y2="494" stroke="rgba(14,14,12,.25)" stroke-width="1"/>
  <line x1="26" y1="260" x2="70" y2="260" stroke="rgba(14,14,12,.25)" stroke-width="1"/>
  <line x1="450" y1="260" x2="494" y2="260" stroke="rgba(14,14,12,.25)" stroke-width="1"/>
  {''.join(orbits)}
  <g transform="translate(206,206) scale(1.7)">
    <rect width="64" height="64" rx="15" fill="#0E0E0C"/>
    <path d="M11.5 32h6.5" stroke="#F3F0E9" stroke-width="5" stroke-linecap="round"/>
    <circle cx="32" cy="32" r="13" fill="none" stroke="#F3F0E9" stroke-width="5"
            stroke-dasharray="62 19.7" stroke-linecap="round" transform="rotate(45 32 32)"/>
    <circle cx="33.5" cy="30.5" r="4.6" fill="#D9502A"/>
  </g>
  <text x="260" y="332" text-anchor="middle" style="font-size:8.6px;letter-spacing:.28em">TONY / PORT</text>
  <text x="260" y="176" text-anchor="middle" style="font-size:8.6px;letter-spacing:.24em">__APPS__ APPS</text>
  <text x="260" y="368" text-anchor="middle" style="font-size:8.6px;letter-spacing:.24em">MCP · REST · SDK</text>
</svg>"""


GLYPHS = {
    "key": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="10" cy="10" r="5.4"/><path d="M13.8 13.8 25 25M21 21l3-3M24 24l3-3"/></svg>',
    "vault": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="4" y="5" width="22" height="20" rx="2"/><circle cx="15" cy="15" r="5"/><path d="M15 10v2M15 18v2M10 15h2M18 15h2"/></svg>',
    "gate": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 15h9M17 15h9"/><rect x="11" y="8" width="8" height="14" rx="1"/><path d="M15 12v6"/></svg>',
    "layers": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M15 4 27 11 15 18 3 11z"/><path d="M3 17l12 7 12-7" opacity=".55"/></svg>',
    "clock": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="15" cy="15" r="11"/><path d="M15 8v8l5 3"/></svg>',
    "ledger": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="5" y="4" width="20" height="22" rx="2"/><path d="M9 10h12M9 15h12M9 20h7"/></svg>',
    "web": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="15" cy="15" r="11"/><path d="M4 15h22M15 4c4 4 4 18 0 22M15 4c-4 4-4 18 0 22"/></svg>',
    "shield": '<svg width="30" height="30" viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M15 3l10 4v9c0 6-5 9-10 11-5-2-10-5-10-11V7z"/><path d="M11 15l3 3 5-6"/></svg>',
}

TICKER = [
    "GitHub", "Gmail", "Slack", "Notion", "Stripe", "Paystack", "Shopify", "Linear",
    "Vercel", "Cloudflare", "Supabase", "Airtable", "HubSpot", "Salesforce", "Figma",
    "Dropbox", "Twilio", "SendGrid", "OpenAI", "Anthropic", "Discord", "Telegram",
    "TikTok", "YouTube", "Spotify", "Mastodon", "Notion", "Jira", "Trello", "Asana",
    "Xero", "QuickBooks", "Zendesk", "Intercom", "Calendly", "Zoom", "Maps", "Weather",
]


def _ticker() -> str:
    items = "".join(
        f'<span class="{"hot" if i % 9 == 4 else ""}">{name}</span>'
        for i, name in enumerate(TICKER * 2)
    )
    return items


BODY = """
<div class="nav"><div class="wrap nav-in">
  <a class="brand" href="/">
    <span class="mark"><img src="/static/brand/tony-mark.svg" alt="" width="26" height="26"></span>
    <b>Tony</b><span>v0.2</span>
  </a>
  <nav class="nav-links">
    <a href="#catalogue">Catalogue</a>
    <a href="#layers">Layers</a>
    <a href="#protocol">Protocol</a>
    <a href="#compare">Compare</a>
    <a href="/docs">Docs</a>
  </nav>
  <div class="nav-cta">
    <a class="btn ghost sm" href="https://github.com/emmanuelerogian723-alt/tony" target="_blank" rel="noopener">GitHub</a>
    <a class="btn signal sm" href="/app">Open console</a>
  </div>
</div></div>

<header class="hero">
  <div class="wrap">
    <div class="hero-grid">
      <div>
        <div class="kicker mono"><span class="bar"></span>Open-source integration gateway · self-hosted · MIT</div>
        <h1>Every app.<br><em>One port.</em><span class="thin">The hands your agent was missing.</span></h1>
        <p class="lede">Tony sits between your agent and <b>__APPS__ real apps</b>. <b>__ACTIONS__ typed actions</b>,
          OAuth done in the browser, credentials sealed with AES-grade encryption, and a human gate on
          anything that writes. One REST call or one MCP endpoint — your server, your keys, your rules.</p>
        <div class="cta-row">
          <a class="btn" href="/app">Open the console
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 10 10 2M4 2h6v6"/></svg>
          </a>
          <a class="btn ghost" href="#protocol">Read the protocol</a>
          <span class="cta-note">no card · no vendor cloud</span>
        </div>
        <div class="counters">
          <div><b id="c-apps">__APPS__</b><span>apps</span></div>
          <div><b id="c-actions">__ACTIONS__</b><span>actions</span></div>
          <div><b id="c-cats">__CATS__</b><span>categories</span></div>
          <div><b id="c-src">__SOURCES__</b><span>catalogues merged</span></div>
        </div>
      </div>
      <div class="port">__PORT__</div>
    </div>
  </div>
  <div class="ticker"><div class="ticker-track">__TICKER__</div></div>
</header>

<section class="sec" id="gap">
  <div class="wrap">
    <div class="sec-head rise">
      <div class="sec-num">00 / the gap</div>
      <div>
        <h2>Agents learned to think. Nobody gave them <em>hands</em>.</h2>
        <p>Tool calling is solved in theory and miserable in practice: a different SDK per app,
          a different key per workspace, and a token that dies quietly at 3am. Tony is the boring,
          reliable layer that makes it one problem instead of seven thousand.</p>
      </div>
    </div>
    <div class="plates rise">
      <div class="plate">
        <div class="glyph"><svg width="26" height="26" viewBox="0 0 26 26" fill="none" stroke="#0E0E0C" stroke-width="1"><circle cx="13" cy="13" r="11" opacity=".35"/><path d="M13 5v16M5 13h16" opacity=".35"/></svg></div>
        <div class="n">PROBLEM 01</div>
        <h3>Talk, no action</h3>
        <p>A model that can describe a refund is not a model that can issue one. Every capability
          costs a bespoke client, a schema, a retry policy and a caveat.</p>
      </div>
      <div class="plate">
        <div class="glyph"><svg width="26" height="26" viewBox="0 0 26 26" fill="none" stroke="#0E0E0C" stroke-width="1"><path d="M3 20 10 8l5 7 3-4 5 9z" opacity=".4"/></svg></div>
        <div class="n">PROBLEM 02</div>
        <h3>Integrations rot</h3>
        <p>APIs move, scopes change, refresh tokens expire. A one-off script from six months ago is
          now a support ticket with a 500 in front of it.</p>
      </div>
      <div class="plate">
        <div class="glyph"><svg width="26" height="26" viewBox="0 0 26 26" fill="none" stroke="#0E0E0C" stroke-width="1"><rect x="5" y="11" width="16" height="11" rx="2" opacity=".4"/><path d="M9 11V8a4 4 0 018 0v3" opacity=".4"/></svg></div>
        <div class="n">PROBLEM 03</div>
        <h3>Trust is the blocker</h3>
        <p>Nobody ships an agent that can delete a repository on a hallucination. Permission has to
          live outside the prompt, in code you can read.</p>
      </div>
    </div>
  </div>
</section>

<section class="sec" id="catalogue" style="padding-top:0">
  <div class="wrap">
    <div class="sec-head rise">
      <div class="sec-num">01 / catalogue</div>
      <div>
        <h2>Search it like a library, <em>not a brochure</em>.</h2>
        <p>Every app below is queryable right now. Type a name — the table queries the live registry,
          not a screenshot.</p>
      </div>
    </div>
    <div class="search-shell rise">
      <div class="search-top">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#6E6B61" stroke-width="1.5"><circle cx="7" cy="7" r="5"/><path d="M11 11l4 4"/></svg>
        <input id="q" placeholder="github · shopify orders · send whatsapp · create invoice" autocomplete="off" spellcheck="false">
        <span class="search-meta" id="qmeta">live registry</span>
      </div>
      <div class="results" id="results"><div class="empty">Start typing, or press ⏎ for the most connected apps.</div></div>
    </div>
  </div>
</section>

<section class="sec dark" id="layers">
  <div class="wrap">
    <div class="sec-head rise">
      <div class="sec-num">02 / anatomy</div>
      <div>
        <h2>Four layers. <em>Honest labels.</em></h2>
        <p>A catalogue that claims seven thousand integrations and ships two hundred is a demo.
          Tony ships all of them and tells you which layer each app sits in, so an agent never
          wonders why a call failed.</p>
      </div>
    </div>
    <div class="layers" id="layers-list">__LAYERS__</div>
    <div class="flow">
      <div><b>Curated</b><p>Written by hand, hit against the live API, kept honest by tests.</p></div>
      <div><b>OpenAPI</b><p>Parsed from published specs — five to ten typed actions per app.</p></div>
      <div><b>Proxy</b><p>Host and auth mode known, so any documented path can be called.</p></div>
      <div><b>Directory</b><p>Connect with an API base and token; Tony handles the rest.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="protocol">
  <div class="wrap">
    <div class="sec-head rise">
      <div class="sec-num">03 / protocol</div>
      <div>
        <h2>One endpoint. <em>Any client.</em></h2>
        <p>Claude Desktop, Cursor, LangChain, a cron job, your own backend — if it speaks HTTP or
          MCP, it is already a Tony client.</p>
      </div>
    </div>
    <div class="rise">
      <div class="tabs" role="tablist">
        <button role="tab" aria-selected="true" data-tab="rest">REST</button>
        <button role="tab" aria-selected="false" data-tab="mcp">MCP</button>
        <button role="tab" aria-selected="false" data-tab="py">Python</button>
        <button role="tab" aria-selected="false" data-tab="js">JavaScript</button>
        <button role="tab" aria-selected="false" data-tab="cli">CLI</button>
      </div>
      <div class="code">
        <button class="copy" data-copy="pane">Copy</button>
<pre id="pane">POST /v1/execute
Authorization: Bearer tony_sk_...

{
  "action": "github.create_issue",
  "args": {
    "owner": "acme",
    "repo": "core",
    "title": "Checkout latency doubled",
    "labels": ["infra"]
  }
}

200 OK · 412ms
{
  "ok": true,
  "data": { "number": 481, "html_url": "…/issues/481" },
  "run_id": "9f2c…"
}</pre>
      </div>
    </div>
    <div class="flow">
      <div><b>01 · call</b><p>Your agent names an action and arguments. Nothing else to learn.</p></div>
      <div><b>02 · resolve</b><p>Tony finds the app, loads the sealed credential, refreshes if stale.</p></div>
      <div><b>03 · gate</b><p>Reads run. Writes and destructive calls wait for an explicit approval.</p></div>
      <div><b>04 · record</b><p>Latency, payload shape and outcome are written to the run ledger.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="compare" style="padding-top:0">
  <div class="wrap">
    <div class="sec-head rise">
      <div class="sec-num">04 / compare</div>
      <div>
        <h2>What changes when <em>you</em> own the layer.</h2>
        <p>Composio is a good product with a closed core and a per-seat price. Tony is the same idea
          with the lid off.</p>
      </div>
    </div>
    <table class="cmp rise">
      <thead><tr><th></th><th>Composio, hosted</th><th class="us">Tony, self-hosted</th></tr></thead>
      <tbody>
        <tr><th>Source</th><td>Closed core, open SDKs</td><td class="us">MIT — engine, catalogue, dashboard</td></tr>
        <tr><th>Hosting</th><td>Their cloud, their region</td><td class="us">Your box, your region, your database</td></tr>
        <tr><th>Catalogue</th><td>~3,000 tools</td><td class="us">__APPS__ apps · __ACTIONS__ actions, labelled by layer</td></tr>
        <tr><th>Cost</th><td>Per action, per seat</td><td class="us">Free. You pay for the server you already have</td></tr>
        <tr><th>Keys</th><td>Deposited with the vendor</td><td class="us">Encrypted in your DB, never leaves it</td></tr>
        <tr><th>Protocol</th><td>Proprietary SDK</td><td class="us">MCP · REST · Python · JS · CLI, same surface</td></tr>
        <tr><th>Danger</th><td>Caller is trusted</td><td class="us">Typed tiers + approval queue + audit ledger</td></tr>
        <tr><th>No-API apps</th><td>Not covered</td><td class="us">Web fetch, readable-text extraction, search fallback</td></tr>
        <tr><th>Exit</th><td>Export your data</td><td class="us">It is already a git repo on your disk</td></tr>
      </tbody>
    </table>
  </div>
</section>

<section class="sec" id="under" style="padding-top:0">
  <div class="wrap">
    <div class="sec-head rise">
      <div class="sec-num">05 / internals</div>
      <div>
        <h2>Eight decisions you can <em>read in the code</em>.</h2>
        <p>No magic layer, no hidden orchestration. Each of these is a module, a test and a paragraph
          of documentation.</p>
      </div>
    </div>
    <div class="feats rise">
      <div class="feat"><div class="n">01</div><div class="g">__G_KEY__</div><h3>OAuth 2.0 + PKCE</h3><p>Browser handoff, state checks, automatic refresh before expiry, per-entity isolation.</p></div>
      <div class="feat"><div class="n">02</div><div class="g">__G_VAULT__</div><h3>Sealed credentials</h3><p>Tokens are encrypted before they reach the database. The key never rides along with the data.</p></div>
      <div class="feat"><div class="n">03</div><div class="g">__G_GATE__</div><h3>Approval tiers</h3><p>Read, write and destructive are separate tiers. The dangerous two cannot run unattended.</p></div>
      <div class="feat"><div class="n">04</div><div class="g">__G_LAYERS__</div><h3>One engine, all apps</h3><p>Manifests, not code. Adding an app is a YAML file, not a service and a deploy.</p></div>
      <div class="feat"><div class="n">05</div><div class="g">__G_CLOCK__</div><h3>Triggers</h3><p>Cron and webhook triggers re-run an action on a schedule and push the result out.</p></div>
      <div class="feat"><div class="n">06</div><div class="g">__G_LEDGER__</div><h3>Run ledger</h3><p>Every call recorded with latency, status and a replayable run id. Debugging without guesswork.</p></div>
      <div class="feat"><div class="n">07</div><div class="g">__G_WEB__</div><h3>No-API fallback</h3><p>When an app has no public API, Tony fetches the page and returns readable text.</p></div>
      <div class="feat"><div class="n">08</div><div class="g">__G_SHIELD__</div><h3>Hard timeouts</h3><p>Every action carries a deadline, so a hanging provider can never hang your agent.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="ship" style="padding-top:0">
  <div class="wrap">
    <div class="sec-head rise">
      <div class="sec-num">06 / ship</div>
      <div><h2>Running in <em>four minutes</em>.</h2></div>
    </div>
    <div class="install rise">
      <div>
        <div class="mono" style="color:var(--muted);margin-bottom:14px">Docker · one command</div>
        <div class="cmd"><b>docker run -p 8000:8000</b> -v tony:/data -e TONY_SECRET_KEY=$KEY ghcr.io/tony/tony</div>
        <div class="cmd"><b>pip install</b> tony-gateway && <i>tony serve</i></div>
        <p style="font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:.05em;margin:14px 0 0;
          text-transform:uppercase">SQLite by default · Postgres when you outgrow it</p>
      </div>
      <div>
        <div class="mono" style="color:var(--muted);margin-bottom:14px">Drop into Claude Desktop</div>
        <div class="cmd" style="white-space:normal;line-height:1.7"><b>{</b> "mcpServers": { "tony": { "url": "https://tony-7su0.onrender.com/mcp", "transport": "http" } } <b>}</b></div>
        <p style="font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:.05em;margin:14px 0 0;
          text-transform:uppercase">__APPS__ apps appear as tools in the next message</p>
      </div>
    </div>
  </div>
</section>

<footer class="foot">
  <div class="wrap">
    <div class="foot-top">
      <div class="wordmark">TONY</div>
      <div class="foot-links">
        <a href="/app">Console</a><a href="/docs">API</a>
        <a href="https://github.com/emmanuelerogian723-alt/tony" target="_blank" rel="noopener">GitHub</a>
        <a href="/v1/stats">Stats</a><a href="/mcp">MCP</a>
      </div>
    </div>
    <div class="foot-bot">
      <span>MIT · self-hosted · no telemetry</span>
      <span>Built for agents that need to do, not describe.</span>
    </div>
  </div>
</footer>

<script>
const $ = (s, r = document) => r.querySelector(s);
const fmt = n => n.toLocaleString('en-US');

/* counters + layer bars, straight off the live registry */
fetch('/v1/stats').then(r => r.json()).then(s => {
  const set = (sel, to) => {
    const el = $(sel); if (!el || !to) return;
    const start = performance.now(), from = 0, dur = 900;
    const tick = t => {
      const p = Math.min((t - start) / dur, 1);
      el.textContent = fmt(Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  set('#c-apps', s.apps); set('#c-actions', s.actions); set('#c-cats', s.categories);
  set('#c-src', Object.keys(s.by_source || {}).length);
}).catch(() => {});

/* live catalogue search */
const results = $('#results'), q = $('#q'), qmeta = $('#qmeta');
const initials = name => name.replace(/[^A-Za-z ]/g, '').split(' ').filter(Boolean)
  .map(w => w[0]).join('').slice(0, 2).toUpperCase();
const label = a => ({curated: 'curated', openapi: 'openapi', 'public-apis': 'directory',
  nango: 'directory', pipedream: 'directory', activepieces: 'directory', n8n: 'directory',
  homeassistant: 'directory'}[a.source] || a.tier);

function render(list, total, query) {
  qmeta.textContent = total ? fmt(total) + (query ? ' matches' : ' apps') : 'no matches';
  if (!list.length) { results.innerHTML = '<div class="empty">Nothing under that name. Try "shopify", "mail" or "pdf".</div>'; return; }
  results.innerHTML = list.map(a => `
    <a class="row" href="/app?app=${encodeURIComponent(a.slug)}">
      <span class="ic">${initials(a.name)}</span>
      <span><span class="nm">${a.name}</span><span class="cat">${a.category}</span></span>
      <span class="acts">${a.actions_count} act.</span>
      <span class="tag ${a.tier === 'actions' ? 'act' : ''}">${label(a)}</span>
    </a>`).join('');
}

async function search(term) {
  const url = '/v1/apps?limit=7' + (term ? '&search=' + encodeURIComponent(term) : '');
  try {
    const d = await (await fetch(url)).json();
    render(d.apps || [], d.total ?? (d.apps || []).length, term);
  } catch (e) { results.innerHTML = '<div class="empty">Registry unreachable.</div>'; }
}
let t; q.addEventListener('input', e => { clearTimeout(t); t = setTimeout(() => search(e.target.value.trim()), 180); });
q.addEventListener('keydown', e => { if (e.key === 'Enter') search(q.value.trim()); });
search('');

/* layer bars draw when visible */
const io = new IntersectionObserver(es => es.forEach(en => {
  if (!en.isIntersecting) return;
  en.target.classList.add('in');
  en.target.querySelectorAll('.bar i').forEach(b => { b.style.width = (b.dataset.w || 0) + '%'; });
  io.unobserve(en.target);
}), { threshold: .18 });
document.querySelectorAll('.rise').forEach(el => io.observe(el));

/* tabs */
const PANES = {
  rest: `POST /v1/execute
Authorization: Bearer tony_sk_...

{
  "action": "github.create_issue",
  "args": { "owner": "acme", "repo": "core", "title": "Checkout latency" }
}

200 OK · 412ms
{ "ok": true, "data": { "number": 481 }, "run_id": "9f2c…" }`,
  mcp: `# Claude Desktop · Cursor · any MCP client
{
  "mcpServers": {
    "tony": { "url": "https://tony-7su0.onrender.com/mcp", "transport": "http" }
  }
}

tools/list  →  __APPS__ apps, __ACTIONS__ actions
tools/call  →  { "name": "gmail.send_email", "arguments": { … } }`,
  py: `from tony import Tony

tony = Tony("http://localhost:8000", key="tony_sk_...")

# one call, typed result
tony.run("slack.post_message",
         channel="#ops",
         text="Deploy 409e9cd is live")

# or let the gateway pick the app
for app in tony.search("invoice"):
    print(app.slug, app.tier, len(app.actions))`,
  js: `import { Tony } from "@tony/sdk";

const tony = new Tony({ url: "http://localhost:8000", key: "tony_sk_..." });

const res = await tony.run("stripe.create_invoice", {
  customer: "cus_NffrFeUfNV2Hib",
  amount: 4200
});
console.log(res.data.status); // "open"`,
  cli: `$ tony apps --search shopify
$ tony actions github
$ tony connect gmail
$ tony run coingecko.price ids=bitcoin vs_currencies=usd

{ "bitcoin": { "usd": 75776 } }`
};
document.querySelectorAll('.tabs button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.tabs button').forEach(x => x.setAttribute('aria-selected', 'false'));
  b.setAttribute('aria-selected', 'true');
  $('#pane').textContent = PANES[b.dataset.tab] || '';
}));

/* copy */
document.querySelectorAll('.copy').forEach(b => b.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('#pane').textContent); b.textContent = 'Copied'; }
  catch { b.textContent = '⌘C'; }
  setTimeout(() => b.textContent = 'Copy', 1400);
}));
</script>
"""


def _layer_rows(stats: dict) -> str:
    tiers = stats.get("tiers") or {}
    sources = stats.get("sources") or {}
    rows = (
        ("Curated", "hand-tested", int(sources.get("curated", 0) or 0), "signal"),
        ("OpenAPI", "real endpoints", int(sources.get("openapi", 0) or 0), ""),
        ("API proxy", "host + auth known", int(tiers.get("proxy", 0) or 0), "grey"),
        ("Directory", "base url + token", int(tiers.get("directory", 0) or 0), "grey"),
    )
    total = max(int(stats.get("apps", 1) or 1), 1)
    out = []
    for name, sub, count, cls in rows:
        width = max(1.2, round(count / total * 100, 1))
        out.append(
            f'<div class="layer"><div class="lname">{name}<small>{sub}</small></div>'
            f'<div class="bar"><i class="{cls}" data-w="{width}"></i></div>'
            f'<div class="lval">{count:,} apps</div></div>'
        )
    return "".join(out)


def _counts(apps) -> tuple[dict, dict]:
    by_source: dict = {}
    by_tier: dict = {}
    for app in apps:
        by_source[app.source] = by_source.get(app.source, 0) + 1
        by_tier[app.tier] = by_tier.get(app.tier, 0) + 1
    return by_source, by_tier


def landing_html(demo_open: bool = True) -> str:
    """Render the marketing page with numbers taken from the live registry."""
    from .catalog import catalog

    apps = list(catalog.apps.values())
    by_source, by_tier = _counts(apps)
    stats = {
        "apps": len(apps),
        "actions": sum(len(a.actions) for a in apps),
        "categories": len({a.category for a in apps}),
        "sources": by_source,
        "tiers": by_tier,
    }
    fill = {
        "__APPS__": f"{stats['apps']:,}",
        "__ACTIONS__": f"{stats['actions']:,}",
        "__CATS__": f"{stats['categories']:,}",
        "__SOURCES__": str(len(by_source)),
        "__LAYERS__": _layer_rows(stats),
        "__PORT__": _port_drawing(),
        "__TICKER__": _ticker(),
        "__G_KEY__": GLYPHS["key"], "__G_VAULT__": GLYPHS["vault"],
        "__G_GATE__": GLYPHS["gate"], "__G_LAYERS__": GLYPHS["layers"],
        "__G_CLOCK__": GLYPHS["clock"], "__G_LEDGER__": GLYPHS["ledger"],
        "__G_WEB__": GLYPHS["web"], "__G_SHIELD__": GLYPHS["shield"],
    }

    def render(chunk: str) -> str:
        # two passes: inserted SVG (the port diagram) carries its own counters
        for _ in range(2):
            for token, value in fill.items():
                chunk = chunk.replace(token, value)
        return chunk

    head = render("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tony — every app, one port</title>
<meta name="description" content="Open-source integration gateway. __APPS__ apps, __ACTIONS__ typed actions, MCP + REST, OAuth handled, credentials sealed, approval gates on anything that writes.">
<meta name="theme-color" content="#F3F0E9">
<link rel="icon" href="/static/brand/favicon.ico" sizes="any">
<link rel="icon" type="image/svg+xml" href="/static/brand/tony-mark.svg">
<link rel="apple-touch-icon" href="/static/brand/tony-180.png">
<link rel="manifest" href="/site.webmanifest">
<meta property="og:title" content="Tony — every app, one port">
<meta property="og:description" content="__APPS__ apps. __ACTIONS__ typed actions. MCP-native. Self-hosted. MIT.">
<meta property="og:image" content="/static/brand/tony-512.png">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<style>""")
    return (head + LANDING_CSS + "</style>\n</head>\n<body>\n"
            + render(BODY) + "\n</body>\n</html>\n")
