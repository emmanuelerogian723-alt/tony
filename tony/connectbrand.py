"""Tony x App brand header, shared by every connect surface.

Composio's connect screen always shows two logos joined by a link: the platform
and the app being connected, with "<Agent> wants to connect to your <App>" under
them. This module renders exactly that for Tony, so the same header appears in
the Playground modal, the hosted /connect page and the Connections dashboard.
"""
from __future__ import annotations

import html

from .playground_page import logo

PAIR_CSS = """
.tpair{display:flex;align-items:center;justify-content:center;gap:0;margin:0 auto 18px}
.tpair .tl,.tpair .ap{width:60px;height:60px;border-radius:16px;display:grid;place-items:center;overflow:hidden;
 background:#fff;border:1px solid rgba(13,13,12,.1);box-shadow:0 6px 20px rgba(13,13,12,.09);position:relative}
.tpair .tl{border:0;background:transparent;box-shadow:0 6px 20px rgba(13,13,12,.22)}
.tpair .tl svg{width:60px;height:60px;display:block}
.tpair .ap img{width:34px;height:34px;object-fit:contain;display:block}
.tpair .ap.fill img{width:100%;height:100%;border-radius:16px}
.tpair .lk{position:relative;width:54px;height:2px;margin:0 6px;
 background:repeating-linear-gradient(90deg,#c9c7bf 0 5px,transparent 5px 9px)}
.tpair .lk:after{content:"";position:absolute;top:-3px;left:0;width:8px;height:8px;border-radius:50%;
 background:#E2542B;animation:tlk 1.5s ease-in-out infinite}
@keyframes tlk{0%{left:0;opacity:.2}50%{opacity:1}100%{left:calc(100% - 8px);opacity:.2}}
.tpair.done .lk{background:#16a34a}.tpair.done .lk:after{display:none}
"""


def pair(slug: str, size: int = 60, done: bool = False) -> str:
    """Tony logo, an animated link, and the app's real logo (with a letter-tile fallback)."""
    s = html.escape(slug, quote=True)
    return (f'<div class="tpair{" done" if done else ""}"><div class="tl">{logo(size, "p" + str(abs(hash(slug)) % 9999))}</div>'
            f'<div class="lk"></div><div class="ap"><img alt="" src="/v1/icon/{s}" '
            f"onerror=\"if(!this.dataset.f){{this.dataset.f=1;this.src='/v1/icon-tile/{s}';this.parentNode.classList.add('fill')}}\">"
            f'</div></div>')
