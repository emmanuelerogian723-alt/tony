"""Agent-speak to Tony-speak.

A model asking for "my latest emails" writes ``gmail.fetch_emails``, not
``gmail.list_messages``. It writes ``query``, not ``srsearch``. Both used to be
hard failures, which is a naming problem, not a capability one.

This module is the translation layer in both directions:

* action aliases - the verbs people and models actually use, mapped onto the
  canonical slug, plus a "did you mean" suggestion when nothing matches;
* parameter aliases - provider-internal names (``srsearch``, ``maxResults``,
  ``per_page``) presented to models as ``query``/``limit``, and accepted back
  the same way at execution time.

Nothing here guesses silently across apps: an alias is always scoped to one app.
"""
from __future__ import annotations

import difflib
from typing import Any

# ── parameter names ──────────────────────────────────────────────────────
# friendly name -> declared names it may stand for, most specific first.
PARAM_SYNONYMS: dict[str, tuple[str, ...]] = {
    "query": ("q", "query", "search", "search_query", "query_text", "term", "terms",
              "srsearch", "text", "keywords", "keyword", "name_query", "prompt"),
    "limit": ("limit", "maxResults", "max_results", "srlimit", "count", "per_page",
              "perpage", "page_size", "pagesize", "size", "top", "num", "rows",
              "first", "number"),
    "page": ("page", "page_number", "pageNumber", "offset_page", "cursor"),
}

# The reverse view, declared -> friendly, used when shaping tool schemas.
_FRIENDLY_OF: dict[str, str] = {}
for _friendly, _names in PARAM_SYNONYMS.items():
    for _n in _names:
        _FRIENDLY_OF.setdefault(_n.lower(), _friendly)


def friendly_param(declared: str) -> str:
    """What to call a provider parameter when a model has to fill it in."""
    return _FRIENDLY_OF.get((declared or "").lower(), declared)


def normalize_args(action: Any, args: dict[str, Any] | None) -> dict[str, Any]:
    """Translate friendly argument names onto the action's declared ones.

    ``{'query': 'lagos', 'limit': 5}`` becomes ``{'srsearch': 'lagos', 'srlimit': 5}``
    for Wikipedia. Declared names always win, so an exact call is untouched.
    """
    given = {k: v for k, v in dict(args or {}).items()
             if isinstance(k, str) and k.strip()}
    declared = {n.lower(): n for n in (getattr(action, "params", {}) or {})}
    if not declared:
        return given
    out: dict[str, Any] = {}
    for key, value in given.items():
        low = key.strip().lower()
        if low in declared:
            out[declared[low]] = value
            continue
        moved = False
        for synonym, names in PARAM_SYNONYMS.items():
            if low == synonym or low in {n.lower() for n in names}:
                for candidate in (synonym,) + names:
                    real = declared.get(candidate.lower())
                    if real and real not in out:
                        out[real] = value
                        moved = True
                        break
            if moved:
                break
        if not moved:
            out[key] = value          # unknown extras still reach validate_args
    return out


def param_map(action: Any) -> dict[str, str]:
    """{declared: friendly} for the parameters where the two differ."""
    out = {}
    for name in (getattr(action, "params", {}) or {}):
        friendly = friendly_param(name)
        if friendly != name:
            out[name] = friendly
    return out


