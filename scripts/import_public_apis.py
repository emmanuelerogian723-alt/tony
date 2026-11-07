"""Merge the public-apis catalogue (MIT) into the Tony registry.

The list is an editorial index of ~2,200 APIs and MCP servers, each with its
own auth mode. It is a directory layer: Tony attaches the documented host as
the base URL, so a user can connect with a token and call any path, and marks
entry-based rows as keyless when the index says no auth is needed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tony" / "registry" / "apps.jsonl"
SRC = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)[:48] or "api"


def parse(md: str) -> list[dict]:
    rows: list[dict] = []
    category = "Other"
    for line in md.splitlines():
        if line.startswith("### "):
            category = line[4:].strip()
            continue
        if not line.startswith("| ") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in {"Name", "API"}:
            continue
        m = LINK.search(cells[0])
        if not m:
            continue
        name, url = m.group(1).strip(), m.group(2).strip()
        desc = cells[1]
        auth_raw = cells[2].lower()
        keyless = auth_raw in {"no", "none", ""} and "key" not in auth_raw
        https = cells[3].lower() == "yes" if len(cells) > 3 else True
        base = url if https or url.startswith("https://") else url
        rows.append({
            "slug": slugify(name),
            "name": name[:64],
            "category": category if category != "Other" else "Developer",
            "description": re.sub(r"\s+", " ", desc)[:200],
            "docs": url,
            "logo": "",
            "base_url": base,
            "auth": {"type": "none" if keyless else "api_key"},
            "actions": [{
                "slug": "call",
                "name": f"Call {name}",
                "description": "Documented endpoint; pass the path and query for the operation you need.",
                "method": "GET",
                "url": base,
                "params": {},
                "required": [],
                "tier": "read",
            }],
            "verified": False,
            "note": "Directory entry from public-apis; endpoint list lives in the linked docs.",
            "tier": "directory",
            "source": "public-apis",
        })
    return rows


def main() -> int:
    md = httpx.get(SRC, timeout=60, follow_redirects=True).text
    incoming = parse(md)
    existing: list[dict] = []
    seen: set[str] = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            existing.append(row)
            seen.add(row["slug"])
    added = 0
    for row in incoming:
        slug = row["slug"]
        if slug in seen:
            continue
        row["slug"] = slug
        seen.add(slug)
        existing.append(row)
        added += 1
    with OUT.open("w") as fh:
        for row in existing:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    apps = len(existing)
    actions = sum(len(r["actions"]) for r in existing)
    print(f"public-apis: {len(incoming)} rows · {added} new · registry now {apps} apps / {actions} actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
