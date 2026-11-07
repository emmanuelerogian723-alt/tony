"""Turn public sources into Tony manifests.

Three importers, one output shape:

* ``from_openapi``  — an OpenAPI/Swagger document becomes an app with real
  endpoints (the highest-value import: every action is a live API path).
* ``from_nango``    — a provider definition with a base URL and auth headers
  becomes an app with a generic, authenticated ``request`` action.
* ``from_directory``— a name from a public integration directory becomes a
  connectable app: the user supplies their own API base + token once, and the
  generic ``request`` action works against it.

Everything produced here is plain data: no code generation, no per-app Python.
"""
from __future__ import annotations

import re
from typing import Any

MAX_ACTIONS_PER_APP = 40
MAX_DESCRIPTION = 220
MAX_ACTION_DESCRIPTION = 180


def slugify(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return re.sub(r"-{2,}", "-", value)[:64]


def _host(url: str) -> str:
    try:
        return url.split("/")[2] or "example.com"
    except IndexError:
        return "example.com"


def _trim(text: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


def _schema_to_params(schema: Any, required: list[str] | None = None) -> dict[str, Any]:
    """Shrink a JSON-Schema object into Tony's flat parameter map."""
    params: dict[str, Any] = {}
    if not isinstance(schema, dict):
        return params
    props = schema.get("properties") or {}
    required = required or list(schema.get("required") or [])
    for name, prop in list(props.items())[:14]:
        if not isinstance(prop, dict):
            continue
        typ = prop.get("type") or ("object" if "properties" in prop else "string")
        typ = _scalar_type(typ)
        if typ not in {"string", "integer", "number", "boolean", "object", "array"}:
            typ = "string"
        spec: dict[str, Any] = {"type": typ}
        desc = prop.get("description") or prop.get("title")
        if desc:
            spec["description"] = _trim(desc, 140)
        if prop.get("enum") and typ == "string":
            spec["enum"] = [str(v) for v in prop["enum"][:20]]
        if prop.get("default") is not None and typ in {"string", "integer", "number", "boolean"}:
            spec["default"] = prop["default"]
        if typ == "array":
            spec["items"] = {"type": (prop.get("items") or {}).get("type", "string")}
        if name in required:
            spec["required"] = True
        params[name] = spec
    return params


def _server_url(spec: dict[str, Any]) -> str:
    servers = spec.get("servers") or []
    if servers:
        url = servers[0].get("url") or ""
        for var, cfg in (servers[0].get("variables") or {}).items():
            default = (cfg or {}).get("default") or ((cfg or {}).get("enum") or [""])[0]
            url = url.replace("{" + var + "}", str(default))
        if url.startswith("/"):
            host = ((spec.get("host") or "") + (spec.get("basePath") or ""))
            scheme = (spec.get("schemes") or ["https"])[0]
            url = f"{scheme}://{host}{url}" if host else url
        return url.rstrip("/")
    host = spec.get("host")
    if host:
        scheme = (spec.get("schemes") or ["https"])[0]
        return f"{scheme}://{host}{(spec.get('basePath') or '').rstrip('/')}"
    return ""


def _auth_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    schemes = ((spec.get("components") or {}).get("securitySchemes")
               or spec.get("securityDefinitions") or {})
    chosen: dict[str, Any] = {"type": "none"}
    for name, scheme in schemes.items():
        if not isinstance(scheme, dict):
            continue
        typ = (scheme.get("type") or "").lower()
        if typ == "oauth2":
            flows = scheme.get("flows") or {}
            flow = next(iter(flows.values()), {}) if flows else {}
            authorize = flow.get("authorizationUrl") or scheme.get("authorizationUrl") or ""
            token_url = flow.get("tokenUrl") or scheme.get("tokenUrl") or ""
            if not (authorize and token_url):
                return {"type": "bearer"}   # incomplete flow -> token access
            return {
                "type": "oauth2",
                "authorize_url": authorize,
                "token_url": token_url,
                "scopes": list((flow.get("scopes") or scheme.get("scopes") or {}).keys())[:20],
                "client_id_env": f"{slugify(name).upper().replace('-', '_')}_CLIENT_ID",
                "client_secret_env": f"{slugify(name).upper().replace('-', '_')}_CLIENT_SECRET",
            }
        if typ == "http":
            http_scheme = (scheme.get("scheme") or "").lower()
            if http_scheme == "bearer":
                chosen = {"type": "bearer"}
            elif http_scheme == "basic":
                chosen = {"type": "basic"}
        elif typ == "apikey":
            chosen = {
                "type": "api_key",
                "in": (scheme.get("in") or "header"),
                "name": scheme.get("name") or "X-API-Key",
                "header_name": scheme.get("name") if (scheme.get("in") == "header") else "",
                "query_name": scheme.get("name") if (scheme.get("in") == "query") else "",
                "value_template": "{token}",
            }
    return chosen


def _action_slug(method: str, path: str, operation_id: str | None) -> str:
    if operation_id:
        raw = operation_id
    else:
        raw = method + "-" + path
    raw = re.sub(r"[{}]", "", raw)
    slug = slugify(raw)
    return slug[:60] or f"{method.lower()}-action"


_VALID_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


def _scalar_type(raw: Any) -> str:
    """OpenAPI 3.1 allows a list of types; collapse to the first usable scalar."""
    if isinstance(raw, list):
        raw = next((t for t in raw if isinstance(t, str) and t in _VALID_TYPES), "string")
    if not isinstance(raw, str) or raw not in _VALID_TYPES:
        return "string"
    return raw


def from_openapi(slug: str, entry: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    """Build an app manifest from an OpenAPI 3 / Swagger 2 document."""
    if not isinstance(spec, dict):
        return None
    info = spec.get("info") or {}
    base = _server_url(spec)
    if not base or not base.startswith(("http://", "https://")):
        return None
    paths = spec.get("paths") or {}
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    # GET first so the most useful, safest actions survive the cap
    order = ["get", "post", "put", "patch", "delete"]
    for method in order:
        for path, ops in paths.items():
            if not isinstance(ops, dict):
                continue
            op = ops.get(method)
            if not isinstance(op, dict):
                continue
            if len(actions) >= MAX_ACTIONS_PER_APP:
                break
            act_slug = _action_slug(method, path, op.get("operationId"))
            if act_slug in seen:
                act_slug = slugify(act_slug + "-" + path.strip("/").replace("/", "-"))[:60]
            if act_slug in seen:
                continue
            seen.add(act_slug)

            params: dict[str, Any] = {}
            required: list[str] = []
            for p in (op.get("parameters") or []) + (ops.get("parameters") or []):
                if not isinstance(p, dict) or not p.get("name"):
                    continue
                if p.get("in") not in {"path", "query", "header"}:
                    continue
                typ = _scalar_type((p.get("schema") or {}).get("type") or p.get("type") or "string")
                spec_p: dict[str, Any] = {"type": typ, "in": p["in"]}
                if p.get("description"):
                    spec_p["description"] = _trim(p["description"], 120)
                if p.get("required"):
                    spec_p["required"] = True
                    if p["in"] == "path":
                        required.append(p["name"])
                params[p["name"]] = spec_p

            body_schema = (((op.get("requestBody") or {}).get("content") or {})
                           .get("application/json") or {}).get("schema")
            if body_schema:
                body_params = _schema_to_params(body_schema)
                for name, p in body_params.items():
                    p.setdefault("in", "body")
                    params.setdefault(name, p)
                    if p.get("required"):
                        required.append(name)

            if method in {"post", "put", "patch"} and not body_schema:
                # No schema published: expose a raw JSON body so the write is still reachable.
                params.setdefault("body", {
                    "type": "object", "in": "body",
                    "description": "Raw JSON body forwarded to the endpoint",
                })

            tier = "read" if method == "get" else ("destructive" if method == "delete" else "write")
            actions.append({
                "slug": act_slug,
                "name": _trim(op.get("summary") or f"{method.upper()} {path}", 70),
                "description": _trim(op.get("description") or op.get("summary") or f"{method.upper()} {path}",
                                     MAX_ACTION_DESCRIPTION),
                "method": method.upper(),
                "url": base + path,
                "params": params,
                "required": sorted(set(required)),
                "tier": tier,
            })
        if len(actions) >= MAX_ACTIONS_PER_APP:
            break

    if not actions:
        return None

    categories = info.get("x-apisguru-categories") or []
    category = {
        "financial": "Finance", "commerce": "Commerce", "messaging": "Communication",
        "social": "Social", "developer_tools": "Developer", "devtools": "Developer",
        "productivity": "Productivity", "machine_learning": "AI", "ai": "AI",
        "media": "Media", "travel": "Travel", "weather": "Data", "data": "Data",
        "security": "Security", "identity": "Security", "iot": "IoT",
        "business": "Business", "health": "Health", "education": "Education",
        "open_data": "Data", "government": "Data", "analytics": "Data",
    }.get(str(categories[0] if categories else "").lower(), "Other")

    logo = ((info.get("x-logo") or {}).get("url")
            or f"https://www.google.com/s2/favicons?domain={base.split('/')[2]}&sz=128")

    return {
        "slug": slug,
        "name": _trim(info.get("title") or slug.replace("-", " ").title(), 60),
        "category": category,
        "description": _trim(info.get("description") or f"{_trim(info.get('title') or slug, 60)} API", MAX_DESCRIPTION),
        "docs": (info.get("contact") or {}).get("url") or (spec.get("externalDocs") or {}).get("url") or base,
        "logo": logo,
        "base_url": base,
        "auth": _auth_from_spec(spec),
        "actions": actions,
        "source": "openapi",
        "tier": "actions",
        "verified": False,
        "note": "Imported from an OpenAPI document. Actions follow the published spec.",
    }


def from_nango(slug: str, provider: dict[str, Any]) -> dict[str, Any] | None:
    """Provider definition (base URL + auth) becomes a proxy app."""
    if not isinstance(provider, dict):
        return None
    name = _trim(provider.get("display_name") or slug.replace("-", " ").title(), 60)
    proxy = provider.get("proxy") or {}
    base = str(proxy.get("base_url") or "").rstrip("/")
    docs = provider.get("docs") or ""
    cats = provider.get("categories") or []
    category = {
        "crm": "Business", "hris": "Business", "accounting": "Finance", "ticketing": "Productivity",
        "communication": "Communication", "team-chat": "Communication", "email": "Communication",
        "developer-tools": "Developer", "dev-tools": "Developer", "productivity": "Productivity",
        "social": "Social", "marketing": "Marketing", "analytics": "Data", "ecommerce": "Commerce",
        "payment": "Finance", "storage": "Storage", "database": "Data", "iam": "Security",
        "security": "Security", "knowledge-base": "Productivity", "project-management": "Productivity",
        "recruiting": "Business", "support": "Productivity", "video": "Media", "design": "Design",
    }.get(str(cats[0] if cats else "").lower(), "Other")

    mode = str(provider.get("auth_mode") or "").upper()
    auth: dict[str, Any] = {"type": "api_key", "in": "header", "header_name": "Authorization",
                            "value_template": "Bearer {token}"}
    if mode.startswith("OAUTH"):
        auth = {"type": "bearer"}
    elif mode == "BASIC":
        auth = {"type": "basic"}

    actions: list[dict[str, Any]] = []
    if True:
        actions.append({
            "slug": "request",
            "name": "Call the API",
            "description": f"Authenticated request to {name}. Path is appended to the documented base URL.",
            "method": "GET",
            "url": (base + "{path}") if (base and "${" not in base and base.startswith("http")) else "{base_url}{path}",
            "params": {
                "path": {"type": "string", "in": "path", "description": "e.g. /v1/me", "required": True},
                "method": {"type": "string", "in": "query", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                           "default": "GET"},
                "query": {"type": "object", "in": "query", "description": "Query parameters"},
                "body": {"type": "object", "in": "body", "description": "JSON body for writes"},
            },
            "required": ["path"],
            "tier": "read",
        })

    if not actions and not docs and not base:
        return None

    return {
        "slug": slug,
        "name": name,
        "category": category,
        "description": _trim(provider.get("description") or f"{name} — authenticated API access.", MAX_DESCRIPTION),
        "docs": docs or base,
        "logo": (f"https://www.google.com/s2/favicons?domain={_host(base)}&sz=128"
                 if (base and "${" not in base and base.startswith("http")) else ""),
        "auth": auth,
        "actions": actions,
        "source": "nango",
        "tier": "proxy" if (base and "${" not in base) else "directory",
        "verified": False,
        "note": "Provider metadata imported from Nango's open provider catalogue."
        + ("" if actions else " This provider needs a per-tenant domain, so it is listed for discovery."),
    }


def from_directory(slug: str, name: str, source: str, homepage: str = "", category: str = "Other") -> dict[str, Any]:
    """A public directory entry: connectable once the user supplies its API base."""
    return {
        "slug": slug,
        "name": _trim(name, 60),
        "category": category or "Other",
        "description": _trim(f"{name} — listed in the {source} integration directory. "
                             "Connect it with your own API base URL and token.", MAX_DESCRIPTION),
        "docs": homepage or "",
        "logo": "",
        "auth": {"type": "api_key", "in": "header", "header_name": "Authorization",
                 "value_template": "Bearer {token}"},
        "actions": [{
            "slug": "request",
            "name": "Call the API",
            "description": "Authenticated request using the API base URL saved when you connected this app.",
            "method": "GET",
            "url": "{base_url}{path}",
            "params": {
                "path": {"type": "string", "in": "path", "description": "e.g. /v1/me", "required": True},
                "method": {"type": "string", "in": "query", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                           "default": "GET"},
                "query": {"type": "object", "in": "query"},
                "body": {"type": "object", "in": "body"},
            },
            "required": ["path"],
            "tier": "read",
        }],
        "source": source,
        "tier": "directory",
        "verified": False,
        "note": f"Discovered via the open {source} directory. Add the app's API base URL to activate it.",
    }
