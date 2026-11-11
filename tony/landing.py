"""Tony landing page.

Palette: black, electric blue, white. Every shape on the page is drawn with
CSS or inline SVG (rings, arcs, grids, crosshairs, connectors), no stock art.
Motion is deliberate: orbits that show multi-app execution, dashed lines that
draw themselves, counters that tick up, and a cursor light that stays subtle.
"""

from __future__ import annotations

from html import escape


def _counts(apps) -> tuple[dict[str, int], dict[str, int]]:
    by_source: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    for app in apps:
        key = getattr(app, "source", "curated")
        by_source[key] = by_source.get(key, 0) + 1
        for action in app.actions:
            by_tier[action.tier] = by_tier.get(action.tier, 0) + 1
    return by_source, by_tier


def _pricing_html() -> str:
    from .billing import PLANS

    tick = ('<svg class="tick" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="3" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>')
    out = []
    for pid in ("free", "pro", "business"):
        p = PLANS[pid]
        hot = pid == "pro"
        price = (f'<b>\u20a6{p["price_ngn"]:,}</b><span>per month</span>' if p["price_ngn"]
                 else '<b>\u20a60</b><span>forever</span>')
        cta = ('<a class="btn ghost wide" href="/app">Start free</a>' if not p["price_ngn"]
               else f'<a class="btn {"solid" if hot else "ghost"} wide" href="/app#billing">Choose {p["name"]}</a>')
        items = "".join(f'<li>{tick}<span>{escape(h)}</span></li>' for h in p["highlights"])
        out.append(f"""<article class="tier{' hot' if hot else ''}">
      {'<span class="flag">most chosen</span>' if hot else ''}
      <div class="tname">{escape(p['name'])}</div>
      <div class="tag">{escape(p['tagline'])}</div>
      <div class="amt">{price}</div>
      <ul>{items}</ul>
      <div class="foot">{cta}</div>
    </article>""")
    return "".join(out)


def _ticker() -> str:
    names = ["GitHub", "Gmail", "Slack", "Notion", "Stripe", "Paystack", "Shopify", "Linear", "Vercel",
             "Cloudflare", "Supabase", "Airtable", "HubSpot", "Salesforce", "Figma", "Dropbox", "Twilio",
             "SendGrid", "OpenAI", "Anthropic", "Discord", "Telegram", "TikTok", "YouTube", "Spotify",
             "Google Sheets", "Google Calendar", "Google Drive", "WhatsApp", "Jira", "Trello", "Asana",
             "Zendesk", "Intercom", "Plaid", "Razorpay", "Mailchimp", "Reddit", "Mastodon", "Hacker News"]
    cells = "".join(f'<span>{escape(n)}<i></i></span>' for n in names)
    return f'<div class="tape" aria-hidden="true"><div class="tape-track">{cells}{cells}</div></div>'


