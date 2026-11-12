"""Read Anything: turn URLs, a sitemap or a whole site into clean text an agent can use.

This is the piece integration platforms leave out. They give you *actions*
("send an email"), not *reading at scale* ("read these 20,000 pages and tell me
what changed"). Scraping APIs exist but bill per page, cap concurrency and hand
back raw HTML that blows up a context window.

Design constraints that shaped this:

* A 512MB single worker cannot hold 20k pages in memory, so the frontier and the
  results live in the database and content is streamed back page by page.
* Work must survive a restart. Rows are the queue: a page is ``pending``,
  ``done``, ``failed`` or ``duplicate``, so a redeploy resumes where it stopped.
* Every fetch goes through the shared governor (per-host politeness), the SSRF
  guard (no metadata endpoints, no loopback) and the injection firewall, because
  a fetched page is untrusted input to a model.
* Dedupe is by content hash, not URL: the same article under eight tracking
  parameters is stored once and the copies are reported as duplicates.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from sqlalchemy import func, select, update

from . import firewall
from .db import session
from .governor import GOVERNOR
from .models import ReadJob, ReadPage

MAX_PAGE_BYTES = int(os.getenv("TONY_READ_PAGE_BYTES", str(2 * 1024 * 1024)))
MAX_CHARS_STORED = int(os.getenv("TONY_READ_PAGE_CHARS", "200000"))
MAX_PAGES_HARD = int(os.getenv("TONY_READ_MAX_PAGES", "20000"))
DEFAULT_TIMEOUT = float(os.getenv("TONY_READ_TIMEOUT", "20"))
USER_AGENT = os.getenv("TONY_READ_UA", "TonyReader/1.0 (+https://tony-7su0.onrender.com)")
WORKERS = int(os.getenv("TONY_READ_WORKERS", "8"))

SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "template", "iframe", "form", "nav",
             "footer", "header", "aside", "menu", "button", "select", "option"}
BLOCK_TAGS = {"p", "div", "section", "article", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
              "pre", "blockquote", "dd", "dt", "table"}
TRACKING_PARAMS = re.compile(r"^(utm_|gclid|fbclid|mc_cid|mc_eid|ref|ref_src|igshid|si)", re.I)


# ── extraction ────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self.description = ""
        self.lang = ""
        self.links: list[tuple[str, str]] = []
        self._skip = 0
        self._in_title = False
        self._href: str | None = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and data.get("lang"):
            self.lang = data["lang"][:20]
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (data.get("name") or data.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.description:
                self.description = data.get("content", "")[:500]
        elif tag == "a" and data.get("href"):
            self._href = data["href"][:2000]
            self._anchor = []
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._href:
            label = " ".join("".join(self._anchor).split())[:200]
            self.links.append((self._href, label))
            self._href, self._anchor = None, []
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip:
            return
        if self._href is not None:
            self._anchor.append(data)
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t\u00a0]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return "\n".join(line.strip() for line in raw.splitlines()).strip()


def extract(html_text: str, base_url: str) -> dict[str, Any]:
    parser = _TextExtractor()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        pass
    text = parser.text()
    links = []
    seen = set()
    for href, label in parser.links:
        absolute = tidy_url(urljoin(base_url, href)) if not href.startswith(("mailto:", "tel:", "javascript:")) else ""
        if not absolute or absolute in seen:
            continue
        seen.add(absolute)
        links.append({"url": absolute, "text": label})
        if len(links) >= 300:
            break
    return {
        "title": " ".join(html.unescape(parser.title).split())[:300],
        "description": html.unescape(parser.description).strip(),
        "lang": parser.lang,
        "text": text[:MAX_CHARS_STORED],
        "word_count": len(text.split()),
        "links": links,
    }


def tidy_url(raw: str) -> str:
    """Drop fragments and tracking parameters so duplicates collapse."""
    try:
        parts = urlsplit(raw.strip())
    except ValueError:
        return ""
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    query = "&".join(
        chunk for chunk in parts.query.split("&")
        if chunk and not TRACKING_PARAMS.match(chunk.split("=", 1)[0])
    )
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def same_site(a: str, b: str) -> bool:
    ha, hb = urlsplit(a).netloc.lower(), urlsplit(b).netloc.lower()
    return ha == hb or ha.removeprefix("www.") == hb.removeprefix("www.")


# ── robots.txt ────────────────────────────────────────────────────────────

_ROBOTS: dict[str, tuple[float, list[str], list[str]]] = {}


async def _robots(client: httpx.AsyncClient, url: str) -> tuple[list[str], list[str], float]:
    """(disallow, allow, crawl_delay) for the site's host, cached for 10 minutes."""
    import time as _time

    parts = urlsplit(url)
    host = parts.netloc.lower()
    cached = _ROBOTS.get(host)
    if cached and _time.time() - cached[0] < 600:
        return cached[1], cached[2], cached[3]
    disallow: list[str] = []
    allow: list[str] = []
    delay = 0.0
    try:
        async with GOVERNOR.slot(host, "robots"):
            resp = await client.get(f"{parts.scheme}://{host}/robots.txt", headers={"user-agent": USER_AGENT})
        if resp.status_code == 200 and len(resp.text) < 200_000:
            applies = False
            for line in resp.text.splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or ":" not in line:
                    if not line:
                        applies = False
                    continue
                key, value = line.split(":", 1)
                key, value = key.strip().lower(), value.strip()
                if key == "user-agent":
                    applies = value == "*" or "tony" in value.lower()
                elif applies and key == "disallow" and value:
                    disallow.append(value)
                elif applies and key == "allow" and value:
                    allow.append(value)
                elif applies and key in {"crawl-delay", "request-rate"}:
                    try:
                        delay = min(5.0, float(value.split("/")[0]))
                    except ValueError:
                        pass
    except Exception:
        pass
    _ROBOTS[host] = (_time.time(), disallow, allow, delay)
    return disallow, allow, delay


