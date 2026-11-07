"""Server-rendered marketing page + dashboard (no build step, no frameworks)."""
from __future__ import annotations

BASE_CSS = """
*{box-sizing:border-box}
:root{
  --ink:#0a0a0a;--ink-2:#1d1d1f;--muted:#6b7280;--muted-2:#8a8f98;
  --bg:#ffffff;--soft:#f5f5f7;--soft-2:#fafafb;--line:rgba(0,0,0,.08);--line-2:rgba(0,0,0,.14);
  --green:#0a8f4e;--green-soft:#e8f7ee;--amber:#b45309;--red:#b42318;--blue:#0b57d0;
  --r-sm:10px;--r:14px;--r-lg:20px;--r-xl:28px;
  --shadow-sm:0 1px 2px rgba(0,0,0,.04),0 1px 1px rgba(0,0,0,.03);
  --shadow:0 10px 30px rgba(0,0,0,.06),0 2px 8px rgba(0,0,0,.04);
  --shadow-lg:0 30px 70px rgba(0,0,0,.10),0 6px 20px rgba(0,0,0,.05);
  --ease:cubic-bezier(.2,.8,.2,1);
}
html,body{margin:0;padding:0}
body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Inter,system-ui,sans-serif;
  color:var(--ink);background:var(--bg);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  font-size:15px;line-height:1.55;
}
a{color:inherit;text-decoration:none}
button{font:inherit;cursor:pointer;border:none;background:none;color:inherit}
code,pre,.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace}
::selection{background:#0a0a0a;color:#fff}
.fade{animation:fade .5s var(--ease) both}
@keyframes fade{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.btn{display:inline-flex;align-items:center;gap:8px;height:42px;padding:0 18px;border-radius:999px;
  background:var(--ink);color:#fff;font-weight:590;font-size:14px;letter-spacing:-.01em;
  transition:transform .18s var(--ease),box-shadow .18s var(--ease),opacity .18s var(--ease);box-shadow:var(--shadow-sm)}
.btn:hover{transform:translateY(-1px);box-shadow:var(--shadow)}
.btn:active{transform:translateY(0)}
.btn.ghost{background:#fff;color:var(--ink);border:1px solid var(--line-2)}
.btn.ghost:hover{background:var(--soft)}
.btn.small{height:34px;padding:0 14px;font-size:13px}
.pill{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 10px;border-radius:999px;
  background:var(--soft);color:var(--ink-2);font-size:12px;font-weight:560;letter-spacing:-.01em}
.pill.green{background:var(--green-soft);color:var(--green)}
.dot{width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 0 3px rgba(10,143,78,.14)}
.muted{color:var(--muted)}
.tiny{font-size:12.5px}
h1,h2,h3{margin:0;letter-spacing:-.03em;line-height:1.08;font-weight:700}
h1{font-size:clamp(40px,6vw,72px)}
h2{font-size:clamp(26px,3vw,40px)}
h3{font-size:17px;letter-spacing:-.02em}
"""

LANDING = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tony — connect any app, let any agent act</title>
<meta name="description" content="Open-source integration gateway. One API, one MCP endpoint, every app.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%230a0a0a'/%3E%3Ctext x='32' y='44' font-size='34' font-family='-apple-system,sans-serif' font-weight='700' fill='white' text-anchor='middle'%3ET%3C/text%3E%3C/svg%3E">
<style>__CSS__
.nav{position:sticky;top:0;z-index:40;backdrop-filter:saturate(180%) blur(20px);background:rgba(255,255,255,.82);
  border-bottom:1px solid var(--line)}
.nav-in{max-width:1120px;margin:0 auto;padding:0 24px;height:62px;display:flex;align-items:center;gap:14px}
.logo{display:flex;align-items:center;gap:9px;font-weight:680;letter-spacing:-.02em;font-size:16px}
.logo-mark{width:28px;height:28px;border-radius:9px;background:var(--ink);color:#fff;display:grid;place-items:center;
  font-size:14px;font-weight:700;letter-spacing:-.02em}
.nav-links{display:flex;gap:22px;margin-left:26px;font-size:13.5px;color:var(--muted)}
.nav-links a{transition:color .18s var(--ease)}.nav-links a:hover{color:var(--ink)}
.nav-cta{margin-left:auto;display:flex;gap:10px;align-items:center}
.hero{max-width:1120px;margin:0 auto;padding:92px 24px 30px;text-align:center}
.eyebrow{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);
  background:var(--soft-2);font-size:12.5px;color:var(--ink-2);font-weight:560;letter-spacing:-.01em}