CSS = """
:root{
  /* paper + ink + sky: the 2f6bff accent is retired but kept for reference */
  --black:#f7f8fa; --coal:#ffffff; --slate:#f1f3f6; --slate-2:#e9edf2;
  --blue:#0284c7; --blue-2:#0ea5e9; --blue-3:#7dd3fc; --blue-deep:#e0f2fe;
  --white:#ffffff; --ink:#0a0c11; --ink-2:#3b4451; --mut:#5f6875; --dim:#8b939f;
  --line:rgba(10,12,17,.10); --line-2:rgba(10,12,17,.16); --line-blue:rgba(14,165,233,.40);
  --display:"Bricolage Grotesque","Inter Tight",system-ui,sans-serif;
  --ui:"Manrope","Inter Tight",system-ui,-apple-system,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --r:14px; --r-lg:22px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;overflow-x:clip;background:var(--black)}
body{margin:0;background:var(--black);color:var(--ink);font-family:var(--ui);font-size:15.5px;line-height:1.62;
  -webkit-font-smoothing:antialiased;overflow-x:clip}
::selection{background:var(--blue);color:#fff}
.mono{font-family:var(--mono)}
a{color:inherit;text-decoration:none}
h1,h2,h3{margin:0;font-weight:600}
p{margin:0}
svg{display:block}

/* ── backdrop: real geometry ───────────────────────────────────────────── */
.back{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;background:
  radial-gradient(1100px 620px at 50% -12%,rgba(14,165,233,.20),transparent 66%),
  radial-gradient(760px 560px at 92% 8%,rgba(14,165,233,.10),transparent 70%),var(--black)}
.back .mesh{position:absolute;inset:0;background-image:
  linear-gradient(to right,rgba(10,12,17,.055) 1px,transparent 1px),
  linear-gradient(to bottom,rgba(10,12,17,.055) 1px,transparent 1px);
  background-size:58px 58px;
  -webkit-mask-image:radial-gradient(ellipse 80% 62% at 50% 0%,#000 8%,transparent 76%);
  mask-image:radial-gradient(ellipse 80% 62% at 50% 0%,#000 8%,transparent 76%)}
.back .ring{position:absolute;border-radius:50%;border:1px solid rgba(10,12,17,.075)}
.back .r1{width:1280px;height:1280px;left:50%;top:-880px;transform:translateX(-50%)}
.back .r2{width:940px;height:940px;left:50%;top:-700px;transform:translateX(-50%);
  border-color:rgba(14,165,233,.24)}
.back .r3{width:640px;height:640px;left:50%;top:-520px;transform:translateX(-50%);
  border-style:dashed;border-color:rgba(10,12,17,.10);animation:spin 120s linear infinite}
.back .arc{position:absolute;border-radius:50%;border:2px solid transparent;
  border-top-color:rgba(14,165,233,.55);border-right-color:rgba(14,165,233,.15);
  width:1500px;height:1500px;left:50%;top:-1080px;transform:translateX(-50%);
  animation:spin 60s linear infinite;filter:drop-shadow(0 0 18px rgba(14,165,233,.35))}
.back .pluses{position:absolute;inset:0;background-image:none}
@keyframes spin{to{transform:translateX(-50%) rotate(360deg)}}
.cross{position:absolute;width:12px;height:12px;opacity:.35}
.cross::before,.cross::after{content:"";position:absolute;background:var(--blue-2)}
.cross::before{left:5px;top:0;width:1.5px;height:12px}
.cross::after{top:5px;left:0;height:1.5px;width:12px}
.c1{left:7vw;top:22vh}.c2{right:9vw;top:34vh}.c3{left:16vw;top:68vh}.c4{right:18vw;top:76vh}

.cursorlight{position:fixed;inset:0;z-index:1;pointer-events:none;
  background:radial-gradient(420px circle at var(--mx,50%) var(--my,0%),rgba(14,165,233,.13),transparent 68%)}

/* ── chrome ────────────────────────────────────────────────────────────── */
.wrap{width:min(1160px,91vw);margin-inline:auto;position:relative;z-index:2}
.top{position:sticky;top:0;z-index:50;border-bottom:1px solid var(--line);
  background:rgba(255,255,255,.80);backdrop-filter:blur(20px) saturate(150%)}
.top .wrap{height:64px;display:flex;align-items:center;gap:20px}
.mark{display:flex;align-items:center;gap:9px;font-weight:700;letter-spacing:-.02em;font-size:16.5px}
.mark .dish{width:27px;height:27px}
.top nav{display:flex;gap:22px;margin-left:16px}
.top nav a{font-size:13.5px;color:var(--ink-2);position:relative;padding:4px 0}
.top nav a::after{content:"";position:absolute;left:0;right:100%;bottom:0;height:1px;background:var(--blue-2);
  transition:right .25s}
.top nav a:hover{color:#fff}
.top nav a:hover::after{right:0}
.grow{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:42px;padding:0 18px;
  border-radius:10px;border:1px solid var(--line-2);background:rgba(10,12,17,.03);color:#fff;
  font-family:var(--ui);font-weight:600;font-size:13.5px;cursor:pointer;
  transition:transform .16s,background .2s,border-color .2s,box-shadow .25s}
.btn:hover{transform:translateY(-1px);background:rgba(10,12,17,.07);border-color:rgba(10,12,17,.32)}
.btn.solid{background:var(--blue);border-color:transparent;
  box-shadow:0 10px 30px -12px rgba(14,165,233,.95),inset 0 1px 0 rgba(10,12,17,.28)}
.btn.solid:hover{background:#3f79ff;box-shadow:0 16px 40px -12px rgba(14,165,233,1),inset 0 1px 0 rgba(10,12,17,.3)}
.btn.ghost{background:transparent}
.btn.sm{height:35px;padding:0 14px;font-size:12.5px;border-radius:9px}
.btn.wide{width:100%}
@media (max-width:980px){.top nav{display:none}}
@media (max-width:560px){.top .signin{display:none}.top .wrap{height:58px;gap:10px}}
.top .btn{white-space:nowrap}

/* ── hero ──────────────────────────────────────────────────────────────── */
.hero{padding:clamp(48px,7vw,92px) 0 0}
.tag{display:inline-flex;align-items:center;gap:10px;height:31px;padding:0 14px 0 10px;border-radius:999px;
  border:1px solid var(--line-blue);background:rgba(14,165,233,.10);font-family:var(--mono);font-size:10.5px;
  letter-spacing:.14em;text-transform:uppercase;color:var(--blue-3)}
.tag .led{width:6px;height:6px;border-radius:50%;background:var(--blue-2);box-shadow:0 0 0 4px rgba(14,165,233,.18);
  animation:led 2.6s ease-in-out infinite}
@keyframes led{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.45;transform:scale(.86)}}
.hero h1{font-family:var(--display);font-weight:600;font-size:clamp(38px,6.2vw,74px);line-height:1.06;padding-bottom:.06em;
  letter-spacing:-.035em;margin:20px 0 0;max-width:16ch}
.hero h1 .blue{color:var(--blue-2)}
.hero h1 .line{display:block}
.lede{margin-top:22px;max-width:54ch;color:var(--ink-2);font-size:clamp(15px,1.5vw,17px)}
.hero .row{display:flex;flex-wrap:wrap;gap:11px;align-items:center;margin-top:26px}
.hero .hint{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.03em}
.hero-grid{display:grid;grid-template-columns:1.02fr .98fr;gap:clamp(26px,4vw,52px);align-items:center}
@media (max-width:960px){.hero-grid{grid-template-columns:1fr}}

/* search */
.find{margin-top:28px;position:relative;display:flex;align-items:center;gap:10px;padding:6px 6px 6px 15px;
  border:1px solid var(--line-2);border-radius:13px;background:rgba(12,12,18,.9);
  box-shadow:0 0 0 1px rgba(14,165,233,.10),0 22px 50px -30px rgba(14,165,233,.7)}
.find:focus-within{border-color:var(--line-blue);box-shadow:0 0 0 3px rgba(14,165,233,.14),0 22px 50px -30px rgba(14,165,233,.8)}
.find svg{color:var(--blue-2);flex:none}
.find input{flex:1;min-width:0;border:0;outline:0;background:none;color:#fff;font-family:var(--mono);
  font-size:13px;padding:13px 0}
.find input::placeholder{color:var(--dim)}
.find button{flex:none;height:40px;padding:0 16px;border:0;border-radius:9px;background:var(--blue);color:#fff;
  font-family:var(--ui);font-weight:600;font-size:13px;cursor:pointer}
.quicks{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px}
.quicks span{font-family:var(--mono);font-size:11px;color:var(--ink-2);border:1px solid var(--line);
  border-radius:999px;padding:5px 11px;cursor:pointer;transition:border-color .18s,color .18s,background .18s}
.quicks span:hover{border-color:var(--line-blue);color:#fff;background:rgba(14,165,233,.12)}
.hits{margin-top:10px}
.hit{display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;
  background:rgba(10,12,17,.022);margin-top:6px;animation:pop .3s cubic-bezier(.2,.7,.3,1) both}
.hit .slug{font-family:var(--mono);font-size:11px;color:var(--blue-2)}
.hit .nm{font-size:13px;color:var(--ink)}
.hit .cat{margin-left:auto;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--dim)}
@keyframes pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

/* orbit diagram: apps orbiting one executor */
.orbit{position:relative;width:100%;max-width:460px;aspect-ratio:1/1;margin-inline:auto;display:grid;place-items:center}
.orbit .halo{position:absolute;inset:0;border-radius:50%;
  background:radial-gradient(circle at 50% 50%,rgba(14,165,233,.22),transparent 62%)}
.orbit .track{position:absolute;inset:0;border-radius:50%;border:1px solid rgba(10,12,17,.09)}
.orbit .t2{inset:13%;border-color:rgba(14,165,233,.28);border-style:dashed;animation:spin2 46s linear infinite}
.orbit .t3{inset:27%;border-color:rgba(10,12,17,.12)}
@keyframes spin2{to{transform:rotate(360deg)}}
.orbit .core{position:relative;width:36%;aspect-ratio:1;border-radius:50%;
  background:radial-gradient(circle at 34% 28%,#2a5cf0,#0a1b46 68%);
  border:1px solid rgba(157,186,255,.5);display:grid;place-items:center;text-align:center;
  box-shadow:0 0 0 8px rgba(14,165,233,.08),0 26px 70px -22px rgba(14,165,233,.95),inset 0 1px 0 rgba(10,12,17,.35)}
.orbit .core b{font-family:var(--display);font-size:clamp(18px,2.6vw,26px);letter-spacing:-.02em;line-height:1}
.orbit .core span{display:block;margin-top:5px;font-family:var(--mono);font-size:9px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--blue-3)}
.orbit .node{position:absolute;width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
  background:#0a0a11;border:1px solid var(--line-2);font-family:var(--mono);font-size:10px;color:var(--ink-2);
  box-shadow:0 10px 24px -14px #000}
.orbit .n1{top:-4%;left:48%}.orbit .n2{top:22%;right:-2%}.orbit .n3{bottom:16%;right:2%}
.orbit .n4{bottom:-4%;left:46%}.orbit .n5{bottom:20%;left:-2%}.orbit .n6{top:24%;left:0%}
.orbit .sat{position:absolute;inset:0;animation:spin2 30s linear infinite}
.orbit .sat i{position:absolute;top:-3px;left:50%;width:7px;height:7px;margin-left:-3.5px;border-radius:50%;
  background:var(--blue-2);box-shadow:0 0 12px var(--blue)}

/* terminal */
.term{position:relative;border:1px solid var(--line-2);border-radius:16px;overflow:hidden;background:#07070b;
  box-shadow:0 40px 90px -50px rgba(14,165,233,.8),0 26px 60px -40px #000}
.term .bar{display:flex;align-items:center;gap:8px;padding:11px 14px;border-bottom:1px solid var(--line);
  background:rgba(10,12,17,.025)}
.term .bar i{width:8px;height:8px;border-radius:50%;background:#26262f}
.term .bar i:first-child{background:var(--blue)}
.term .bar .file{margin-left:6px;font-family:var(--mono);font-size:11px;color:var(--dim)}
.term pre{margin:0;padding:16px 16px 18px;font-family:var(--mono);font-size:12.2px;line-height:1.8;
  color:#d6dbe6;overflow-x:auto}
.term .k{color:#8fb0ff}.term .s{color:#c9d7ff}.term .f{color:#6f9bff}.term .c{color:#5b6272}.term .n{color:#fff}
.term .run{border-top:1px solid var(--line);padding:11px 16px;display:flex;align-items:center;gap:9px;
  font-family:var(--mono);font-size:10.5px;color:var(--ink-2);background:rgba(14,165,233,.07)}
.term .run b{color:#fff}
.term .run .dot{width:6px;height:6px;border-radius:50%;background:#41d18a;box-shadow:0 0 9px #41d18a}

/* stats */
.tally{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:clamp(38px,5.5vw,66px);
  border:1px solid var(--line);border-radius:var(--r);overflow:hidden;background:var(--line)}
.tally div{background:var(--coal);padding:20px 18px}
.tally b{display:block;font-family:var(--display);font-weight:600;font-size:clamp(25px,3.2vw,35px);
  line-height:1;letter-spacing:-.03em;color:#fff}
.tally span{display:block;margin-top:8px;font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--dim)}
@media (max-width:720px){.tally{grid-template-columns:1fr 1fr}}

/* tape */
.tape{margin-top:clamp(40px,6vw,68px);border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  overflow:hidden;position:relative;background:#060609}
.tape::before,.tape::after{content:"";position:absolute;top:0;bottom:0;width:120px;z-index:2;pointer-events:none}
.tape::before{left:0;background:linear-gradient(90deg,#040406,transparent)}
.tape::after{right:0;background:linear-gradient(270deg,#040406,transparent)}
.tape-track{display:flex;width:max-content;animation:tape 56s linear infinite}
.tape:hover .tape-track{animation-play-state:paused}
@keyframes tape{to{transform:translate3d(-50%,0,0)}}
.tape span{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:11px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--dim);padding:12px 20px;border-right:1px solid var(--line);white-space:nowrap}
.tape span i{width:5px;height:5px;border-radius:50%;background:rgba(14,165,233,.7)}
.tape span:hover{color:#fff}

/* sections */
.sec{padding:clamp(58px,8vw,104px) 0;position:relative}
.head{max-width:62ch}
.kick{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:10px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--blue-2)}
.kick::after{content:"";height:1px;width:96px;background:linear-gradient(90deg,rgba(14,165,233,.65),transparent)}
h2{font-family:var(--display);font-weight:600;font-size:clamp(28px,4vw,46px);line-height:1.06;
  letter-spacing:-.03em;margin:14px 0 0}
h2 .blue{color:var(--blue-2)}
.sub{margin-top:14px;color:var(--mut);max-width:56ch}

.steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:32px}
@media (max-width:940px){.steps{grid-template-columns:1fr 1fr}}
@media (max-width:560px){.steps{grid-template-columns:1fr}}
.step{position:relative;padding:20px 18px;border:1px solid var(--line);border-radius:var(--r);background:var(--coal);
  transition:border-color .25s,transform .25s}
.step:hover{border-color:var(--line-blue);transform:translateY(-2px)}
.step .n{font-family:var(--mono);font-size:10px;letter-spacing:.16em;color:var(--blue-2)}
.step b{display:block;margin:9px 0 6px;font-size:14.5px;font-weight:700}
.step p{color:var(--mut);font-size:13px}
.step .wire{position:absolute;top:50%;right:-12px;width:12px;height:1px;background:var(--line-blue)}
.step:last-child .wire{display:none}
@media (max-width:940px){.step .wire{display:none}}

.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin-top:30px}
@media (max-width:900px){.grid3{grid-template-columns:1fr}}
.tile{position:relative;padding:23px 21px;border:1px solid var(--line);border-radius:var(--r);overflow:hidden;
  background:linear-gradient(180deg,rgba(10,12,17,.04),rgba(10,12,17,.012));
  transition:transform .25s,border-color .25s}
.tile:hover{transform:translateY(-3px);border-color:rgba(14,165,233,.45)}
.tile .pic{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;color:var(--blue-2);
  border:1px solid rgba(14,165,233,.35);background:rgba(14,165,233,.10)}
.tile h3{margin:15px 0 7px;font-size:16px;font-weight:700;letter-spacing:-.01em}
.tile p{color:var(--mut);font-size:13.6px}
.tile .meta{margin-top:13px;font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--dim)}

/* comparison */
.compare{margin-top:30px;border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.compare table{width:100%;border-collapse:collapse;font-size:13.4px}
.compare th,.compare td{padding:13px 15px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
.compare th{background:rgba(14,165,233,.08);font-family:var(--mono);font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--blue-3);font-weight:500}
.compare td:first-child{color:var(--ink-2)}
.compare td.tony{color:#fff;background:rgba(14,165,233,.055);font-weight:600}
.compare tr:last-child td{border-bottom:0}
@media (max-width:640px){.compare{overflow-x:auto}.compare table{min-width:560px}}

/* features matrix */
.matrix{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin-top:30px;
  border:1px solid var(--line);border-radius:var(--r);overflow:hidden;background:var(--line)}
@media (max-width:900px){.matrix{grid-template-columns:1fr 1fr}}
@media (max-width:600px){.matrix{grid-template-columns:1fr}}
.cell{background:var(--coal);padding:21px;transition:background .25s}
.cell:hover{background:#0e0e16}
.cell .t{font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--blue-2)}
.cell b{display:block;margin:9px 0 6px;font-size:14.8px;font-weight:700}
.cell p{color:var(--mut);font-size:13.2px}

/* pricing */
.plans{display:grid;gap:13px;grid-template-columns:1fr;margin-top:32px}
@media (min-width:880px){.plans{grid-template-columns:repeat(3,minmax(0,1fr))}}
.tier{position:relative;display:flex;flex-direction:column;gap:13px;min-width:0;padding:25px 21px 20px;
  border:1px solid var(--line);border-radius:var(--r-lg);
  background:linear-gradient(180deg,rgba(10,12,17,.035),rgba(10,12,17,.008));
  transition:transform .25s,border-color .25s,box-shadow .3s}
.tier:hover{transform:translateY(-3px);border-color:var(--line-2)}
.tier.hot{border-color:rgba(14,165,233,.6);background:linear-gradient(180deg,rgba(14,165,233,.13),rgba(10,12,17,.01));
  box-shadow:0 0 0 1px rgba(14,165,233,.25),0 30px 70px -42px rgba(14,165,233,1)}
.tier .flag{position:absolute;top:-10px;right:16px;background:var(--blue);color:#fff;border-radius:999px;
  padding:4px 10px;font-family:var(--mono);font-size:9px;letter-spacing:.14em;text-transform:uppercase}
.tname{font-family:var(--display);font-size:22px;letter-spacing:-.02em}
.tag{color:var(--mut);font-size:13px;min-height:38px;line-height:1.45;white-space:normal;overflow-wrap:anywhere}
.amt{display:flex;align-items:baseline;gap:7px}
.amt b{font-family:var(--display);font-size:38px;line-height:1;letter-spacing:-.03em}
.amt span{font-family:var(--mono);font-size:10.5px;color:var(--dim)}
.tier ul{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.tier li{display:flex;gap:9px;font-size:13px;color:var(--ink-2);line-height:1.45}
.tier li .tick{flex:none;margin-top:2px;color:var(--blue-2)}
.foot{margin-top:auto;padding-top:5px}

/* faq */
.faq{margin-top:28px;border-top:1px solid var(--line)}
.faq details{border-bottom:1px solid var(--line);padding:15px 0}
.faq summary{list-style:none;display:flex;align-items:center;gap:12px;cursor:pointer;font-size:14.8px;font-weight:600}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";margin-left:auto;font-family:var(--mono);color:var(--blue-2);font-size:15px}
.faq details[open] summary::after{content:"-"}
.faq p{margin:9px 0 0;color:var(--mut);font-size:13.8px;max-width:72ch}

/* close */
.final{margin-top:clamp(54px,8vw,96px);position:relative;overflow:hidden;border-radius:24px;padding:clamp(26px,4.6vw,52px);
  border:1px solid rgba(14,165,233,.38);background:
  radial-gradient(600px circle at 12% -30%,rgba(14,165,233,.32),transparent 62%),
  radial-gradient(520px circle at 92% 130%,rgba(14,165,233,.20),transparent 62%),#07070c}
.final::after{content:"";position:absolute;right:-90px;top:-90px;width:280px;height:280px;border-radius:50%;
  border:1px solid rgba(10,12,17,.14);box-shadow:0 0 0 26px rgba(10,12,17,.03),0 0 0 54px rgba(10,12,17,.02)}
.final h2{max-width:17ch}
.final .row{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:24px;position:relative;z-index:2}
.final .mono{font-family:var(--mono);font-size:11px;color:var(--mut)}

footer{border-top:1px solid var(--line);margin-top:64px;padding:26px 0 40px;position:relative;z-index:2}
footer .wrap{display:flex;flex-wrap:wrap;gap:16px;align-items:center}
footer .mono{font-family:var(--mono);font-size:10.5px;color:var(--dim)}
footer a:hover{color:var(--blue-2)}

body{overflow-x:clip}
.tape{overflow:hidden;border-bottom:1px solid #111;padding:17px 0;margin-top:0}
.tape-track{display:flex;width:max-content;animation:slide 42s linear infinite;
 font-family:'JetBrains Mono',monospace;font-size:11.6px;letter-spacing:.06em;text-transform:uppercase;color:#5a5a5a}
.tape-track span{display:inline-flex;align-items:center;gap:34px;padding-right:34px;white-space:nowrap}
.tape-track i{width:3px;height:3px;border-radius:50%;background:#393939;display:block}
@keyframes slide{to{transform:translateX(-50%)}}
@media(prefers-reduced-motion:reduce){.tape-track{animation:none}}
.rv{opacity:0;transform:translateY(16px);transition:opacity .65s cubic-bezier(.2,.7,.3,1),transform .65s cubic-bezier(.2,.7,.3,1)}
.rv.on{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .rv{opacity:1;transform:none}
}

.adv{display:grid;grid-template-columns:repeat(2,1fr);gap:14px;margin-top:26px}
.adv-i{border:1px solid var(--line);border-radius:var(--r);background:var(--coal);padding:20px 20px 18px;
  transition:transform .35s cubic-bezier(.2,.7,.2,1),border-color .35s,box-shadow .35s}
.adv-i:hover{transform:translateY(-3px);border-color:var(--line-blue);box-shadow:0 18px 40px rgba(10,12,17,.07)}
.adv-i h3{font-family:var(--display);font-size:17px;letter-spacing:-.01em;margin-bottom:6px}
.adv-i p{color:var(--ink-2);font-size:14.5px;line-height:1.6}
.pri{margin:24px 0 0;padding:0;list-style:none;counter-reset:pri;display:grid;gap:12px}
.pri li{counter-increment:pri;position:relative;padding:16px 18px 16px 56px;border:1px solid var(--line);
  border-radius:var(--r);background:var(--coal);color:var(--ink-2);font-size:14.5px}
.pri li:before{content:counter(pri,decimal-leading-zero);position:absolute;left:18px;top:15px;
  font-family:var(--mono);font-size:12px;color:var(--blue);letter-spacing:.08em}
.pri b{color:var(--ink);font-weight:600}
.authstrip{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px;font-size:12px;letter-spacing:.06em;
  text-transform:uppercase;color:var(--ink-2)}
.authstrip span{border:1px solid var(--line-2);border-radius:999px;padding:7px 13px;background:var(--coal)}
@media (max-width:820px){.adv{grid-template-columns:1fr}}

"""

