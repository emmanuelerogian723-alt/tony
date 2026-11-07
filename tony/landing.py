"""Tony landing page.

Design intent: a developer console you can read from across the room.
Graphite canvas, one electric accent, three typefaces with a job each,
light that behaves like light (soft falloff, additive glows, masked grid),
and motion that explains the product instead of decorating it.
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
    """Plan cards straight from the billing module, so the page can never lie."""
    from .billing import PLANS

    tick = ('<svg class="tick" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2.6" stroke-linecap="round"><path d="M4 12.5 9.4 18 20 6.6"/></svg>')
    out = []
    for pid in ("free", "pro", "business"):
        p = PLANS[pid]
        hot = pid == "pro"
        price = (f'<b>₦{p["price_ngn"]:,}</b><span>/month</span>' if p["price_ngn"]
                 else '<b>₦0</b><span>forever</span>')
        cta = ('<a class="btn ghost wide" href="/app">Start free</a>' if not p["price_ngn"]
               else f'<a class="btn {"solid" if hot else "ghost"} wide" href="/app#billing">Choose {p["name"]}</a>')
        items = "".join(f'<li>{tick}<span>{escape(h)}</span></li>' for h in p["highlights"])
        out.append(f"""<div class="tier{' hot' if hot else ''}">
      {'<span class="flag">most chosen</span>' if hot else ''}
      <div class="tname">{escape(p['name'])}</div>
      <div class="tag">{escape(p['tagline'])}</div>
      <div class="amt">{price}</div>
      <ul>{items}</ul>
      <div class="foot">{cta}</div>
    </div>""")
    return "".join(out)


def _ticker() -> str:
    names = ["GitHub", "Gmail", "Slack", "Notion", "Stripe", "Paystack", "Shopify", "Linear", "Vercel",
             "Cloudflare", "Supabase", "Airtable", "HubSpot", "Salesforce", "Figma", "Dropbox", "Twilio",
             "SendGrid", "OpenAI", "Anthropic", "Discord", "Telegram", "TikTok", "YouTube", "Spotify",
             "Mastodon", "Google Sheets", "Google Calendar", "Google Drive", "WhatsApp", "X", "Jira",
             "Trello", "Asana", "Zendesk", "Intercom", "Stripe Connect", "Plaid", "Razorpay", "Mailchimp"]
    cells = "".join(f'<span>{escape(n)}</span>' for n in names)
    return f'<div class="ticker" aria-hidden="true"><div class="ticker-track">{cells}{cells}</div></div>'


CSS = """
:root{
  --void:#060608; --void-2:#0a0a0f; --plate:#0e0e14; --plate-2:#12121a;
  --line:rgba(255,255,255,.09); --line-2:rgba(255,255,255,.16);
  --ink:#f5f6f8; --ink-2:#c9cbd4; --mut:#8b8f9c; --dim:#5f6470;
  --lime:#c8ff2e; --cyan:#5ce1ff; --violet:#a78bfa; --ember:#ff7a45;
  --glow-lime:rgba(200,255,46,.4); --glow-cyan:rgba(92,225,255,.32);
  --display:"Instrument Serif",ui-serif,Georgia,serif;
  --ui:"Inter Tight","Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --r:16px; --r-lg:22px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;overflow-x:clip}
body{margin:0;background:var(--void);color:var(--ink);font-family:var(--ui);
  font-size:15.5px;line-height:1.6;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  overflow-x:clip}
a{color:inherit;text-decoration:none}
h1,h2,h3{margin:0;font-weight:400}
p{margin:0}
::selection{background:var(--lime);color:#000}

/* ---------- light field ---------- */
.field{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
.field .aura{position:absolute;border-radius:50%;filter:blur(90px);opacity:.5;mix-blend-mode:screen}
.field .a1{width:52vw;height:52vw;left:-14vw;top:-18vw;background:radial-gradient(circle,rgba(200,255,46,.30),transparent 62%);
  animation:drift 26s ease-in-out infinite}
.field .a2{width:46vw;height:46vw;right:-12vw;top:6vh;background:radial-gradient(circle,rgba(92,225,255,.24),transparent 64%);
  animation:drift 32s ease-in-out infinite reverse}
.field .a3{width:40vw;height:40vw;left:24vw;top:52vh;background:radial-gradient(circle,rgba(167,139,250,.18),transparent 66%);
  animation:drift 38s ease-in-out infinite}
.field .grid{position:absolute;inset:-2px;background-image:
   linear-gradient(to right,rgba(255,255,255,.055) 1px,transparent 1px),
   linear-gradient(to bottom,rgba(255,255,255,.055) 1px,transparent 1px);
  background-size:64px 64px;
  -webkit-mask-image:radial-gradient(ellipse 70% 60% at 50% 0%,#000 20%,transparent 78%);
  mask-image:radial-gradient(ellipse 70% 60% at 50% 0%,#000 20%,transparent 78%)}
.field .grain{position:absolute;inset:0;opacity:.05;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E")}
.spot{position:fixed;inset:0;pointer-events:none;z-index:1;opacity:.55;
  background:radial-gradient(340px circle at var(--mx,50%) var(--my,0%),rgba(200,255,46,.10),transparent 70%);
  transition:opacity .3s}
@keyframes drift{0%,100%{transform:translate3d(0,0,0) scale(1)}50%{transform:translate3d(3vw,4vh,0) scale(1.08)}}

/* ---------- shell ---------- */
.wrap{width:min(1180px,92vw);margin-inline:auto;position:relative;z-index:2}
.nav{position:sticky;top:0;z-index:40;backdrop-filter:blur(18px) saturate(140%);
  background:linear-gradient(to bottom,rgba(6,6,8,.82),rgba(6,6,8,.42));border-bottom:1px solid var(--line)}
.nav .wrap{display:flex;align-items:center;gap:22px;height:66px}
.brand{display:flex;align-items:center;gap:10px;font-family:var(--ui);font-weight:600;letter-spacing:-.02em;font-size:16px}
.brand svg{filter:drop-shadow(0 0 12px rgba(200,255,46,.45))}
.nav .links{display:flex;gap:24px;margin-left:14px}
@media (max-width:980px){.nav .links{display:none}}
@media (max-width:560px){.nav .btngroup{display:none}.nav .wrap{gap:10px;height:60px}}
.nav .wrap .btn.sm{white-space:nowrap}
.nav .links a{font-size:13.5px;color:var(--ink-2);transition:color .18s}
.nav .links a:hover{color:var(--lime)}
.nav .sp{flex:1}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:42px;padding:0 18px;
  border-radius:11px;font-family:var(--ui);font-weight:500;font-size:13.5px;border:1px solid var(--line-2);
  color:var(--ink);background:rgba(255,255,255,.03);cursor:pointer;transition:transform .16s,box-shadow .2s,background .2s,border-color .2s}
.btn:hover{transform:translateY(-1px);border-color:rgba(255,255,255,.3);background:rgba(255,255,255,.07)}
.btn.solid{background:var(--lime);color:#07070a;border-color:transparent;font-weight:600;
  box-shadow:0 0 0 1px rgba(200,255,46,.4),0 12px 34px -12px var(--glow-lime)}
.btn.solid:hover{box-shadow:0 0 0 1px rgba(200,255,46,.6),0 18px 44px -12px var(--glow-lime)}
.btn.ghost{background:transparent}
.btn.wide{width:100%}
.btn.sm{height:36px;padding:0 14px;font-size:12.5px;border-radius:9px}

/* ---------- hero ---------- */
.hero{padding:clamp(54px,8vw,104px) 0 0;position:relative}
.eyebrow{display:inline-flex;align-items:center;gap:9px;height:30px;padding:0 13px 0 9px;border-radius:999px;
  border:1px solid var(--line-2);background:rgba(255,255,255,.04);font-family:var(--mono);font-size:10.5px;
  letter-spacing:.13em;text-transform:uppercase;color:var(--ink-2)}
.eyebrow i{width:6px;height:6px;border-radius:50%;background:var(--lime);box-shadow:0 0 0 4px rgba(200,255,46,.16);
  animation:blink 2.4s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}
.hero h1{font-family:var(--display);font-size:clamp(44px,7.4vw,88px);line-height:.95;letter-spacing:-.028em;
  margin:22px 0 0;max-width:15ch}
.hero h1 em{font-style:italic;color:var(--lime);text-shadow:0 0 44px rgba(200,255,46,.45)}
.hero .lede{margin-top:22px;max-width:56ch;font-size:clamp(15px,1.5vw,17.5px);color:var(--ink-2);line-height:1.62}
.hero .cta{display:flex;flex-wrap:wrap;gap:11px;margin-top:28px;align-items:center}
.hero .cta .note{font-family:var(--mono);font-size:11px;color:var(--dim);letter-spacing:.04em}
.hero-grid{display:grid;grid-template-columns:1.03fr .97fr;gap:clamp(24px,4vw,54px);align-items:center}
@media (max-width:940px){.hero-grid{grid-template-columns:1fr}}

/* prompt */
.prompt{margin-top:30px;position:relative;padding:1px;border-radius:15px;
  background:linear-gradient(120deg,rgba(200,255,46,.75),rgba(92,225,255,.5) 42%,rgba(255,255,255,.08) 72%);
  box-shadow:0 0 0 1px rgba(255,255,255,.05),0 26px 60px -30px rgba(200,255,46,.55)}
.prompt .inner{display:flex;align-items:center;gap:12px;background:#0b0b10;border-radius:14px;padding:6px 6px 6px 16px}
.prompt .inner>svg{flex:none;color:var(--lime)}
.prompt input{flex:1;background:none;border:0;outline:0;color:var(--ink);font-family:var(--mono);font-size:13.5px;
  padding:14px 0;min-width:0}
.prompt input::placeholder{color:var(--dim)}
.prompt .go{flex:none;height:42px;padding:0 16px;border-radius:10px;border:0;background:var(--lime);color:#07070a;
  font-family:var(--ui);font-weight:600;font-size:13px;cursor:pointer;box-shadow:0 8px 26px -10px var(--glow-lime)}
.prompt .go:active{transform:scale(.985)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chip{font-family:var(--mono);font-size:11px;color:var(--ink-2);border:1px solid var(--line);border-radius:999px;
  padding:6px 11px;background:rgba(255,255,255,.02);cursor:pointer;transition:border-color .18s,color .18s}
.chip:hover{border-color:rgba(200,255,46,.5);color:var(--lime)}
.result{margin-top:12px;min-height:0}
.result .row{display:flex;align-items:center;gap:10px;padding:11px 13px;border:1px solid var(--line);
  border-radius:11px;background:rgba(255,255,255,.025);margin-top:7px;
  animation:rise .35s cubic-bezier(.2,.7,.3,1) both}
.result .row .mono{font-family:var(--mono);font-size:11.5px;color:var(--cyan)}
.result .row .nm{font-size:13px;color:var(--ink)}
.result .row .cat{margin-left:auto;font-family:var(--mono);font-size:10px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--dim)}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}

/* code card */
.codecard{position:relative;border:1px solid var(--line-2);border-radius:var(--r-lg);overflow:hidden;
  background:linear-gradient(180deg,#0d0d13,#0a0a0f);
  box-shadow:0 1px 0 rgba(255,255,255,.06) inset,0 40px 90px -50px rgba(200,255,46,.35),0 30px 60px -40px rgba(0,0,0,.9);
  transform:perspective(1200px) rotateY(-4deg) rotateX(2deg);transition:transform .5s cubic-bezier(.2,.7,.3,1)}
.codecard:hover{transform:perspective(1200px) rotateY(0) rotateX(0)}
.codecard .bar{display:flex;align-items:center;gap:7px;padding:12px 14px;border-bottom:1px solid var(--line);
  background:rgba(255,255,255,.02)}
.codecard .bar .dot{width:9px;height:9px;border-radius:50%;background:#2a2a34}
.codecard .bar .dot:first-child{background:var(--lime);box-shadow:0 0 10px var(--glow-lime)}
.codecard .bar .file{margin-left:8px;font-family:var(--mono);font-size:11px;color:var(--dim)}
.codecard pre{margin:0;padding:18px 18px 20px;font-family:var(--mono);font-size:12.4px;line-height:1.75;
  color:#d7dae2;overflow-x:auto}
.codecard .k{color:var(--violet)} .codecard .s{color:var(--lime)} .codecard .c{color:#5f6470}
.codecard .f{color:var(--cyan)} .codecard .n{color:var(--ember)}
.codecard .out{border-top:1px solid var(--line);padding:12px 18px;display:flex;gap:10px;align-items:center;
  font-family:var(--mono);font-size:11px;color:var(--ink-2);background:rgba(200,255,46,.045)}
.codecard .out b{color:var(--lime);font-weight:600}

/* stats */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:clamp(40px,6vw,74px);
  border:1px solid var(--line);border-radius:var(--r);overflow:hidden;background:var(--line)}
.stat{background:var(--void-2);padding:20px 18px}
.stat b{display:block;font-family:var(--display);font-size:clamp(26px,3.4vw,36px);letter-spacing:-.02em;line-height:1;
  color:var(--ink)}
.stat span{display:block;margin-top:7px;font-family:var(--mono);font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim)}
@media (max-width:720px){.stats{grid-template-columns:1fr 1fr}}

/* sections */
.sec{padding:clamp(64px,9vw,116px) 0;position:relative}
.sec-head{max-width:64ch}
.kicker{font-family:var(--mono);font-size:10.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--lime);
  display:flex;align-items:center;gap:10px}
.kicker::after{content:"";height:1px;flex:1;background:linear-gradient(90deg,rgba(200,255,46,.5),transparent);max-width:120px}
h2{font-family:var(--display);font-size:clamp(30px,4.4vw,50px);line-height:1.04;letter-spacing:-.025em;margin:14px 0 0}
h2 em{font-style:italic;color:var(--cyan);text-shadow:0 0 34px var(--glow-cyan)}
.sub{margin-top:14px;color:var(--mut);max-width:58ch;font-size:15.5px}

.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:34px}
@media (max-width:900px){.cards{grid-template-columns:1fr}}
.card{position:relative;border:1px solid var(--line);border-radius:var(--r);padding:24px 22px;background:
  linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.012));overflow:hidden;transition:transform .25s,border-color .25s}
.card::before{content:"";position:absolute;inset:0;background:radial-gradient(320px circle at var(--cx,50%) var(--cy,0%),
  rgba(200,255,46,.12),transparent 65%);opacity:0;transition:opacity .3s;pointer-events:none}
.card:hover{transform:translateY(-3px);border-color:rgba(200,255,46,.35)}
.card:hover::before{opacity:1}
.card .ico{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;border:1px solid var(--line-2);
  background:rgba(200,255,46,.09);color:var(--lime);box-shadow:0 0 22px -6px var(--glow-lime)}
.card h3{margin:16px 0 8px;font-family:var(--ui);font-weight:600;font-size:16.5px;letter-spacing:-.01em}
.card p{color:var(--mut);font-size:14px}
.card .meta{margin-top:14px;font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim)}

/* flow */
.flow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:34px;counter-reset:f}
@media (max-width:900px){.flow{grid-template-columns:1fr 1fr}}
@media (max-width:560px){.flow{grid-template-columns:1fr}}
.step{position:relative;border:1px solid var(--line);border-radius:var(--r);padding:20px 18px;background:var(--plate)}
.step::after{content:"";position:absolute;top:50%;right:-13px;width:13px;height:1px;
  background:linear-gradient(90deg,var(--lime),transparent)}
.step:last-child::after{display:none}
@media (max-width:900px){.step::after{display:none}}
.step .num{font-family:var(--mono);font-size:10px;letter-spacing:.14em;color:var(--lime)}
.step b{display:block;margin-top:9px;font-size:14.5px;font-weight:600}
.step p{margin-top:6px;color:var(--mut);font-size:13px}

/* feature grid */
.feats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin-top:34px;
  border:1px solid var(--line);border-radius:var(--r);overflow:hidden;background:var(--line)}
@media (max-width:900px){.feats{grid-template-columns:1fr 1fr}}
@media (max-width:600px){.feats{grid-template-columns:1fr}}
.feat{background:var(--void-2);padding:22px;transition:background .25s}
.feat:hover{background:#101017}
.feat .t{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--cyan)}
.feat b{display:block;margin:10px 0 7px;font-size:15px;font-weight:600;letter-spacing:-.01em}
.feat p{color:var(--mut);font-size:13.4px}

/* ticker */
.ticker{margin-top:clamp(42px,6vw,72px);border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  overflow:hidden;position:relative;background:rgba(255,255,255,.012)}
.ticker::before,.ticker::after{content:"";position:absolute;top:0;bottom:0;width:110px;z-index:2;pointer-events:none}
.ticker::before{left:0;background:linear-gradient(90deg,var(--void),transparent)}
.ticker::after{right:0;background:linear-gradient(270deg,var(--void),transparent)}
.ticker-track{display:flex;width:max-content;animation:slide 52s linear infinite}
.ticker:hover .ticker-track{animation-play-state:paused}
@keyframes slide{from{transform:translate3d(0,0,0)}to{transform:translate3d(-50%,0,0)}}
.ticker span{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--dim);padding:13px 22px;border-right:1px solid var(--line);white-space:nowrap}
.ticker span:hover{color:var(--lime)}

