"""Keyless web search that survives datacenter IPs.

DuckDuckGo's HTML endpoint and most scraped engines blackhole requests coming
from cloud networks, which is exactly where Tony runs. So search here is a
fan-out: Google News RSS (current events), DuckDuckGo's Instant Answer API
(definitions and topic hubs) and Wikipedia's search API (reference). Each
source is independent, so one being blocked never empties the result set.
"""
from __future__ import annotations

import asyncio
import html as _html
import re
from typing import Any
from urllib.parse import quote_plus

import httpx

UA = "Mozilla/5.0 (compatible; TonyGateway/0.2; +https://github.com/emmanuelerogian723-alt/tony)"
TIMEOUT = 8.0
_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return _html.unescape(_TAG.sub(" ", s or "")).replace("\xa0", " ").strip()


def _rss(xml: str, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for block in re.findall(r"(?is)<item>(.*?)</item>", xml or "")[:limit]:
        def grab(tag: str) -> str:
            m = re.search(rf"(?is)<{tag}[^>]*>(.*?)</{tag}>", block)
            return _clean(m.group(1)) if m else ""
        title = grab("title")
        link = grab("link")
        if not title or not link:
            continue
        out.append({
            "title": title,
            "url": link,
            "snippet": grab("description")[:300],
            "published": grab("pubDate"),
            "source": "news",
        })
    return out


async def _news(client: httpx.AsyncClient, q: str, limit: int) -> list[dict[str, Any]]:
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
    r = await client.get(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml"})
    r.raise_for_status()
    return _rss(r.text, limit)


async def _instant(client: httpx.AsyncClient, q: str, limit: int) -> list[dict[str, Any]]:
    url = ("https://api.duckduckgo.com/?q=" + quote_plus(q)
           + "&format=json&no_html=1&skip_disambig=1&t=tony")
    r = await client.get(url, headers={"User-Agent": UA, "Accept": "application/json"})
    r.raise_for_status()
    d = r.json()
    out: list[dict[str, Any]] = []
    if d.get("AbstractText"):
        out.append({
            "title": d.get("Heading") or q,
            "url": d.get("AbstractURL") or "",
            "snippet": _clean(d["AbstractText"])[:300],
            "source": "instant",
        })
    for topic in (d.get("RelatedTopics") or [])[:limit]:
        if isinstance(topic, dict) and topic.get("FirstURL"):
            out.append({
                "title": _clean(topic.get("Text", ""))[:110] or topic["FirstURL"],
                "url": topic["FirstURL"],
                "snippet": _clean(topic.get("Text", ""))[:300],
                "source": "instant",
            })
    return out


async def _wiki(client: httpx.AsyncClient, q: str, limit: int) -> list[dict[str, Any]]:
    url = ("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit="
           + str(min(limit, 8)) + "&srsearch=" + quote_plus(q))
    r = await client.get(url, headers={"User-Agent": UA, "Accept": "application/json"})
    r.raise_for_status()
    hits = (((r.json().get("query") or {}).get("search")) or [])
    return [{
        "title": _clean(h.get("title", "")),
        "url": "https://en.wikipedia.org/wiki/" + quote_plus((h.get("title") or "").replace(" ", "_")),
        "snippet": _clean(h.get("snippet", ""))[:300],
        "source": "wiki",
    } for h in hits]


async def multi_search(q: str, limit: int = 12) -> dict[str, Any]:
    """Search three independent, keyless sources and merge the results."""
    q = (q or "").strip()[:300]
    if not q:
        return {"query": q, "results": [], "sources": {}}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        gathered = await asyncio.gather(
            _news(client, q, limit), _instant(client, q, limit), _wiki(client, q, max(4, limit // 2)),
            return_exceptions=True,
        )
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources: dict[str, int] = {}
    for name, res in zip(("news", "instant", "wiki"), gathered):
        if isinstance(res, Exception):
            sources[name] = 0
            continue
        sources[name] = len(res)
        for item in res:
            key = (item.get("url") or item.get("title") or "").lower()[:180]
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return {"query": q, "results": merged[:limit], "sources": sources, "blocked": [k for k, v in sources.items() if v == 0]}