BODY = """
<div class="back" aria-hidden="true">
  <div class="mesh"></div>
  <div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div><div class="arc"></div>
  <span class="cross c1"></span><span class="cross c2"></span><span class="cross c3"></span><span class="cross c4"></span>
</div>
<div class="cursorlight" aria-hidden="true"></div>

<header class="top">
  <div class="wrap">
    <a class="mark" href="/">
      <svg class="dish" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <rect x="1.5" y="1.5" width="29" height="29" rx="9" fill="#0a0a11" stroke="rgba(14,165,233,.55)"/>
        <circle cx="16" cy="16" r="8.4" stroke="#ffffff" stroke-width="1.6"/>
        <path d="M16 7.6v16.8M7.6 16h16.8" stroke="rgba(10,12,17,.22)" stroke-width="1"/>
        <circle cx="16" cy="16" r="3.4" fill="#2f6bff"/>
      </svg>
      Tony
    </a>
    <nav>
      <a href="#execution">Execution</a>
      <a href="#catalogue">Catalogue</a>
      <a href="#api">API</a>
      <a href="#compare">Compare</a>
      <a href="#pricing">Pricing</a>
    </nav>
    <span class="grow"></span>
    <a class="btn ghost sm signin" href="/app">Sign in</a>
    <a class="btn solid sm" href="/app">Open console</a>
  </div>
</header>

<main>
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <span class="tag"><i class="led"></i>__APPS__ apps &middot; __ACTIONS__ actions &middot; one endpoint</span>
      <h1><span class="line">One connection. One execution engine.</span>
        <span class="line blue">Any application. Any AI agent.</span></h1>
      <p class="lede">Connect an account once, then let any model call real apps with real writes. Tony finds the
        right tool from plain intent, picks the authentication a service actually needs, and runs it with retries,
        budgets and receipts, so Tony executes while your model reasons. No glue code, no credential sprawl.</p>

      <form class="find" id="find" onsubmit="return false" role="search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
          stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
        <input id="q" placeholder="type an app name: github, stripe, notion" autocomplete="off" aria-label="Search apps">
        <button type="submit">Search</button>
      </form>
      <div class="quicks" id="quicks">
        <span data-q="github">github</span>
        <span data-q="gmail">gmail</span>
        <span data-q="stripe">stripe</span>
        <span data-q="notion">notion</span>
        <span data-q="slack">slack</span>
      </div>
      <div class="hits" id="hits"></div>

      <div class="row">
        <a class="btn solid" href="/app">Create a free workspace</a>
        <a class="btn ghost" href="#api">See the API</a>
        <span class="hint">no card &middot; 14 days of Pro</span>
      </div>
    </div>

    <div class="orbit" aria-hidden="true">
      <div class="halo"></div>
      <div class="track"></div>
      <div class="track t2"></div>
      <div class="track t3"></div>
      <div class="sat"><i></i></div>
      <div class="core"><div><b>Tony</b><span>executor</span></div></div>
      <div class="node n1">API</div><div class="node n2">DB</div><div class="node n3">MAIL</div>
      <div class="node n4">PAY</div><div class="node n5">FILES</div><div class="node n6">CRM</div>
    </div>
  </div>

  <div class="wrap">
    <div class="tally rv">
      <div><b data-count="__APPS_N__">__APPS__</b><span>apps</span></div>
      <div><b data-count="__ACTIONS_N__">__ACTIONS__</b><span>typed actions</span></div>
      <div><b data-count="__WRITES_N__">__WRITES__</b><span>gate-ready writes</span></div>
      <div><b>30s</b><span>hard call deadline</span></div>
    </div>
  </div>
  __TICKER__
</section>

<section class="sec" id="execution">
  <div class="wrap">
    <div class="head rv">
      <div class="kick">execution model</div>
      <h2>One goal in. <span class="blue">Receipts out.</span></h2>
      <p class="sub">You describe the outcome. Tony picks the app, builds the call, runs it and shows you what
        came back, including the parts that failed.</p>
    </div>
    <div class="steps rv">
      <div class="step"><div class="n">STEP 01</div><b>Connect an account</b><p>OAuth for providers that support it, a token for the rest. Stored per user, encrypted, never echoed back.</p><span class="wire"></span></div>
      <div class="step"><div class="n">STEP 02</div><b>Pull the tool belt</b><p><span class="mono">/v1/tools</span> returns schemas your model already understands: OpenAI functions, Anthropic tools or MCP.</p><span class="wire"></span></div>
      <div class="step"><div class="n">STEP 03</div><b>Execute</b><p><span class="mono">/v1/agent</span> plans across apps, chains follow-up calls and returns a step trace with latency.</p><span class="wire"></span></div>
      <div class="step"><div class="n">STEP 04</div><b>Approve and audit</b><p>Writes wait for a human yes. Every attempt lands in the audit log either way.</p></div>
    </div>

    <div class="grid3">
      <div class="tile"><div class="pic"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2.5 4.5 6v6c0 4.8 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.7 7.5-9.5V6L12 2.5Z"/><path d="m8.8 12 2.2 2.2 4.2-4.4"/></svg></div>
        <h3>Ownership, not sharing</h3><p>Each key belongs to the workspace that created it. Credentials decrypt only inside the request that needs them, and API keys are stored hashed.</p><div class="meta">isolation</div></div>
      <div class="tile"><div class="pic"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v10"/><path d="m7.5 8.5 4.5 4.5 4.5-4.5"/><path d="M4 16v3.2A1.8 1.8 0 0 0 5.8 21h12.4A1.8 1.8 0 0 0 20 19.2V16"/></svg></div>
        <h3>Writes that ask first</h3><p>A destructive call returns a preview and a run id. Nothing changes until it is approved, and sessions can be pinned to read-only.</p><div class="meta">control</div></div>
      <div class="tile"><div class="pic"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 5h16M4 11h16M4 17h9"/></svg></div>
        <h3>A log you can defend</h3><p>Status, provider code, latency, payload size and error text for every call, filterable by app and by day.</p><div class="meta">observability</div></div>
    </div>
  </div>
</section>

<section class="sec" id="catalogue">
  <div class="wrap">
    <div class="head rv">
      <div class="kick">catalogue</div>
      <h2>__APPS__ apps. <span class="blue">__ACTIONS__ ways in.</span></h2>
      <p class="sub">Hand-written actions where agents do real work, OpenAPI ingestion for the long tail, and a
        proxy path for anything documented but not yet modelled. One contract across all three.</p>
    </div>
    <div class="matrix rv">
      <div class="cell"><div class="t">curated</div><b>__CURATED__ apps, typed by hand</b><p>Real parameter names, real response shapes, pagination and danger levels recorded per action.</p></div>
      <div class="cell"><div class="t">openapi</div><b>__OPENAPI__ ingested apps</b><p>Public specs normalised into the same action contract, so nothing about your code changes.</p></div>
      <div class="cell"><div class="t">proxy</div><b>Raw path access</b><p><span class="mono">/v1/proxy/{app}/{path}</span> with stored credentials injected and the call still audited.</p></div>
      <div class="cell"><div class="t">sessions</div><b>Scoped agent identities</b><p>App allowlists, tier ceilings, TTL and a run budget per session, all enforced server-side.</p></div>
      <div class="cell"><div class="t">memory</div><b>State between turns</b><p><span class="mono">/v1/memory</span> keeps per-entity facts your agent can read on the next call.</p></div>
      <div class="cell"><div class="t">custody</div><b>Your accounts stay yours</b><p>You connect with your own credentials, so vendor usage bills to you and data never detours through us.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="api">
  <div class="wrap">
    <div class="head rv">
      <div class="kick">the api</div>
      <h2>Six endpoints. <span class="blue">No SDK required.</span></h2>
      <p class="sub">REST with predictable names, typed errors and a hard deadline on every call. SDKs exist, they
        are just optional.</p>
    </div>
    <div class="term rv" style="margin-top:28px">
      <div class="bar"><i></i><i></i><i></i><span class="file">one goal, four apps</span></div>
<pre><span class="c"># the model does not need to know any provider's API</span>
<span class="k">curl</span> -X POST https://tony-7su0.onrender.com/v1/agent \\
  -H <span class="s">"Authorization: Bearer tk_live_..."</span> \\
  -d <span class="s">'{"goal":"file this bug, then tell the team in Slack"}'</span>

<span class="c"># {"engine":"llm","steps":[linear.create_issue, slack.post_message],</span>
<span class="c">#  "answer":"LIN-482 filed and linked in #eng","elapsed_ms":1840}</span></pre>
      <div class="run"><span class="dot"></span> writes gated &middot; <b>2 tools called</b> &middot; audit id recorded</div>
    </div>
    <div class="grid3">
      <div class="tile"><div class="mono t">POST /v1/agent</div><h3>Goal, not script</h3><p>Multi-step execution across apps with a visible trace. Falls back to a deterministic call if the model is unavailable.</p></div>
      <div class="tile"><div class="mono t">POST /v1/execute</div><h3>Exact action</h3><p>Typed arguments, dry-run previews, approval gates, 30 second deadline, typed error codes.</p></div>
      <div class="tile"><div class="mono t">GET /v1/tools</div><h3>Model-ready schemas</h3><p>Any slice of the catalogue, reads by default, writes on request, in three tool dialects.</p></div>
      <div class="tile"><div class="mono t">POST /v1/batch</div><h3>Twenty in one trip</h3><p>Fan out reads or writes, get ordered results with per-call status instead of partial silence.</p></div>
      <div class="tile"><div class="mono t">GET /v1/usage</div><h3>Honest meters</h3><p>Runs by day, success rate, top apps. The same numbers billing reads, so nothing drifts.</p></div>
      <div class="tile"><div class="mono t">GET /v1/audit</div><h3>Receipts</h3><p>Every run with latency, provider status and payload size, kept for the workspace that ran it.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="advantage">
  <div class="wrap">
    <span class="kicker mono">Why Tony wins</span>
    <h2>Built where the others stop at the demo.</h2>
    <div class="adv">
      <div class="adv-i"><h3>Faster tool discovery</h3><p>Intent search ranks actions across __APPS__ apps, so an
        agent asks for what it wants in words and gets the exact action, not a schema dump.</p></div>
      <div class="adv-i"><h3>Lower execution overhead</h3><p>One endpoint, one session, one receipt. No per-app
        SDK, no per-tool glue, no cold chain of HTTP wrappers.</p></div>
      <div class="adv-i"><h3>Efficient authentication</h3><p>OAuth 2.0, API keys, bearer tokens, basic auth and
        custom schemes are resolved before the call, not by the model.</p></div>
      <div class="adv-i"><h3>Broader API coverage</h3><p>Curated actions plus an OpenAPI importer, a raw proxy and
        a directory layer: __ACTIONS__ typed actions and counting.</p></div>
      <div class="adv-i"><h3>Reliable at scale</h3><p>Retries with backoff, circuit breakers, rate-limit handling,
        and an audit trail you can read back line by line.</p></div>
      <div class="adv-i"><h3>Own your infrastructure</h3><p>Self-hostable. Postgres you control, credentials
        encrypted at rest, no vendor holding your users' tokens.</p></div>
      <div class="adv-i"><h3>Effortless developer experience</h3><p>MCP for any client, a typed REST surface, and a
        console that shows what ran, what waited for approval, and what failed.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="priorities">
  <div class="wrap">
    <span class="kicker mono">What we are sharpening</span>
    <h2>Six things that separate an integration toy from an execution layer.</h2>
    <ol class="pri">
      <li><b>Intelligent authentication orchestration.</b> Detect the auth method, scopes and connection a service
        needs, then walk the user through only that.</li>
      <li><b>Adaptive tool discovery.</b> Rank by intent instead of loading thousands of schemas into a context
        window that cannot hold them.</li>
      <li><b>Execution optimisation.</b> Parallel calls, caching, retries, circuit breakers and honest rate-limit
        handling.</li>
      <li><b>Universal agent identity.</b> Every end-user and every agent gets isolated permissions, credentials
        and an execution budget.</li>
      <li><b>Integration health intelligence.</b> Broken APIs, expired permissions and schema drift surface before
        your users hit them.</li>
      <li><b>Authentication coverage.</b> OAuth 2.0, API keys, bearer tokens, basic auth and custom configurations,
        in one model.</li>
    </ol>
    <div class="authstrip mono"><span>OAuth 2.0</span><span>API keys</span><span>Bearer tokens</span>
      <span>Basic auth</span><span>Custom schemes</span></div>
  </div>
</section>

<section class="sec" id="compare">
  <div class="wrap">
    <div class="head rv">
      <div class="kick">honest comparison</div>
      <h2>Where Tony differs.</h2>
      <p class="sub">Not a replacement for every tool, and we will not pretend otherwise. This is the short list of
        what changes when an agent actually has to act.</p>
    </div>
    <div class="compare rv">
      <table>
        <thead><tr><th>Concern</th><th>Typical integration layer</th><th>Tony</th></tr></thead>
        <tbody>
          <tr><td>Credentials</td><td>Platform-held keys shared across users</td><td class="tony">Per-workspace ownership, AES-GCM at rest</td></tr>
          <tr><td>Writes</td><td>Allowed or disabled entirely</td><td class="tony">Preview, approval gate, then execute</td></tr>
          <tr><td>Failures</td><td>Long hangs and vague errors</td><td class="tony">Hard 30s deadline, typed error, audit row</td></tr>
          <tr><td>Coverage</td><td>Curated list only</td><td class="tony">Curated plus __APPS__ apps plus raw proxy</td></tr>
          <tr><td>Agent support</td><td>Tool schemas, no runtime</td><td class="tony">Tool schemas and a runtime that plans</td></tr>
          <tr><td>Data flow</td><td>Data routed through a vendor</td><td class="tony">Your account, your data, your bill</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</section>

<section class="sec" id="pricing">
  <div class="wrap">
    <div class="head rv">
      <div class="kick">pricing</div>
      <h2>Free to start. <span class="blue">Priced on runs.</span></h2>
      <p class="sub">Same catalogue on every plan. The difference is how hard you can drive it.</p>
    </div>
    <div class="plans rv">__PRICING__</div>
  </div>
</section>

<section class="sec">
  <div class="wrap">
    <div class="head rv">
      <div class="kick">questions</div>
      <h2>The first five things devs ask.</h2>
    </div>
    <div class="faq rv">
      <details open><summary>Do I have to bring my own API keys?</summary>
        <p>For most apps, yes, and that is deliberate. You connect the account you already pay for, so usage bills to you and Tony never becomes a middleman for your data. OAuth apps need one sign-in; token apps take a key once.</p></details>
      <details><summary>What actually stops a runaway agent?</summary>
        <p>Three things: writes return a preview instead of executing, sessions can be capped at read-only, and every call has a hard deadline. The run budget on your plan is a fourth.</p></details>
      <details><summary>Does it work from my own agent loop?</summary>
        <p>Yes. Pull schemas from <span class="mono">/v1/tools</span> and call <span class="mono">/v1/execute</span> directly, or point an MCP client at <span class="mono">/mcp</span>. Python, TypeScript, JS, Go and Java SDKs are on <span class="mono">/sdk</span>.</p></details>
      <details><summary>What happens on a provider outage?</summary>
        <p>The call fails fast with the provider's status code in the audit log, so you can tell an upstream problem from a Tony bug. Retries are yours to choose; Tony does not silently replay writes.</p></details>
      <details><summary>What is in the trial?</summary>
        <p>Fourteen days of Pro from the moment you sign up, full catalogue, agent runtime and SDKs included. It drops to the free tier automatically unless you pick a plan.</p></details>
    </div>

    <div class="final rv">
      <div class="kick">start</div>
      <h2>Give the model a <span class="blue">real console.</span></h2>
      <div class="row">
        <a class="btn solid" href="/app">Create a workspace</a>
        <a class="btn ghost" href="/docs">Read the docs</a>
        <span class="mono">key in under a minute</span>
      </div>
    </div>
  </div>
</section>
</main>

<footer>
  <div class="wrap">
    <span class="mono">Tony &middot; execution layer for agents</span>
    <span class="grow"></span>
    <a class="mono" href="/app">Console</a>
    <a class="mono" href="/docs">Docs</a>
    <a class="mono" href="/sdk">SDKs</a>
    <a class="mono" href="/mcp">MCP</a>
    <span class="mono">v1</span>
  </div>
</footer>
"""

