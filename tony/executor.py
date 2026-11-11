"""The execution engine: turns a manifest + arguments into a real API call.

Design goals
------------
* One code path for every app (declarative, no per-app Python).
* Safe by default: SSRF guard, tiered approvals, response budgeting.
* Predictable output for LLMs: normalised JSON, capped size, clear errors.
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from .catalog import ActionSpec, AppSpec
from .config import settings

USER_AGENT = "Tony/0.1 (+https://github.com/emmanuelerogian723-alt/tony)"
_PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
              "169.254.0.0/16", "0.0.0.0/8", "100.64.0.0/10", "::1/128", "fc00::/7", "fe80::/10")
]


class ExecutionError(Exception):
    def __init__(self, message: str, *, status: int = 0, detail: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


@dataclass
class ExecResult:
    ok: bool
    status: int
    latency_ms: int
    data: Any = None
    meta: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "meta": self.meta,
        }
        if self.ok:
            payload["data"] = self.data
        else:
            payload["error"] = self.error
            if self.meta.get("detail") is not None:
                payload["detail"] = self.meta["detail"]
        return payload


# ── argument handling ─────────────────────────────────────────────────────
_HTTP_VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def _placement(action: ActionSpec, name: str, spec: dict[str, Any]) -> str:
    where = str(spec.get("in") or "").lower()
    if where in {"query", "path", "body", "header"}:
        return where
    return "query" if action.method in {"GET", "DELETE", "HEAD"} else "body"


def coerce_value(spec: dict[str, Any], value: Any) -> Any:
    if value is None:
        return None
    t = (spec or {}).get("type")
    if t == "integer":
        return int(value)
    if t == "number":
        return float(value)
    if t == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if t == "array" and not isinstance(value, list):
        return [value]
    if t == "object" and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
    return value


def validate_args(action: ActionSpec, args: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(args or {})
    unknown = [k for k in args if k not in action.params]
    if unknown:
        raise ExecutionError(f"Unknown argument(s): {', '.join(sorted(unknown))}. Allowed: {', '.join(sorted(action.params)) or 'none'}")
    cleaned: dict[str, Any] = {}
    for name, spec in action.params.items():
        spec = spec or {}
        if name in args and args[name] is not None:
            try:
                cleaned[name] = coerce_value(spec, args[name])
            except (TypeError, ValueError) as exc:
                raise ExecutionError(f"Argument '{name}' is not a valid {spec.get('type', 'value')}") from exc
        elif "default" in spec:
            cleaned[name] = spec["default"]
    missing = [r for r in action.required if cleaned.get(r) in (None, "")]
    if missing:
        raise ExecutionError(f"Missing required argument(s): {', '.join(missing)}")
    # enum validation
    for name, value in list(cleaned.items()):
        enum = (action.params.get(name) or {}).get("enum")
        if enum and value not in enum:
            raise ExecutionError(f"Argument '{name}' must be one of: {', '.join(map(str, enum))}")
    return cleaned


# ── security ──────────────────────────────────────────────────────────────
def assert_safe_url(url: str) -> None:
    if settings.allow_private_networks:
        return
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ExecutionError("Only http(s) URLs are allowed")
    host = parsed.hostname or ""
    if not host:
        raise ExecutionError("Request URL has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ExecutionError(f"Could not resolve host '{host}'") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if any(addr in net for net in _PRIVATE_NETS):
            raise ExecutionError("Blocked request to a private network address (SSRF guard)")




# ── lightweight web parsers (sites without an API) ────────────────────────
import html as _html
import re as _re
from xml.etree import ElementTree as _ET


def _strip_tags(text: str) -> str:
    text = _re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", text)
    text = _re.sub(r"(?s)<!--.*?-->", " ", text)
    text = _re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = _re.sub(r"(?i)</(p|div|li|h[1-6]|tr|section|article)>", "\n", text)
    text = _re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = _re.sub(r"[ \t\u00a0]+", " ", text)
    text = _re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def html_to_text(raw: str) -> dict:
    title = ""
    m = _re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    if m:
        title = _html.unescape(_strip_tags(m.group(1))).strip()
    desc = ""
    d = _re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', raw)
    if d:
        desc = _html.unescape(d.group(1)).strip()
    return {"title": title, "description": desc, "text": _strip_tags(raw)[:8000]}


def html_links(raw: str, limit: int = 40) -> list:
    out, seen = [], set()
    for href, label in _re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw):
        text = _strip_tags(label)
        if not text or len(text) < 3 or href.startswith(("#", "javascript:")):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append({"title": text[:160], "url": _html.unescape(href)})
        if len(out) >= limit:
            break
    return out


def ddg_results(raw: str, limit: int = 15) -> list:
    results = []
    blocks = _re.split(r'(?i)<div[^>]+class=["\'][^"\']*result[^"\']*["\'][^>]*>', raw)
    for block in blocks[1:]:
        m = _re.search(r'(?is)<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block)
        if not m:
            continue
        url, title = _html.unescape(m.group(1)), _strip_tags(m.group(2))
        sn = _re.search(r'(?is)class=["\'][^"\']*result__snippet[^"\']*["\'][^>]*>(.*?)</(?:a|div|span)>', block)
        snippet = _strip_tags(sn.group(1)) if sn else ""
        if url.startswith("//duckduckgo.com/l/?uddg="):
            from urllib.parse import parse_qs, unquote
            from urllib.parse import urlparse as _up
            q = parse_qs(_up(url).query).get("uddg")
            if q:
                url = unquote(q[0])
        results.append({"title": title, "url": url, "snippet": snippet[:280]})
        if len(results) >= limit:
            break
    return results


def rss_items(raw: str, limit: int = 20) -> list:
    items = []
    try:
        root = _ET.fromstring(raw.encode("utf-8", "ignore"))
    except _ET.ParseError:
        return []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag not in {"item", "entry"}:
            continue
        row = {}
        for child in node:
            key = child.tag.split("}")[-1].lower()
            if key in {"title", "link", "published", "updated", "summary", "description", "id"}:
                val = (child.text or "").strip()
                if key == "link" and not val:
                    val = child.attrib.get("href", "")
                row[key] = val[:400]
        if row:
            items.append(row)
        if len(items) >= limit:
            break
    return items


# ── request building ──────────────────────────────────────────────────────
def needs_base_url(spec: AppSpec) -> bool:
    """True when an app's URL template still expects the user to supply a host."""
    for act in spec.actions:
        if getattr(act, "universal", False):
            continue
        if "{base_url}" in (act.url or ""):
            return True
    # Every app now carries the "call any endpoint" passthrough. If the app has no
    # published host, that passthrough cannot work until the user supplies one, so
    # the connect form must ask for it up front instead of failing on first call.
    if not (spec.base_url or "").strip():
        return any(getattr(act, "universal", False) for act in spec.actions)
    return False