/* pricing */
.pricing{display:grid;gap:14px;grid-template-columns:minmax(0,1fr);margin-top:34px}
@media (min-width:880px){.pricing{grid-template-columns:repeat(3,minmax(0,1fr))}}
.tier{position:relative;display:flex;flex-direction:column;gap:14px;min-width:0;padding:26px 22px 22px;
  border:1px solid var(--line);border-radius:var(--r-lg);background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.01));
  transition:transform .25s,border-color .25s,box-shadow .25s}
.tier:hover{transform:translateY(-3px);border-color:var(--line-2)}
.tier.hot{border-color:rgba(200,255,46,.5);box-shadow:0 0 0 1px rgba(200,255,46,.2),0 30px 70px -40px var(--glow-lime);
  background:linear-gradient(180deg,rgba(200,255,46,.07),rgba(255,255,255,.012))}
.tier .flag{position:absolute;top:-10px;right:18px;font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;
  text-transform:uppercase;background:var(--lime);color:#07070a;border-radius:999px;padding:4px 10px;font-weight:600}
.tier .tname{font-family:var(--display);font-size:23px;letter-spacing:-.02em}
.tier .tag{font-size:13.2px;color:var(--mut);min-height:38px;line-height:1.45;white-space:normal;overflow-wrap:anywhere}
.tier .amt{display:flex;align-items:baseline;gap:7px}
.tier .amt b{font-family:var(--display);font-size:40px;letter-spacing:-.03em;line-height:1}
.tier .amt span{font-family:var(--mono);font-size:11px;color:var(--dim)}
.tier ul{list-style:none;margin:0;padding:0;display:grid;gap:9px}
.tier li{display:flex;gap:9px;font-size:13.2px;color:var(--ink-2);line-height:1.45}
.tier li .tick{flex:none;margin-top:2px;color:var(--lime)}
.tier .foot{margin-top:auto;padding-top:6px}

/* faq */
.faq{margin-top:30px;border-top:1px solid var(--line)}
.faq details{border-bottom:1px solid var(--line);padding:16px 0}
.faq summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;
  font-size:15px;font-weight:500;letter-spacing:-.01em}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";margin-left:auto;font-family:var(--mono);color:var(--lime);font-size:16px}