JS = """
<script>
(function(){
  var raf = null;
  addEventListener('pointermove', function(e){
    if (raf) return;
    raf = requestAnimationFrame(function(){
      raf = null;
      document.documentElement.style.setProperty('--mx', e.clientX + 'px');
      document.documentElement.style.setProperty('--my', e.clientY + 'px');
    });
  }, {passive:true});

  var io = new IntersectionObserver(function(list){
    list.forEach(function(en){ if (en.isIntersecting){ en.target.classList.add('on'); io.unobserve(en.target); } });
  }, {threshold:.12});
  document.querySelectorAll('.rv').forEach(function(el){ io.observe(el); });

  document.querySelectorAll('[data-count]').forEach(function(el){
    var target = parseInt(el.getAttribute('data-count') || '0', 10);
    var seen = new IntersectionObserver(function(list){
      list.forEach(function(en){
        if (!en.isIntersecting) return;
        seen.disconnect();
        var t0 = performance.now();
        function tick(t){
          var p = Math.min(1, (t - t0) / 950);
          var eased = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * eased).toLocaleString();
          if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      });
    }, {threshold:.6});
    seen.observe(el);
  });

  var q = document.getElementById('q'), hits = document.getElementById('hits'), timer = null;
  function paint(items){
    if (!items.length){ hits.innerHTML = '<div class="hit"><span class="nm">Nothing matched. Try a vendor name.</span></div>'; return; }
    hits.innerHTML = items.slice(0,4).map(function(a){
      return '<div class="hit"><span class="slug">' + a.slug + '</span><span class="nm">' +
             (a.name || a.slug) + '</span><span class="cat">' + (a.category || 'app') + '</span></div>';
    }).join('');
  }
  function search(term){
    if (!term.trim()){ hits.innerHTML = ''; return; }
    fetch('/v1/apps?q=' + encodeURIComponent(term) + '&limit=4')
      .then(function(r){ return r.json(); })
      .then(function(d){ paint(d.apps || d.results || []); })
      .catch(function(){ hits.innerHTML = ''; });
  }
  if (q) q.addEventListener('input', function(){ clearTimeout(timer); timer = setTimeout(function(){ search(q.value); }, 170); });
  document.querySelectorAll('#quicks span').forEach(function(s){
    s.addEventListener('click', function(){ q.value = s.getAttribute('data-q'); search(q.value); q.focus(); });
  });
})();
</script>
"""