def apply_auth(
    spec: AppSpec,
    headers: dict[str, str],
    query: dict[str, Any],
    creds: dict[str, Any] | None,
) -> None:
    """Mutate headers/query with the credentials for this app."""
    auth = spec.auth
    creds = creds or {}
    token = (
        creds.get("access_token")
        or creds.get("api_key")
        or creds.get("token")
        or creds.get("bearer_token")
        or ""
    )
    if auth.type in {"oauth2", "bearer"}:
        if token:
            headers.setdefault("Authorization", f"Bearer {token}")
    elif auth.type == "api_key":
        if token:
            if auth.query_name:
                query[auth.query_name] = token
            else:
                headers.setdefault(auth.header_name or "Authorization",
                                   auth.value_template.format(token=token))
    elif auth.type == "basic":
        user = creds.get("username") or creds.get("api_key") or ""
        pwd = creds.get("password") or ""
        if user:
            headers.setdefault("Authorization", "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode())
    elif auth.type == "path":
        pass  # already substituted into the URL above
    elif auth.type == "custom" and token:
        headers.setdefault(auth.header_name or "Authorization", auth.value_template.format(token=token))


def build_request(
    spec: AppSpec,
    action: ActionSpec,
    args: dict[str, Any],
    creds: dict[str, Any] | None,
    page: int = 1,
    cursor: str | None = None,
    page_size: int | None = None,
) -> tuple[str, str, dict[str, str], dict[str, Any], Any]:
    headers: dict[str, str] = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    headers.update(spec.default_headers or {})
    headers.update(action.headers or {})
    if "Accept" not in (action.headers or {}):
        pass

    url = action.url
    query: dict[str, Any] = {}
    body: dict[str, Any] = {}

    method_override: str | None = None
    for name, value in args.items():
        if name in url and ("{" + name + "}") in url:
            continue
        spec_p = action.params.get(name) or {}
        placement = _placement(action, name, spec_p)
        # a param named "method" with verb enum switches the HTTP verb
        if name == "method" and placement == "query" and str(value).upper() in _HTTP_VERBS:
            method_override = str(value).upper()
            continue
        if placement == "query":
            if isinstance(value, dict):
                for qk, qv in value.items():
                    if qv is not None:
                        query[str(qk)] = qv
            elif value is not None:
                query[name] = value
        elif placement == "header":
            headers[name] = str(value)
        elif placement == "body":
            if isinstance(value, dict) and name in {"body", "payload", "data"}:
                body.update(value)
            else:
                body[name] = value
        else:  # path segment
            raw = str(value)
            keep_slash = str(spec_p.get("format") or "") == "path" or name in {"path", "url_path"}
            if raw.lower().startswith(("http://", "https://")):
                url = url.replace("{" + name + "}", raw)
            else:
                url = url.replace("{" + name + "}", quote(raw, safe="/" if keep_slash else ""))

    if method_override:
        method = method_override

    # credentials may fill URL placeholders ({token}, {account_sid}, {shop}, …)
    for cred_key, cred_val in (creds or {}).items():
        token = "{" + str(cred_key) + "}"
        if token in url and isinstance(cred_val, (str, int, float)):
            url = url.replace(token, str(cred_val))

    # any explicit path params in the URL template
    for name, spec_ in action.params.items():
        token = "{" + name + "}"
        if token in url:
            if name not in args:
                if spec_.get("required", False) or name in action.required:
                    raise ExecutionError(f"Missing path parameter '{name}'")
                continue
            _raw = str(args[name])
            keep_slash = str(spec_.get("format") or "") == "path" or name in {"path", "url_path"}
            if _raw.lower().startswith(("http://", "https://")):
                url = url.replace(token, _raw)
            else:
                url = url.replace(token, quote(_raw, safe="/" if keep_slash else ""))
    if "{base_url}" in url:
        root = (spec.base_url or "").rstrip("/")
        if root:
            url = url.replace("{base_url}", root)
        else:
            raise ExecutionError(
                f"{spec.name} has no API host yet. Open the console, pick {spec.name} → Connect, "
                f"and paste its API base URL (docs: {spec.docs or 'see the vendor docs'}).")
    if "{" in url and "}" in url:
        raise ExecutionError(f"Unresolved path parameter in URL: {url}")

    # pagination controls
    if action.pagination:
        pag = action.pagination
        mode = str(pag.get("mode", "page"))
        if mode in {"page", "offset"}:
            query[str(pag.get("param", "page"))] = page
        elif mode == "cursor" and cursor:
            query[str(pag.get("param", "cursor"))] = cursor
        if page_size and pag.get("page_size_param"):
            query[str(pag["page_size_param"])] = page_size

    if action.body_template:
        body = _deep_merge(action.body_template, body)

    # The effective verb: an explicit `method` argument (the proxy takes one, and
    # so does any action with a verb enum) must win over the manifest default.
    # This was silently discarded before, so POST /gists went out as a GET and
    # wrote nothing while still reporting success.
    effective = (method_override or action.method).upper()

    payload: Any = None
    if effective in {"POST", "PUT", "PATCH", "DELETE"} and body:
        payload = body
    elif effective in {"POST", "PUT", "PATCH"}:
        payload = {}

    apply_auth(spec, headers, query, creds)
    return url, effective, headers, query, payload


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(base.get(k), v) if k in base else v
        return out
    return override if override not in (None, {}, []) else base


# ── response shaping ──────────────────────────────────────────────────────
def dig(data: Any, path: str | None) -> Any:
    if not path or path in {"$", "", "."}:
        return data
    cur = data
    for part in str(path).lstrip("$").strip(".").split("."):
        if not part:
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def unfreeze(raw: Any) -> Any:
    """Some endpoints return JSON as a string; unwrap it."""
    if isinstance(raw, dict) and set(raw.keys()) == {"text"}:
        text = raw["text"]
        stripped = text.lstrip()
        if stripped[:1] in "[{":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return raw
    return raw


def shape_response(action: ActionSpec, raw: Any) -> tuple[Any, dict[str, Any]]:
    meta: dict[str, Any] = {}
    transform = str((action.response or {}).get("transform") or "")
    if transform:
        text = raw.get("text", "") if isinstance(raw, dict) else str(raw)
        if transform == "html_text":
            data = html_to_text(text)
        elif transform == "linklist":
            data = {"links": html_links(text)}
        elif transform == "ddg":
            data = {"results": ddg_results(text)}
        elif transform == "rss":
            data = {"items": rss_items(text)}
        else:
            data = raw
        meta["transform"] = transform
    else:
        raw = unfreeze(raw)
        path = (action.response or {}).get("path")
        data = dig(raw, path) if path else raw
    max_items = int((action.response or {}).get("max_items", 50) or 50)
    if isinstance(data, list) and len(data) > max_items:
        meta["items_total"] = len(data)
        data = data[:max_items]
        meta["items_returned"] = len(data)
        meta["truncated"] = True
    max_chars = int((action.response or {}).get("max_chars", settings.max_response_chars) or settings.max_response_chars)
    data, cut = _fit_budget(data, max_chars)
    if cut:
        meta["truncated"] = True
        meta.setdefault("note", "Trimmed to fit the response budget; request fewer fields or items.")
    meta["chars"] = len(json.dumps(data, ensure_ascii=False, default=str))
    return data, meta


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _shrink_strings(value: Any, limit: int = 1200) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, list):
        return [_shrink_strings(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: _shrink_strings(v, limit) for k, v in value.items()}
    return value


def _fit_budget(data: Any, max_chars: int) -> tuple[Any, bool]:
    """Keep structure where possible; trim content before collapsing to text."""
    if _size(data) <= max_chars:
        return data, False
    if isinstance(data, list):
        cut = list(data)
        while cut and _size(cut) > max_chars:
            cut = cut[: max(1, int(len(cut) * 0.6))]
        if cut and _size(cut) <= max_chars:
            return cut, True
        data = cut
    if isinstance(data, dict):
        shrunk = _shrink_strings(data)
        if _size(shrunk) <= max_chars:
            return shrunk, True
        keys = list(shrunk.keys())
        keep: dict[str, Any] = {}
        dropped: list[str] = []
        for key in keys:
            candidate = {**keep, key: shrunk[key]}
            if _size(candidate) <= max_chars:
                keep = candidate
            else:
                dropped.append(key)
        if keep:
            if dropped:
                keep["_truncated_keys"] = dropped[:20]
            return keep, True
        return shrunk, True
    # last resort: collapse to text
    text = json.dumps(data, ensure_ascii=False, default=str)[:max_chars]
    return text, True


def redact_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    parts = []
    for chunk in parsed.query.split("&"):
        key = chunk.split("=", 1)[0]
        if any(s in key.lower() for s in ("key", "token", "secret", "password", "sig")):
            parts.append(f"{key}=***")
        else:
            parts.append(chunk)
    return parsed._replace(query="&".join(parts)).geturl()


# ── execution ─────────────────────────────────────────────────────────────

async def _guarded_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    max_hops: int = 5,
) -> httpx.Response:
    """Send a request, re-validating every redirect hop against the SSRF guard.

    httpx's automatic redirect following would happily follow a 302 into
    169.254.169.254, so redirects are handled here instead.
    """
    current_url = url
    current_method = method
    current_body = json_body
    for hop in range(max_hops + 1):
        assert_safe_url(current_url)
        resp = await client.request(
            current_method,
            current_url,
            headers=headers,
            params=params if hop == 0 else None,
            json=current_body,
            follow_redirects=False,
        )
        if resp.status_code not in (301, 302, 303, 307, 308):
            return resp
        location = resp.headers.get("location")
        if not location:
            return resp
        current_url = str(httpx.URL(current_url).join(location))
        if resp.status_code in (301, 302, 303) and current_method not in ("GET", "HEAD"):
            current_method = "GET"
            current_body = None
        params = None
    return resp


