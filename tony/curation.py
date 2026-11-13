"""Catalogue curation: one honest entry per product, and no invented apps.

Tony's catalogue is assembled from several open catalogues (curated manifests,
Pipedream, Nango, Activepieces, n8n, Home Assistant, OpenAPI dumps). That makes it
wide, but it also produces two kinds of noise:

* **duplicates** - the same product imported four times under four spellings
  ("google_calendar", "google-calendar", "Google Calendar (OAuth)", ...)
* **non-apps** - rows that are not API apps at all. The Home Assistant export is
  the worst offender: its rows are device integrations ("Yi", "Baf", "Ads") with
  no host and no endpoint, which is exactly the kind of entry that inflates a
  catalogue without ever being connectable.

This module decides, deterministically, which entry represents a product and
which rows are noise. Nothing is deleted from disk: the catalogue simply stops
presenting duplicates, and non-callable rows move to a clearly-labelled
``directory`` list that is never counted as a connectable app.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Sources ordered by how much we trust them to represent a real, callable product.
SOURCE_RANK = {
    "curated": 0, "managed": 1, "openapi": 2, "nango": 3,
    "activepieces": 4, "n8n": 5, "pipedream": 6, "homeassistant": 9,
}

# Catalogue exports whose rows are not API apps in the first place.
NON_APP_SOURCES = {"homeassistant"}

# Tony's own built-in tools live in the registry like any other app, but they are the
# platform itself (the universal proxy, the file bridge). Curation never touches them.
PLATFORM_SLUGS = {"proxy", "files", "tony", "knowledge", "sandbox", "shell", "http"}

# Words that never identify a product on their own, plus the suffixes exports bolt on.
NOISE_WORDS = {
    "api", "apis", "app", "apps", "v1", "v2", "v3", "v1.0.0", "client", "sdk",
    "rest", "graphql", "server", "service", "integration", "integrations",
    "connector", "plugin", "beta", "alpha", "official", "public", "private",
    "oauth", "oauth2", "token", "pat", "key", "keys", "endpoint", "endpoints",
    "webhook", "webhooks", "account", "accounts", "unlimited", "cloud",
}
SUFFIX_WORDS = {"rest", "api", "apis", "graphql", "oauth", "oauth2", "beta", "alpha",
                "official", "public", "pat", "cloud", "app", "sdk", "v1", "v2", "v3"}

# Vendor spellings that mean the same product.
ALIASES = {
    "googlemail": "gmail", "gmailapi": "gmail",
    "googledrive": "googledrive", "googlesheets": "googlesheets",
    "msteams": "microsoftteams", "msgraph": "microsoftgraph",
    "fb": "facebook", "twitterx": "x", "twitter": "x",
    "whatsappbusiness": "whatsapp", "gcp": "googlecloud", "aws": "amazonwebservices",
}


def _words(text: str) -> list[str]:
    text = re.sub(r"\(.*?\)", " ", text or "")
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text).strip().lower()
    return [w for w in text.split() if w]


def identity(name: str, slug: str) -> str:
    """A stable product key: the name without export noise or vendor suffixes."""
    words = [w for w in _words(name) if w not in NOISE_WORDS]
    if words:
        while len(words) > 1 and words[-1] in SUFFIX_WORDS:
            words.pop()
        key = "".join(words)
    else:
        key = re.sub(r"[^a-z0-9]+", "", (slug or "").lower())
    key = ALIASES.get(key, key)
    # "Google Calendar" and "Calendar" are different products; only merge an exact key.
    return key


def is_junk(spec: Any) -> bool:
    """True for rows that are not a product at all.

    The bar is deliberately high: a row is junk only when we have positive evidence,
    never merely because it looks unfamiliar.
    """
    # A row that can actually reach an API is a real capability. Never call it junk
    # just because its display name came out of a generator ("Account Service").
    if is_callable(spec):
        if getattr(spec, "source", "") in NON_APP_SOURCES and not (getattr(spec, "base_url", "") or "").strip():
            return True
        return False
    if getattr(spec, "source", "") in NON_APP_SOURCES:
        return True
    name = (getattr(spec, "name", "") or "").strip()
    words = _words(name)
    # "API", "API V1", "API Client", "API Endpoints": a label, not a product.
    if not words or all(w in NOISE_WORDS for w in words):
        return True
    if len("".join(words)) < 3:
        return True
    return False


def real_actions(spec: Any) -> list[Any]:
    return [a for a in getattr(spec, "actions", []) if not getattr(a, "universal", False)]


def is_callable(spec: Any) -> bool:
    """True when Tony can actually reach this app's API without the user inventing a host."""
    if (getattr(spec, "base_url", "") or "").strip():
        return True
    return any((getattr(a, "url", "") or "").startswith("http") for a in real_actions(spec))