def landing_html(demo_open: bool = True) -> str:
    """Render the marketing page with numbers taken from the live registry."""
    from .catalog import catalog

    apps = list(catalog.apps.values())
    by_source, by_tier = _counts(apps)
    app_count = len(apps)
    action_count = sum(len(a.actions) for a in apps)
    writes = sum(v for k, v in by_tier.items() if k != "read")

    body = BODY
    body = body.replace("__TICKER__", _ticker())
    body = body.replace("__PRICING__", _pricing_html())
    body = body.replace("__CURATED__", f"{by_source.get('curated', 0):,}")
    body = body.replace("__OPENAPI__", f"{by_source.get('openapi', 0):,}")
    body = body.replace("__WRITES_N__", str(writes))
    body = body.replace("__APPS_N__", str(app_count))
    body = body.replace("__ACTIONS_N__", str(action_count))
    body = body.replace("__WRITES__", f"{writes:,}")
    body = body.replace("__ACTIONS__", f"{action_count:,}")
    body = body.replace("__APPS__", f"{app_count:,}")

    fonts = ("https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;650;700&"
             "family=JetBrains+Mono:wght@400;500&display=swap")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tony &middot; execution layer for AI agents</title>
<meta name="description" content="{app_count:,} apps and {action_count:,} typed actions behind one API, with encrypted credentials, approval-gated writes and full audit.">
<meta name="theme-color" content="#000000">
<meta property="og:image" content="/static/brand/hero-orbit.jpg">
<meta property="og:title" content="Tony, the execution layer for AI agents">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{fonts}">
<link rel="icon" href="/static/brand/tony-mark.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/static/brand/tony-180.png">
<style>{CSS}</style>
</head>
<body>
{body}
{JS}
</body>
</html>"""

# ─── rebuilt marketing page ─────────────────────────────────────────────────
# True black, white type, the console's own mark, and copy that names the real
# endpoints instead of generic claims. Later bindings override the originals.
CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#000;color:#fff;font-family:'Inter Tight',system-ui,-apple-system,sans-serif;
 font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased;letter-spacing:-.01em}
a{color:inherit;text-decoration:none}
.wrap{width:100%;max-width:1140px;margin:0 auto;padding:0 24px}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:12px;letter-spacing:.02em;text-transform:uppercase}
.top{position:sticky;top:0;z-index:50;background:rgba(0,0,0,.82);backdrop-filter:blur(16px);
 border-bottom:1px solid #161616}
.top .wrap{display:flex;align-items:center;gap:11px;height:62px}
.mark{display:flex;align-items:center;gap:10px;font-weight:650;font-size:16px;letter-spacing:-.025em}
.mark svg{width:26px;height:26px;display:block}
nav{display:flex;gap:24px;margin-left:26px}
nav a{font-size:13.5px;color:#9a9a9a;transition:color .18s}
nav a:hover{color:#fff}
.grow{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;border-radius:9px;
 padding:11px 18px;font-size:13.5px;font-weight:550;border:1px solid transparent;transition:.18s;cursor:pointer}
.btn.sm{padding:8px 14px;font-size:13px}
.btn.solid{background:#fff;color:#000}
.btn.solid:hover{background:#e6e6e6}
.btn.ghost{border-color:#262626;color:#e8e8e8}
.btn.ghost:hover{border-color:#484848;background:#0b0b0b}
.btn.wide{width:100%}
.hero{padding:104px 0 0;position:relative;overflow:hidden}
.hero:before{content:'';position:absolute;inset:0;background:
 radial-gradient(680px 300px at 78% 6%,rgba(226,84,43,.12),transparent 70%),
 radial-gradient(560px 240px at 8% 88%,rgba(255,255,255,.05),transparent 72%);pointer-events:none}
.hero-grid{display:grid;grid-template-columns:1.06fr .94fr;gap:56px;align-items:start;position:relative}
.eyebrow{display:inline-flex;align-items:center;gap:9px;padding:6px 11px;border:1px solid #1f1f1f;
 border-radius:999px;color:#a3a3a3;margin-bottom:26px}
.eyebrow i{width:5px;height:5px;border-radius:50%;background:#E2542B;box-shadow:0 0 0 3px rgba(226,84,43,.16)}
h1{margin:0 0 22px;font-size:clamp(38px,4.6vw,60px);line-height:1.03;letter-spacing:-.038em;font-weight:640}
h1 em{font-style:normal;color:#7d7d7d}
.lede{margin:0 0 30px;font-size:16.5px;line-height:1.62;color:#a8a8a8;max-width:31em}
.lede b{color:#fff;font-weight:550}
.cta{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.hint{color:#6d6d6d;font-size:12.5px}
.snip{margin-top:30px;border:1px solid #191919;border-radius:12px;background:#050505;overflow:hidden}
.snip-hd{display:flex;align-items:center;gap:8px;padding:9px 13px;border-bottom:1px solid #141414;color:#6f6f6f}
.snip-hd span{flex:1}
.snip-hd button{background:none;border:1px solid #232323;color:#a3a3a3;border-radius:6px;padding:3px 9px;
 font-size:11px;cursor:pointer;font-family:inherit}
.snip-hd button:hover{color:#fff;border-color:#3d3d3d}
pre{margin:0;padding:15px 15px 17px;overflow-x:auto;font-family:'JetBrains Mono',monospace;font-size:12.4px;
 line-height:1.75;color:#d6d6d6;white-space:pre-wrap;overflow-wrap:anywhere}
pre .c{color:#5e5e5e}
pre .k{color:#E2542B}
pre .s{color:#9ee6c7}
pre .f{color:#fff}
.card{border:1px solid #191919;border-radius:16px;background:linear-gradient(180deg,#080808,#040404);padding:22px}
.consent{position:relative}
.consent-top{display:flex;align-items:center;justify-content:center;gap:13px;margin:4px 0 18px}
.plate{width:46px;height:46px;border-radius:12px;display:grid;place-items:center;background:#0b0b0b;
 border:1px solid #232323}
.plate svg{width:30px;height:30px}
.pin{width:22px;height:1px;background:#2e2e2e}
.consent h3{margin:0 0 6px;font-size:15.5px;text-align:center;font-weight:580;letter-spacing:-.015em}
.consent p{margin:0 0 16px;text-align:center;font-size:12.6px;color:#8b8b8b}
.scope{display:flex;gap:11px;padding:10px 12px;border:1px solid #1c1c1c;border-radius:10px;margin-bottom:7px}
.scope b{display:block;font-size:12.6px;font-weight:540}
.scope span{font-size:11.5px;color:#7c7c7c}
.scope svg{width:15px;height:15px;flex:none;margin-top:2px;stroke:#E2542B}
.foot-note{margin-top:13px;text-align:center;font-size:11px;color:#5f5f5f}
.stats{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #161616;border-bottom:1px solid #161616;
 margin-top:86px}
.stats div{padding:26px 20px;border-right:1px solid #161616}
.stats div:last-child{border-right:0}
.stats b{display:block;font-size:26px;font-weight:600;letter-spacing:-.03em}
.stats span{font-size:12px;color:#7a7a7a}
.sec{padding:96px 0;border-bottom:1px solid #111}
.sec-hd{max-width:36em;margin-bottom:44px}
.sec-hd .mono{color:#E2542B;display:block;margin-bottom:14px}
h2{margin:0 0 14px;font-size:clamp(26px,3vw,34px);letter-spacing:-.032em;font-weight:620;line-height:1.12}
.sec-hd p{margin:0;color:#979797;font-size:15.2px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.step{border:1px solid #161616;border-radius:14px;padding:22px;background:#040404}
.step .n{font-family:'JetBrains Mono',monospace;font-size:11px;color:#E2542B;margin-bottom:14px;display:block}
.step h4{margin:0 0 8px;font-size:15.5px;font-weight:580}
.step p{margin:0 0 14px;font-size:13.4px;color:#8f8f8f;line-height:1.6}
.step code{font-family:'JetBrains Mono',monospace;font-size:11.6px;color:#c9c9c9;background:#0b0b0b;
 border:1px solid #1a1a1a;border-radius:6px;padding:2px 6px}
.layers{display:grid;grid-template-columns:repeat(2,1fr);gap:0 34px}
.layer{display:flex;gap:13px;padding:16px 0;border-bottom:1px solid #131313}
.layer svg{width:17px;height:17px;flex:none;margin-top:3px;stroke:#fff}
.layer b{display:block;font-size:14px;font-weight:550;margin-bottom:2px}
.layer span{font-size:13px;color:#8b8b8b}
.split{display:grid;grid-template-columns:1fr 1fr;gap:46px;align-items:center}
.tiers{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.tier{border:1px solid #171717;border-radius:16px;padding:24px;background:#040404;position:relative}
.tier.hot{border-color:#3a3a3a;background:linear-gradient(180deg,#0d0d0d,#050505)}
.tier .flag{position:absolute;top:-10px;left:24px;background:#fff;color:#000;font-size:10.5px;font-weight:600;
 padding:3px 9px;border-radius:999px;letter-spacing:.01em}
.tname{font-size:14px;font-weight:600;margin-bottom:4px}
.tier .tag{font-size:12.5px;color:#7e7e7e;margin-bottom:18px}
.amt{display:flex;align-items:baseline;gap:7px;margin-bottom:20px}
.amt b{font-size:30px;font-weight:600;letter-spacing:-.035em}
.amt span{font-size:12px;color:#7a7a7a}
.tier ul{list-style:none;margin:0 0 22px;padding:0}
.tier li{display:flex;gap:9px;align-items:flex-start;font-size:13px;color:#a5a5a5;padding:5px 0}
.tier li svg{width:13px;height:13px;flex:none;margin-top:4px;stroke:#fff}
.close{text-align:center;padding:104px 0}
.close .mark{justify-content:center;margin-bottom:26px}
.close h2{margin-bottom:16px}
.close p{margin:0 auto 30px;color:#939393;max-width:34em;font-size:15px}
footer{border-top:1px solid #141414;padding:30px 0}
footer .wrap{display:flex;gap:22px;align-items:center;flex-wrap:wrap;color:#6f6f6f}
footer a:hover{color:#fff}
.rv{opacity:0;transform:translateY(14px);transition:opacity .6s cubic-bezier(.2,.7,.2,1),transform .6s cubic-bezier(.2,.7,.2,1)}
.rv.on{opacity:1;transform:none}
@media(max-width:900px){
 .hero-grid,.split{grid-template-columns:1fr;gap:40px}
 .steps,.tiers{grid-template-columns:1fr}
 .layers{grid-template-columns:1fr}
 .stats{grid-template-columns:repeat(2,1fr)}
 .stats div:nth-child(2){border-right:0}
 .stats div:nth-child(1),.stats div:nth-child(2){border-bottom:1px solid #161616}
 nav{display:none}
 .hero{padding-top:64px}
 h1{font-size:clamp(32px,8.4vw,44px)}
 .sec{padding:64px 0}
 .close{padding:70px 0}
}
"""

