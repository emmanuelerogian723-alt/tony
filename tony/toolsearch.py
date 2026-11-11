"""Intelligent tool discovery.

Composio-style platforms lose users at the search box: you ask for "send an
email to my customer" and get SCIM noise. This engine ranks ACTIONS (not just
apps) using hybrid retrieval:

    score = 3.0 * exact-phrase hits
          + 2.0 * keyword/token coverage
          + 1.5 * fuzzy token similarity (typos, partial words)
          + 1.2 * synonym/intent expansion ("mail" -> email, "post" -> publish)
          + 0.8 * verb-object intent match ("send" + "email")
          + 0.6 * usage prior (what people actually run)
          - 0.8 * tier penalty (proxy < actions < read-write risk)
          + boosts for app-name matches

It is pure keyword/semantic-lite: no embeddings service required, no API keys,
sub-10ms for the whole catalog, and it works on thousands of actions without
loading any of them into a model context.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

STOP = {
    "a", "an", "the", "my", "me", "i", "to", "for", "of", "in", "on", "with", "and",
    "or", "please", "can", "you", "could", "would", "this", "that", "it", "is", "are",
    "some", "any", "from", "into", "at", "by", "be", "do", "does", "then", "so",
}

# intent vocabulary: user word -> canonical concepts present in action text
SYNONYMS: dict[str, list[str]] = {
    "email": ["email", "mail", "gmail", "message", "inbox", "send"],
    "mail": ["email", "mail", "gmail", "send"],
    "message": ["message", "send", "chat", "post", "slack", "sms"],
    "video": ["video", "youtube", "upload", "media", "clip"],
    "photo": ["photo", "image", "picture", "upload", "media"],
    "picture": ["photo", "image", "picture", "upload"],
    "upload": ["upload", "create", "publish", "send", "attach"],
    "post": ["post", "publish", "create", "share", "tweet"],
    "publish": ["publish", "post", "create", "share", "upload"],
    "file": ["file", "drive", "document", "attachment", "upload", "storage"],
    "document": ["document", "file", "doc", "pdf", "drive"],
    "calendar": ["calendar", "event", "meeting", "schedule"],
    "meeting": ["meeting", "event", "calendar", "schedule"],
    "issue": ["issue", "ticket", "bug", "task", "github"],
    "repo": ["repo", "repository", "github", "project"],
    "sheet": ["sheet", "spreadsheet", "rows", "excel", "table"],
    "customer": ["customer", "client", "contact", "lead", "user"],
    "client": ["client", "customer", "contact", "lead"],
    "invoice": ["invoice", "billing", "payment", "charge"],
    "payment": ["payment", "charge", "invoice", "checkout", "pay"],
    "delete": ["delete", "remove", "archive", "destroy"],
    "search": ["search", "find", "list", "query", "lookup"],
    "list": ["list", "all", "search", "browse", "fetch"],
    "reply": ["reply", "respond", "answer", "send"],
    "download": ["download", "export", "fetch", "get"],
}

# the verb usually carries the intent; object words carry the target
VERBS = {
    "send", "create", "post", "publish", "upload", "delete", "update", "get", "list",
    "search", "find", "download", "read", "reply", "schedule", "invite", "add",
    "remove", "archive", "cancel", "book", "share", "comment", "react", "follow",
}

APP_ALIASES: dict[str, list[str]] = {
    "gmail": ["email", "mail", "inbox", "gmail"],
    "googlecalendar": ["calendar", "event", "meeting", "schedule", "appointment"],
    "youtube": ["youtube", "video", "channel", "subscribe"],
    "googledrive": ["drive", "file", "folder", "storage", "upload"],
    "googlesheets": ["sheet", "spreadsheet", "excel", "rows"],
    "slack": ["slack", "channel", "workspace", "team chat"],
    "github": ["github", "repo", "repository", "issue", "pull request", "pr"],
    "linkedin": ["linkedin", "post", "professional network"],
    "facebook": ["facebook", "page", "meta"],
    "instagram": ["instagram", "reel", "story", "post"],
    "tiktok": ["tiktok", "clip", "short video"],
    "x": ["tweet", "twitter", "x post"],
    "notion": ["notion", "page", "database"],
    "stripe": ["stripe", "payment", "charge", "subscription"],
    "paystack": ["paystack", "payment", "naira"],
}

# risk preference: when scores tie, prefer actions that actually do the work
TIER_BONUS = {"read": 0.15, "write": 0.10, "destructive": -0.55}
PROXY_PENALTY = 0.8

# catch-all apps (generic HTTP, public-API dumps) should never outrank a real
# integration unless the user actually names them
GENERIC_APPS = {"api", "proxy", "http", "rest", "public-api", "apis"}
GENERIC_PENALTY = 1.6

# questions ask for information, so read actions should win them outright
READ_INTENT = re.compile(
    r"\b(what|whats|what's|which|who|when|where|how many|how much|show|list|"
    r"summari[sz]e|summary|latest|recent|check|read|find|search|look|any|"
    r"status|report|history|fetch|get)\b", re.I)


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in raw if t not in STOP and len(t) > 1]


def _bigrams(tokens: list[str]) -> set[str]:
    return {f"{a} {b}" for a, b in zip(tokens, tokens[1:])}


def _ratio(a: str, b: str) -> float:
    """Cheap edit-distance similarity without pulling in a dependency."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    if b.startswith(a):
        return 0.9 * (len(a) / len(b))
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    dist = prev[lb]
    return max(0.0, 1.0 - dist / max(la, lb))


