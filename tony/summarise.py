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
WORD = re.compile(r"[a-z0-9][a-z0-9'’-]{2,}")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“])")


def _terms(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOP]


def _sentences(text: str, limit: int = 220) -> list[str]:
    parts = [s.strip() for s in SENT_SPLIT.split(text or "") if 40 <= len(s.strip()) <= 400]
    return parts[:limit]


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


def _keywords(texts: list[str], k: int = 12) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(set(_terms(text)))
    return counts.most_common(k)


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
        total_known = s.scalar(select(ReadPage.id).where(ReadPage.job_id == job_id).limit(1))
        seed = job.seed_url or (pages_in[0]["url"] if pages_in else "")

    if not pages_in:
        return {"job_id": job_id, "pages_used": 0, "words_in": 0, "words_out": 0, "compression": 0,
                "brief": "No readable text was stored for this job.", "themes": [], "points": [],
                "sources": [], "flagged_pages": 0, "has_more_pages": False}

    corpus_text = "\n".join(p["content"][:20000] for p in pages_in[:400])
    counts = Counter(_terms(corpus_text))
    total_docs = max(1, len(pages_in))
    df: Counter[str] = Counter()
    for page in pages_in[:400]:
        df.update(set(_terms(page["content"][:20000])))
    idf = {term: math.log(1 + total_docs / (1 + n)) for term, n in df.items()}

    # the words that recur across many pages are the subject matter, so they get a nudge
    global_top = [t for t, _ in counts.most_common(40)]
    boost = {t: 1.0 for t in global_top}

    for page in pages_in:
        sents = _sentences(page["content"])
        page["top_terms"] = [t for t, _ in Counter(_terms(page["content"][:20000])).most_common(25)]
        best = _score_sentences(sents, idf, boost)[:max_sentences]
        page["summary"] = " ".join(s for _, _, s in best)[:700] or (page["content"][:280] if page["content"] else "")

    clusters = _cluster(pages_in)
    points: list[dict[str, Any]] = []
    themes: list[dict[str, Any]] = []
    for cluster in clusters[: max(3, max_points // 2)]:
        head = cluster["pages"][0]
        label = ", ".join(t for t, _ in Counter(
            [t for p in cluster["pages"][:12] for t in p["top_terms"][:8]]).most_common(4))
        themes.append({"theme": label or head["title"][:60], "pages": len(cluster["pages"]),
                       "words": sum(p["words"] for p in cluster["pages"]),
                       "sample": head["url"]})
        for page in cluster["pages"][:2]:
            if len(points) < max_points and page["summary"]:
                points.append({"point": page["summary"], "source": page["url"],
                               "title": page["title"][:120], "theme": label})
    if not points:
        points = [{"point": p["summary"], "source": p["url"], "title": p["title"][:120], "theme": ""}
                  for p in pages_in[:max_points] if p["summary"]]

    words = sum(p["words"] for p in pages_in)
    flagged = [p for p in pages_in if p["risk"]]
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
        "words_out": sum(len(p["point"].split()) for p in points),
        "compression": round(words / max(1, sum(len(p["point"].split()) for p in points)), 1),
        "themes": themes,
        "points": points,
        "sources": [{"url": p["url"], "title": p["title"][:120], "words": p["words"]} for p in pages_in[:80]],
        "flagged_pages": len(flagged),
        "brief": "\n".join(brief_lines),
        "has_more_pages": bool(total_known),
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