MARK = ('<svg viewBox="0 0 64 64" fill="none" aria-hidden="true">'
        '<rect width="64" height="64" rx="15" fill="#0E0E0C" stroke="#232320"/>'
        '<path d="M11.5 32h6.5" stroke="#F3F0E9" stroke-width="5" stroke-linecap="round"/>'
        '<circle cx="32" cy="32" r="13" fill="none" stroke="#F3F0E9" stroke-width="5" stroke-dasharray="62 19.7"'
        ' stroke-linecap="round" transform="rotate(45 32 32)"/>'
        '<circle cx="33.5" cy="30.5" r="4.6" fill="#E2542B"/></svg>')

BODY = """
<header class="top"><div class="wrap">
  <a class="mark" href="/">__MARK__Tony</a>
  <nav>
    <a href="#connect">Connect</a>
    <a href="#security">Security</a>
    <a href="#pricing">Pricing</a>
    <a href="/docs">Docs</a>
  </nav>
  <span class="grow"></span>
  <a class="btn ghost sm" href="/account">Sign in</a>
  <a class="btn solid sm" href="/account">Open console</a>
</div></header>

<main>
<section class="hero"><div class="wrap hero-grid">
  <div>
    <span class="eyebrow mono"><i></i>Hosted OAuth &middot; __APPS__ apps &middot; __ACTIONS__ actions</span>
    <h1>Users sign in once.<br><em>Their agent does the rest.</em></h1>
    <p class="lede">Tony hands your user a link. They approve access on the provider's own page, and Tony keeps the
      token encrypted, refreshed and scoped. Your agent then calls GitHub, Gmail, Slack or Notion on their behalf,
      with <b>no API keys in your code</b> and every write on the record.</p>
    <div class="cta">
      <a class="btn solid" href="/account">Connect an app</a>
      <a class="btn ghost" href="#connect">How the flow works</a>
      <span class="hint">free workspace &middot; no card</span>
    </div>
    <div class="snip">
      <div class="snip-hd mono"><span>create a connection link</span><button data-copy="c1">copy</button></div>
      <pre id="c1"><span class="c"># returns a single-use URL your user opens</span>
<span class="f">curl</span> -X POST https://tony-7su0.onrender.com/v1/connect-links \\
  -H <span class="s">"Authorization: Bearer $TONY_KEY"</span> \\
  -d <span class="s">'{"app":"github","agent_name":"Mira","tiers":["read","write"]}'</span>
<span class="k">→</span> { "url": "https://tony-7su0.onrender.com/connect/tcl_..." }</pre>
    </div>
  </div>

  <div class="card consent" aria-label="Hosted consent page">
    <div class="consent-top">
      <div class="plate">__MARK__</div><div class="pin"></div>
      <div class="plate"><svg viewBox="0 0 24 24" fill="#F3F0E9"><path d="M12 1.8a10.2 10.2 0 0 0-3.23 19.88c.5.09.68-.22.68-.49v-1.9c-2.78.6-3.37-1.18-3.37-1.18-.45-1.16-1.1-1.47-1.1-1.47-.9-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02a9.5 9.5 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.59.69.49A10.2 10.2 0 0 0 12 1.8"/></svg></div>
    </div>
    <h3>Mira wants to connect to your GitHub</h3>
    <p>You sign in on GitHub's own page. Tony never sees your password.</p>
    <div class="scope"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>
      <div><b>View repositories and issues</b><span>read access to your account</span></div></div>
    <div class="scope"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>
      <div><b>Open issues and comment</b><span>write access, on the record</span></div></div>
    <div class="scope"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>
      <div><b>Read your profile</b><span>needed to attribute the actions</span></div></div>
    <a class="btn solid wide" style="margin-top:14px" href="/account">Continue to GitHub</a>
    <div class="foot-note">Secured by Tony &middot; single use &middot; expires in 30 minutes</div>
  </div>
</div>

<div class="wrap"><div class="stats">
  <div><b>__APPS__</b><span>apps in the catalogue</span></div>
  <div><b>__ACTIONS__</b><span>typed actions</span></div>
  <div><b>__WRITES__</b><span>gated write actions</span></div>
  <div><b>PKCE</b><span>where the provider supports it</span></div>
</div></div>
</section>

__TICKER__

<section class="sec" id="connect"><div class="wrap">
  <div class="sec-hd rv">
    <span class="mono">The flow</span>
    <h2>Three moving parts, no glue code.</h2>
    <p>Nothing here is a one-off integration. The same three endpoints cover every provider in the catalogue,
       because scopes, token exchange and refresh all come from one declarative registry.</p>
  </div>
  <div class="steps rv">
    <div class="step"><span class="n">01 / issue</span>
      <h4>Create the link</h4>
      <p>Ask for an app and the tiers you need. Tony mints a signed, single-use URL bound to one workspace.</p>
      <code>POST /v1/connect-links</code></div>
    <div class="step"><span class="n">02 / approve</span>
      <h4>The user consents</h4>
      <p>They see what is being asked, then sign in at the provider. Authorization code with PKCE, callback
         verified on Tony, tokens encrypted before they touch the database.</p>
      <code>GET /connect/tcl_...</code></div>
    <div class="step"><span class="n">03 / act</span>
      <h4>Your agent executes</h4>
      <p>Tokens refresh on the way in. Reads run immediately, writes can wait for a human approval, and the
         result comes back with a receipt.</p>
      <code>POST /v1/execute</code></div>
  </div>
</div></section>

<section class="sec" id="security"><div class="wrap">
  <div class="split">
    <div class="sec-hd rv" style="margin-bottom:0">
      <span class="mono">Security</span>
      <h2>Built for a hostile internet.</h2>
      <p>An agent gateway holds real credentials, so it has to assume someone is probing it. Every request is
         scored, not just counted: probe paths, scanner agents, endpoint sweeps and repeated rejected keys all
         raise a decaying score, and a persistent offender earns a timed block that doubles on repeat.</p>
      <div class="cta" style="margin-top:24px">
        <a class="btn ghost sm" href="/docs">Read the security notes</a>
        <span class="hint">blocks self-heal</span>
      </div>
    </div>
    <div class="layers rv">
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M12 2.8 5 6v6c0 4.6 3 8 7 9.2 4-1.2 7-4.6 7-9.2V6l-7-3.2Z"/></svg>
        <div><b>Behavioural scoring</b><span>bursts, sweeps and scanner signatures, with decay</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><rect x="4" y="10" width="16" height="10" rx="2.4"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/></svg>
        <div><b>Encrypted credentials</b><span>tokens sealed at rest, never returned by the API</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M4 12h16M12 4v16"/></svg>
        <div><b>Scoped agent tokens</b><span>restricted to apps, tiers and an expiry you set</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M5 12.5 10 17l9-10"/></svg>
        <div><b>Approval gate</b><span>writes and deletes can wait for a human decision</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><circle cx="12" cy="12" r="8.4"/><path d="M12 8v4.4l3 1.8"/></svg>
        <div><b>Single-use links</b><span>short expiry, bound to one workspace and one entity</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M4 6h16M4 12h10M4 18h7"/></svg>
        <div><b>Full audit</b><span>every call, argument and veto is recorded</span></div></div>
    </div>
  </div>
</div></section>

<section class="sec"><div class="wrap">
  <div class="split">
    <div class="rv">
      <span class="mono" style="color:#E2542B;display:block;margin-bottom:14px">A real call</span>
      <h2>Plain HTTP in, a receipt out.</h2>
      <p style="color:#979797;font-size:15px;margin:0 0 8px">Any language, any model. One action name, validated
        arguments, and a result the agent can read.</p>
    </div>
    <div class="snip rv">
      <div class="snip-hd mono"><span>execute an authorised action</span><button data-copy="c2">copy</button></div>
      <pre id="c2"><span class="f">curl</span> -X POST https://tony-7su0.onrender.com/v1/execute \\
  -H <span class="s">"Authorization: Bearer $TONY_KEY"</span> \\
  -d <span class="s">'{"action":"github.create_issue",
      "args":{"repo":"acme/app","title":"Login loop"}}'</span>

<span class="k">→</span> { "ok": true, "status": 201,
    "data": { "number": 412, "url": "..." },
    "receipt": { "approval": "granted", "ms": 684 } }</pre>
    </div>
  </div>
</div></section>

<section class="sec" id="pricing"><div class="wrap">
  <div class="sec-hd rv"><span class="mono">Pricing</span>
    <h2>Priced per workspace, not per clever idea.</h2>
    <p>Start free. Pay when an agent starts doing real work.</p></div>
  <div class="tiers rv">__PRICING__</div>
</div></section>

<section class="close"><div class="wrap">
  <div class="mark">__MARK__</div>
  <h2>Connect your first app in about a minute.</h2>
  <p>Open the console, mint a link, send it to yourself, and watch the token land encrypted.</p>
  <div class="cta" style="justify-content:center">
    <a class="btn solid" href="/account">Open the console</a>
    <a class="btn ghost" href="/mcp">Install in your client</a>
  </div>
</div></section>
</main>

<footer><div class="wrap">
  <a class="mark" href="/" style="font-size:14px">__MARK_SM__Tony</a>
  <span class="grow"></span>
  <a class="mono" href="/docs">Docs</a>
  <a class="mono" href="/sdk">SDKs</a>
  <a class="mono" href="/mcp">MCP</a>
  <a class="mono" href="/account">Console</a>
  <span class="mono" style="color:#4b4b4b">v1</span>
</div></footer>
"""