async def execute(
    spec: AppSpec,
    action: ActionSpec,
    args: dict[str, Any] | None,
    creds: dict[str, Any] | None,
    *,
    client: httpx.AsyncClient | None = None,
    dry_run: bool = False,
) -> ExecResult:
    started = time.perf_counter()
    cleaned = validate_args(action, args)

    # Fan-out search: three keyless sources, merged, no single point of failure.
    if str((action.response or {}).get("transform") or "") == "search":
        from .search import multi_search
        query = str(cleaned.get("q") or cleaned.get("query") or "")
        limit = int((action.response or {}).get("max_items", 12) or 12)
        found = await asyncio.wait_for(multi_search(query, limit), timeout=settings.execution_deadline)
        return ExecResult(True, 200, int((time.perf_counter() - started) * 1000), found,
                          {"transform": "search", "sources": found.get("sources", {})})
    pages: list[Any] = []
    last_raw: Any = None
    meta: dict[str, Any] = {}
    max_pages = 1
    if action.pagination:
        max_pages = int(action.pagination.get("max_pages", 3) or 3)

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=False)
    cursor: str | None = None
    status = 0
    try:
        for page in range(1, max_pages + 1):
            url, method, headers, query, payload = build_request(spec, action, cleaned, creds, page=page, cursor=cursor)
            assert_safe_url(url)
            if dry_run:
                return ExecResult(True, 0, 0, None, {
                    "dry_run": True,
                    "method": method,
                    "url": redact_url(url),
                    "query": {k: ("***" if "token" in k.lower() else v) for k, v in query.items()},
                    "body": payload,
                    "args": cleaned,
                })
            attempt = 0
            while True:
                try:
                    resp = await _guarded_request(client, method, url, headers=headers, params=query, json_body=payload)
                except httpx.HTTPError as exc:
                    if attempt < settings.http_retries:
                        attempt += 1
                        await asyncio.sleep(0.4 * attempt)
                        continue
                    raise ExecutionError(f"Network error: {type(exc).__name__}: {exc}") from exc
                status = resp.status_code
                if status in {429, 500, 502, 503, 504} and attempt < settings.http_retries:
                    retry_after = resp.headers.get("Retry-After", "")
                    delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 0.5 * (2 ** attempt)
                    attempt += 1
                    await asyncio.sleep(min(delay, 5))
                    continue
                break

            if status >= 400:
                try:
                    detail = resp.json()
                except ValueError:
                    detail = resp.text[:800]
                raise ExecutionError(f"{spec.name} returned HTTP {status}", status=status, detail=detail)

            try:
                raw = resp.json()
            except ValueError:
                raw = {"text": resp.text[: settings.max_response_chars]}
            last_raw = raw
            if action.pagination:
                items_path = str(action.pagination.get("items_path", "items"))
                items = dig(raw, items_path)
                if isinstance(items, list):
                    pages.extend(items)
                mode = str(action.pagination.get("mode", "page"))
                nxt = dig(raw, str(action.pagination.get("next_path", ""))) if action.pagination.get("next_path") else None
                if mode == "cursor":
                    if not nxt:
                        break
                    cursor = str(nxt)
                elif isinstance(items, list) and (not items or len(items) < int(action.pagination.get("page_size", 50) or 50)):
                    break
            else:
                break

        raw_out = pages if pages else last_raw
        if pages:
            meta["pages"] = max_pages
        data, shape_meta = shape_response(action, raw_out)
        meta.update(shape_meta)
        latency = int((time.perf_counter() - started) * 1000)
        return ExecResult(True, status or 200, latency, data, meta)
    finally:
        if owns_client:
            await client.aclose()