def _rank(spec: Any) -> tuple:
    return (
        0 if is_callable(spec) else 1,
        SOURCE_RANK.get(getattr(spec, "source", ""), 8),
        -len(real_actions(spec)),
        0 if getattr(spec, "logo", "") else 1,
        0 if getattr(spec, "docs", "") and "nango.dev" not in getattr(spec, "docs", "") else 1,
        len(getattr(spec, "slug", "")),
    )


@dataclass
class Report:
    kept: int = 0
    junk: list[str] = field(default_factory=list)
    merged: dict[str, str] = field(default_factory=dict)
    directory: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kept": self.kept,
            "junk_removed": len(self.junk),
            "duplicates_merged": len(self.merged),
            "directory_only": len(self.directory),
            "junk_sample": self.junk[:10],
        }


def curate(apps: dict[str, Any], *, drop_directory: bool = False) -> tuple[dict[str, Any], Report]:
    """Return the catalogue Tony should present, plus what was pruned and why."""
    report = Report()

    # 0. Tony's own hand-written manifests (proxy, files, the platform tools) are the
    # product surface, never catalogue noise, so curation may not touch them.
    protected = {s for s, a in apps.items()
                 if getattr(a, "source", "") in {"curated", "managed"} or s in PLATFORM_SLUGS}

    # 1. drop non-products
    survivors: dict[str, Any] = {}
    for slug, spec in apps.items():
        if slug in protected:
            survivors[slug] = spec
            continue
        if is_junk(spec):
            report.junk.append(slug)
            report.reasons[slug] = "not a product"
            continue
        survivors[slug] = spec

    # 2. one entry per product
    groups: dict[str, list[Any]] = {}
    for spec in survivors.values():
        groups.setdefault(identity(spec.name, spec.slug), []).append(spec)

    kept: dict[str, Any] = {}
    for key, members in groups.items():
        guards = [m for m in members if m.slug in protected]
        if guards:
            # A hand-written or managed entry always wins, and its imported twins
            # still fold into it - otherwise "Google Calendar" shows up twice.
            for m in guards:
                kept[m.slug] = m
            winner = sorted(guards, key=_rank)[0]
            for dup in [m for m in members if m.slug not in protected]:
                if _same_product(winner, dup):
                    report.merged[dup.slug] = winner.slug
                    report.reasons[dup.slug] = f"duplicate of {winner.slug}"
                else:
                    kept[dup.slug] = dup
            continue
        members.sort(key=_rank)
        winner = members[0]
        kept[winner.slug] = winner
        for dup in members[1:]:
            # never fold a different product that merely shares a name: require the
            # same host family, or one of them being an official/curated import.
            if not _same_product(winner, dup):
                kept[dup.slug] = dup
                continue
            report.merged[dup.slug] = winner.slug
            report.reasons[dup.slug] = f"duplicate of {winner.slug}"

    # 3. separate shells from apps Tony can actually call
    if drop_directory:
        for slug, spec in list(kept.items()):
            if not is_callable(spec):
                report.directory.append(slug)
                kept.pop(slug, None)
    else:
        for spec in kept.values():
            if not is_callable(spec):
                spec.tier = "directory"
                report.directory.append(spec.slug)

    report.kept = len(kept)
    return kept, report


def _host(spec: Any) -> str:
    base = (getattr(spec, "base_url", "") or "").strip()
    if not base:
        return ""
    m = re.match(r"https?://([^/]+)", base)
    return (m.group(1) if m else "").lower()


def _same_product(a: Any, b: Any) -> bool:
    ha, hb = _host(a), _host(b)
    if ha and hb:
        if ha == hb:
            return True
        # different hosts are still the same product when both are callable and the
        # name matched exactly after normalisation; only the regional/hosted variant differs
        return _bare(ha) == _bare(hb) or a.source in {"curated", "managed"} or b.source in {"curated", "managed"}
    return True


def _bare(host: str) -> str:
    parts = [p for p in host.split(".") if p not in {"api", "www", "app", "mcp", "eu", "us", "com", "io", "co", "net", "org", "dev"}]
    return parts[0] if parts else host
