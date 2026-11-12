"""Map-reduce briefs: 20,000 pages in, one readable answer out.

A reader that returns 20k pages has not solved the problem, it has moved it:
the agent still cannot fit them in a context window. So the last stage of a read
job is compression.

No model call is required. Summaries are extractive and deterministic: sentences
are scored against the job's own term statistics, pages are clustered by shared
vocabulary so eight copies of the same press release collapse into one theme, and
the brief carries the sources and the counts a reviewer needs to trust it. That
keeps cost at zero per job and makes the output reproducible, which matters when
the thing you are summarising is untrusted text off the open web.

Two details decide whether a brief is useful or noise, and both are handled here:
dates and site chrome ("posted", "september") are stripped from keywords so a
weblog archive does not theme itself around month names, and each key point is one
cleaned sentence, not a paragraph, so the answer stays skimmable.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from sqlalchemy import select

from .db import session
from .models import ReadJob, ReadPage

STOP = set("""a an the and or but if then than that this these those of to in on for with from by as at is are was were be been being it its
""".split())

# Months and weekdays are dates, not subjects.
CALENDAR = set("""january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec monday tuesday wednesday thursday friday saturday sunday
""".split())

# Front-end chrome that leaks into extracted text on almost every site.
CHROME = set("""posted comments comment read more share subscribe newsletter sign signin login logout register
privacy cookie cookies terms contact about home search menu skip previous next view all rights reserved
page pages blog post posts article articles author published updated tag tags category categories follow
""".split())

NOISE = STOP | CALENDAR | CHROME
YEAR = re.compile(r"^(19|20)\d{2}$")
WORD = re.compile(r"[a-z0-9][a-z0-9'’-]{2,}")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“])")

POINT_CHARS = 260
ANALYSIS_PAGES = 400


def _terms(text: str) -> list[str]:
    return [w for w in WORD.findall((text or "").lower())
            if w not in NOISE and not YEAR.match(w) and not w.isdigit()]


def _clean(text: str, limit: int = POINT_CHARS) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def _chrome_sentence(sentence: str) -> bool:
    """Reject navigation and link lists that survive extraction."""
    low = sentence.strip().lower()
    if low.startswith(("skip to", "jump to", "read the docs", "posted by", "posted on")):
        return True
    if sentence.count("|") >= 2 or "›" in sentence or "»" in sentence:
        return True
    letters = sum(1 for c in sentence if c.isalpha() or c.isspace())
    return letters / max(1, len(sentence)) < 0.72


def _fingerprint(sentence: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", sentence.lower()))[:140]


def _boilerplate(pages: list[dict[str, Any]]) -> set[str]:
    """Sentences repeated across many pages are the site's furniture, not its content.

    A sponsor strip or "skip to main content" appears on every page of a site, so it
    wins every frequency contest unless it is identified and removed first.
    """
    seen: Counter[str] = Counter()
    for page in pages:
        prints = {_fingerprint(s) for s in _sentences(page["content"][:20000], limit=60)}
        seen.update(prints)
    floor = max(3, int(0.12 * len(pages)))
    return {fp for fp, n in seen.items() if n >= floor}


def _sentences(text: str, limit: int = 220) -> list[str]:
    parts = [s.strip() for s in SENT_SPLIT.split(text or "") if 40 <= len(s.strip()) <= 400]
    return [s for s in parts if not _chrome_sentence(s)][:limit]


def _score_sentences(sentences: list[str], idf: dict[str, float], boost: dict[str, float]) -> list[tuple[float, int, str]]:
    scored: list[tuple[float, int, str]] = []
    for idx, sentence in enumerate(sentences):
        terms = _terms(sentence)
        if not terms:
            continue
        weight = sum(idf.get(t, 1.0) for t in terms) / (len(terms) ** 0.65)
        weight += sum(boost.get(t, 0.0) for t in set(terms)) * 0.6
        if idx == 0:
            weight *= 1.25          # openers tend to carry the point
        if len(terms) < 6:
            weight *= 0.6
        scored.append((weight, idx, sentence))
    scored.sort(reverse=True)
    return scored


def _top_terms(text: str, idf: dict[str, float], k: int = 25) -> list[str]:
    """Keywords weighted by rarity across the job, so 'september' cannot win."""
    counts = Counter(_terms(text))
    scored = {t: n * idf.get(t, 1.0) for t, n in counts.items()}
    return [t for t, _ in sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:k]]


def _bigrams(text: str, idf: dict[str, float], df_ratio: dict[str, float], k: int = 12) -> list[str]:
    """Phrases ranked by rarity, so a site-wide slogan never becomes a theme."""
    words = [w for w in _terms(text) if df_ratio.get(w, 0.0) <= 0.5]
    pairs = [f"{a} {b}" for a, b in zip(words, words[1:]) if len(a) > 3 and len(b) > 3]
    counts = Counter(pairs)
    scored = {p: n * (idf.get(p.split()[0], 1.0) + idf.get(p.split()[1], 1.0)) / 2
              for p, n in counts.items()}
    return [p for p, _ in sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:k]]


def _cluster(pages: list[dict[str, Any]], threshold: float = 0.42) -> list[dict[str, Any]]:
    """Group pages that talk about the same thing, so 8 copies count once."""
    clusters: list[dict[str, Any]] = []
    for page in pages:
        terms = set(page["top_terms"])
        placed = False
        for cluster in clusters:
            overlap = len(terms & cluster["terms"]) / max(1, len(terms | cluster["terms"]))
            if overlap >= threshold:
                cluster["pages"].append(page)
                cluster["terms"] |= terms
                placed = True
                break
        if not placed:
            clusters.append({"terms": set(terms), "pages": [page]})
    clusters.sort(key=lambda c: sum(p["words"] for p in c["pages"]), reverse=True)
    return clusters


def _theme_label(cluster: dict[str, Any]) -> str:
    """A phrase two or more of its pages share beats a bag of single words."""
    pairs: Counter[str] = Counter()
    for page in cluster["pages"][:12]:
        pairs.update(set(page.get("bigrams") or []))
    repeated = [p for p, n in pairs.most_common(8) if n >= 2]
    if repeated:
        return ", ".join(repeated[:2])
    singles = [t for t, n in Counter(
        [t for p in cluster["pages"][:12] for t in p["top_terms"][:8]]).most_common(4) if n >= 2]
    if singles:
        return ", ".join(singles[:3])
    head = cluster["pages"][0]
    return _clean(head["title"], 70) or head["url"]


def build_brief(job_id: str, workspace: str, max_points: int = 12, max_sentences: int = 3) -> dict[str, Any]:
    """Compress a finished read job into a brief with themes, points and sources."""
    with session() as s:
        job = s.scalar(select(ReadJob).where(ReadJob.id == job_id, ReadJob.workspace_id == workspace))
        if job is None:
            raise KeyError(job_id)
        rows = s.scalars(select(ReadPage).where(
            ReadPage.job_id == job_id, ReadPage.status == "done", ReadPage.word_count > 0)).all()
        pages_in = [{
            "url": r.url, "title": r.title or r.url, "content": r.content or "",
            "words": r.word_count, "risk": r.risk_score, "http": r.http_status,
        } for r in rows]
        seed = job.seed_url or (pages_in[0]["url"] if pages_in else "")

    if not pages_in:
        return {"job_id": job_id, "pages_used": 0, "words_in": 0, "words_out": 0, "compression": 0,
                "brief": "No readable text was stored for this job.", "themes": [], "points": [],
                "sources": [], "flagged_pages": 0, "has_more_pages": False}

    sample = pages_in[:ANALYSIS_PAGES]
    total_docs = max(1, len(sample))
    df: Counter[str] = Counter()
    for page in sample:
        df.update(set(_terms(page["content"][:20000])))
    idf = {term: math.log(1 + total_docs / (1 + n)) for term, n in df.items()}
    df_ratio = {term: n / total_docs for term, n in df.items()}

    # Words that recur, but not on nearly every page: subject matter rather than
    # site furniture. Anything above half the pages is treated as chrome.
    boost = {t: 1.0 for t, n in df.items() if 1 < n <= max(2, 0.35 * total_docs)}

    furniture = _boilerplate(pages_in)
    for page in pages_in:
        body = page["content"][:20000]
        page["top_terms"] = _top_terms(body, idf)
        page["bigrams"] = _bigrams(body, idf, df_ratio)
        usable = [s for s in _sentences(body) if _fingerprint(s) not in furniture]
        best = _score_sentences(usable, idf, boost)[:max(1, max_sentences)]
        page["summary"] = _clean(" ".join(s for _, _, s in best)) or ""

    clusters = _cluster(pages_in)
    points: list[dict[str, Any]] = []
    themes: list[dict[str, Any]] = []
    for cluster in clusters[: max(3, max_points // 2)]:
        head = cluster["pages"][0]
        label = _theme_label(cluster)
        themes.append({"theme": label, "pages": len(cluster["pages"]),
                       "words": sum(p["words"] for p in cluster["pages"]),
                       "sample": head["url"]})
        for page in cluster["pages"][:2]:
            if len(points) < max_points and page["summary"]:
                points.append({"point": page["summary"], "source": page["url"],
                               "title": _clean(page["title"], 120), "theme": label})
    if not points:
        points = [{"point": p["summary"], "source": p["url"], "title": _clean(p["title"], 120), "theme": ""}
                  for p in pages_in[:max_points] if p["summary"]]
    if not points:
        points = [{"point": _clean(p["title"], 90), "source": p["url"],
                   "title": _clean(p["title"], 120), "theme": ""} for p in pages_in[:max_points]]

    words = sum(p["words"] for p in pages_in)
    flagged = [p for p in pages_in if p["risk"]]
    words_out = sum(len(p["point"].split()) for p in points)
    brief_lines = [
        f"Read {len(pages_in)} page(s) from {seed or 'the submitted URLs'}, {words:,} words in total.",
        f"{len(clusters)} distinct theme(s) after collapsing duplicate content.",
    ]
    if themes:
        brief_lines.append("Subjects: " + "; ".join(f"{t['theme']} ({t['pages']})" for t in themes[:6]) + ".")
    if flagged:
        brief_lines.append(f"{len(flagged)} page(s) carried prompt-injection patterns and were neutralised before use.")
    brief_lines.append("Key points follow, each tied to its source.")

    return {
        "job_id": job_id,
        "seed": seed,
        "pages_used": len(pages_in),
        "words_in": words,
        "words_out": words_out,
        "compression": round(words / max(1, words_out), 1),
        "themes": themes,
        "points": points,
        "sources": [{"url": p["url"], "title": _clean(p["title"], 120), "words": p["words"]} for p in pages_in[:80]],
        "flagged_pages": len(flagged),
        "brief": "\n".join(brief_lines),
        "has_more_pages": len(pages_in) > ANALYSIS_PAGES,
    }


def brief_markdown(brief: dict[str, Any]) -> str:
    lines = [f"# Brief: {brief.get('seed') or brief['job_id']}", "", brief.get("brief", ""), ""]
    if brief.get("themes"):
        lines.append("## Themes")
        for theme in brief["themes"]:
            lines.append(f"- {theme['theme']} — {theme['pages']} page(s), {theme['words']:,} words")
        lines.append("")
    if brief.get("points"):
        lines.append("## Key points")
        for point in brief["points"]:
            lines.append(f"- {point['point']}  \n  <{point['source']}>")
        lines.append("")
    if brief.get("sources"):
        lines.append("## Sources")
        for src in brief["sources"]:
            lines.append(f"- {src['title']} — {src['url']}")
    return "\n".join(lines)
