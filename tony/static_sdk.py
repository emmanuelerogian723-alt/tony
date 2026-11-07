"""The /sdk download page: five clients, one API surface."""
from __future__ import annotations


def sdk_html() -> str:
    rows = [
        ("Python", "tony_sdk.py", "pip install tony-gateway", "tony_sdk.py",
         'from tony_sdk import Tony\ntony = Tony("tk_live_...")\ntony.execute("github.list_repos", per_page=3)'),
        ("TypeScript", "tony.ts", "npm i tony-sdk", "tony.ts",
         'const tony = new Tony(key);\nawait tony.execute("github.list_repos", { per_page: 3 });'),
        ("JavaScript", "tony.js", "import { Tony } from 'tony-sdk'", "tony.js",
         'const tony = new Tony(key);\nawait tony.batch([{ action: "hackernews.top_stories" }]);'),
        ("Go", "tony.go", "go get github.com/emmanuelerogian723-alt/tony/sdk/go", "tony.go",
         'c := tony.New(key)\nres, err := c.Execute(ctx, "github.list_repos", map[string]any{"per_page": 3}, false)'),
        ("Java", "Tony.java", "maven: dev.tony:tony-sdk:1.0.0", "Tony.java",
         'Tony tony = new Tony(key);\ntony.execute("github.list_repos", Map.of("per_page", 3), false);'),
    ]
    cards = "".join(
        f"""<article class="card">
      <div class="top"><h2>{name}</h2><a class="dl" href="/sdk/{file}">Download</a></div>
      <code class="inst">{inst}</code>
      <pre>{code}</pre>
    </article>"""
        for name, file, inst, _label, code in rows
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tony SDKs</title><style>
:root{{--ink:#09090B;--muted:#71717A;--line:rgba(9,9,11,.1);--signal:#E2542B}}
*{{box-sizing:border-box}}body{{margin:0;background:#fff;color:var(--ink);
font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:44px 20px 80px}}
a{{color:inherit}}nav a{{color:var(--muted);text-decoration:none;margin-right:16px;font-size:14px}}
h1{{font-size:clamp(30px,5vw,46px);letter-spacing:-.03em;margin:26px 0 10px;line-height:1.08}}
p.lede{{color:var(--muted);max-width:62ch;margin:0 0 30px}}
.grid{{display:grid;gap:16px;grid-template-columns:1fr}}
@media(min-width:860px){{.grid{{grid-template-columns:1fr 1fr}}}}
.card{{border:1px solid var(--line);border-radius:14px;padding:20px;background:#fff;
box-shadow:0 1px 2px rgba(9,9,11,.04)}}
.card .top{{display:flex;align-items:center;justify-content:space-between;gap:12px}}
.card h2{{font-size:17px;margin:0;letter-spacing:-.01em}}
.dl{{font-size:12.5px;color:var(--signal);text-decoration:none;border:1px solid var(--line);
padding:5px 10px;border-radius:999px}}
.inst{{display:block;color:var(--muted);font-size:12px;margin:10px 0 8px;font-family:ui-monospace,monospace}}
pre{{margin:0;background:#FAFAFA;border:1px solid var(--line);border-radius:10px;padding:13px;
overflow-x:auto;font-size:12.2px;line-height:1.55;font-family:ui-monospace,monospace}}
.plug{{margin-top:28px;border:1px solid var(--line);border-radius:14px;padding:20px;background:#FAFAFA}}
.plug b{{display:block;margin-bottom:8px}}
.plug span{{display:inline-block;font-size:12.5px;color:var(--muted);margin:0 12px 8px 0}}
</style></head><body><div class="wrap">
<nav><a href="/">Tony</a><a href="/app">Console</a><a href="/docs">API</a></nav>
<h1>One API. Five clients.<br>No dependencies.</h1>
<p class="lede">Every SDK wraps the same four calls: execute, batch, tools and connections.
Vendor the single file if you like; nothing here phones home.</p>
<div class="grid">{cards}</div>
<div class="plug"><b>Framework plugins</b>
<span>LangChain</span><span>LlamaIndex</span><span>CrewAI</span><span>Vercel AI SDK</span>
<span>OpenAI Agents</span><span>Anthropic tool use</span><span>Claude Desktop</span>
<span>Cursor</span><span>MCP (HTTP + stdio)</span><span>CLI</span></div>
</div></body></html>"""