.faq details[open] summary::after{content:"–"}
.faq p{margin:10px 0 0;color:var(--mut);font-size:14px;max-width:70ch}

/* close */
.close{margin-top:clamp(60px,9vw,110px);border:1px solid var(--line-2);border-radius:26px;padding:clamp(28px,5vw,58px);
  position:relative;overflow:hidden;background:
  radial-gradient(700px circle at 20% -20%,rgba(200,255,46,.16),transparent 60%),
  radial-gradient(600px circle at 90% 120%,rgba(92,225,255,.14),transparent 60%),#0b0b10}
.close h2{max-width:18ch}
.close .row{display:flex;flex-wrap:wrap;gap:11px;margin-top:26px;align-items:center}
.close .mono{font-family:var(--mono);font-size:11.5px;color:var(--mut)}

footer{border-top:1px solid var(--line);margin-top:70px;padding:30px 0 44px;position:relative;z-index:2}
footer .wrap{display:flex;flex-wrap:wrap;gap:18px;align-items:center}
footer .mono{font-family:var(--mono);font-size:11px;color:var(--dim)}
footer .sp{flex:1}
footer a:hover{color:var(--lime)}

/* reveal */
.rv{opacity:0;transform:translateY(16px);transition:opacity .6s cubic-bezier(.2,.7,.3,1),transform .6s cubic-bezier(.2,.7,.3,1)}
.rv.on{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .rv{opacity:1;transform:none}
}
"""

BODY = """
<div class="field" aria-hidden="true">
  <div class="aura a1"></div><div class="aura a2"></div><div class="aura a3"></div>
  <div class="grid"></div><div class="grain"></div>
</div>
<div class="spot" id="spot" aria-hidden="true"></div>

<header class="nav">
  <div class="wrap">
    <a class="brand" href="/">
      <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <rect x="2" y="2" width="28" height="28" rx="8" fill="#0e0e14" stroke="rgba(255,255,255,.16)"/>
        <circle cx="16" cy="16" r="7.4" stroke="#f5f6f8" stroke-width="2"/>
        <circle cx="16" cy="16" r="3.1" fill="#c8ff2e"/>
      </svg>
      Tony
    </a>
    <nav class="links">
      <a href="#how">How it works</a>
      <a href="#catalogue">Catalogue</a>
      <a href="#power">API</a>
      <a href="#pricing">Pricing</a>
      <a href="/app">Console</a>
    </nav>
    <span class="sp"></span>
    <a class="btn ghost sm" href="/app" data-hide-sm>Sign in</a>
    <a class="btn solid sm" href="/app">Start free</a>
  </div>
</header>

<main>
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <span class="eyebrow"><i></i>__APPS__ apps · __ACTIONS__ actions · one API</span>
      <h1>Give your AI <em>hands</em> on every app.</h1>
      <p class="lede">Tony is the execution layer for agents. Your model plans, Tony calls the app: __APPS__ integrations,
        real writes, encrypted credentials, approvals and receipts. One endpoint instead of forty SDKs.</p>
      <form class="prompt" id="search" onsubmit="return false" role="search">
        <span class="inner">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
            stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></svg>
          <input id="q" placeholder="search 7,900+ apps — try github, stripe, notion" autocomplete="off" aria-label="Search apps">
          <button class="go" type="submit">Find</button>
        </span>
      </form>
      <div class="chips" id="chips">
        <span class="chip" data-q="github">github</span>
        <span class="chip" data-q="gmail">gmail</span>
        <span class="chip" data-q="stripe">stripe</span>
        <span class="chip" data-q="notion">notion</span>
        <span class="chip" data-q="slack">slack</span>
      </div>
      <div class="result" id="result"></div>
      <div class="cta">
        <a class="btn solid" href="/app">Get an API key</a>
        <a class="btn ghost" href="#power">Read the API</a>
        <span class="note">free forever tier · no card</span>
      </div>
    </div>
    <div>
      <div class="codecard">
        <div class="bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>
          <span class="file">agent.py</span></div>
<pre><span class="c"># your model decides, Tony executes</span>
<span class="k">import</span> requests

r = requests.<span class="f">post</span>(<span class="s">"https://tony-7su0.onrender.com/v1/agent"</span>,
    headers={<span class="s">"Authorization"</span>: <span class="s">"Bearer tk_live_..."</span>},
    json={<span class="s">"goal"</span>: <span class="s">"open issues on my repo, summarise"</span>})

<span class="f">print</span>(r.json()[<span class="s">"answer"</span>])</pre>
        <div class="out"><b>✓ 412 ms</b> github.list_issues → 3 tools called · writes gated</div>
      </div>
    </div>
  </div>

  <div class="wrap">
    <div class="stats rv">
      <div class="stat"><b data-count="__APPS_N__">__APPS__</b><span>apps</span></div>
      <div class="stat"><b data-count="__ACTIONS_N__">__ACTIONS__</b><span>typed actions</span></div>
      <div class="stat"><b data-count="__WRITES_N__">__WRITES__</b><span>write actions</span></div>
      <div class="stat"><b>0</b><span>SDKs to learn</span></div>
    </div>
  </div>
  __TICKER__
</section>

<section class="sec" id="how">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">how it works</div>
      <h2>Your agent thinks. <em>Tony acts.</em></h2>
      <p class="sub">Four moves, no glue code. You keep the reasoning and the prompts; Tony owns auth, retries,
        rate limits, schemas and the audit trail.</p>
    </div>
    <div class="flow rv">
      <div class="step"><div class="num">01</div><b>Connect once</b><p>OAuth for apps that support it, a pasted key for the rest. Credentials are encrypted per call, never returned.</p></div>
      <div class="step"><div class="num">02</div><b>Hand over the tools</b><p><span class="mono">GET /v1/tools</span> returns model-ready schemas in OpenAI, Anthropic or MCP shape.</p></div>
      <div class="step"><div class="num">03</div><b>Let it execute</b><p><span class="mono">POST /v1/agent</span> plans across apps and returns the trace. Or call <span class="mono">/v1/execute</span> directly.</p></div>
      <div class="step"><div class="num">04</div><b>Approve the writes</b><p>Destructive actions wait for an explicit yes. Every run is logged with latency and status.</p></div>
    </div>
    <div class="cards">
      <div class="card"><div class="ico"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2 4 6v6c0 5 3.4 8.6 8 10 4.6-1.4 8-5 8-10V6l-8-4Z"/><path d="m9 12 2 2 4-4"/></svg></div>
        <h3>Credentials stay yours</h3><p>AES-256-GCM at rest, decrypted only for the request that needs it. API keys are stored as hashes. Per-user ownership, no shared pool.</p><div class="meta">security</div></div>
      <div class="card"><div class="ico"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z"/></svg></div>
        <h3>Writes with a gate</h3><p>Reads run instantly. Writes return a preview and a run id, then execute only when approved. Batch up to 20 calls with ordered results.</p><div class="meta">control</div></div>
      <div class="card"><div class="ico"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h10"/></svg></div>
        <h3>Receipts for everything</h3><p>Every call lands in the audit log with status, provider code, latency and payload size. Usage rolls up by app and by day.</p><div class="meta">observability</div></div>
    </div>
  </div>
</section>

<section class="sec" id="catalogue">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">catalogue</div>
      <h2>__APPS__ apps, <em>__ACTIONS__ actions</em>, one shape.</h2>
      <p class="sub">Curated hand-written actions for the apps agents reach for daily, OpenAPI ingestion for the long
        tail, and a documented proxy layer for everything else. Search is server-side and answers in milliseconds.</p>
    </div>
    <div class="feats rv">
      <div class="feat"><div class="t">curated</div><b>__CURATED__ apps</b><p>Typed inputs, real response shapes, pagination and danger notes written by hand.</p></div>
      <div class="feat"><div class="t">openapi</div><b>__OPENAPI__ apps</b><p>Ingested from public specs, normalised into the same action contract.</p></div>
      <div class="feat"><div class="t">proxy</div><b>Any REST endpoint</b><p><span class="mono">/v1/proxy/{app}/{path}</span> reaches documented paths with stored credentials injected.</p></div>
      <div class="feat"><div class="t">tools</div><b>Schema export</b><p>OpenAI functions, Anthropic tool use, MCP servers: same catalogue, three dialects.</p></div>
      <div class="feat"><div class="t">sessions</div><b>Scoped agents</b><p>Per-run identities with an app allowlist, tier ceiling, TTL and their own budget.</p></div>
      <div class="feat"><div class="t">memory</div><b>State that persists</b><p><span class="mono">/v1/memory</span> keeps per-entity state between agent calls, no extra database.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="power">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">the api</div>
      <h2>Small surface. <em>Sharp edges filed off.</em></h2>
      <p class="sub">Five endpoints cover the whole system. Everything else is discovery.</p>
    </div>
    <div class="cards">
      <div class="card"><div class="mono t">POST /v1/agent</div><h3>Goal in, evidence out</h3><p>Multi-step execution across apps with a trace of every tool call. Falls back to direct execution when the model is unavailable.</p></div>
      <div class="card"><div class="mono t">POST /v1/execute</div><h3>One action, exact</h3><p>Deterministic calls with typed args, dry-run previews, approval gates and a 30s hard deadline so nothing hangs.</p></div>
      <div class="card"><div class="mono t">GET /v1/tools</div><h3>Your model's toolbox</h3><p>Any slice of the catalogue as tool schemas, filtered to reads unless you ask for writes.</p></div>
      <div class="card"><div class="mono t">ALL /v1/proxy</div><h3>Escape hatch</h3><p>Call a documented endpoint Tony has not modelled yet, with auth and audit still applied.</p></div>
      <div class="card"><div class="mono t">POST /v1/batch</div><h3>Twenty at once</h3><p>Fan out reads or writes in one round trip, ordered results, per-call status.</p></div>
      <div class="card"><div class="mono t">GET /v1/usage</div><h3>Know the cost</h3><p>Runs by day, success rate, top apps. Billing meters read from the same numbers.</p></div>
    </div>
  </div>
</section>

<section class="sec" id="pricing">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">pricing</div>
      <h2>Start free. <em>Pay when it ships.</em></h2>
      <p class="sub">Every plan includes the full catalogue, the agent runtime and the SDKs. Limits are on runs, not on ambition.</p>
    </div>
    <div class="pricing rv">__PRICING__</div>
  </div>
</section>

<section class="sec">
  <div class="wrap">
    <div class="sec-head rv">
      <div class="kicker">questions</div>
      <h2>The things devs ask first.</h2>
    </div>
    <div class="faq rv">
      <details open><summary>Do I need my own API keys for every app?</summary>
        <p>Yes, and that is the point. You connect your own accounts, so usage bills land with the vendor you already pay and Tony never sits between you and your data. OAuth apps connect with a sign-in; key-based apps take a token once.</p></details>
      <details><summary>What stops an agent from deleting something?</summary>
        <p>Writes are gated. A write action returns a preview and a run id, and only executes when you approve it. Sessions can be capped at read-only, and every attempt is logged whether it ran or not.</p></details>
      <details><summary>What happens when a provider is slow or down?</summary>
        <p>Every call has a hard deadline and typed errors. Tony never hangs your agent thread, and the audit log records the provider's status code and latency so you can tell a Tony bug from a vendor outage.</p></details>
      <details><summary>Can I use this from Claude, Cursor or my own agent loop?</summary>
        <p>Both. Point an MCP client at <span class="mono">/mcp</span>, or call the REST API from your own loop with the tool schemas from <span class="mono">/v1/tools</span>. Python, TypeScript, JS, Go and Java SDKs are on <span class="mono">/sdk</span>.</p></details>
      <details><summary>What is the free tier really?</summary>
        <p>Pro-level catalogue access, a monthly run budget, connected accounts and custom tools. The trial starts on Pro for two weeks so you can measure it on real work, then it drops to free unless you pick a plan.</p></details>
    </div>
    <div class="close rv">
      <div class="kicker">ship it</div>
      <h2>Your model is smart. Give it <em>hands</em>.</h2>
      <div class="row">
        <a class="btn solid" href="/app">Create a free workspace</a>
        <a class="btn ghost" href="/docs">Read the docs</a>
        <span class="mono">tk_live_… in under a minute</span>
      </div>
    </div>
  </div>
</section>
</main>

<footer>
  <div class="wrap">
    <span class="mono">Tony · execution layer for agents</span>
    <span class="sp"></span>
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
  var spot = document.getElementById('spot');
  var raf = null;
  addEventListener('pointermove', function(e){
    if (raf) return;
    raf = requestAnimationFrame(function(){
      raf = null;
      document.documentElement.style.setProperty('--mx', e.clientX + 'px');
      document.documentElement.style.setProperty('--my', e.clientY + 'px');
    });
  }, {passive:true});

  document.querySelectorAll('.card').forEach(function(c){
    c.addEventListener('pointermove', function(e){
      var r = c.getBoundingClientRect();
      c.style.setProperty('--cx', ((e.clientX - r.left) / r.width * 100) + '%');
      c.style.setProperty('--cy', ((e.clientY - r.top) / r.height * 100) + '%');
    });
  });

  var io = new IntersectionObserver(function(entries){
    entries.forEach(function(en){ if (en.isIntersecting){ en.target.classList.add('on'); io.unobserve(en.target); } });
  }, {threshold:.12});
  document.querySelectorAll('.rv').forEach(function(el){ io.observe(el); });

  function countUp(el){
    var target = parseInt(el.getAttribute('data-count') || '0', 10);
    if (!target) return;
    var start = performance.now(), dur = 900;
    function frame(t){
      var p = Math.min(1, (t - start) / dur);
      el.textContent = Math.round(target * (0.2 + 0.8 * p) ).toLocaleString() ;
      if (p < 1) requestAnimationFrame(frame); else el.textContent = target.toLocaleString();
    }
    requestAnimationFrame(frame);
  }
  var seen = new IntersectionObserver(function(es){
    es.forEach(function(e){ if (e.isIntersecting){ countUp(e.target); seen.unobserve(e.target); } });
  }, {threshold:.6});
  document.querySelectorAll('[data-count]').forEach(function(el){ seen.observe(el); });

  var q = document.getElementById('q'), box = document.getElementById('result');
  var timer = null;
  function render(items){
    if (!items.length){ box.innerHTML = '<div class="row"><span class="nm">No match. Try a vendor name.</span></div>'; return }
    box.innerHTML = items.slice(0,4).map(function(a){
      return '<div class="row"><span class="mono">'+a.slug+'</span><span class="nm">'+
        (a.name||a.slug)+'</span><span class="cat">'+(a.category||'app')+'</span></div>';
    }).join('');
  }
  function search(term){
    if (!term.trim()){ box.innerHTML = ''; return }
    fetch('/v1/apps?q='+encodeURIComponent(term)+'&limit=4')
      .then(function(r){ return r.json() })
      .then(function(d){ render(d.apps || d.results || []) })
      .catch(function(){ box.innerHTML = '' });
  }
  if (q){
    q.addEventListener('input', function(){
      clearTimeout(timer);
      timer = setTimeout(function(){ search(q.value) }, 180);
    });
  }
  document.querySelectorAll('.chip').forEach(function(chip){
    chip.addEventListener('click', function(){
      if (!q) return;
      q.value = chip.getAttribute('data-q') || '';
      search(q.value); q.focus();
    });
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

    fonts = ("https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&"
             "family=Inter+Tight:wght@400;500;600;700&"
             "family=JetBrains+Mono:wght@400;500;600&display=swap")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tony · the execution layer for AI agents</title>
<meta name="description" content="One API that gives your AI hands on {app_count:,} apps with {action_count:,} typed actions, encrypted credentials and approval-gated writes.">
<meta name="theme-color" content="#060608">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{fonts}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<style>{CSS}</style>
</head>
<body>
{body}
{JS}
</body>
</html>"""