async def execute_plan(
    spec: AppSpec,
    action: ActionSpec,
    plan: dict[str, Any],
    creds: dict[str, Any] | None,
    *,
    dry_run: bool = False,
) -> ExecResult:
    """Run a typed connector's request plan (email MIME, file uploads, typed args).

    Connectors hand back the exact verb, URL and payload they want sent. Without
    this the plan was silently dropped and the raw catalog endpoint ran instead,
    which is why friendly actions like gmail.send_email used to fail.
    """
    started = time.perf_counter()
    url = str(plan.get("url") or "")
    method = str(plan.get("method") or "POST").upper()
    headers = {k: str(v) for k, v in (plan.get("headers") or {}).items()}
    query = dict(plan.get("params") or plan.get("query") or {})
    payload = plan.get("body")
    if not url:
        raise ExecutionError(f"{spec.slug}.{action.slug}: connector produced no URL")
    apply_auth(spec, headers, query, creds)
    headers.setdefault("Accept", "application/json")
    assert_safe_url(url)
    if dry_run:
        return ExecResult(True, 0, 0, None, {
            "dry_run": True, "method": method, "url": redact_url(url),
            "query": {k: ("***" if "token" in k.lower() else v) for k, v in query.items()},
            "body": {k: v for k, v in (payload or {}).items() if k != "raw"} if isinstance(payload, dict) else payload,
            "summary": plan.get("summary", ""),
        })
    attempt = 0
    async with httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=False) as client:
        while True:
            try:
                resp = await _guarded_request(client, method, url, headers=headers, params=query,
                                              json_body=payload)
            except httpx.HTTPError as exc:
                if attempt < settings.http_retries:
                    attempt += 1
                    await asyncio.sleep(0.4 * attempt)
                    continue
                raise ExecutionError(f"Network error: {type(exc).__name__}: {exc}") from exc
            if resp.status_code in {429, 500, 502, 503, 504} and attempt < settings.http_retries:
                attempt += 1
                await asyncio.sleep(min(0.5 * (2 ** attempt), 5))
                continue
            break
    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text[:800]
        raise ExecutionError(f"{spec.name} returned HTTP {resp.status_code}", status=resp.status_code,
                             detail=detail)
    try:
        raw = resp.json()
    except ValueError:
        raw = {"text": resp.text[: settings.max_response_chars]}
    data, shape_meta = shape_response(action, raw)
    meta = {"typed": True, "summary": plan.get("summary", ""), **shape_meta}
    return ExecResult(True, resp.status_code, int((time.perf_counter() - started) * 1000), data, meta)


async def execute_direct(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    max_chars: int | None = None,
) -> ExecResult:
    """Raw request used by the built-in `web` connector and trigger checks."""
    started = time.perf_counter()
    assert_safe_url(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    async with httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=False) as client:
        resp = await _guarded_request(client, method, url, headers=headers, params=params, json_body=json_body)
    latency = int((time.perf_counter() - started) * 1000)
    if resp.status_code >= 400:
        return ExecResult(False, resp.status_code, latency, None, {}, f"HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError:
        data = {"text": resp.text[: (max_chars or settings.max_response_chars)]}
    encoded = json.dumps(data, ensure_ascii=False, default=str)
    cap = max_chars or settings.max_response_chars
    meta = {"chars": len(encoded)}
    if len(encoded) > cap:
        data = encoded[:cap]
        meta["truncated"] = True
    return ExecResult(True, resp.status_code, latency, data, meta)
