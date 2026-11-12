"""Build the unified app-auth registry.

Tony's catalogue is huge (7.8k apps) but its auth data is thin: most entries say
"api_key" and stop. Nango's open-source registry is the opposite: 1.2k providers
with real authorize/token endpoints, dynamic-client-registration URLs, MCP
endpoints and scope lists, and no per-app secrets baked in.

This script merges both into one file the connect flow can trust, so every app
knows exactly how a user gets connected: public, key, OAuth with ready
credentials, OAuth by dynamic client registration (the keyless path), OAuth
needing a one-time owner registration, or MCP registration.

Run:  python3 scripts/build_app_auth.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[1]
REGISTRY = BASE / "tony" / "registry"
APPS = REGISTRY / "apps.jsonl"
NANGO = REGISTRY / "nango_providers.yaml"
OUT = REGISTRY / "app_auth.json"

READ_WORDS = ("read", "readonly", "read_only", "view", "list", "get", "search", "browse", ".me", "profile")
WRITE_WORDS = ("write", "modify", "send", "manage", "create", "update", "delete", "full", "admin",
               "compose", "upload", "post", "publish", "edit", "insert", "remove", "compose")


def norm(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def classify(scope: str) -> str:
    s = (scope or "").lower()
    if any(w in s for w in WRITE_WORDS):
        return "write"
    if any(w in s for w in READ_WORDS):
        return "read"
    return "write"


def load_nango() -> dict[str, dict]:
    if not NANGO.exists():
        return {}
    raw = yaml.safe_load(NANGO.read_text()) or {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def nango_index(nango: dict[str, dict]) -> dict[str, str]:
    """normalized name -> nango provider key"""
    return {norm(k): k for k in nango}


def plan_for(app: dict, nango: dict[str, dict], index: dict[str, str], ready: set[str]) -> dict:
    slug = app.get("slug", "")
    auth = app.get("auth") or {}
    kind = (auth.get("type") or "none").lower()
    actions = app.get("actions") or []
    reads = sum(1 for a in actions if a.get("tier") == "read")
    writes = sum(1 for a in actions if a.get("tier") == "write")
    destructive = sum(1 for a in actions if a.get("tier") == "destructive")

    prov_key = index.get(norm(slug)) or index.get(norm(slug).removesuffix("api"))
    if not prov_key:
        # second pass: match on the app's display name ("Google Drive" -> google-drive)
        prov_key = index.get(norm(app.get("name", "")))
    prov = nango.get(prov_key, {}) if prov_key else {}
    mode = (prov.get("auth_mode") or "").upper()

    scopes = list(auth.get("scopes") or []) or list(prov.get("default_scopes") or [])
    authorize = auth.get("authorize_url") or prov.get("authorization_url") or ""
    token = auth.get("token_url") or prov.get("token_url") or ""
    registration = prov.get("registration_url") or ""
    mcp = ""
    proxy = prov.get("proxy") or {}
    if prov.get("mcp_endpoint"):
        base = (proxy.get("base_url") or "").rstrip("/")
        mcp = f"{base}{prov['mcp_endpoint']}" if base else ""
    base_url = app.get("base_url") or proxy.get("base_url") or ""

    dynamic = str(prov.get("client_registration", "")).lower() == "dynamic"

    if app.get("auth", {}).get("type") == "none" or mode == "NONE":
        strategy = "public"
    elif mcp and mode.startswith("MCP_OAUTH2"):
        strategy = "mcp_dcr"
    elif kind == "oauth2" or mode in {"OAUTH2", "OAUTH2_CC"}:
        if registration or dynamic:
            strategy = "oauth_dcr"
        elif norm(slug) in ready:
            strategy = "oauth_ready"
        else:
            strategy = "oauth_byo"
    else:
        strategy = "key"

    read_scopes = [s for s in scopes if classify(s) == "read"]
    write_scopes = [s for s in scopes if classify(s) == "write"]

    return {
        "strategy": strategy,
        "keyless_via": "",
        "auth_mode": mode or kind.upper(),
        "authorize_url": authorize,
        "token_url": token,
        "registration_url": registration,
        "dynamic_registration": bool(registration or dynamic),
        "scopes": scopes,
        "scopes_read": read_scopes,
        "scopes_write": write_scopes,
        "authorize_params": dict(prov.get("authorization_params") or {}),
        "registration_params": dict(prov.get("registration_params") or {}),
        "token_request_auth_method": prov.get("token_request_auth_method", ""),
        "base_url": base_url,
        "mcp_url": mcp,
        "docs": prov.get("docs") or app.get("docs") or "",
        "reads": reads,
        "writes": writes,
        "destructive": destructive,
        "can_read": reads > 0,
        "can_write": (writes + destructive) > 0,
        "source": "nango" if prov else "catalog",
        "provider_key": prov_key or "",
    }


def main() -> None:
    from importlib import util

    spec = util.spec_from_file_location("pr", BASE / "tony" / "provider_registry.py")
    ready: set[str] = set()
    try:
        mod = util.module_from_spec(spec)          # type: ignore[arg-type]
        spec.loader.exec_module(mod)               # type: ignore[union-attr]
        ready = {norm(s) for s in mod.PROVIDERS}
    except Exception:
        ready = set()

    apps = [json.loads(line) for line in APPS.read_text().splitlines() if line.strip()]
    nango = load_nango()
    index = nango_index(nango)

    out_apps: dict[str, dict] = {}
    for app in apps:
        out_apps[app["slug"]] = plan_for(app, nango, index, ready)

    # Point OAuth apps that still need a one-time owner registration at the same
    # vendor's MCP server, which registers Tony automatically (RFC 7591).
    keyless = {slug: p for slug, p in out_apps.items()
               if p["strategy"] in {"mcp_dcr", "oauth_dcr"} and (p["registration_url"] or p["mcp_url"])}
    for slug, p in out_apps.items():
        if p["strategy"] not in {"oauth_byo", "key"}:
            continue
        bare = norm(slug)
        for cand_slug, cand in keyless.items():
            metadata = cand.get("provider_key") or ""
            if norm(cand_slug).removesuffix("mcp") == bare or norm(metadata).removesuffix("mcp") == bare:
                p["keyless_via"] = cand_slug
                break

    cov: dict[str, int] = {}
    for p in out_apps.values():
        cov[p["strategy"]] = cov.get(p["strategy"], 0) + 1

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "apps_total": len(out_apps),
        "nango_providers": len(nango),
        "coverage": dict(sorted(cov.items(), key=lambda kv: -kv[1])),
        "readable": sum(1 for p in out_apps.values() if p["can_read"]),
        "writable": sum(1 for p in out_apps.values() if p["can_write"]),
        "keyless_via_mcp": sum(1 for p in out_apps.values() if p["keyless_via"]),
        "apps": out_apps,
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(json.dumps({k: payload[k] for k in ("apps_total", "nango_providers", "coverage", "readable", "writable", "keyless_via_mcp")}, indent=1))
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