BODY = BODY.replace("__MARK__", MARK).replace("__MARK_SM__", MARK)

JS = """
<script>
(function(){
  var io = new IntersectionObserver(function(list){
    list.forEach(function(en){ if(en.isIntersecting){ en.target.classList.add('on'); io.unobserve(en.target) } });
  },{threshold:.14});
  document.querySelectorAll('.rv').forEach(function(e){ io.observe(e) });

  document.querySelectorAll('[data-copy]').forEach(function(b){
    b.onclick = function(){
      var t = document.getElementById(b.dataset.copy);
      if(!t) return;
      navigator.clipboard.writeText(t.textContent.trim()).then(function(){
        var o = b.textContent; b.textContent = 'copied';
        setTimeout(function(){ b.textContent = o }, 1300);
      }).catch(function(){});
    };
  });
})();
</script>
"""

# appended last so it wins over both stylesheets above
CSS += """
body{overflow-x:clip}
.tape{overflow:hidden;border-bottom:1px solid #111;padding:17px 0}
.tape-track{display:flex;width:max-content;animation:slide 42s linear infinite;
 font-family:'JetBrains Mono',monospace;font-size:11.6px;letter-spacing:.06em;text-transform:uppercase;color:#5a5a5a}
.tape-track span{display:inline-flex;align-items:center;gap:34px;padding-right:34px;white-space:nowrap}
.tape-track i{width:3px;height:3px;border-radius:50%;background:#393939;display:block}
@keyframes slide{to{transform:translateX(-50%)}}
@media(prefers-reduced-motion:reduce){.tape-track{animation:none}}
"""

# ─── architecture pass: hero art, section rhythm, more energy ───────────────
CSS += """
:root{--ink:#000;--line:#171717;--line2:#232323;--dim:#8f8f8f;--hot:#E2542B}
body{background:#000}
.top .wrap{height:64px}
.hero{padding:88px 0 0}
.hero-grid{grid-template-columns:1.02fr .98fr;gap:44px;align-items:center}
.hero-art{position:relative;isolation:isolate}
.hero-art img{width:100%;height:auto;display:block;border-radius:20px;
 filter:saturate(1.04) contrast(1.05);}
.hero-art:before{content:'';position:absolute;inset:-12% -8%;z-index:-1;border-radius:50%;
 background:radial-gradient(closest-side,rgba(226,84,43,.20),rgba(226,84,43,.05) 55%,transparent 78%);
 animation:breathe 7s ease-in-out infinite}
.hero-art:after{content:'';position:absolute;inset:0;border-radius:20px;pointer-events:none;
 background:linear-gradient(180deg,transparent 62%,rgba(0,0,0,.55));}
@keyframes breathe{0%,100%{opacity:.65;transform:scale(.99)}50%{opacity:1;transform:scale(1.02)}}
.art-tag{position:absolute;left:16px;bottom:14px;z-index:2;display:flex;align-items:center;gap:8px;
 padding:6px 11px;border-radius:999px;background:rgba(8,8,8,.72);border:1px solid #262626;
 color:#c9c9c9;font-family:'JetBrains Mono',monospace;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;
 backdrop-filter:blur(8px)}
.art-tag i{width:5px;height:5px;border-radius:50%;background:#E2542B;animation:blip 2.4s ease-in-out infinite}
@keyframes blip{0%,100%{opacity:.35}50%{opacity:1}}
.eyebrow{border-color:#242424;background:linear-gradient(180deg,#0a0a0a,#050505)}
.eyebrow svg{width:11px;height:11px;stroke:#E2542B;fill:none;stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round}
h1 em{color:#6f6f6f}
.btn.solid{box-shadow:0 1px 0 rgba(255,255,255,.6) inset,0 10px 30px rgba(255,255,255,.08)}
.btn.solid:hover{transform:translateY(-1px)}
.btn.ghost:hover{transform:translateY(-1px)}
.card,.step,.tier{transition:border-color .22s,transform .22s,background .22s}
.step:hover,.tier:hover{border-color:#2e2e2e;transform:translateY(-2px)}
.snum{display:flex;align-items:center;gap:12px;margin-bottom:34px}
.snum b{font-family:'JetBrains Mono',monospace;font-size:11px;color:#E2542B;letter-spacing:.1em}
.snum span{flex:1;height:1px;background:linear-gradient(90deg,#1e1e1e,transparent)}
.sec{padding:92px 0}
.sec-hd{margin-bottom:40px}
.connect-grid{display:grid;grid-template-columns:1.02fr .98fr;gap:44px;align-items:start}
.stack{display:grid;gap:12px}
.stack .step{padding:20px 22px}
.stack .step h4{margin-bottom:6px}
.pulse-line{height:1px;background:linear-gradient(90deg,transparent,#E2542B,transparent);opacity:.5}
.ticker-wrap{border-top:1px solid #141414;border-bottom:1px solid #141414}
@media(max-width:900px){
 .hero-grid,.connect-grid{grid-template-columns:1fr}
 .hero-art{order:-1;margin-bottom:6px}
 .hero{padding-top:40px}
 .art-tag{font-size:10px}
}
"""