# ── action names ─────────────────────────────────────────────────────────
# (app slug, the words an agent uses) -> canonical action slug.
ACTION_ALIASES: dict[tuple[str, str], str] = {
    ("gmail", "fetch_emails"): "list_messages",
    ("gmail", "get_emails"): "list_messages",
    ("gmail", "read_emails"): "list_messages",
    ("gmail", "list_emails"): "list_messages",
    ("gmail", "search_emails"): "list_messages",
    ("gmail", "emails"): "list_messages",
    ("gmail", "inbox"): "list_messages",
    ("gmail", "messages"): "list_messages",
    ("gmail", "search"): "list_messages",
    ("gmail", "send_email"): "send_message",
    ("gmail", "send"): "send_message",
    ("gmail", "email"): "send_message",
    ("gmail", "get_email"): "get_message",
    ("gmail", "read_email"): "get_message",
    ("gmail", "message"): "get_message",
    ("wikipedia", "query"): "search",
    ("wikipedia", "lookup"): "search",
    ("wikipedia", "find"): "search",
    ("wikipedia", "article"): "summary",
    ("wikipedia", "get_article"): "summary",
    ("hackernews", "top"): "top_stories",
    ("hackernews", "stories"): "top_stories",
    ("hackernews", "news"): "top_stories",
    ("hackernews", "item"): "story",
    ("github", "repos"): "list_repos",
    ("github", "repositories"): "list_repos",
    ("github", "issues"): "list_issues",
    ("notion", "pages"): "search",
    ("slack", "send"): "post_message",
    ("slack", "message"): "post_message",
    ("google_calendar", "events"): "list_events",
    ("google_calendar", "calendar"): "list_events",
    ("google_drive", "files"): "list_files",
    ("google_drive", "search"): "list_files",
    ("google_sheets", "read"): "get_values",
    ("google_sheets", "rows"): "get_values",
}

# Verbs agents prefix that carry no meaning on their own.
_NOISE_PREFIXES = ("fetch_", "get_", "list_", "read_", "search_", "retrieve_",
                   "find_", "show_", "pull_", "check_")


def canonical(app: Any, spoken: str) -> str | None:
    """The real action slug behind an agent's word, or None."""
    slug = (spoken or "").strip().lower().replace(" ", "_")
    if not slug:
        return None
    if app.action(slug):
        return slug
    alias = ACTION_ALIASES.get((app.slug, slug))
    if alias and app.action(alias):
        return alias
    # "fetch_recent_emails" -> try the meaningful tail as an alias too
    for prefix in _NOISE_PREFIXES:
        if slug.startswith(prefix):
            tail = slug[len(prefix):]
            hit = canonical(app, tail)
            if hit:
                return hit
    # last resort: fuzzy against the slug and the human action name
    pool = {a.slug: a for a in app.actions}
    names = {a.slug: (a.name or "").lower() for a in app.actions}
    best = difflib.get_close_matches(slug, list(pool), n=1, cutoff=0.72)
    if best:
        return best[0]
    for a in app.actions:
        words = set((a.name or "").lower().replace("-", " ").split())
        if slug.replace("_", " ") in (a.name or "").lower() or (slug and slug in words):
            return a.slug
    return None


def suggest_actions(app: Any, spoken: str, limit: int = 3) -> list[str]:
    """Closest real actions, for a 404 that tells the caller what to send instead."""
    slug = (spoken or "").strip().lower().replace(" ", "_")
    pool = [a.slug for a in app.actions]
    if not pool:
        return []
    out = difflib.get_close_matches(slug, pool, n=limit, cutoff=0.4)
    for prefix in _NOISE_PREFIXES:
        if slug.startswith(prefix):
            out += difflib.get_close_matches(slug[len(prefix):], pool, n=limit, cutoff=0.5)
    seen: list[str] = []
    for name in out:
        if name not in seen:
            seen.append(name)
    if seen:
        return seen[:limit]
    # Nothing lexically close: point at the app's own read actions instead of
    # leaving the caller with a bare 404 and no next move.
    words = set(slug.replace("-", " ").split("_")) | set(slug.split())
    scored = []
    for a in app.actions:
        hay = f"{a.slug} {a.name}".lower().replace("-", " ")
        scored.append((len(words & set(hay.split())), a.tier != "read", a.slug))
    scored.sort()
    return [row[2] for row in scored[:limit]]


def explain(app: Any, spoken: str) -> str:
    """One error string that names the app, the miss and the fix."""
    options = suggest_actions(app, spoken)
    hint = f" Closest actions: {', '.join(f'{app.slug}.{o}' for o in options)}." if options else ""
    return f"App '{app.slug}' has no action '{spoken}'.{hint}"