def expand(query: str) -> list[str]:
    """Query expansion: add the canonical concepts behind the user's words."""
    extra: list[str] = []
    for t in _tokens(query):
        extra.extend(SYNONYMS.get(t, []))
    out = []
    for t in extra:
        if t not in out:
            out.append(t)
    return out


class ToolIndex:
    """Ranked action index over the catalog. Built lazily, cached by revision."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self._usage: Counter[str] = Counter()
        self._built_for: Any = None
        self._postings: dict[str, list[int]] = {}
        self._vocab: dict[str, list[str]] = {}
        self._cache: dict[Any, list[dict[str, Any]]] = {}

    # ── building ───────────────────────────────────────────────────────────
    def build(self, catalog: Any, force: bool = False) -> "ToolIndex":
        revision = getattr(catalog, "revision", None) or len(getattr(catalog, "apps", {}) or {})
        if not force and self._built_for == revision and self.docs:
            return self
        docs: list[dict[str, Any]] = []
        shadowed = getattr(catalog, "shadowed", set()) or set()
        for app in (catalog.apps.values() if hasattr(catalog, "apps") else []):
            if app.slug in shadowed:
                continue   # duplicate import of a product we already index
            app_tokens = _tokens(f"{app.slug} {app.name} {getattr(app, 'category', '')} "
                                 f"{getattr(app, 'description', '')}")
            for action in app.actions:
                if getattr(action, "universal", False):
                    continue   # same passthrough on every app: never let it crowd real actions
                text = (f"{app.slug} {app.name} {action.slug} {action.name} "
                        f"{getattr(action, 'description', '')} {getattr(action, 'tier', '')}")
                toks = _tokens(text)
                docs.append({
                    "app": app, "action": action,
                    "slug": f"{app.slug}.{action.slug}",
                    "app_tokens": app_tokens, "tokens": toks,
                    "bigrams": _bigrams(toks),
                    "tier": getattr(action, "tier", "read") or "read",
                    "name": f"{app.name} {action.name}".strip(),
                    "description": getattr(action, "description", "") or "",
                })
        # typed connectors are curated, friendly actions — index them first-class
        try:
            from . import connectors as _cx
            meta = {
                ("gmail", "send_email"): "Send an email with to, subject, body and attachments",
                ("gmail", "reply_email"): "Reply in an existing email thread",
                ("youtube", "upload_video"): "Upload a video file to YouTube with title and privacy",
                ("slack", "post_message"): "Post a message to a Slack channel",
                ("slack", "upload_file"): "Upload a file to Slack",
                ("github", "create_issue"): "Create a GitHub issue with labels and assignees",
                ("linkedin", "create_post"): "Publish a LinkedIn post",
                ("facebook", "create_post"): "Publish a Facebook page post or photo",
                ("googlecalendar", "create_event"): "Create a calendar event with attendees",
            }
            for app_slug, acts in _cx.CONNECTORS.items():
                app = catalog.apps.get(app_slug) if hasattr(catalog, "apps") else None
                for act_slug in acts:
                    desc = meta.get((app_slug, act_slug), f"{act_slug.replace('_', ' ')} on {app_slug}")
                    app_name = getattr(app, "name", app_slug.title()) if app else app_slug.title()
                    text = f"{app_slug} {app_name} {act_slug} {desc} typed action connector"
                    toks = _tokens(text)
                    from types import SimpleNamespace
                    docs.insert(0, {
                        "app": app or SimpleNamespace(slug=app_slug, name=app_name,
                                                     category="", description="", actions=[]),
                        "action": SimpleNamespace(slug=act_slug, name=act_slug.replace("_", " ").title(),
                                                  description=desc, tier="write", url=""),
                        "slug": f"{app_slug}.{act_slug}",
                        "app_tokens": _tokens(f"{app_slug} {app_name}"),
                        "tokens": toks, "bigrams": _bigrams(toks), "tier": "write",
                        "name": f"{app_name} {act_slug.replace('_', ' ').title()}",
                        "description": desc, "typed": True,
                    })
        except Exception:
            pass
        self.docs = docs
        postings: dict[str, list[int]] = defaultdict(list)
        vocab: dict[str, list[str]] = defaultdict(list)
        for i, d in enumerate(docs):
            for t in set(d["tokens"]) | set(d["app_tokens"]):
                postings[t].append(i)
                vocab[t[:1]].append(t)
        self._postings = dict(postings)
        self._vocab = {k: sorted(set(v)) for k, v in vocab.items()}
        self._cache = {}
        self._built_for = revision
        return self

    def note_usage(self, slug: str, weight: int = 1) -> None:
        self._usage[slug] += weight

    # ── searching ──────────────────────────────────────────────────────────
    def search(self, query: str, limit: int = 10, app: str | None = None,
               tier: str | None = None) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        q_low = q.lower()
        q_tokens = _tokens(q)
        if not q_tokens:
            return []
        q_bigrams = _bigrams(q_tokens)
        expanded = expand(q)
        exp_tokens = [t for t in expanded if t not in q_tokens]
        verb_hits = {t for t in q_tokens if t in VERBS}
        read_intent = bool(READ_INTENT.search(q_low))
        # ── candidate narrowing ────────────────────────────────────────────
        # Scoring 40k actions per query is what made the playground hang, so the
        # inverted index narrows the field first. Anything that shares a token
        # (or a very close spelling of one) with the query becomes a candidate.
        key = (q_low, limit, app, tier)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        cand: set[int] = set()
        for t in list(q_tokens) + list(exp_tokens):
            cand.update(self._postings.get(t, ()))
            if len(t) > 2:
                for vt in self._vocab.get(t[:1], ()):
                    if abs(len(vt) - len(t)) <= 3 and _ratio(t, vt) >= 0.72:
                        cand.update(self._postings.get(vt, ()))
        if not cand:
            return []
        pool = [self.docs[i] for i in sorted(cand)]
        scored: list[tuple[float, dict[str, Any]]] = []

        for d in pool:
            if app and d["app"].slug != app:
                continue
            if tier and d["tier"] != tier:
                continue
            toks = d["tokens"]
            tok_set = set(toks)
            app_set = set(d["app_tokens"])
            score = 0.0

            # exact phrase beats everything
            if len(q_low) > 2 and (q_low in " ".join(toks) or q_low in d["slug"].replace(".", " ")):
                score += 3.0

            # keyword coverage on the action text
            hit = sum(1 for t in q_tokens if t in tok_set)
            score += 2.0 * (hit / max(1, len(q_tokens)))

            # the app itself being named matters a lot (including its aliases)
            app_hit = sum(1 for t in q_tokens if t in app_set)
            score += 1.6 * (app_hit / max(1, len(q_tokens)))
            aliases = APP_ALIASES.get(d["app"].slug, [])
            alias_hit = sum(1 for a in aliases if a in q_low)
            if alias_hit:
                score += 1.4 * min(1.0, alias_hit / 2)
            named_app = (d["app"].slug in q_tokens) or (d["app"].name.lower() in q_low) or bool(alias_hit)
            if named_app:
                score += 3.2
            if d["app"].slug in GENERIC_APPS and not named_app:
                score -= GENERIC_PENALTY

            # fuzzy / typo tolerance
            if hit < len(q_tokens):
                missing = [qt for qt in q_tokens if qt not in tok_set]
                best = 0.0
                for t in toks:
                    for qt in missing:
                        if t[:1] != qt[:1] or abs(len(t) - len(qt)) > 3:
                            continue
                        best = max(best, _ratio(qt, t))
                score += 1.5 * best

            # query expansion (synonyms + intent concepts)
            if exp_tokens:
                exp_hit = sum(1 for t in exp_tokens if t in tok_set)
                score += 1.2 * min(1.0, exp_hit / max(2, len(exp_tokens) * 0.5))

            # verb + object intent: "send ... email" should prefer send_email
            if verb_hits:
                v_hit = sum(1 for v in verb_hits if v in tok_set)
                score += 0.8 * (v_hit / max(1, len(verb_hits)))
                if any(v in d["action"].slug for v in verb_hits):
                    score += 0.5

            # the action's own words appearing in the query beats near-misses
            slug_words = set(_tokens(d["action"].slug.replace("_", " ")))
            act_words = slug_words | set(_tokens(d["action"].name))
            exact = sum(1 for t in q_tokens if t in act_words)
            if exact:
                score += 0.9 * (exact / max(1, len(q_tokens)))
            if slug_words:
                cov = sum(1 for t in q_tokens if t in slug_words) / len(slug_words)
                score += 1.1 * cov

            # phrase proximity bonus (query bigrams appearing in the action)
            if q_bigrams:
                overlap = len(q_bigrams & d["bigrams"])
                score += 0.7 * (overlap / len(q_bigrams))

            # popularity prior + risk preference
            usage = self._usage.get(d["slug"], 0)
            if usage:
                score += 0.6 * min(1.0, math.log1p(usage) / 3)
            score += TIER_BONUS.get(d["tier"], 0.0)
            if read_intent:
                score += 0.75 if d["tier"] == "read" else -0.35
            if getattr(d["action"], "url", "").endswith(("",)) and "proxy" in d["slug"]:
                score -= PROXY_PENALTY

            # curated typed connectors answer the same intent with far friendlier
            # arguments, so they win ties against raw endpoints
            if d.get("typed"):
                score += 1.25

            if score > 0:
                scored.append((score, d))

        scored.sort(key=lambda x: (-x[0], x[1]["slug"]))
        out: list[dict[str, Any]] = []
        seen_slugs: set[str] = set()
        for score, d in scored:
            if d["slug"] in seen_slugs:
                continue
            seen_slugs.add(d["slug"])
            out.append({
                "action": d["slug"], "app": d["app"].slug, "app_name": d["app"].name,
                "name": d["name"], "description": d["description"],
                "tier": d["tier"], "score": round(score, 3),
            })
            if len(out) >= limit:
                break
        if len(self._cache) > 256:
            self._cache.clear()
        self._cache[key] = out
        return out


_INDEX = ToolIndex()


def index() -> ToolIndex:
    return _INDEX


def search_actions(catalog: Any, query: str, limit: int = 10, app: str | None = None,
                   tier: str | None = None) -> list[dict[str, Any]]:
    return index().build(catalog).search(query, limit=limit, app=app, tier=tier)
