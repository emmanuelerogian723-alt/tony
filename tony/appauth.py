"""Per-app auth plans for the whole catalogue.

The catalogue knows 7.8k apps; the managed OAuth registry knows 35. This module
bridges them with data instead of hardcoding, the way Nango's open-source
provider registry does:

* every app resolves to one connect *strategy*
  - ``public``      no auth at all
  - ``key``         user pastes an API key / bearer token / basic credentials
  - ``oauth_dcr``   Tony registers itself at connect time (RFC 7591), no secrets
  - ``mcp_dcr``     the vendor's MCP server registers Tony automatically
  - ``oauth_ready`` platform credentials already present, one click
  - ``oauth_byo``   needs a one-time owner registration, or the key route
* each app also carries its read/write surface:
  ``reads``, ``writes``, ``destructive``, ``can_read``, ``can_write``, and the
  read-only vs write scope split used for least-privilege consent.

Nothing here stores a credential. It only says how a connection is obtained.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "registry" / "app_auth.json"

STRATEGY_LABEL = {
    "public": "No sign-in needed",
    "key": "Connect with an API key",
    "oauth_dcr": "One-click sign-in (auto-registered, no setup)",
    "mcp_dcr": "One-click sign-in via the app's MCP server",
    "oauth_ready": "One-click sign-in",
    "oauth_byo": "Owner adds OAuth credentials once",
}


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    try:
        return json.loads(DATA_FILE.read_text())
    except Exception:
        return {"apps": {}, "coverage": {}, "apps_total": 0}


def reload() -> None:
    _data.cache_clear()


def plan(slug: str) -> dict[str, Any] | None:
    if not slug:
        return None
    return (_data().get("apps") or {}).get(slug)


def plan_or_default(slug: str, auth_type: str = "") -> dict[str, Any]:
    """A usable plan even for an app the registry has never seen."""
    found = plan(slug)
    if found:
        return found
    strategy = "public" if auth_type == "none" else "key"
    return {"strategy": strategy, "label": STRATEGY_LABEL[strategy], "scopes": [],
            "scopes_read": [], "scopes_write": [], "authorize_url": "", "token_url": "",
            "registration_url": "", "mcp_url": "", "keyless_via": "",
            "reads": 0, "writes": 0, "destructive": 0, "can_read": False, "can_write": False,
            "source": "catalog", "provider_key": "", "hero": ""}


def scope_list(slug: str, access: str = "read") -> list[str]:
    """Least-privilege scopes: read-only consent unless writes were asked for."""
    p = plan(slug) or {}
    read = list(p.get("scopes_read") or [])
    write = list(p.get("scopes_write") or [])
    if access == "write":
        return list(dict.fromkeys(write + read))
    if read:
        return read
    return list(p.get("scopes") or [])


def coverage() -> dict[str, Any]:
    d = _data()
    cov = dict(d.get("coverage") or {})
    labelled = [{"strategy": k, "label": STRATEGY_LABEL.get(k, k), "apps": v} for k, v in cov.items()]
    return {
        "apps_total": d.get("apps_total", 0),
        "nango_providers": d.get("nango_providers", 0),
        "coverage": cov,
        "by_strategy": labelled,
        "readable": d.get("readable", 0),
        "writable": d.get("writable", 0),
        "keyless_via_mcp": d.get("keyless_via_mcp", 0),
        "generated": d.get("generated", ""),
        "connectable_now": sum(v for k, v in cov.items() if k in {"public", "key", "oauth_ready", "oauth_dcr", "mcp_dcr"}),
    }


def apply(spec: Any) -> bool:
    """Fill an AppSpec's auth block from the registry. Returns True if anything changed.

    This is the Nango trick: the connect flow stays generic, and every provider
    is described by data. Managed providers keep their curated values; the rest
    of the catalogue inherits real endpoints, scopes and a registration URL.
    """
    p = plan(getattr(spec, "slug", ""))
    if not p:
        return False
    changed = False
    auth = spec.auth
    if p.get("registration_url") and not getattr(auth, "registration_url", ""):
        auth.registration_url = p["registration_url"]
        changed = True
    if p["strategy"] not in {"oauth_dcr", "mcp_dcr", "oauth_ready"}:
        return changed
    if not getattr(auth, "authorize_url", ""):
        auth.authorize_url = p.get("authorize_url", "")
        changed = True
    if not getattr(auth, "token_url", ""):
        auth.token_url = p.get("token_url", "")
        changed = True
    if not list(getattr(auth, "scopes", []) or []) and p.get("scopes"):
        auth.scopes = list(p["scopes"])
        changed = True
    if auth.type != "oauth2" and auth.authorize_url and auth.token_url:
        auth.type = "oauth2"
        changed = True
    if not auth.pkce:
        auth.pkce = True
        changed = True
    for key, value in (p.get("authorize_params") or {}).items():
        if key not in {"response_type", "client_id", "redirect_uri", "state", "code_challenge",
                       "code_challenge_method"} and key not in auth.authorize_params:
            auth.authorize_params[key] = value
            changed = True
    if not getattr(auth, "registration_params", None):
        try:
            auth.registration_params = dict(p.get("registration_params") or {})
        except Exception:
            pass
    base = p.get("base_url") or p.get("mcp_url") or ""
    if base and not getattr(spec, "base_url", ""):
        spec.base_url = base
        changed = True
    return changed