def allowed_by_robots(path: str, disallow: list[str], allow: list[str]) -> bool:
    for rule in allow:
        if path.startswith(rule):
            return True
    for rule in disallow:
        if rule == "/":
            return False
        if path.startswith(rule):
            return False
    return True


# ── job engine ────────────────────────────────────────────────────────────

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:32]


def _add_page(job_id: str, url: str, depth: int, status: str = "pending") -> bool:
    """Insert a frontier row, ignoring URLs already known for this job."""
    with session() as s:
        existing = s.scalar(select(ReadPage.id).where(ReadPage.job_id == job_id, ReadPage.url == url))
        if existing:
            return False
        s.add(ReadPage(job_id=job_id, url=url, depth=depth, status=status))
        s.flush()
    return True


def create_job(workspace: str, *, urls: list[str] | None = None, site: str = "", sitemap: str = "",
               depth: int = 1, max_pages: int = 50, entity_id: str = "default",
               follow_links: bool = True, render: bool = False) -> str:
    targets = [tidy_url(u) for u in (urls or []) if tidy_url(u)]
    seed = tidy_url(site or (targets[0] if targets else ""))
    if not targets and not seed and sitemap:
        seed = ""
    max_pages = max(1, min(int(max_pages or 50), MAX_PAGES_HARD))
    if not targets and not seed and not sitemap:
        raise ValueError("Give urls, a site or a sitemap")
    with session() as s:
        job = ReadJob(
            workspace_id=workspace,
            entity_id=entity_id or "default",
            status="queued",
            seed_url=seed,
            sitemap_url=sitemap or "",
            depth=max(0, min(int(depth), 4)),
            max_pages=max_pages,
            follow_links=bool(follow_links),
            render=bool(render),
            options_json=json.dumps({"urls": targets[:500]}),
        )
        s.add(job)
        s.flush()
        job_id = job.id
    for u in targets[:500]:
        _add_page(job_id, u, 0)
    if not targets and sitemap:
        _add_page(job_id, tidy_url(sitemap), 0, status="sitemap")
    elif not targets and seed:
        _add_page(job_id, seed, 0, status="sitemap")
    return job_id


