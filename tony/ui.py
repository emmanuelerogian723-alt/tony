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
.logo-mark{width:26px;height:26px;border-radius:8px;display:block}
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
/* billing + sessions */
.planhero{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding:22px 24px;border-radius:var(--r-lg);
  background:linear-gradient(140deg,#0a0a0a,#232326);color:#fff;margin-bottom:16px}
.planhero .amt{font-size:34px;font-weight:720;letter-spacing:-.04em;line-height:1}
.planhero .sub{font-size:12.5px;opacity:.72}
.planhero .pill{background:rgba(255,255,255,.14);color:#fff}
.meters{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px}
.meter{background:#fff;border:1px solid var(--line);border-radius:var(--r);padding:14px 16px}
.meter .k{font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);font-weight:600}
.meter .v{font-size:19px;font-weight:680;letter-spacing:-.03em;margin-top:4px;font-variant-numeric:tabular-nums}
.bar{height:6px;border-radius:999px;background:var(--soft);margin-top:9px;overflow:hidden}
.bar span{display:block;height:100%;background:var(--ink);border-radius:999px;transition:width .5s var(--ease)}
.bar.warn span{background:#b45309}
.plangrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.plan{border:1px solid var(--line);border-radius:var(--r-lg);padding:20px;background:#fff;display:flex;flex-direction:column;gap:10px}
.plan.mid{border-color:var(--ink);box-shadow:var(--shadow)}
.plan h3{font-size:16px}
.plan .p{font-size:26px;font-weight:720;letter-spacing:-.04em}
.plan .p small{font-size:12px;font-weight:500;color:var(--muted);letter-spacing:0}
.plan ul{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:7px}
.plan li{font-size:12.8px;color:var(--ink-2);padding-left:18px;position:relative}
.plan li:before{content:"✓";position:absolute;left:0;color:var(--green);font-weight:700}
@media(max-width:640px){.planhero .amt{font-size:28px}}
</style></head>
<body>
<div class="shell">
  <aside class="side">
    <div class="logo"><img class="logo-mark" src="/static/brand/tony-mark.svg" alt="" width="26" height="26"><span>Tony</span></div>
    <div class="nav-item active" data-page="apps"><span class="i">▦</span><span>Apps</span></div>
    <div class="nav-item" data-page="agent"><span class="i">✳</span><span>Agent</span></div>
    <div class="nav-item" data-page="connections"><span class="i">🔗</span><span>Connections</span></div>
    <div class="nav-item" data-page="runs"><span class="i">⟳</span><span>Runs</span></div>
    <div class="nav-item" data-page="triggers"><span class="i">⚡</span><span>Triggers</span></div>
    <div class="nav-item" data-page="sessions"><span class="i">◎</span><span>Sessions</span></div>
    <div class="nav-item" data-page="developers"><span class="i">{ }</span><span>Developers</span></div>
    <div class="nav-item" data-page="billing"><span class="i">₦</span><span>Billing</span></div>
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
      <section class="page" id="page-agent">
        <div class="head"><div><h2>Agent</h2><p>Give it an outcome. It plans across apps, runs the calls, and shows the receipts.</p></div></div>
        <div class="grid2" style="grid-template-columns:1.15fr .85fr">
          <div class="panel"><div class="panel-h"><b>Goal</b><span class="tiny muted">writes need approval</span></div>
            <div class="panel-b">
              <textarea id="ag-goal" class="input" rows="4" style="width:100%;resize:vertical;font-family:var(--mono);font-size:12.5px"
                placeholder="e.g. check the top hacker news stories and summarise the best three"></textarea>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">
                <button class="btn" id="ag-run">Run agent</button>
                <button class="btn ghost" id="ag-write">Allow writes</button>
                <button class="btn ghost" id="ag-clear">Clear</button>
              </div>
              <div class="tiny muted" style="margin-top:10px">Try: <span id="ag-eg"></span></div>
            </div>
          </div>
          <div class="panel"><div class="panel-h"><b>Answer</b><span class="tiny muted" id="ag-engine"></span></div>
            <div class="panel-b"><div id="ag-answer" style="font-size:13px;line-height:1.6">No run yet.</div></div>
          </div>
        </div>
        <div class="panel" style="margin-top:14px"><div class="panel-h"><b>Steps</b><span class="tiny muted">app.action, status, latency</span></div>
          <div class="panel-b" id="ag-steps"><p class="tiny muted">Nothing has run.</p></div>
        </div>
      </section>
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
      <!-- SESSIONS -->
      <section class="page" id="page-sessions">
        <div class="head"><div><h2>Sessions</h2><p>One session per end-user: pinned identity, app allowlist, tier limit and a run budget.</p></div>
          <button class="btn ghost small" onclick="loadSessions()">Refresh</button></div>
        <div class="grid2">
          <div class="panel"><div class="panel-h"><b>New session</b></div><div class="panel-b">
            <div class="field"><label>End-user identity</label><input class="input" id="se-entity" placeholder="user_42"></div>
            <div class="field"><label>Label</label><input class="input" id="se-label" placeholder="Support bot for Ada"></div>
            <div class="field"><label>Allowed apps (comma separated, empty = all)</label><input class="input" id="se-apps" placeholder="gmail, slack"></div>
            <div class="field"><label>Allowed tiers</label>
              <div style="display:flex;gap:14px;margin-top:6px" class="tiny">
                <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="se-t-read" checked> read</label>
                <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="se-t-write" checked> write</label>
                <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="se-t-dest"> destructive</label>
              </div></div>
            <div class="field" style="display:flex;gap:10px">
              <div style="flex:1"><label>TTL (hours)</label><input class="input" id="se-ttl" value="24"></div>
              <div style="flex:1"><label>Run budget (0 = plan)</label><input class="input" id="se-limit" value="0"></div>
            </div>
            <button class="btn small" onclick="createSession()">Create session</button>
            <p class="muted tiny" style="margin:10px 0 0">Send <code>X-Tony-Session: &lt;id&gt;</code> with any call. The workspace key stays on your server.</p>
          </div></div>
          <div class="panel"><div class="panel-h"><b>Active sessions</b><span class="tiny muted" id="se-count" style="margin-left:auto"></span></div>
            <div id="sessions"><div class="empty">None yet</div></div></div>
        </div>
      </section>
      <!-- BILLING -->
      <section class="page" id="page-billing">
        <div class="head"><div><h2>Billing</h2><p>Free covers a real product. Upgrade only when volume says so.</p></div>
          <button class="btn ghost small" onclick="loadBilling()">Refresh</button></div>
        <div id="billing-hero"></div>
        <div class="meters" id="billing-meters"></div>
        <div class="plangrid" id="billing-plans"></div>
        <div class="grid2" style="margin-top:16px">
          <div class="panel"><div class="panel-h"><b>Pass code</b></div><div class="panel-b">
            <p class="muted tiny" style="margin:0 0 10px">Owner-issued codes unlock a tier with no card.</p>
            <div style="display:flex;gap:8px"><input class="input" id="pc-code" placeholder="TONY-…" style="flex:1">
              <button class="btn small" onclick="redeem()">Apply</button></div>
          </div></div>
          <div class="panel"><div class="panel-h"><b>Payments</b></div><div class="panel-b">
            <p class="muted tiny" id="pay-note" style="margin:0">Checking…</p>
            <div id="pay-actions" style="display:flex;gap:8px;margin-top:10px"></div>
          </div></div>
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
  if(el.dataset.page==='agent')mountAgent();
  if(el.dataset.page==='connections')loadConns();
  if(el.dataset.page==='triggers')loadTriggers();
  if(el.dataset.page==='billing')loadBilling();
  if(el.dataset.page==='sessions')loadSessions();
});

const PAGE = 60;

let AG_WRITES = false, AG_ON = false;
const AG_EXAMPLES = [
  'summarise the top hacker news stories right now',
  'find the latest space news and explain it in three lines',
  'what are the top stories on the front page today',
  'look up a random wikipedia article and summarise it'
];
function mountAgent(){
  if(AG_ON) return; AG_ON = true;
  const eg = document.getElementById('ag-eg');
  eg.innerHTML = AG_EXAMPLES.map(x=>'<span class="chip" style="cursor:pointer;margin-right:6px">'+esc(x.split(' ').slice(0,3).join(' '))+'</span>').join('');
  eg.querySelectorAll('.chip').forEach((c,i)=>c.onclick=()=>{document.getElementById('ag-goal').value=AG_EXAMPLES[i]});
  document.getElementById('ag-write').onclick=()=>{
    AG_WRITES=!AG_WRITES;
    document.getElementById('ag-write').textContent = AG_WRITES?'Writes allowed':'Allow writes';
    document.getElementById('ag-write').style.borderColor = AG_WRITES?'var(--ink)':'';
  };
  document.getElementById('ag-clear').onclick=()=>{
    document.getElementById('ag-goal').value='';
    document.getElementById('ag-answer').textContent='No run yet.';
    document.getElementById('ag-engine').textContent='';
    document.getElementById('ag-steps').innerHTML='<p class="tiny muted">Nothing has run.</p>';
  };
  document.getElementById('ag-run').onclick=runAgent;
  document.getElementById('ag-goal').addEventListener('keydown',e=>{
    if((e.metaKey||e.ctrlKey)&&e.key==='Enter') runAgent();
  });
}
async function runAgent(){
  const goal = (document.getElementById('ag-goal').value||'').trim();
  if(!goal){ toast('Describe the outcome first'); return; }
  const btn = document.getElementById('ag-run');
  btn.disabled = true; btn.textContent = 'Thinking…';
  const ans = document.getElementById('ag-answer');
  const steps = document.getElementById('ag-steps');
  ans.innerHTML = '<span class="muted">Planning across the catalogue…</span>';
  steps.innerHTML = '<p class="tiny muted">Running…</p>';
  try{
    const r = await fetch('/v1/agent', {method:'POST', headers:headers(),
      body: JSON.stringify({goal, max_steps: 4, approve_writes: AG_WRITES})});
    const d = await r.json();
    if(!r.ok) throw new Error(d.detail||('HTTP '+r.status));
    document.getElementById('ag-engine').textContent = (d.engine||'') + ' · ' + (d.elapsed_ms||0) + ' ms';
    ans.textContent = d.answer || 'No answer returned.';
    const rows = (d.steps||[]).map(s=>{
      const ok = s.ok;
      return '<div class="row" style="display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-top:1px solid var(--line)">'+
        '<span style="color:'+(ok?'#137a45':'#a33')+';font-size:12px">'+(ok?'OK':'FAIL')+'</span>'+
        '<div style="flex:1;min-width:0"><div class="mono tiny">'+esc(s.app||'-')+'.'+esc(s.action||'-')+'</div>'+
        '<div class="tiny muted" style="margin-top:2px">'+esc((s.error||'').slice(0,180) || ((s.latency_ms||0)+' ms'))+'</div></div></div>';
    }).join('');
    steps.innerHTML = rows || '<p class="tiny muted">The model answered without calling a tool.</p>';
  }catch(e){
    ans.textContent = 'That run failed: ' + e.message;
    steps.innerHTML = '<p class="tiny muted">No calls were recorded.</p>';
  }finally{
    btn.disabled = false; btn.textContent = 'Run agent';
  }
}
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
  const base = (conn && conn.base_url) || '';
  if(conn){
    box.innerHTML = '<div class="panel" style="border-radius:12px"><div class="panel-b">'+
      '<p style="margin:0 0 4px"><b>Connected</b></p>'+
      (base?'<p class="mono-sm" style="margin:0 0 6px;word-break:break-all">'+esc(base)+'</p>':'')+
      '<p class="muted tiny" style="margin:0">Scopes: '+esc((conn.scopes||[]).join(' ')||'—')+'</p>'+
      '<button class="btn small ghost" style="margin-top:12px" onclick="disconnect()">Disconnect</button>'+
      '</div></div>';
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

  const needsBase = !!d.needs_base_url, needsToken = d.auth.type !== 'none';
  let rows = '';
  if(needsBase){
    rows += '<div class="field"><label>API base URL *<span class="hint">https</span></label>'+
      '<input class="input" id="k-base" placeholder="https://api.'+esc(d.slug.replace(/-/g,''))+'.com" autocomplete="off"></div>';
  }
  if(needsToken){
    rows += '<div class="field"><label>'+(needsBase?'Token / API key *':'API key / token *')+'</label>'+
      '<input class="input" id="k-val" type="password" placeholder="paste the key" autocomplete="off"></div>';
  }
  const explain = needsBase
    ? 'This app ships with its documented paths but no fixed host, so Tony needs you to tell it where the API lives. Paths get appended to the base URL you paste here.'
    : 'Stored encrypted with Fernet on this server. Never shown again.';
  box.innerHTML = '<div class="panel" style="border-radius:12px"><div class="panel-b">'+
    '<p style="margin:0 0 6px"><b>'+(needsBase?'Point Tony at ':'Add your ')+esc(d.name)+'</b></p>'+
    '<p class="muted tiny" style="margin:0 0 14px">'+esc(explain)+'</p>'+ rows +
    '<button class="btn small" onclick="saveKey()">Save connection</button>'+
    (d.docs?'<p class="muted tiny" style="margin:10px 0 0">Base URL is in the vendor docs: '+
      '<a href="'+esc(d.docs)+'" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline">'+esc(d.docs)+'</a></p>':'')+
    '</div></div>';
}

async function startConnect(){
  const r = await fetch(BASE+'/v1/connections/'+CUR.slug+'/start?entity_id=default',{method:'POST',headers:headers()});
  const d = await r.json();
  if(d.authorization_url){ location.href = d.authorization_url; }
  else { toast(d.detail||'Could not start'); }
}
async function saveKey(){
  const values = {};
  const baseEl = document.getElementById('k-base');
  const keyEl = document.getElementById('k-val');
  if(baseEl){
    const b = baseEl.value.trim();
    if(!b){ toast('Paste the API base URL'); return }
    values.base_url = b;
  }
  if(keyEl){
    const v = keyEl.value.trim();
    if(!v && CUR.auth.type!=='none'){ toast('Paste a key first'); return }
    if(v){ values.api_key = v; values.token = v; values.access_token = v; }
  }
  const btn = event && event.target; if(btn) btn.disabled = true;
  const r = await fetch(BASE+'/v1/connections/'+CUR.slug+'/key',{method:'POST',headers:headers(),
    body:JSON.stringify({entity_id:'default', values, label:'console'})});
  const d = await r.json().catch(()=>({}));
  if(btn) btn.disabled = false;
  if(d.connection){ toast('Connected'); closeDrawer(); loadConns(); openApp(CUR.slug); }
  else toast(d.detail||'Failed');
}

async function disconnect(){
  await fetch(BASE+'/v1/connections/'+CUR.slug+'?entity_id=default',{method:'DELETE',headers:headers()});
  toast('Disconnected'); loadConns(); closeDrawer();
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




def dashboard_html(key: str = "", workspace_id: str = "", demo_open: bool = True) -> str:
    from .config import settings
    html = DASH.replace("__CSS__", BASE_CSS).replace("__KEY__", key).replace("__BASE__", settings.base_url)
    return html