BODY = """
<header class="top"><div class="wrap">
  <a class="mark" href="/">__MARK__Tony</a>
  <nav>
    <a href="#connect">Connect</a><a href="#security">Security</a>
    <a href="#pricing">Pricing</a><a href="/docs">Docs</a>
  </nav>
  <span class="grow"></span>
  <a class="btn ghost sm" href="/account">Sign in</a>
  <a class="btn solid sm" href="/account">Open console</a>
</div></header>

<main>
<section class="hero"><div class="wrap hero-grid">
  <div>
    <span class="eyebrow mono"><svg viewBox="0 0 24 24"><path d="M13 2 4.5 13.5H11L9.5 22 19 10.2h-6.4L13 2Z"/></svg>
      Hosted OAuth &middot; __APPS__ apps &middot; __ACTIONS__ actions</span>
    <h1>Users sign in once.<br><em>Their agent does the rest.</em></h1>
    <p class="lede">Tony hands your user a link. They approve on the provider's own page, and Tony keeps the token
      encrypted, refreshed and scoped. Your agent then works inside GitHub, Gmail, Slack or Notion on their behalf,
      with <b>no API keys in your code</b> and every write on the record.</p>
    <div class="cta">
      <a class="btn solid" href="/account">Connect an app</a>
      <a class="btn ghost" href="#connect">See the flow</a>
    </div>
    <div class="snip">
      <div class="snip-hd mono"><span>mint a connection link</span><button data-copy="c1">copy</button></div>
      <pre id="c1"><span class="f">curl</span> -X POST https://tony-7su0.onrender.com/v1/connect-links \\
  -H <span class="s">"Authorization: Bearer $TONY_KEY"</span> \\
  -d <span class="s">'{"app":"github","agent_name":"Mira","tiers":["read","write"]}'</span>
<span class="k">→</span> { "url": "https://tony-7su0.onrender.com/connect/tcl_..." }</pre>
    </div>
  </div>

  <div class="hero-art">
    <img src="/static/brand/hero-orbit.jpg" width="1100" height="1100"
         alt="Tony's mark standing at the centre of a ring of connected application icons"
         loading="eager" decoding="async">
    <span class="art-tag"><i></i>every tile is one granted scope</span>
  </div>
</div>

<div class="wrap"><div class="stats">
  <div><b>__APPS__</b><span>apps in the catalogue</span></div>
  <div><b>__ACTIONS__</b><span>typed actions</span></div>
  <div><b>__WRITES__</b><span>gated write actions</span></div>
  <div><b>PKCE</b><span>where the provider supports it</span></div>
</div></div>
</section>

<div class="ticker-wrap">__TICKER__</div>

<section class="sec" id="connect"><div class="wrap">
  <div class="snum"><b>01</b><span></span></div>
  <div class="sec-hd rv"><span class="mono" style="color:#E2542B;display:block;margin-bottom:13px">The flow</span>
    <h2>One link, then the provider does the asking.</h2>
    <p>Not a one-off integration. The same three endpoints cover every provider, because scopes, token exchange
       and refresh come from one declarative registry.</p></div>
  <div class="connect-grid">
    <div class="card consent rv">
      <div class="consent-top">
        <div class="plate">__MARK__</div><div class="pin"></div>
        <div class="plate"><svg viewBox="0 0 24 24" fill="#F3F0E9"><path d="M12 1.8a10.2 10.2 0 0 0-3.23 19.88c.5.09.68-.22.68-.49v-1.9c-2.78.6-3.37-1.18-3.37-1.18-.45-1.16-1.1-1.47-1.1-1.47-.9-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.65 0 0 .84-.27 2.75 1.02a9.5 9.5 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.38.2 2.4.1 2.65.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.59.69.49A10.2 10.2 0 0 0 12 1.8"/></svg></div>
      </div>
      <h3>Mira wants to connect to your GitHub</h3>
      <p>You sign in on GitHub's own page. Tony never sees your password.</p>
      <div class="scope"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>
        <div><b>View repositories and issues</b><span>read access to your account</span></div></div>
      <div class="scope"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>
        <div><b>Open issues and comment</b><span>write access, on the record</span></div></div>
      <div class="scope"><svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>
        <div><b>Read your profile</b><span>needed to attribute the actions</span></div></div>
      <a class="btn solid wide" style="margin-top:14px" href="/account">Continue to GitHub</a>
      <div class="foot-note">Secured by Tony &middot; single use &middot; expires in 30 minutes</div>
    </div>
    <div class="stack rv">
      <div class="step"><span class="n">01 / issue</span><h4>Create the link</h4>
        <p>Ask for an app and the tiers you need. Tony mints a signed, single-use URL bound to one workspace.</p>
        <code>POST /v1/connect-links</code></div>
      <div class="step"><span class="n">02 / approve</span><h4>The user consents</h4>
        <p>Authorization code with PKCE where offered, callback verified on Tony, tokens encrypted before storage.</p>
        <code>GET /connect/tcl_...</code></div>
      <div class="step"><span class="n">03 / act</span><h4>Your agent executes</h4>
        <p>Tokens refresh on the way in, reads run at once, writes can wait for a human, and you get a receipt.</p>
        <code>POST /v1/execute</code></div>
      <div class="step"><span class="n">04 / prove it</span><h4>Health, not hope</h4>
        <p>A probe classifies every connection: healthy, expired, rate limited or gone, and reconnects the ones that died.</p>
        <code>POST /v1/health/check</code></div>
    </div>
  </div>
</div></section>

<section class="sec" id="security" style="border-top:1px solid #101010"><div class="wrap">
  <div class="snum"><b>02</b><span></span></div>
  <div class="split">
    <div class="sec-hd rv" style="margin-bottom:0">
      <span class="mono" style="color:#E2542B;display:block;margin-bottom:13px">Security</span>
      <h2>Built for a hostile internet.</h2>
      <p>A gateway holds real credentials, so it assumes someone is probing it. Every request is scored, not just
         counted: probe paths, scanner agents, endpoint sweeps and repeated rejected keys raise a decaying score,
         and a persistent offender earns a timed block that doubles on repeat.</p>
      <div class="cta" style="margin-top:24px"><a class="btn ghost sm" href="/docs">Security notes</a>
        <span class="hint">blocks self-heal</span></div>
    </div>
    <div class="layers rv">
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M12 2.8 5 6v6c0 4.6 3 8 7 9.2 4-1.2 7-4.6 7-9.2V6l-7-3.2Z"/></svg>
        <div><b>Behavioural scoring</b><span>bursts, sweeps, scanner signatures, with decay</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><rect x="4" y="10" width="16" height="10" rx="2.4"/><path d="M8 10V7.5a4 4 0 0 1 8 0V10"/></svg>
        <div><b>Encrypted credentials</b><span>sealed at rest, never returned by the API</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M4 12h16M12 4v16"/></svg>
        <div><b>Scoped agent tokens</b><span>limited to apps, tiers and an expiry you set</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M5 12.5 10 17l9-10"/></svg>
        <div><b>Approval gate</b><span>writes and deletes can wait for a human</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><circle cx="12" cy="12" r="8.4"/><path d="M12 8v4.4l3 1.8"/></svg>
        <div><b>Single-use links</b><span>short expiry, one workspace, one entity</span></div></div>
      <div class="layer"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8"><path d="M4 6h16M4 12h10M4 18h7"/></svg>
        <div><b>Full audit</b><span>every call, argument and veto recorded</span></div></div>
    </div>
  </div>
</div></section>

<section class="sec" style="border-top:1px solid #101010"><div class="wrap">
  <div class="snum"><b>03</b><span></span></div>
  <div class="split">
    <div class="rv">
      <h2 style="margin-bottom:14px">Plain HTTP in, a receipt out.</h2>
      <p style="color:#979797;font-size:15px;margin:0">Any language, any model. One action name, validated
        arguments, and a result the agent can read back into its plan.</p>
    </div>
    <div class="snip rv">
      <div class="snip-hd mono"><span>execute an authorised action</span><button data-copy="c2">copy</button></div>
      <pre id="c2"><span class="f">curl</span> -X POST https://tony-7su0.onrender.com/v1/execute \\
  -H <span class="s">"Authorization: Bearer $TONY_KEY"</span> \\
  -d <span class="s">'{"action":"github.create_issue",
      "args":{"repo":"acme/app","title":"Login loop"}}'</span>

<span class="k">→</span> { "ok": true, "status": 201,
    "data": { "number": 412, "url": "..." },
    "receipt": { "approval": "granted", "ms": 684 } }</pre>
    </div>
  </div>
</div></section>

<section class="sec" id="pricing" style="border-top:1px solid #101010"><div class="wrap">
  <div class="snum"><b>04</b><span></span></div>
  <div class="sec-hd rv"><h2>Priced per workspace, not per clever idea.</h2>
    <p>Start free. Pay when an agent starts doing real work.</p></div>
  <div class="tiers rv">__PRICING__</div>
</div></section>

<section class="close"><div class="wrap">
  <div class="mark">__MARK__</div>
  <h2>Connect your first app in about a minute.</h2>
  <p>Open the console, mint a link, send it to yourself, and watch the token land encrypted.</p>
  <div class="cta" style="justify-content:center">
    <a class="btn solid" href="/account">Open the console</a>
    <a class="btn ghost" href="/mcp">Install in your client</a>
  </div>
</div></section>
</main>

<footer><div class="wrap">
  <a class="mark" href="/" style="font-size:14px">__MARK_SM__Tony</a>
  <span class="grow"></span>
  <a class="mono" href="/docs">Docs</a><a class="mono" href="/sdk">SDKs</a>
  <a class="mono" href="/mcp">MCP</a><a class="mono" href="/account">Console</a>
  <span class="mono" style="color:#4b4b4b">v1</span>
</div></footer>
"""
BODY = BODY.replace("__MARK__", MARK).replace("__MARK_SM__", MARK)

JS = """
<script>
(function(){
  var io = new IntersectionObserver(function(l){
    l.forEach(function(e){ if(e.isIntersecting){ e.target.classList.add('on'); io.unobserve(e.target) } });
  },{threshold:.14});
  document.querySelectorAll('.rv').forEach(function(e){ io.observe(e) });
  document.querySelectorAll('[data-copy]').forEach(function(b){
    b.onclick=function(){ var t=document.getElementById(b.dataset.copy); if(!t) return;
      navigator.clipboard.writeText(t.textContent.trim()).then(function(){
        var o=b.textContent; b.textContent='copied'; setTimeout(function(){ b.textContent=o },1300);
      }).catch(function(){}); };
  });
})();
</script>
"""

# ─── real brand icons orbiting the Tony mark ────────────────────────────────
ORBIT_ICONS = [("github", "GitHub"), ("gmail", "Gmail"), ("slack", "Slack"), ("notion", "Notion"),
               ("stripe", "Stripe"), ("discord", "Discord"), ("figma", "Figma"), ("linear", "Linear"),
               ("googledrive", "Google Drive"), ("vercel", "Vercel"), ("spotify", "Spotify"),
               ("whatsapp", "WhatsApp"), ("telegram", "Telegram"), ("dropbox", "Dropbox"),
               ("shopify", "Shopify"), ("googlesheets", "Google Sheets"), ("trello", "Trello")]


def _orbit_html() -> str:
    """The mark at the centre, real provider icons on two rings around it."""
    import math

    nodes = []
    rings = [(4, 30.0, 0.0), (6, 41.0, 15.0), (7, 47.5, 12.0)]
    i = 0
    for count, radius, offset in rings:
        for k in range(count):
            if i >= len(ORBIT_ICONS):
                break
            slug, label = ORBIT_ICONS[i]
            ang = math.radians(offset + (360.0 / count) * k - 90)
            x = 50 + radius * math.cos(ang)
            y = 50 + radius * math.sin(ang)
            nodes.append(
                f'<span class="node r{count}" style="--x:{x:.2f}%;--y:{y:.2f}%;'
                f'animation-delay:{-(i * 0.63):.2f}s">'
                f'<img src="/static/brand/icons/{slug}.svg" alt="{label}" width="22" height="22" loading="lazy"></span>')
            i += 1
    return ('<div class="orbit" role="img" aria-label="Tony at the centre of the apps your agents can work in">'
            '<span class="ring r1"></span><span class="ring r2"></span><span class="ring r3"></span>'
            '<span class="orbit-glow"></span>'
            f'<span class="core">{MARK}</span>'
            + "".join(nodes) + "</div>")


CSS += """
.orbit-wrap{position:relative;display:grid;place-items:center}
.orbit{position:relative;width:100%;max-width:560px;aspect-ratio:1}
.ring{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);border-radius:50%;
 border:1px solid #131313}
.ring.r1{width:60%;height:60%}
.ring.r2{width:82%;height:82%;border-color:#171717}
.ring.r3{width:99%;height:99%;border-style:dashed;border-color:#141414}
.orbit-glow{position:absolute;left:50%;top:50%;width:46%;height:46%;transform:translate(-50%,-50%);
 border-radius:50%;background:radial-gradient(closest-side,rgba(226,84,43,.26),rgba(226,84,43,.06) 58%,transparent 76%);
 animation:breathe 6.5s ease-in-out infinite}
.core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:104px;height:104px;
 display:grid;place-items:center;border-radius:24px;background:#080807;border:1px solid #2a2a27;
 box-shadow:0 0 0 1px rgba(0,0,0,.9),0 24px 60px rgba(226,84,43,.18)}
.core svg{width:78px;height:78px;border-radius:18px;display:block}
.node{position:absolute;left:var(--x);top:var(--y);transform:translate(-50%,-50%);width:44px;height:44px;
 border-radius:12px;background:linear-gradient(180deg,#0d0d0d,#070707);border:1px solid #232323;
 display:grid;place-items:center;box-shadow:0 14px 30px rgba(0,0,0,.75);animation:bob 7s ease-in-out infinite}
.node img{width:21px;height:21px;display:block;opacity:.94}
.node.r4{width:38px;height:38px;border-radius:11px}
.node.r4 img{width:18px;height:18px}
@keyframes bob{0%,100%{transform:translate(-50%,-50%) translateY(-3px)}50%{transform:translate(-50%,-50%) translateY(3px)}}
@media(prefers-reduced-motion:reduce){.node,.orbit-glow{animation:none}}
@media(max-width:900px){
 .orbit{max-width:390px}
 .core{width:84px;height:84px;border-radius:20px}.core svg{width:62px;height:62px;border-radius:14px}
 .node{width:36px;height:36px;border-radius:10px}.node img{width:17px;height:17px}
 .node.r4{width:31px;height:31px}.node.r4 img{width:14px;height:14px}
}
"""

BODY = BODY.replace('''  <div class="hero-art">
    <img src="/static/brand/hero-orbit.jpg" width="1100" height="1100"
         alt="Tony's mark standing at the centre of a ring of connected application icons"
         loading="eager" decoding="async">
    <span class="art-tag"><i></i>every tile is one granted scope</span>
  </div>''', '''  <div class="hero-art">
    __ORBIT__
    <span class="art-tag"><i></i>one granted scope per tile</span>
  </div>''')
BODY = BODY.replace("__ORBIT__", _orbit_html())