.hero h1{margin:22px auto 0;max-width:900px}
.hero .sub{max-width:640px;margin:20px auto 0;font-size:18px;color:var(--muted);letter-spacing:-.01em}
.hero-cta{margin-top:32px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.stats{display:flex;gap:40px;justify-content:center;margin:52px 0 0;flex-wrap:wrap}
.stat b{display:block;font-size:30px;letter-spacing:-.03em;font-weight:700;font-variant-numeric:tabular-nums}
.stat span{font-size:12.5px;color:var(--muted);letter-spacing:.01em;text-transform:none}
.section{max-width:1120px;margin:0 auto;padding:80px 24px}
.grid-3{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}
.card{border:1px solid var(--line);border-radius:var(--r-lg);padding:24px;background:#fff;
  transition:transform .22s var(--ease),box-shadow .22s var(--ease),border-color .22s var(--ease)}
.card:hover{transform:translateY(-2px);box-shadow:var(--shadow);border-color:var(--line-2)}
.card h3{margin-bottom:8px}
.card p{margin:0;color:var(--muted);font-size:14px}
.ico{width:38px;height:38px;border-radius:11px;background:var(--soft);display:grid;place-items:center;margin-bottom:16px;
  font-size:17px}
.code-wrap{background:#0a0a0a;border-radius:var(--r-xl);padding:26px 26px 22px;color:#e8e8ea;overflow:hidden;
  box-shadow:var(--shadow-lg);position:relative}
.code-wrap .bar{display:flex;gap:6px;margin-bottom:16px}
.code-wrap .bar i{width:10px;height:10px;border-radius:50%;background:#2a2a2e;display:block}
.code-wrap pre{margin:0;font-size:13.5px;line-height:1.75;white-space:pre-wrap;word-break:break-word}
.k{color:#7dd3a0}.s{color:#a5b4fc}.c{color:#6b7280}.n{color:#fbbf24}
.split{display:grid;grid-template-columns:1.05fr .95fr;gap:56px;align-items:center}
.checklist{display:grid;gap:14px;margin-top:26px}
.check{display:flex;gap:11px;align-items:flex-start;font-size:14.5px;color:var(--ink-2)}
.check b{font-weight:600}
.check .tick{width:20px;height:20px;border-radius:50%;background:var(--green-soft);color:var(--green);
  display:grid;place-items:center;font-size:11px;flex:none;margin-top:2px}
.table{width:100%;border-collapse:collapse;font-size:14px}
.table th{text-align:left;font-weight:590;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em;
  padding:0 12px 12px;border-bottom:1px solid var(--line)}
.table td{padding:14px 12px;border-bottom:1px solid var(--line)}
.table tr:last-child td{border-bottom:none}
.cta{text-align:center;padding:90px 24px 100px}
.cta h2{max-width:640px;margin:0 auto}
.cta p{color:var(--muted);max-width:520px;margin:16px auto 0}
.footer{border-top:1px solid var(--line);padding:30px 24px;display:flex;gap:16px;justify-content:space-between;
  align-items:center;flex-wrap:wrap;max-width:1120px;margin:0 auto;font-size:13px;color:var(--muted)}
@media(max-width:820px){.split{grid-template-columns:1fr;gap:34px}.nav-links{display:none}.hero{padding-top:64px}}
</style></head>
<body>
<nav class="nav"><div class="nav-in">
  <a class="logo" href="/"><span class="logo-mark">T</span>Tony</a>
  <div class="nav-links">
    <a href="#how">How it works</a><a href="#compare">Why Tony</a><a href="#apps">Catalogue</a>
    <a href="https://github.com/emmanuelerogian723-alt/tony" target="_blank" rel="noopener">GitHub</a>
  </div>
  <div class="nav-cta">
    <a class="btn ghost small" href="/docs" target="_blank" rel="noopener">API</a>
    <a class="btn small" href="/app">Open dashboard</a>
  </div>
</div></nav>

<header class="hero">
  <span class="eyebrow fade"><span class="dot"></span> Open source · self-hosted · no per-action pricing</span>
  <h1 class="fade">Connect any app.<br>Let any agent act on it.</h1>
  <p class="sub fade">Tony is the integration layer your product was missing — one API, one MCP endpoint,
  and real, live data from every app your users sign into.</p>
  <div class="hero-cta fade">
    <a class="btn" href="/app">Try it live →</a>
    <a class="btn ghost" href="https://github.com/emmanuelerogian723-alt/tony" target="_blank" rel="noopener">Star on GitHub</a>
  </div>
  <div class="stats fade" id="stats">
    <div class="stat"><b id="s-apps">—</b><span>apps connected</span></div>
    <div class="stat"><b id="s-actions">—</b><span>actions</span></div>
    <div class="stat"><b id="s-runs">—</b><span>live runs</span></div>
    <div class="stat"><b id="s-lat">—</b><span>avg latency</span></div>
  </div>
</header>

<section class="section" id="how">
  <div class="split">
    <div>
      <h2>Your users sign in.<br>You get a clean API.</h2>
      <p class="muted" style="margin-top:16px;font-size:16px">Tony runs the whole OAuth dance, refreshes tokens
      before they expire, and encrypts every credential at rest. Your code never touches a provider secret.</p>
      <div class="checklist">
        <div class="check"><span class="tick">✓</span><div><b>Bring your own OAuth app</b><br><span class="muted tiny">Each provider uses your client ID. No shared rate limits, no vendor lock.</span></div></div>
        <div class="check"><span class="tick">✓</span><div><b>Tokens refresh themselves</b><br><span class="muted tiny">Expiring credentials are renewed in the background before a call fails.</span></div></div>
        <div class="check"><span class="tick">✓</span><div><b>Row-level safety</b><br><span class="muted tiny">Write and destructive actions wait for an explicit approval, and every call is logged.</span></div></div>
      </div>
    </div>
    <div class="code-wrap fade">
      <div class="bar"><i></i><i></i><i></i></div>
<pre><span class="c"># 1 — connect a user's app (one link)</span>
<span class="k">POST</span> /v1/connections/github/start
   { <span class="s">"entity_id"</span>: <span class="s">"user_42"</span> }
<span class="c">→ { authorization_url: "https://github.com/login/oauth/..." }</span>

<span class="c"># 2 — let any model use it</span>
<span class="k">POST</span> /v1/execute
   { <span class="s">"action"</span>: <span class="s">"github.list_repos"</span>,
     <span class="s">"entity_id"</span>: <span class="s">"user_42"</span>,
     <span class="s">"args"</span>: { <span class="s">"per_page"</span>: <span class="n">10</span> } }
<span class="c">→ real repositories, 180ms, tokens never leave Tony</span>

<span class="c"># 3 — or point Claude / Cursor at it</span>
<span class="k">POST</span> /mcp   <span class="c"># MCP JSON-RPC, 200+ tools</span></pre>
    </div>
  </div>
</section>

<section class="section" id="apps">
  <h2>Built for real data</h2>
  <p class="muted" style="margin-top:14px;font-size:16px;max-width:620px">Every action is a declarative manifest — add a new
  app with twenty lines of YAML, no core changes, no SDK release.</p>
  <div class="grid-3" style="margin-top:34px">
    <div class="card"><div class="ico">🔌</div><h3>Universal REST connector</h3>
      <p>Any API with a key or a bearer token works on day one. Paste the key, call the action.</p></div>
    <div class="card"><div class="ico">🌐</div><h3>No-API fallback</h3>
      <p>For sites that never shipped an API, Tony fetches the page, extracts the text, or searches the web.</p></div>
    <div class="card"><div class="ico">⚡</div><h3>Triggers</h3>
      <p>Poll an action on a schedule and webhook your server the moment the result actually changes.</p></div>
    <div class="card"><div class="ico">🧠</div><h3>LLM-ready responses</h3>
      <p>Path extraction, item caps and response budgets keep every payload small enough for a context window.</p></div>
    <div class="card"><div class="ico">🔒</div><h3>Encrypted at rest</h3>
      <p>Fernet-encrypted credentials, hashed API keys, SSRF guard on every outbound call.</p></div>
    <div class="card"><div class="ico">📊</div><h3>Run log</h3>
      <p>Every call is timestamped with latency, status and byte count — replay any of them.</p></div>
  </div>
</section>

<section class="section" id="compare">
  <h2>How Tony compares</h2>
  <div style="margin-top:28px;border:1px solid var(--line);border-radius:var(--r-lg);overflow:hidden">
  <table class="table">
    <tr><th>Capability</th><th>Hosted aggregator</th><th>Tony</th></tr>
    <tr><td>Pricing model</td><td class="muted">Per connected user, per month</td><td><b>Free, self-hosted</b></td></tr>
    <tr><td>OAuth client</td><td class="muted">Shared, rate-limited</td><td><b>Yours</b></td></tr>
    <tr><td>Add a new app</td><td class="muted">Wait for a vendor release</td><td><b>One YAML file</b></td></tr>
    <tr><td>Agent protocol</td><td class="muted">Proprietary SDK</td><td><b>MCP + OpenAPI</b></td></tr>
    <tr><td>Data residency</td><td class="muted">Their cloud</td><td><b>Your server</b></td></tr>
    <tr><td>Destructive calls</td><td class="muted">Trust the caller</td><td><b>Approval + audit log</b></td></tr>
  </table>
  </div>
</section>

<section class="cta">
  <h2>Ship integrations<br>this afternoon.</h2>
  <p>Clone the repo, set one secret, run one command. Your agents get every app in the catalogue.</p>
  <div style="margin-top:28px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
    <a class="btn" href="/app">Open the live dashboard</a>
    <a class="btn ghost" href="https://github.com/emmanuelerogian723-alt/tony" target="_blank" rel="noopener">Read the source</a>
  </div>
</section>

<footer class="footer">
  <div class="logo" style="font-size:14px"><span class="logo-mark" style="width:24px;height:24px;border-radius:8px;font-size:12px">T</span>Tony</div>
  <div>Apache-2.0 · built to be the open layer under every agent</div>
</footer>
<script>
(async function(){
  try{
    const r = await fetch('/v1/stats'); const d = await r.json();
    document.getElementById('s-apps').textContent = d.apps;
    document.getElementById('s-actions').textContent = d.actions;
    document.getElementById('s-runs').textContent = d.runs;
  }catch(e){}
  try{
    const r = await fetch('/v1/runs',{headers:{}});
  }catch(e){}
})();
</script>
</body></html>"""

DASH = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tony — dashboard</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%230a0a0a'/%3E%3Ctext x='32' y='44' font-size='34' fill='white' font-family='-apple-system,sans-serif' font-weight='700' text-anchor='middle'%3ET%3C/text%3E%3C/svg%3E">
<style>__CSS__
body{background:var(--soft-2);height:100vh;overflow:hidden}
.shell{display:grid;grid-template-columns:232px 1fr;height:100vh}
.side{background:#fff;border-right:1px solid var(--line);display:flex;flex-direction:column;padding:18px 14px}
.side .logo{padding:4px 8px 18px}
.nav-item{display:flex;align-items:center;gap:10px;height:38px;padding:0 10px;border-radius:9px;color:var(--ink-2);
  font-size:13.5px;font-weight:520;letter-spacing:-.01em;transition:background .16s var(--ease);cursor:pointer}
.nav-item:hover{background:var(--soft)}
.nav-item.active{background:var(--ink);color:#fff}
.nav-item .i{width:16px;text-align:center;font-size:13px;opacity:.9}
.side-foot{margin-top:auto;padding:10px 8px;font-size:11.5px;color:var(--muted-2);display:grid;gap:6px}
.main{display:flex;flex-direction:column;min-width:0;height:100vh}
.topbar{height:58px;display:flex;align-items:center;gap:12px;padding:0 22px;border-bottom:1px solid var(--line);
  background:rgba(255,255,255,.8);backdrop-filter:blur(14px);flex:none}
.search{display:flex;align-items:center;gap:8px;height:34px;padding:0 12px;border-radius:999px;background:var(--soft);
  min-width:280px;border:1px solid transparent;transition:border-color .18s var(--ease),background .18s var(--ease)}
.search:focus-within{background:#fff;border-color:var(--line-2)}
.search input{border:none;background:none;outline:none;font-size:13.5px;width:100%;color:var(--ink)}
.scroll{overflow:auto;padding:26px 26px 60px;flex:1}
.page{display:none;animation:fade .35s var(--ease) both}
.page.on{display:block}
.head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:22px;flex-wrap:wrap}
.head h2{font-size:26px}
.head p{margin:6px 0 0;color:var(--muted);font-size:13.5px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
.chip{height:30px;padding:0 13px;border-radius:999px;background:#fff;border:1px solid var(--line);font-size:12.5px;
  color:var(--ink-2);display:inline-flex;align-items:center;gap:6px;transition:all .16s var(--ease)}
.chip:hover{border-color:var(--line-2)}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.apps{display:grid;grid-template-columns:repeat(auto-fill,minmax(236px,1fr));gap:12px}
.app{background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:15px 15px 13px;cursor:pointer;
  transition:transform .18s var(--ease),box-shadow .18s var(--ease),border-color .18s var(--ease);position:relative}
.app:hover{transform:translateY(-2px);box-shadow:var(--shadow);border-color:var(--line-2)}
.app .row{display:flex;align-items:center;gap:11px}
.app img{width:32px;height:32px;border-radius:9px;background:var(--soft);object-fit:contain;padding:5px}
.app .nm{font-weight:600;font-size:13.5px;letter-spacing:-.01em;line-height:1.2}
.app .cat{font-size:11.5px;color:var(--muted)}
.app .desc{margin:11px 0 0;font-size:12.5px;color:var(--muted);line-height:1.5;display:-webkit-box;
  -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:34px}
.app .foot{display:flex;align-items:center;gap:6px;margin-top:12px}
.badge{font-size:10.5px;font-weight:600;padding:3px 8px;border-radius:999px;background:var(--soft);color:var(--ink-2);
  letter-spacing:.01em;text-transform:uppercase}
.badge.ok{background:var(--green-soft);color:var(--green)}
.badge.read{background:#eef2ff;color:#3730a3}
.badge.write{background:#fef3c7;color:#92400e}
.badge.destructive{background:#fee4e2;color:#b42318}
.panel{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);overflow:hidden}
.panel-h{padding:15px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px}
.panel-h b{font-size:14px;letter-spacing:-.01em}
.panel-b{padding:18px}
.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}
@media(max-width:1080px){.grid2{grid-template-columns:1fr}}
.field{margin-bottom:13px}
.field label{display:block;font-size:12px;font-weight:600;color:var(--ink-2);margin-bottom:5px;letter-spacing:-.01em}
.field .hint{font-size:11.5px;color:var(--muted);font-weight:400;margin-left:5px}
.input,textarea,select{width:100%;border:1px solid var(--line-2);border-radius:9px;padding:9px 11px;font-size:13px;
  font-family:inherit;background:#fff;outline:none;transition:border-color .16s var(--ease),box-shadow .16s var(--ease)}
.input:focus,textarea:focus{border-color:#0a0a0a;box-shadow:0 0 0 3px rgba(10,10,10,.07)}
pre.out{margin:0;background:#0a0a0a;color:#e8e8ea;border-radius:12px;padding:15px;font-size:12px;line-height:1.6;
  max-height:420px;overflow:auto;white-space:pre-wrap;word-break:break-word}
.kv{display:flex;gap:14px;font-size:12px;color:var(--muted);margin-bottom:10px;flex-wrap:wrap}
.mono{display:grid;place-items:center;border-radius:9px;color:#fff;font-weight:650;letter-spacing:-.02em;flex:none;box-shadow:0 1px 2px rgba(0,0,0,.14)}
.ico{position:relative;display:inline-flex;flex:none;width:30px;height:30px}
.ico img{position:absolute;inset:0;width:30px;height:30px;object-fit:contain;border-radius:8px;background:var(--surface,#fff)}
.badge.actions{background:#eef7ee;color:#166534}
.badge.proxy{background:#eef2ff;color:#3730a3}
.badge.directory{background:#f4f4f5;color:#52525b}
@media(prefers-color-scheme:dark){.badge.actions{background:#12301c;color:#7ee2a8}.badge.proxy{background:#1b1f3a;color:#a5b4fc}.badge.directory{background:#26262a;color:#a1a1aa}}
.toast{position:fixed;right:20px;bottom:20px;background:var(--ink);color:#fff;padding:11px 16px;border-radius:11px;
  font-size:13px;box-shadow:var(--shadow-lg);opacity:0;transform:translateY(8px);transition:all .24s var(--ease);z-index:99}
.toast.on{opacity:1;transform:none}
.rowline{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--line);font-size:13px}
.rowline:last-child{border-bottom:none}
.rowline .grow{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mono-sm{font-family:ui-monospace,Menlo,monospace;font-size:11.5px}
.empty{padding:34px;text-align:center;color:var(--muted);font-size:13px}
.act{display:flex;align-items:center;gap:10px;padding:11px 14px;border-radius:10px;cursor:pointer;
  transition:background .15s var(--ease);border:1px solid transparent}
.act:hover{background:var(--soft)}
.act.on{background:var(--soft);border-color:var(--line)}
.drawer{position:fixed;inset:0;background:rgba(10,10,10,.28);backdrop-filter:blur(4px);display:none;z-index:60;
  animation:fade .2s var(--ease) both}
.drawer.on{display:grid;place-items:center;padding:22px}
.modal{background:#fff;border-radius:var(--r-lg);max-width:940px;width:100%;max-height:88vh;overflow:auto;
  box-shadow:var(--shadow-lg);animation:pop .28s var(--ease) both}
@keyframes pop{from{opacity:0;transform:scale(.98) translateY(6px)}to{opacity:1;transform:none}}
.modal-h{padding:20px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;
  position:sticky;top:0;background:rgba(255,255,255,.92);backdrop-filter:blur(12px);z-index:2}
.modal-b{padding:20px 22px 26px}
.x{margin-left:auto;width:30px;height:30px;border-radius:8px;display:grid;place-items:center;color:var(--muted)}
.x:hover{background:var(--soft);color:var(--ink)}
.tabs{display:flex;gap:22px;border-bottom:1px solid var(--line);margin:0 0 18px}
.tab{padding:0 0 10px;font-size:13px;font-weight:560;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;
  margin-bottom:-1px;transition:all .16s var(--ease)}
.tab.on{color:var(--ink);border-bottom-color:var(--ink)}
.snippet{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:12px 13px;font-size:12px;
  overflow:auto;white-space:pre;font-family:ui-monospace,Menlo,monospace;color:var(--ink-2)}
.statgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.statcard{background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:16px}
.statcard b{display:block;font-size:24px;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.statcard span{font-size:12px;color:var(--muted)}
@media(max-width:860px){.shell{grid-template-columns:68px 1fr}.side .logo span,.nav-item span,.side-foot{display:none}
  .nav-item{justify-content:center}.search{min-width:0;flex:1}}
</style></head>
<body>
<div class="shell">
  <aside class="side">
    <div class="logo"><span class="logo-mark">T</span><span>Tony</span></div>
    <div class="nav-item active" data-page="apps"><span class="i">▦</span><span>Apps</span></div>
    <div class="nav-item" data-page="connections"><span class="i">🔗</span><span>Connections</span></div>
    <div class="nav-item" data-page="runs"><span class="i">⟳</span><span>Runs</span></div>
    <div class="nav-item" data-page="triggers"><span class="i">⚡</span><span>Triggers</span></div>
    <div class="nav-item" data-page="developers"><span class="i">{ }</span><span>Developers</span></div>
    <div class="side-foot">
      <div id="wsline">workspace · demo</div>
      <div style="display:flex;align-items:center;gap:6px"><span class="dot"></span> live</div>
    </div>
  </aside>
  <div class="main">
    <div class="topbar">
      <div class="search"><span class="muted">⌕</span><input id="q" placeholder="Search apps and actions…"></div>
      <div style="margin-left:auto;display:flex;gap:9px;align-items:center">
        <span class="pill green" id="topstatus"><span class="dot"></span> connected</span>
        <a class="btn ghost small" href="/docs" target="_blank" rel="noopener">API docs</a>
      </div>
    </div>
    <div class="scroll">
      <!-- APPS -->
      <section class="page on" id="page-apps">
        <div class="head">
          <div><h2>Apps</h2><p>Connect once. Any agent can then act through Tony.</p></div>
          <div class="muted tiny" id="appcount"></div>
        </div>
        <div class="chips" id="tiers"></div>
        <div class="chips" id="cats"></div>
        <div class="apps" id="appgrid"></div>
        <button class="btn ghost" id="more" style="display:none;margin:14px auto 0"></button>
        <div class="tiny muted" style="text-align:center;margin:10px 0 30px">Icons come from each app's own brand data; everything else gets a generated monogram.</div>
      </section>
      <!-- CONNECTIONS -->
      <section class="page" id="page-connections">
        <div class="head"><div><h2>Connections</h2><p>Accounts your users have signed into.</p></div></div>
        <div class="panel"><div id="conns"><div class="empty">Loading…</div></div></div>
      </section>
      <!-- RUNS -->
      <section class="page" id="page-runs">
        <div class="head"><div><h2>Runs</h2><p>Every call, with latency and size.</p></div>
          <button class="btn ghost small" onclick="loadRuns()">Refresh</button></div>
        <div class="statgrid" id="runstats"></div>
        <div class="panel"><div id="runs"><div class="empty">Loading…</div></div></div>
      </section>
      <!-- TRIGGERS -->
      <section class="page" id="page-triggers">
        <div class="head"><div><h2>Triggers</h2><p>Watch an action, webhook your server when the data changes.</p></div></div>
        <div class="grid2">
          <div class="panel"><div class="panel-h"><b>New trigger</b></div><div class="panel-b">
            <div class="field"><label>Action</label><input class="input" id="tr-action" placeholder="coingecko.price"></div>
            <div class="field"><label>Arguments (JSON)</label><textarea id="tr-args" rows="3">{ "ids": "bitcoin", "vs_currencies": "usd" }</textarea></div>
            <div class="field"><label>Every (seconds)</label><input class="input" id="tr-int" value="300"></div>
            <div class="field"><label>Webhook URL</label><input class="input" id="tr-hook" placeholder="https://yourapp.com/hooks/tony"></div>
            <button class="btn small" onclick="createTrigger()">Create trigger</button>
          </div></div>
          <div class="panel"><div class="panel-h"><b>Active</b></div><div id="triggers"><div class="empty">None yet</div></div></div>
        </div>
      </section>
      <!-- DEVELOPERS -->
      <section class="page" id="page-developers">
        <div class="head"><div><h2>Developers</h2><p>Three ways in: REST, MCP, or generated tool schemas.</p></div></div>
        <div class="grid2">
          <div class="panel"><div class="panel-h"><b>REST</b></div><div class="panel-b">
            <div class="snippet">POST /v1/execute
{
  "action": "hackernews.top_stories",
  "entity_id": "user_42",
  "args": {}
}</div>
            <p class="muted tiny" style="margin:12px 0 0">Auth: <code>Authorization: Bearer tk_live_…</code></p>
          </div></div>
          <div class="panel"><div class="panel-h"><b>MCP</b></div><div class="panel-b">
            <div class="snippet">{
  "mcpServers": {
    "tony": { "url": "__BASE__/mcp" }
  }
}</div>
            <p class="muted tiny" style="margin:12px 0 0">Point Claude Desktop, Cursor or any MCP client here.</p>
          </div></div>
          <div class="panel"><div class="panel-h"><b>Tool schemas</b></div><div class="panel-b">
            <div class="snippet">GET /v1/tools?fmt=openai
GET /v1/tools?fmt=anthropic</div>
            <p class="muted tiny" style="margin:12px 0 0">Drop straight into a function-calling loop.</p>
          </div></div>
          <div class="panel"><div class="panel-h"><b>Python</b></div><div class="panel-b">
            <div class="snippet">from tony_sdk import Tony
t = Tony("__BASE__", "tk_live_…")
t.execute("github.list_repos",
          entity_id="user_42", args={"per_page": 5})</div>
          </div></div>
        </div>
      </section>
    </div>
  </div>
</div>

<!-- APP DRAWER -->
<div class="drawer" id="drawer" onclick="if(event.target===this)closeDrawer()">
  <div class="modal">
    <div class="modal-h">
      <img id="d-logo" src="" style="width:34px;height:34px;border-radius:10px;background:var(--soft);padding:6px">
      <div><div style="font-weight:650;letter-spacing:-.02em" id="d-name">App</div>
        <div class="tiny muted" id="d-cat"></div></div>
      <div style="margin-left:auto;display:flex;gap:8px;align-items:center">
        <span id="d-state" class="badge">not connected</span>
        <button class="x" onclick="closeDrawer()">✕</button>
      </div>
    </div>
    <div class="modal-b">
      <p class="muted" id="d-desc" style="margin:0 0 16px;font-size:13.5px"></p>
      <div class="tabs"><div class="tab on" data-tab="actions">Actions</div><div class="tab" data-tab="connect">Connect</div></div>
      <div id="tab-actions">
        <div class="grid2">
          <div class="panel" style="border-radius:12px"><div style="padding:8px" id="d-actions"></div></div>
          <div>
            <div class="panel" style="border-radius:12px"><div class="panel-h"><b id="p-title">Run an action</b></div>
              <div class="panel-b">
                <div id="p-fields"><div class="empty">Pick an action on the left.</div></div>
                <div style="display:flex;gap:8px;margin-top:6px">
                  <button class="btn small" id="runbtn" onclick="runAction()" disabled>Run</button>
                  <label class="tiny muted" style="display:flex;align-items:center;gap:6px">
                    <input type="checkbox" id="p-dry"> dry run</label>
                </div>
              </div>
            </div>
            <div class="panel" style="border-radius:12px;margin-top:12px"><div class="panel-h"><b>Response</b>
              <span class="tiny muted" id="p-meta" style="margin-left:auto"></span></div>
              <div class="panel-b"><pre class="out" id="p-out">No calls yet.</pre></div>
            </div>
          </div>
        </div>
      </div>
      <div id="tab-connect" style="display:none">
        <div id="connect-body"></div>
      </div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<script>
const TONY_KEY = "__KEY__";
const BASE = location.origin;
let APPS = [], CATS = [], CUR = null, CURACT = null, CONNS = [];

function h(html){const d=document.createElement('template');d.innerHTML=html.trim();return d.content.firstChild}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function toast(msg){const t=document.getElementById('toast');t.textContent=msg;t.classList.add('on');
  clearTimeout(t._x);t._x=setTimeout(()=>t.classList.remove('on'),2400)}
function headers(extra){return Object.assign({'Content-Type':'application/json'}, TONY_KEY?{'Authorization':'Bearer '+TONY_KEY}:{}, extra||{})}

document.querySelectorAll('.nav-item').forEach(el=>el.onclick=()=>{
  document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('on'));
  document.getElementById('page-'+el.dataset.page).classList.add('on');
  if(el.dataset.page==='runs')loadRuns();
  if(el.dataset.page==='connections')loadConns();
  if(el.dataset.page==='triggers')loadTriggers();
});

const PAGE = 60;
let APPS = [], CATS = [], CUR = null, CURACT = null, CONNS = [], TOTAL = 0, OFFSET = 0, Q = '', CAT = '', TIER = '';

function initials(name){
  const w = String(name||'').replace(/[^A-Za-z0-9 ]/g,' ').trim().split(/\s+/).filter(Boolean);
  if(!w.length) return '?';
  return (w.length===1 ? w[0].slice(0,2) : w[0][0]+w[1][0]).toUpperCase();
}
function hue(slug){let x=0;for(const ch of String(slug))x=(x*31+ch.charCodeAt(0))%360;return x}
function iconHTML(a, size){
  const s = size || 30;
  const mono = '<span class="mono" style="width:'+s+'px;height:'+s+'px;background:hsl('+hue(a.slug)+',58%,46%);font-size:'+Math.round(s*0.38)+'px">'+esc(initials(a.name))+'</span>';
  if(!a.logo) return mono;
  return '<span class="ico">'+mono+'<img src="'+esc(a.logo)+'" alt="" loading="lazy" decoding="async" onload="this.previousElementSibling.style.display=\'none\'" onerror="this.remove()">'+'</span>';
}

async function loadApps(reset){
  if(reset){OFFSET=0; APPS=[];}
  const url = BASE+'/v1/apps?limit='+PAGE+'&offset='+OFFSET+
    '&search='+encodeURIComponent(Q)+'&category='+encodeURIComponent(CAT)+'&tier='+encodeURIComponent(TIER);
  const d = await (await fetch(url)).json();
  CATS = d.categories || CATS; TOTAL = d.total||0;
  APPS = APPS.concat(d.apps||[]); OFFSET = APPS.length;
  document.getElementById('appcount').textContent = TOTAL.toLocaleString()+' apps';
  renderChips(); renderApps(); loadConns();
}
function renderChips(){
  const chips = document.getElementById('cats');
  if(chips){
    chips.innerHTML = '<div class="chip'+(CAT===''?' on':'')+'" data-c="">All</div>' +
      CATS.map(c=>'<div class="chip'+(CAT===c?' on':'')+'" data-c="'+esc(c)+'">'+esc(c)+'</div>').join('');
    chips.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{CAT=ch.dataset.c; loadApps(true)});
  }
  const t = document.getElementById('tiers');
  if(t){
    const opts=[['','All apps'],['actions','Built-in actions'],['proxy','API proxy'],['directory','Directory']];
    t.innerHTML = opts.map(([v,l])=>'<div class="chip'+(TIER===v?' on':'')+'" data-t="'+v+'">'+l+'</div>').join('');
    t.querySelectorAll('.chip').forEach(ch=>ch.onclick=()=>{TIER=ch.dataset.t; loadApps(true)});
  }
}
function tierLabel(t){return t==='actions'?'actions':(t==='proxy'?'proxy':'directory')}
function renderApps(){
  const grid = document.getElementById('appgrid');
  if(!APPS.length){grid.innerHTML='<div class="empty" style="grid-column:1/-1">Nothing matched.</div>';return}
  grid.innerHTML = APPS.map(a=>{
    const c = CONNS.find(x=>x.app===a.slug && x.status==='active');
    return '<div class="app" data-slug="'+esc(a.slug)+'">'+
      '<div class="row">'+iconHTML(a,30)+
      '<div style="min-width:0"><div class="nm">'+esc(a.name)+'</div><div class="cat">'+esc(a.category)+'</div></div></div>'+
      '<p class="desc">'+esc(a.description||'')+'</p>'+
      '<div class="foot">'+(c?'<span class="badge ok">connected</span>':'')+
      '<span class="badge">'+a.actions_count+' act</span>'+
      '<span class="badge '+a.tier+'">'+tierLabel(a.tier)+'</span></div></div>';
  }).join('');
  grid.querySelectorAll('.app').forEach(el=>el.onclick=()=>openApp(el.dataset.slug));
  const more = document.getElementById('more');
  if(more){
    more.style.display = OFFSET < TOTAL ? 'block' : 'none';
    more.textContent = 'Load more ('+OFFSET.toLocaleString()+' of '+TOTAL.toLocaleString()+')';
  }
}
let _qt;
document.getElementById('q').addEventListener('input',e=>{
  clearTimeout(_qt);
  _qt = setTimeout(()=>{Q = e.target.value.trim(); loadApps(true)}, 220);
});
async function loadConns(){
  const r = await fetch(BASE+'/v1/connections'); const d = await r.json();
  CONNS = d.connections||[];
  const box = document.getElementById('conns');
  if(!CONNS.length){box.innerHTML='<div class="empty">No connections yet — open an app and connect it.</div>';return}
  box.innerHTML = CONNS.map(c=>'<div class="rowline"><b>'+esc(c.app)+'</b>'+
    '<span class="badge ok">'+esc(c.status)+'</span>'+
    '<span class="grow muted tiny">entity '+esc(c.entity_id)+' · '+esc(c.label||'')+'</span>'+
    '<button class="btn ghost small" data-del="'+esc(c.app)+'">Disconnect</button></div>').join('');
  box.querySelectorAll('[data-del]').forEach(b=>b.onclick=async()=>{
    await fetch(BASE+'/v1/connections/'+b.dataset.del+'?entity_id=default',{method:'DELETE'});
    toast('Disconnected'); loadConns(); renderApps(document.querySelector('#cats .chip.on')?.dataset.c||'','');
  });
  if(document.getElementById('page-apps').classList.contains('on')){
    renderApps(document.querySelector('#cats .chip.on')?.dataset.c||'', document.getElementById('q').value);
  }
}

async function openApp(slug){
  const d = await (await fetch(BASE+'/v1/apps/'+slug)).json();
  CUR = d;
  document.getElementById('drawer').classList.add('on');
  const dl = document.getElementById('d-logo');
  const wrap = dl.parentElement;
  if(d.logo){ dl.style.display=''; dl.src = d.logo; wrap.querySelector('.mono-d')?.remove(); }
  else { dl.style.display='none'; wrap.querySelector('.mono-d')?.remove();
    const m = document.createElement('span'); m.className='mono mono-d';
    m.style.cssText='width:34px;height:34px;font-size:13px;background:hsl('+hue(d.slug)+',58%,46%)';
    m.textContent = initials(d.name); wrap.prepend(m); }
  document.getElementById('d-name').textContent = d.name;
  document.getElementById('d-cat').textContent = d.category + ' · ' + d.actions_count + ' actions';
  document.getElementById('d-desc').textContent = d.description;
  const conn = CONNS.find(x=>x.app===slug && x.status==='active');
  document.getElementById('d-state').textContent = conn ? 'connected' : (d.auth.type==='none'?'public':'not connected');
  document.getElementById('d-state').className = 'badge ' + (conn||d.auth.type==='none'?'ok':'');
  document.getElementById('d-actions').innerHTML = d.actions.map((a,i)=>
    '<div class="act'+(i===0?' on':'')+'" data-i="'+i+'"><div style="flex:1;min-width:0">'+
    '<div style="font-weight:560;font-size:13px;letter-spacing:-.01em">'+esc(a.name)+'</div>'+
    '<div class="tiny muted" style="margin-top:2px">'+esc(a.slug)+'</div></div>'+
    '<span class="badge '+esc(a.tier)+'">'+esc(a.tier)+'</span></div>').join('');
  document.getElementById('d-actions').querySelectorAll('.act').forEach(el=>el.onclick=()=>{
    document.querySelectorAll('#d-actions .act').forEach(x=>x.classList.remove('on'));
    el.classList.add('on'); pickAction(parseInt(el.dataset.i,10));
  });
  pickAction(0);
  renderConnectTab(d, conn);
  document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on')); t.classList.add('on');
    document.getElementById('tab-actions').style.display = t.dataset.tab==='actions'?'block':'none';
    document.getElementById('tab-connect').style.display = t.dataset.tab==='connect'?'block':'none';
  });
}

function pickAction(i){
  const a = CUR.actions[i]; CURACT = a;
  document.getElementById('p-title').textContent = a.name;
  const fields = Object.entries(a.params||{}).map(([k,v])=>{
    const req = (a.required||[]).includes(k);
    const typ = v.type||'string';
    let input;
    if(v.enum){ input = '<select class="input" data-arg="'+esc(k)+'">'+v.enum.map(o=>'<option>'+esc(o)+'</option>').join('')+'</select>'; }
    else if(typ==='boolean'){ input = '<select class="input" data-arg="'+esc(k)+'"><option value="true">true</option><option value="false">false</option></select>'; }
    else { input = '<input class="input" data-arg="'+esc(k)+'" type="'+(typ==='integer'||typ==='number'?'number':'text')+'"'+
      (v.default!==undefined?' value="'+esc(v.default)+'"':'')+'>'; }
    return '<div class="field"><label>'+esc(k)+(req?' *':'')+'<span class="hint">'+esc(typ)+'</span></label>'+input+
      (v.description?'<div class="tiny muted" style="margin-top:4px">'+esc(v.description)+'</div>':'')+'</div>';
  }).join('');
  document.getElementById('p-fields').innerHTML = fields || '<div class="empty">This action takes no arguments.</div>';
  document.getElementById('runbtn').disabled = false;
  document.getElementById('p-out').textContent = 'Ready.';
  document.getElementById('p-meta').textContent = '';
}

async function runAction(){
  const a = CURACT; if(!a) return;
  const args = {};
  document.querySelectorAll('#p-fields [data-arg]').forEach(el=>{
    let v = el.value;
    if(v==='') return;
    const spec = (a.params||{})[el.dataset.arg]||{};
    if(spec.type==='integer') v = parseInt(v,10);
    else if(spec.type==='number') v = parseFloat(v);
    else if(spec.type==='boolean') v = v==='true';
    else if(spec.type==='array') v = v.split(',').map(s=>s.trim()).filter(Boolean);
    args[el.dataset.arg] = v;
  });
  const dry = document.getElementById('p-dry').checked;
  const out = document.getElementById('p-out'), meta = document.getElementById('p-meta');
  out.textContent = 'Running…'; meta.textContent = '';
  const t0 = performance.now();
  try{
    const r = await fetch(BASE+'/v1/execute',{method:'POST',headers:headers(),
      body:JSON.stringify({action:CUR.slug+'.'+a.slug, entity_id:'default', args, approved:true, dry_run:dry})});
    const d = await r.json();
    const ms = Math.round(performance.now()-t0);
    meta.textContent = (d.status||'') + ' · ' + ms + 'ms' + (d.latency_ms?(' · server '+d.latency_ms+'ms'):'');
    out.textContent = JSON.stringify(d,null,2);
    if(d.status==='pending_approval'){ toast('Needs approval'); }
  }catch(e){ out.textContent = 'Error: '+e.message; }
}

function renderConnectTab(d, conn){
  const box = document.getElementById('connect-body');
  if(d.auth.type==='none'){
    box.innerHTML = '<div class="panel" style="border-radius:12px"><div class="panel-b">'+
      '<p style="margin:0 0 6px"><b>Public app</b></p>'+
      '<p class="muted" style="margin:0;font-size:13px">No credentials needed. Run any action right away.</p></div></div>';
    return;
  }
  if(conn){
    box.innerHTML = '<div class="panel" style="border-radius:12px"><div class="panel-b">'+
      '<p style="margin:0 0 4px"><b>Connected</b></p>'+
      '<p class="muted tiny" style="margin:0">Scopes: '+esc((conn.scopes||[]).join(' ')||'—')+'</p></div></div>';
    return;
  }
  if(d.auth.type==='oauth2'){
    const ready = d.configured;
    box.innerHTML = '<div class="panel" style="border-radius:12px"><div class="panel-b">'+
      '<p style="margin:0 0 8px"><b>Sign in with '+esc(d.name)+'</b></p>'+
      '<p class="muted" style="margin:0 0 14px;font-size:13px">Tony redirects the user to '+esc(d.name)+
      ', then stores the tokens encrypted on this server.</p>'+
      (ready?'<button class="btn small" onclick="startConnect()">Connect '+esc(d.name)+'</button>'
            :'<div class="snippet">Set '+esc(d.auth.client_id_env||'CLIENT_ID')+' and '+
             esc(d.auth.client_secret_env||'CLIENT_SECRET')+' in the environment, then restart Tony.</div>')+
      '</div></div>';
    return;
  }
  box.innerHTML = '<div class="panel" style="border-radius:12px"><div class="panel-b">'+
    '<p style="margin:0 0 10px"><b>Add your '+esc(d.name)+' key</b></p>'+
    '<div class="field"><label>API key / token</label><input class="input" id="k-val" placeholder="paste the key"></div>'+
    '<button class="btn small" onclick="saveKey()">Save key</button>'+
    '<p class="muted tiny" style="margin:10px 0 0">Stored encrypted with Fernet. Never shown again.</p></div></div>';
}

async function startConnect(){
  const r = await fetch(BASE+'/v1/connections/'+CUR.slug+'/start?entity_id=default',{method:'POST',headers:headers()});
  const d = await r.json();
  if(d.authorization_url){ location.href = d.authorization_url; }
  else { toast(d.detail||'Could not start'); }
}
async function saveKey(){
  const val = document.getElementById('k-val').value.trim();
  if(!val){ toast('Paste a key first'); return }
  const r = await fetch(BASE+'/v1/connections/'+CUR.slug+'/key',{method:'POST',headers:headers(),
    body:JSON.stringify({entity_id:'default', values:{api_key:val, access_token:val, token:val}, label:'api key'})});
  const d = await r.json();
  if(d.connection){ toast('Connected'); closeDrawer(); loadConns(); }
  else toast(d.detail||'Failed');
}
function closeDrawer(){document.getElementById('drawer').classList.remove('on')}

async function loadRuns(){
  const r = await fetch(BASE+'/v1/runs?limit=40'); const d = await r.json();
  const runs = d.runs||[];
  const ok = runs.filter(x=>x.status==='success');
  const avg = ok.length ? Math.round(ok.reduce((s,x)=>s+(x.latency_ms||0),0)/ok.length) : 0;
  document.getElementById('runstats').innerHTML =
    '<div class="statcard"><b>'+runs.length+'</b><span>recent runs</span></div>'+
    '<div class="statcard"><b>'+ok.length+'</b><span>successful</span></div>'+
    '<div class="statcard"><b>'+avg+'ms</b><span>avg latency</span></div>'+
    '<div class="statcard"><b>'+runs.reduce((s,x)=>s+(x.chars||0),0).toLocaleString()+'</b><span>chars returned</span></div>';
  const box = document.getElementById('runs');
  if(!runs.length){box.innerHTML='<div class="empty">No runs yet.</div>';return}
  box.innerHTML = runs.map(x=>'<div class="rowline">'+
    '<span class="mono-sm" style="width:64px;color:var(--muted)">'+(x.created_at||'').slice(11,19)+'</span>'+
    '<b style="width:210px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(x.app)+'.'+esc(x.action)+'</b>'+
    '<span class="badge '+esc(x.tier)+'">'+esc(x.tier)+'</span>'+
    '<span class="grow muted tiny">'+esc(x.status)+(x.error?(' · '+esc(x.error)):'')+'</span>'+
    '<span class="mono-sm muted">'+(x.latency_ms||0)+'ms</span></div>').join('');
}

async function loadTriggers(){
  const r = await fetch(BASE+'/v1/triggers'); const d = await r.json();
  const box = document.getElementById('triggers');
  if(!d.triggers.length){box.innerHTML='<div class="empty">None yet</div>';return}
  box.innerHTML = d.triggers.map(t=>'<div class="rowline"><b>'+esc(t.action)+'</b>'+
    '<span class="badge '+(t.enabled?'ok':'')+'">'+(t.enabled?'on':'off')+'</span>'+
    '<span class="grow muted tiny">every '+t.interval_seconds+'s</span>'+
    '<button class="btn ghost small" data-tdel="'+esc(t.id)+'">Delete</button></div>').join('');
  box.querySelectorAll('[data-tdel]').forEach(b=>b.onclick=async()=>{
    await fetch(BASE+'/v1/triggers/'+b.dataset.tdel,{method:'DELETE'}); loadTriggers();
  });
}
async function createTrigger(){
  const action = document.getElementById('tr-action').value.trim();
  let args = {};
  try{ args = JSON.parse(document.getElementById('tr-args').value||'{}') }catch(e){ toast('Args must be JSON'); return }
  const r = await fetch(BASE+'/v1/triggers',{method:'POST',headers:headers(),body:JSON.stringify({
    action, args, interval_seconds: parseInt(document.getElementById('tr-int').value||'300',10),
    webhook_url: document.getElementById('tr-hook').value.trim()})});
  const d = await r.json();
  if(d.id){ toast('Trigger created'); loadTriggers(); } else toast(d.detail||'Failed');
}

loadApps(true);
</script>
</body></html>"""


def landing_html(demo_open: bool = True) -> str:
    return LANDING.replace("__CSS__", BASE_CSS)


def dashboard_html(key: str = "", workspace_id: str = "", demo_open: bool = True) -> str:
    from .config import settings
    html = DASH.replace("__CSS__", BASE_CSS).replace("__KEY__", key).replace("__BASE__", settings.base_url)
    return html
