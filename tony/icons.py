"""App icons that never come back empty.

Three things used to break the catalogue tiles:

* ``cdn.simpleicons.org`` answers 403 to datacenter IPs, so Render saw an error
  for every mark. jsDelivr and unpkg serve the same icons as static files and do
  not block us;
* the local brand SVGs shipped white (``fill="#F3F0E9"``) with no background, so
  on a light card they rendered as nothing at all;
* a missing logo fell straight through to a guessed favicon.

Every icon now resolves through one ordered chain and always ends in real bytes:
local mark on a dark tile, a cached copy, then a mirror, then favicon services,
then a deterministic letter tile.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ICON_DIR = Path(__file__).resolve().parent / "static" / "brand" / "icons"

# Marks that 404 or 403 on the public simple-icons CDN, and the mirror name that
# does serve them. Keeping this data (not code per app) is what makes it cheap.
SIMPLE_SLUG_OVERRIDES = {
    "openai": "openai",
    "linkedin": "linkedin",
    "sendgrid": "sendgrid",
    "twilio": "twilio",
    "groq": "groq",
    "mondaydotcom": "mondaydotcom",
    "monday": "mondaydotcom",
    "google_calendar": "googlecalendar",
    "google_drive": "googledrive",
    "google_sheets": "googlesheets",
    "whatsapp": "whatsapp",
    "hackernews": "ycombinator",
    "hacker_news": "ycombinator",
    "x": "x",
    "twitter": "x",
    "gmail": "gmail",
    "exchangerate": "exchangeratehost",
    "alpha_vantage": "alphavantage",
    "elevenlabs": "elevenlabs",
    "jsonplaceholder": "json",
    "lemonsqueezy": "lemonsqueezy",
    "coingecko": "coingecko",
    "gnews": "googlenews",
    "calcom": "caldotcom",
    "finnhub": "finnhub",
    "flutterwave": "flutterwave",
}

# Where the product actually lives, when the slug is not the domain.
DOMAIN_OVERRIDES = {
    "mondaydotcom": "monday.com", "monday": "monday.com",
    "google_calendar": "calendar.google.com", "googlecalendar": "calendar.google.com",
    "google_drive": "drive.google.com", "googledrive": "drive.google.com",
    "google_sheets": "docs.google.com", "googlesheets": "docs.google.com",
    "gmail": "mail.google.com",
    "hackernews": "news.ycombinator.com", "hacker_news": "news.ycombinator.com",
    "alpha_vantage": "alphavantage.co", "alphavantage": "alphavantage.co",
    "exchangerate": "exchangerate.host", "jsonplaceholder": "jsonplaceholder.typicode.com",
    "gnews": "gnews.io", "calcom": "cal.com", "x": "x.com", "twitter": "x.com",
}

_PALETTE = ["#E2542B", "#2563EB", "#16A34A", "#9333EA", "#D97706", "#0891B2",
            "#DB2777", "#4F46E5", "#0D9488", "#CA8A04", "#7C3AED", "#EA580C"]
_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def simple_slug(slug: str) -> str:
    key = (slug or "").strip().lower()
    return SIMPLE_SLUG_OVERRIDES.get(key, key.replace("_", "").replace("-", ""))


def local_mark(slug: str) -> Path | None:
    """A brand SVG shipped with Tony, if there is one."""
    for cand in (slug, (slug or "").replace("_", "").replace("-", "")):
        if not cand:
            continue
        path = ICON_DIR / f"{cand}.svg"
        if path.exists() and path.stat().st_size > 0:
            return path
    key = simple_slug(slug)
    path = ICON_DIR / f"{key}.svg"
    return path if path.exists() and path.stat().st_size > 0 else None


def wrap_mark(raw: str, slug: str, bg: str = "") -> bytes:
    """Put a white-on-nothing mark on a dark rounded tile.

    The shipped SVGs are single-colour paths with a fixed off-white fill and a
    24x24 viewBox. Dropped into a light card they were invisible, which is what
    the empty tiles in the catalogue actually were.
    """
    text = raw if isinstance(raw, str) else raw.decode("utf-8", "ignore")
    view = re.search(r'viewBox="([^"]+)"', text)
    box = view.group(1) if view else "0 0 24 24"
    body = re.sub(r"<svg[^>]*>", "", text, count=1)
    body = body.replace("</svg>", "")
    body = _HEX.sub("#FFFFFF", body)
    body = re.sub(r'fill="(?!none|#FFFFFF)[^"]*"', 'fill="#FFFFFF"', body)
    colour = bg or _PALETTE[int(hashlib.md5((slug or "app").encode()).hexdigest(), 16) % len(_PALETTE)]
    parts = box.split()
    width = parts[2] if len(parts) >= 4 else "24"
    height = parts[3] if len(parts) >= 4 else "24"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="64" height="64">'
        f'<rect width="{width}" height="{height}" rx="{float(width) * 0.22:g}" fill="{colour}"/>'
        f'<g transform="translate({float(width) * 0.18:g} {float(height) * 0.18:g}) '
        f'scale({float(width) * 0.64 / 24:g})">{body}</g></svg>'
    ).encode("utf-8")


def letter_tile(name: str, slug: str) -> str:
    letter = (re.sub(r"[^A-Za-z0-9]", "", name or slug)[:1] or "?").upper()
    colour = _PALETTE[int(hashlib.md5((slug or name).encode()).hexdigest(), 16) % len(_PALETTE)]
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
            f'<rect width="64" height="64" rx="16" fill="{colour}"/>'
            '<text x="32" y="43" text-anchor="middle" font-family="Inter,Arial,sans-serif" '
            f'font-size="32" font-weight="700" fill="#fff">{letter}</text></svg>')


def _host(spec: Any) -> str:
    for u in (getattr(spec, "base_url", ""), getattr(spec, "docs", "")):
        try:
            host = urlparse(u or "").netloc.lower()
        except Exception:
            host = ""
        if host and "{" not in host:
            parts = host.split(".")
            root = ".".join(parts[-2:]) if len(parts) > 2 and parts[-2] not in ("co", "com") else host
            return root[4:] if root.startswith("api.") else root
    return ""


def remote_candidates(spec: Any, slug: str) -> list[str]:
    """Every place a real mark might live, best first. Static CDNs before favicons."""
    out: list[str] = []
    logo = (getattr(spec, "logo", "") or "").strip()
    if "cdn.simpleicons.org/" in logo:
        name = logo.rsplit("/", 2)[-2]
        out.append(f"https://cdn.jsdelivr.net/npm/simple-icons@13/icons/{name}.svg")
        out.append(f"https://unpkg.com/simple-icons@13/icons/{name}.svg")
    elif logo.startswith("http") and "favicons?domain=" not in logo:
        out.append(logo)
        if "simpleicons" in logo:
            out.append(f"https://cdn.jsdelivr.net/npm/simple-icons@13/icons/{simple_slug(slug)}.svg")
    mirror = simple_slug(slug)
    out.append(f"https://cdn.jsdelivr.net/npm/simple-icons@13/icons/{mirror}.svg")
    host = _host(spec)
    if not host:
        host = DOMAIN_OVERRIDES.get((slug or "").lower(), "")
    if not host and spec is not None:
        # No base_url to read (many directory entries), so fall back to the one
        # guess that is usually right: the product's own .com.
        guess = (slug or "").replace("_", "").replace("-", "")
        host = f"{guess}.com" if guess else ""
    if host:
        out.append(f"https://icons.duckduckgo.com/ip3/{host}.ico")
        out.append(f"https://icon.horse/icon/{host}")
        out.append(f"https://www.google.com/s2/favicons?domain={host}&sz=128")
    seen: list[str] = []
    for url in out:
        if url and url not in seen:
            seen.append(url)
    return seen
