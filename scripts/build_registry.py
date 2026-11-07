#!/usr/bin/env python3
"""Build Tony's app registry from public, open catalogues.

Sources
-------
apis.guru    2,500+ real OpenAPI documents      -> apps with live endpoints
nango        1,200 provider definitions         -> apps with base URL + auth
pipedream    3,200 public app slugs             -> directory entries
activepieces   700 community pieces             -> directory entries
n8n            300 node packages                -> directory entries
homeassistant 1,250 official integrations       -> directory entries

Output
------
tony/registry/apps.jsonl   one compact manifest per line
tony/registry/meta.json    counts, sources, build time

Usage
-----
    python scripts/build_registry.py                 # full build
    python scripts/build_registry.py --skip-openapi  # fast rebuild of directories
    python scripts/build_registry.py --limit 200     # smoke build
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tony.importer import from_directory, from_nango, from_openapi, slugify  # noqa: E402

CACHE = Path(os.getenv("TONY_IMPORT_CACHE", "/tmp/tony-import-cache"))
REGISTRY = ROOT / "tony" / "registry"
GURU_LIST = "https://api.apis.guru/v2/list.json"
NANGO_PROVIDERS = "https://raw.githubusercontent.com/NangoHQ/nango/master/packages/providers/providers.yaml"
PIPEDREAM_APPS = "https://pipedream.com/sitemap-apps.xml"
ACTIVEPIECES_TREE = "https://api.github.com/repos/activepieces/activepieces/git/trees/main?recursive=1"
N8N_TREE = "https://api.github.com/repos/n8n-io/n8n/git/trees/master?recursive=1"
HA_INTEGRATIONS = "https://raw.githubusercontent.com/home-assistant/core/dev/homeassistant/generated/integrations.json"

UA = {"User-Agent": "TonyCatalogBot/0.2 (+https://github.com/emmanuelerogian723-alt/tony)"}


async def fetch(client: httpx.AsyncClient, url: str, cache_name: str | None = None,
                timeout: float = 45.0) -> bytes | None:
    if cache_name:
        cached = CACHE / cache_name
        if cached.exists() and cached.stat().st_size > 0:
            return cached.read_bytes()
    try:
        r = await client.get(url, headers=UA, timeout=timeout, follow_redirects=True)
        if r.status_code >= 400:
            print(f"  ! {url} -> HTTP {r.status_code}")
            return None
        if cache_name:
            cached = CACHE / cache_name
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(r.content)
        return r.content
    except Exception as exc:  # noqa: BLE001 - network best effort
        print(f"  ! {url} -> {type(exc).__name__}: {exc}")
        return None


def guru_slug(key: str) -> str:
    base, _, sub = key.partition(":")
    host = base.split(".")[0]
    return slugify("-".join([host] + ([sub] if sub else [])))


async def load_openapi(client: httpx.AsyncClient, limit: int | None, concurrency: int) -> list[dict]:
    print("· apis.guru: fetching index")
    raw = await fetch(client, GURU_LIST, "guru-list.json", timeout=120)
    if not raw:
        return []
    index = json.loads(raw)
    entries: list[tuple[str, str, dict]] = []
    used: set[str] = set()
    for key, item in index.items():
        versions = item.get("versions") or {}
        preferred = item.get("preferred") or next(iter(versions), None)
        info = (versions.get(preferred) or {}) if preferred else {}
        spec_url = info.get("swaggerUrl") or info.get("openapiUrl")
        if not spec_url:
            continue
        slug = guru_slug(key)
        if slug in used:
            slug = slugify(key)
        used.add(slug)
        entries.append((slug, spec_url, item))
    if limit:
        entries = entries[:limit]
    print(f"· apis.guru: {len(entries)} documents to import")

    sem = asyncio.Semaphore(concurrency)
    done = {"n": 0}
    apps: list[dict] = []
    lock = asyncio.Lock()

    async def one(slug: str, url: str, item: dict) -> None:
        async with sem:
            raw_spec = await fetch(client, url, f"specs/{slug}.json", timeout=25)
            async with lock:
                done["n"] += 1
                if done["n"] % 250 == 0:
                    print(f"    {done['n']}/{len(entries)} specs, {len(apps)} apps built")
            if not raw_spec:
                return
            try:
                spec = json.loads(raw_spec)
            except json.JSONDecodeError:
                try:
                    spec = yaml.safe_load(raw_spec)
                except Exception:  # noqa: BLE001
                    return
            manifest = from_openapi(slug, item, spec)
            if manifest:
                async with lock:
                    apps.append(manifest)

    await asyncio.gather(*(one(s, u, i) for s, u, i in entries))
    print(f"· apis.guru: {len(apps)} apps with actions")
    return apps


async def load_nango(client: httpx.AsyncClient, limit: int | None = None) -> list[dict]:
    raw = await fetch(client, NANGO_PROVIDERS, "nango-providers.yaml", timeout=60)
    if not raw:
        return []
    providers = yaml.safe_load(raw) or {}
    apps = []
    for key, provider in list(providers.items())[: limit or None]:
        manifest = from_nango(slugify(key), provider)
        if manifest:
            apps.append(manifest)
    print(f"· nango: {len(apps)} providers")
    return apps


async def load_pipedream(client: httpx.AsyncClient) -> list[dict]:
    raw = await fetch(client, PIPEDREAM_APPS, "pipedream-apps.xml", timeout=60)
    if not raw:
        return []
    slugs = re.findall(r"<loc>https://pipedream\.com/apps/([^<]+)</loc>", raw.decode("utf-8", "ignore"))
    apps = []
    for slug in slugs:
        slug = slugify(slug)
        if not slug or slug == "apps":
            continue
        name = " ".join(w.capitalize() for w in slug.split("-"))[:60]
        apps.append(from_directory(slug, name, "pipedream", f"https://pipedream.com/apps/{slug}"))
    print(f"· pipedream: {len(apps)} directory entries")
    return apps


async def load_tree_source(client: httpx.AsyncClient, url: str, prefix: str, name: str,
                           depth: int, cache_name: str) -> list[dict]:
    raw = await fetch(client, url, cache_name, timeout=120)
    if not raw:
        return []
    tree = json.loads(raw).get("tree") or []
    apps, seen = [], set()
    for node in tree:
        path = node.get("path", "")
        if not path.startswith(prefix):
            continue
        parts = path.split("/")
        if len(parts) <= depth:
            continue
        slug = slugify(parts[depth])
        if not slug or slug in seen:
            continue
        seen.add(slug)
        apps.append(from_directory(slug, " ".join(w.capitalize() for w in slug.split("-"))[:60],
                                   name, f"https://github.com/{prefix.split('/')[0]}"))
    print(f"· {name.lower()}: {len(apps)} entries")
    return apps


async def load_home_assistant(client: httpx.AsyncClient) -> list[dict]:
    raw = await fetch(client, HA_INTEGRATIONS, "ha-integrations.json", timeout=60)
    if not raw:
        return []
    data = json.loads(raw)
    integrations = data.get("integration") or {}
    apps = []
    for domain in integrations:
        slug = slugify(domain)
        if not slug:
            continue
        name = " ".join(w.capitalize() for w in domain.replace("_", " ").split())[:60]
        apps.append(from_directory(slug, name, "homeassistant",
                                   f"https://www.home-assistant.io/integrations/{domain}", "IoT"))
    print(f"· home assistant: {len(apps)} integrations")
    return apps


PRIORITY = {"curated": 0, "openapi": 1, "nango": 2, "pipedream": 3,
            "activepieces": 4, "n8n": 5, "homeassistant": 6}


def merge(curated_slugs: set[str], groups: list[list[dict]]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for app in group:
            slug = app["slug"]
            if slug in curated_slugs:
                continue
            current = merged.get(slug)
            if current is None or PRIORITY.get(app.get("source", ""), 9) < PRIORITY.get(current.get("source", ""), 9):
                if current and not app.get("docs"):
                    app["docs"] = current.get("docs", "")
                merged[slug] = app
    return list(merged.values())


def curated_slugs() -> set[str]:
    out = set()
    for path in (ROOT / "tony" / "apps").glob("*.yaml"):
        try:
            data = yaml.safe_load(path.read_text()) or {}
            if data.get("slug"):
                out.add(data["slug"])
        except Exception:  # noqa: BLE001
            continue
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-openapi", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="limit OpenAPI imports (smoke build)")
    ap.add_argument("--concurrency", type=int, default=18)
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    REGISTRY.mkdir(parents=True, exist_ok=True)
    started = time.time()

    async with httpx.AsyncClient() as client:
        tasks = {
            "openapi": [] if args.skip_openapi else await load_openapi(client, args.limit, args.concurrency),
            "nango": await load_nango(client),
            "pipedream": await load_pipedream(client),
            "activepieces": await load_tree_source(
                client, ACTIVEPIECES_TREE, "packages/pieces/community/", "activepieces", 3, "ap-tree.json"),
            "n8n": await load_tree_source(
                client, N8N_TREE, "packages/nodes-base/nodes/", "n8n", 3, "n8n-tree.json"),
            "homeassistant": await load_home_assistant(client),
        }

    have = curated_slugs()
    print(f"· curated manifests: {len(have)}")
    apps = merge(have, list(tasks.values()))

    apps.sort(key=lambda a: (PRIORITY.get(a.get("source", ""), 9), a["slug"]))
    out = REGISTRY / "apps.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for app in apps:
            fh.write(json.dumps(app, separators=(",", ":"), ensure_ascii=False) + "\n")

    actions = sum(len(a.get("actions") or []) for a in apps)
    by_source: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    for a in apps:
        by_source[a.get("source", "?")] = by_source.get(a.get("source", "?"), 0) + 1
        by_tier[a.get("tier", "?")] = by_tier.get(a.get("tier", "?"), 0) + 1

    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "apps": len(apps) + len(have),
        "registry_apps": len(apps),
        "curated_apps": len(have),
        "actions_registry": actions,
        "by_source": by_source,
        "by_tier": by_tier,
        "build_seconds": round(time.time() - started, 1),
    }
    (REGISTRY / "meta.json").write_text(json.dumps(meta, indent=2))
    size = out.stat().st_size / 1024 / 1024
    print(f"\nbuilt {len(apps) + len(have)} apps ({actions} registry actions) "
          f"in {time.time() - started:.0f}s — {size:.1f} MB")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