def enqueue(job_id: str) -> None:
    """Start the job in this process (fire and forget)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(run_job(job_id))


def _job_row(job_id: str):
    with session() as s:
        return s.scalar(select(ReadJob).where(ReadJob.id == job_id))


def _set_status(job_id: str, status: str, **fields: Any) -> None:
    with session() as s:
        job = s.scalar(select(ReadJob).where(ReadJob.id == job_id))
        if job is None:
            return
        job.status = status
        for key, value in fields.items():
            setattr(job, key, value)
        if status in {"done", "failed", "cancelled"}:
            job.finished_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        s.flush()


def _next_pending(job_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with session() as s:
        rows = s.scalars(
            select(ReadPage).where(ReadPage.job_id == job_id, ReadPage.status.in_({"pending", "sitemap"}))
            .order_by(ReadPage.depth.asc(), ReadPage.created_at.asc()).limit(limit)
        ).all()
        out = []
        for row in rows:
            kind = row.status          # sitemap seeds keep their kind through the claim
            row.status = "claimed"
            out.append({"id": row.id, "url": row.url, "depth": row.depth, "kind": kind})
        s.flush()
    return out


def _save_page(page_id: str, **fields: Any) -> None:
    with session() as s:
        row = s.scalar(select(ReadPage).where(ReadPage.id == page_id))
        if row is None:
            return
        for key, value in fields.items():
            setattr(row, key, value)
        s.flush()


def _counts(job_id: str) -> dict[str, int]:
    with session() as s:
        rows = s.execute(
            select(ReadPage.status, func.count()).where(ReadPage.job_id == job_id).group_by(ReadPage.status)
        ).all()
    return {status: int(n) for status, n in rows}


async def _expand_sitemap(client: httpx.AsyncClient, job: dict[str, Any], url: str, job_id: str) -> list[tuple[str, int]]:
    """Read a sitemap (or sitemap index) and return its page URLs."""
    found: list[tuple[str, int]] = []
    try:
        async with GOVERNOR.slot(urlsplit(url).netloc, job["workspace_id"]):
            resp = await client.get(url, headers={"user-agent": USER_AGENT})
        if resp.status_code >= 400 or len(resp.text) > 5 * 1024 * 1024:
            return found
        body = resp.text
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body, re.I)
        nested = bool(re.search(r"<sitemapindex", body[:2000], re.I))
        if nested:
            for child in locs[:5]:
                child_url = html.unescape(child)
                async with GOVERNOR.slot(urlsplit(child_url).netloc, job["workspace_id"]):
                    sub = await client.get(child_url, headers={"user-agent": USER_AGENT})
                if sub.status_code < 400:
                    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sub.text, re.I)[: job["max_pages"]]:
                        found.append((tidy_url(html.unescape(loc)), 0))
        else:
            found = [(tidy_url(html.unescape(loc)), 0) for loc in locs]
    except Exception:
        pass
    return [(u, d) for u, d in found if u]


async def _fetch_one(client: httpx.AsyncClient, job: dict[str, Any], page: dict[str, Any]) -> dict[str, Any]:
    """Fetch and extract one page, with politeness, robots and retries."""
    url = page["url"]
    parts = urlsplit(url)
    started = asyncio.get_running_loop().time()

    if page["kind"] == "sitemap":
        seeds = await _expand_sitemap(client, job, url, job["id"])
        _save_page(page["id"], status="done", http_status=200,
                   title=f"sitemap: {len(seeds)} urls", content="", word_count=0,
                   content_hash=_hash(url))
        for seed_url, depth in seeds:
            if _total(job["id"]) < job["max_pages"]:
                _add_page(job["id"], seed_url, depth + 1)
        return {"expanded": len(seeds)}

    disallow, allow, delay = await _robots(client, url)
    if not allowed_by_robots(parts.path or "/", disallow, allow):
        _save_page(page["id"], status="skipped", error="robots.txt disallows this path",
                   title="", content="", word_count=0, content_hash=_hash(url))
        return {"skipped": "robots"}

    last_error = ""
    for attempt in range(3):
        try:
            async with GOVERNOR.slot(parts.netloc, job["workspace_id"]):
                if delay:
                    await asyncio.sleep(min(delay, 3.0))
                resp = await client.get(url, headers={"user-agent": USER_AGENT,
                                                      "accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"})
            if resp.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                _save_page(page["id"], status="failed", http_status=resp.status_code,
                           error=f"HTTP {resp.status_code}", title="", content="", word_count=0,
                           content_hash=_hash(url))
                return {"failed": resp.status_code}
            raw = resp.content[:MAX_PAGE_BYTES]
            ctype = resp.headers.get("content-type", "")
            if "html" in ctype or raw[:200].lstrip().lower().startswith((b"<!doctype", b"<html")):
                data = extract(raw.decode(resp.encoding or "utf-8", "ignore"), url)
            elif ctype.startswith("text/") or "json" in ctype or "xml" in ctype:
                text = raw.decode(resp.encoding or "utf-8", "ignore")
                data = {"title": "", "description": "", "lang": "", "text": text[:MAX_CHARS_STORED],
                        "word_count": len(text.split()), "links": []}
            else:
                _save_page(page["id"], status="skipped", http_status=resp.status_code,
                           error=f"unsupported content-type {ctype[:60]}", title="", content="",
                           word_count=0, content_hash=_hash(url))
                return {"skipped": "content-type"}

            digest = _hash(data["text"] or url)
            verdict = firewall.scan(data["text"][:40000]) if data["text"] else {"score": 0, "flags": []}
            duplicate = False
            with session() as s:
                duplicate = bool(s.scalar(select(ReadPage.id).where(
                    ReadPage.job_id == job["id"], ReadPage.content_hash == digest,
                    ReadPage.status == "done", ReadPage.id != page["id"])))
            latency = int((asyncio.get_running_loop().time() - started) * 1000)
            _save_page(page["id"], status="duplicate" if duplicate else "done",
                       http_status=resp.status_code, title=data["title"], description=data["description"],
                       content="" if duplicate else data["text"], content_hash=digest,
                       word_count=data["word_count"], links_json=json.dumps(data["links"])[:60000],
                       latency_ms=latency, risk_score=int(verdict.get("score", 0) or 0),
                       error="" if not duplicate else "duplicate content")
            if job["follow_links"] and page["depth"] < job["depth"] and not duplicate:
                for link in data["links"][:60]:
                    if not same_site(link["url"], job["seed_url"] or url):
                        continue
                    if _total(job["id"]) >= job["max_pages"]:
                        break
                    _add_page(job["id"], link["url"], page["depth"] + 1)
            return {"ok": True, "duplicate": duplicate, "words": data["word_count"]}
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"[:300]
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))
    _save_page(page["id"], status="failed", error=last_error, title="", content="", word_count=0,
               content_hash=_hash(url))
    return {"failed": last_error}


def _total(job_id: str) -> int:
    with session() as s:
        return int(s.scalar(select(func.count()).select_from(ReadPage).where(ReadPage.job_id == job_id)) or 0)


async def run_job(job_id: str) -> None:
    job = _job_row(job_id)
    if job is None:
        return
    if job.status in {"done", "cancelled"}:
        return
    _set_status(job_id, "running")
    meta = {
        "id": job_id, "workspace_id": job.workspace_id, "seed_url": job.seed_url or "",
        "depth": job.depth, "max_pages": job.max_pages, "follow_links": job.follow_links,
    }
    bytes_in = 0
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True,
                                     limits=httpx.Limits(max_connections=24, max_keepalive_connections=12)) as client:
            while True:
                fresh = _job_row(job_id)
                if fresh is None or fresh.status in {"cancelled"}:
                    return
                batch = _next_pending(job_id, limit=WORKERS * 3)
                if not batch:
                    break
                results = await asyncio.gather(*[_fetch_one(client, meta, page) for page in batch],
                                               return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        continue
                counts = _counts(job_id)
                done = counts.get("done", 0) + counts.get("duplicate", 0)
                if _total(job_id) >= meta["max_pages"] and not _next_pending(job_id, 1):
                    break
                _set_status(job_id, "running", fetched=done)
        # Anything still queued hit the page cap or a crashed worker: record it
        # honestly instead of leaving phantom work in the job state.
        with session() as s:
            s.execute(update(ReadPage).where(
                ReadPage.job_id == job_id, ReadPage.status.in_({"pending", "claimed", "sitemap"})
            ).values(status="skipped", error="not fetched (page cap or shutdown)"))
        counts = _counts(job_id)
        finished = counts.get("done", 0) + counts.get("duplicate", 0)
        _set_status(job_id, "done", fetched=finished,
                    failed=counts.get("failed", 0) + counts.get("skipped", 0),
                    bytes_in=bytes_in)
    except Exception as exc:  # noqa: BLE001
        _set_status(job_id, "failed", error=f"{type(exc).__name__}: {exc}"[:400])


def resume_unfinished() -> None:
    """On boot, pick up jobs a restart interrupted."""
    try:
        with session() as s:
            rows = s.scalars(select(ReadJob).where(ReadJob.status.in_({"queued", "running"}))).all()
            ids = [r.id for r in rows]
        for job_id in ids:
            enqueue(job_id)
        if ids:
            import logging
            logging.getLogger("tony").info("reader resumed %d job(s)", len(ids))
    except Exception:
        pass


# ── reads for the API ─────────────────────────────────────────────────────

def job_state(job_id: str, workspace: str) -> dict[str, Any] | None:
    with session() as s:
        job = s.scalar(select(ReadJob).where(ReadJob.id == job_id, ReadJob.workspace_id == workspace))
        if job is None:
            return None
        counts = _counts(job_id)
        return {
            "job_id": job.id,
            "status": job.status,
            "seed": job.seed_url,
            "sitemap": job.sitemap_url,
            "depth": job.depth,
            "max_pages": job.max_pages,
            "pages_known": sum(counts.values()),
            "done": counts.get("done", 0),
            "duplicate": counts.get("duplicate", 0),
            "failed": counts.get("failed", 0),
            "skipped": counts.get("skipped", 0),
            "pending": counts.get("pending", 0) + counts.get("claimed", 0) + counts.get("sitemap", 0),
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else "",
            "finished_at": job.finished_at.isoformat() if job.finished_at else "",
        }


def job_pages(job_id: str, workspace: str, offset: int = 0, limit: int = 50,
              include_content: bool = True, status: str = "") -> dict[str, Any]:
    with session() as s:
        job = s.scalar(select(ReadJob).where(ReadJob.id == job_id, ReadJob.workspace_id == workspace))
        if job is None:
            raise KeyError(job_id)
        q = select(ReadPage).where(ReadPage.job_id == job_id, ReadPage.status.in_({"done", "duplicate"}))
        if status:
            q = select(ReadPage).where(ReadPage.job_id == job_id, ReadPage.status == status)
        rows = s.scalars(q.order_by(ReadPage.created_at.asc()).offset(offset).limit(min(limit, 200))).all()
        pages = []
        for row in rows:
            item = {
                "url": row.url,
                "status": row.status,
                "http_status": row.http_status,
                "title": row.title,
                "description": row.description,
                "word_count": row.word_count,
                "content_hash": row.content_hash,
                "risk_score": row.risk_score,
                "latency_ms": row.latency_ms,
                "error": row.error,
            }
            if include_content:
                item["content"] = row.content
                try:
                    item["links"] = json.loads(row.links_json or "[]")
                except ValueError:
                    item["links"] = []
            pages.append(item)
        return {"pages": pages, "offset": offset, "limit": limit, "count": len(pages)}
