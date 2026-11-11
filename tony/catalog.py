"""Manifest loading + validation. Every app is a single YAML file."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import BASE_DIR

APPS_DIR = BASE_DIR / "apps"
_SLUG_RE = re.compile(r"^[a-z0-9_]{2,40}$")
_REG_SLUG_RE = re.compile(r"^[a-z0-9_-]{2,64}$")
_TIERS = {"read", "write", "destructive"}

# Verbs that can never change state remotely. Everything else needs approval.
_READ_VERBS = {"GET", "HEAD", "OPTIONS"}

# A few APIs only expose a query over POST (GraphQL, search, list). Those are
# reads even though the verb is POST, so they must not be gated as writes.
_READ_ONLY_POST = {
    ("dropbox", "account"), ("dropbox", "list_folder"),
    ("linear", "viewer"), ("linear", "issues"),
    ("monday", "me"), ("monday", "boards"),
    ("notion", "search"), ("notion", "query_database"),
    ("tiktok", "list_videos"),
}


def infer_tier(app: str, action: str, method: str) -> str:
    """Read/write tier for an action that does not declare one.

    A missing tier used to default to "read", which silently let POST, PUT,
    PATCH and DELETE actions run without approval. The verb is the safe
    default: only known query-by-POST endpoints stay on the read side.
    """
    verb = (method or "GET").upper()
    if verb in _READ_VERBS:
        return "read"
    if (app, action) in _READ_ONLY_POST:
        return "read"
    return "write"



class ManifestError(ValueError):
    pass


@dataclass
class AuthSpec:
    type: str = "none"                      # none|oauth2|api_key|bearer|basic|custom
    authorize_url: str = ""
    token_url: str = ""
    scopes: list[str] = field(default_factory=list)
    client_id_env: str = ""
    client_secret_env: str = ""
    pkce: bool = False
    authorize_params: dict[str, str] = field(default_factory=dict)
    token_params: dict[str, str] = field(default_factory=dict)
    # api_key style
    header_name: str = "Authorization"
    query_name: str = ""
    value_template: str = "Bearer {token}"
    # static key support (self-hosted single-tenant apps)
    static_env: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> AuthSpec:
        raw = raw or {}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class ActionSpec:
    slug: str
    name: str
    description: str
    method: str = "GET"
    url: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    tier: str = "read"
    headers: dict[str, str] = field(default_factory=dict)
    body_template: dict[str, Any] | None = None
    pagination: dict[str, Any] | None = None
    response: dict[str, Any] = field(default_factory=dict)
    danger_note: str = ""
    public: bool = False
    universal: bool = False

    @property
    def full_slug(self) -> str:
        return f"{self.slug}"


# One shared, authenticated passthrough that every app gets. This is what makes
# "every app in the catalogue can write" true without inventing endpoints: Tony
# forwards any method/path/body the vendor documents, with the app's own stored
# credentials attached by the normal auth layer. It is a single object shared by
# all apps on purpose (7,900 copies would be pointless memory on a 512MB host).
UNIVERSAL_REQUEST = ActionSpec(
    slug="api_request",
    name="Call any endpoint",
    description=("Send any authenticated request to this app's API: pick the method, the path after "
                 "the API root, query string and a JSON body. Use this for writes the built-in "
                 "actions do not cover (create, update, delete, upload, custom fields)."),
    method="POST",
    url="{base_url}/{path}",
    params={
        "path": {"type": "string", "in": "path", "format": "path", "default": "",
                 "description": "Path after the API root, e.g. v1/customers/42"},
        "method": {"type": "string", "in": "query", "default": "POST",
                   "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                   "description": "HTTP verb to send"},
        "query": {"type": "object", "in": "query", "description": "Query string parameters"},
        "body": {"type": "object", "in": "body", "description": "JSON body for the request"},
    },
    tier="write",
    danger_note="Writes reach the real API. Destructive calls still pass the approval gate.",
    universal=True,
)


def infer_base_url(spec: "AppSpec") -> str:
    """Best-effort API host for apps whose manifest never declared one.

    Only scheme + host is used, so the passthrough path is always unambiguous
    ("api/v3/customers/42" against CoinGecko, "v0/topstories.json" against
    Hacker News). Directory apps with no real endpoints stay empty and are asked
    for a base URL at connect time.
    """
    from urllib.parse import urlparse
    urls = [a.url for a in spec.actions if not a.universal and a.url.startswith(("http://", "https://"))]
    if not urls:
        return ""
    parsed = [urlparse(u) for u in urls]
    hosts = {p.netloc for p in parsed}
    if len(hosts) != 1:
        return ""
    return f"{parsed[0].scheme}://{parsed[0].netloc}"


def attach_universal(spec: "AppSpec") -> "AppSpec":
    """Give an app the shared write passthrough, unless it already declares one."""
    if not any(a.slug == UNIVERSAL_REQUEST.slug for a in spec.actions):
        spec.actions.append(UNIVERSAL_REQUEST)
    return spec


@dataclass
class AppSpec:
    slug: str
    name: str
    category: str
    description: str
    docs: str
    logo: str
    auth: AuthSpec
    actions: list[ActionSpec]
    default_headers: dict[str, str] = field(default_factory=dict)
    base_url: str = ""
    verified: bool = True
    notes: str = ""
    path: str = ""
    source: str = "curated"
    tier: str = "actions"
    haystack: str = ""
    popular: bool = False

    def action(self, slug: str) -> ActionSpec | None:
        return next((a for a in self.actions if a.slug == slug), None)

    def to_public(self, include_actions: bool = True) -> dict[str, Any]:
        data = {
            "slug": self.slug,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "docs": self.docs,
            "logo": self.logo,
            "verified": self.verified,
            "auth": {
                "type": self.auth.type,
                "scopes": self.auth.scopes,
                "pkce": self.auth.pkce,
            },
            "actions_count": len(self.actions),
            "notes": self.notes,
            "source": self.source,
            "tier": self.tier,
            "popular": self.popular,
            "reads": sum(1 for a in self.actions if a.tier == "read"),
            "writes": sum(1 for a in self.actions if a.tier != "read"),
        }
        if include_actions:
            data["actions"] = [a.to_public() for a in self.actions]
        return data


def _action_to_public(self: ActionSpec) -> dict[str, Any]:
    return {
        "slug": self.slug,
        "name": self.name,
        "description": self.description,
        "method": self.method,
        "tier": self.tier,
        "params": self.params,
        "required": self.required,
        "pagination": bool(self.pagination),
        "danger_note": self.danger_note,
        "public": self.public,
    }


ActionSpec.to_public = _action_to_public  # type: ignore[attr-defined]


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data or data[key] in (None, ""):
        raise ManifestError(f"{where}: missing required field '{key}'")
    return data[key]


def parse_manifest(path: Path) -> AppSpec:
    where = str(path)
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ManifestError(f"{where}: invalid YAML ({exc})") from exc
    if not isinstance(raw, dict):
        raise ManifestError(f"{where}: manifest must be a mapping")

    slug = str(_require(raw, "slug", where))
    if not _SLUG_RE.match(slug):
        raise ManifestError(f"{where}: slug '{slug}' must be lowercase a-z0-9_")

    actions_raw = raw.get("actions") or []
    if not isinstance(actions_raw, list) or not actions_raw:
        raise ManifestError(f"{where}: needs at least one action")

    actions: list[ActionSpec] = []
    seen: set[str] = set()
    for i, a in enumerate(actions_raw):
        if not isinstance(a, dict):
            raise ManifestError(f"{where}: action #{i} must be a mapping")
        a_slug = str(_require(a, "slug", f"{where} action#{i}"))
        if not _SLUG_RE.match(a_slug):
            raise ManifestError(f"{where}: action slug '{a_slug}' invalid")
        if a_slug in seen:
            raise ManifestError(f"{where}: duplicate action '{a_slug}'")
        seen.add(a_slug)
        tier = str(a.get("tier") or infer_tier(slug, a_slug, str(a.get("method", "GET")))).lower()
        if tier not in _TIERS:
            raise ManifestError(f"{where}: action '{a_slug}' tier must be one of {_TIERS}")
        params = a.get("params") or {}
        if not isinstance(params, dict):
            raise ManifestError(f"{where}: action '{a_slug}' params must be a mapping")
        required = a.get("required") or [k for k, v in params.items() if isinstance(v, dict) and v.get("required")]
        url = str(a.get("url") or raw.get("base_url") or "")
        if "{" not in url and not url.startswith(("http://", "https://")):
            raise ManifestError(f"{where}: action '{a_slug}' needs an absolute url")
        actions.append(
            ActionSpec(
                slug=a_slug,
                name=str(a.get("name") or a_slug.replace("_", " ").title()),
                description=str(a.get("description") or ""),
                method=str(a.get("method", "GET")).upper(),
                url=url,
                params=params,
                required=[str(r) for r in required],
                tier=tier,
                headers={str(k): str(v) for k, v in (a.get("headers") or {}).items()},
                body_template=a.get("body"),
                pagination=a.get("pagination"),
                response=a.get("response") or {},
                danger_note=str(a.get("danger_note") or ""),
                public=bool(a.get("public") or False),
            )
        )

    return AppSpec(
        slug=slug,
        name=str(_require(raw, "name", where)),
        category=str(raw.get("category") or "Other"),
        description=str(raw.get("description") or ""),
        docs=str(raw.get("docs") or ""),
        logo=str(raw.get("logo") or f"https://www.google.com/s2/favicons?domain={slug}.com&sz=64"),
        auth=AuthSpec.from_dict(raw.get("auth")),
        actions=actions,
        default_headers={str(k): str(v) for k, v in (raw.get("default_headers") or {}).items()},
        base_url=str(raw.get("base_url") or ""),
        verified=bool(raw.get("verified", True)),
        notes=str(raw.get("notes") or ""),
        path=where,
        popular=bool(raw.get("popular", True)),
    )


REGISTRY_FILE = BASE_DIR / "registry" / "apps.jsonl"


def parse_registry_line(line: str, where: str) -> AppSpec:
    raw = json.loads(line)
    slug = str(raw.get("slug") or "")
    if not _REG_SLUG_RE.match(slug):
        raise ManifestError(f"{where}: bad slug '{slug}'")
    actions = []
    for a in raw.get("actions") or []:
        act_slug = str(a.get("slug") or "")
        if not _REG_SLUG_RE.match(act_slug):
            continue
        actions.append(ActionSpec(
            slug=act_slug,
            name=str(a.get("name") or act_slug.replace("_", " ").title()),
            description=str(a.get("description") or ""),
            method=str(a.get("method", "GET")).upper(),
            url=str(a.get("url") or ""),
            params=a.get("params") or {},
            required=[str(r) for r in (a.get("required") or [])],
            tier=(str(a.get("tier")).lower() if str(a.get("tier")).lower() in _TIERS
                  else infer_tier(slug, act_slug, str(a.get("method", "GET")))),
            headers={str(k): str(v) for k, v in (a.get("headers") or {}).items()},
            body_template=a.get("body_template"),
            pagination=a.get("pagination"),
            response=a.get("response") or {},
            danger_note=str(a.get("danger_note") or ""),
            public=bool(a.get("public") or False),
        ))
    return AppSpec(
        slug=slug,
        name=str(raw.get("name") or slug),
        category=str(raw.get("category") or "Other"),
        description=str(raw.get("description") or ""),
        docs=str(raw.get("docs") or ""),
        logo=str(raw.get("logo") or ""),
        auth=AuthSpec.from_dict(raw.get("auth")),
        actions=actions,
        base_url=str(raw.get("base_url") or ""),
        verified=bool(raw.get("verified", False)),
        notes=str(raw.get("note") or raw.get("notes") or ""),
        path=where,
        source=str(raw.get("source") or "registry"),
        tier=str(raw.get("tier") or ("actions" if actions else "directory")),
        popular=bool(raw.get("popular", False)),
    )


# Hand-ordered so the catalogue opens with what builders actually reach for.
FEATURED = [
    "gmail", "googlecalendar", "googledrive", "googlesheets", "slack", "github", "notion", "linear",
    "jira", "hubspot", "salesforce", "stripe", "openai", "anthropic", "youtube", "linkedin",
    "facebook", "instagram", "discord", "telegram", "whatsapp", "twilio", "sendgrid", "mailchimp",
    "airtable", "asana", "trello", "zoom", "outlook", "dropbox", "shopify", "figma", "zendesk",
    "intercom", "quickbooks", "xero", "paypal", "gitlab", "confluence", "monday", "clickup",
]
_FEATURED_RANK = {s: i for i, s in enumerate(FEATURED)}


class Catalog:
    def __init__(self, apps_dir: Path = APPS_DIR, registry_file: Path = REGISTRY_FILE) -> None:
        self.apps_dir = apps_dir
        self.registry_file = registry_file
        self.apps: dict[str, AppSpec] = {}
        self.errors: list[str] = []
        self._act_cache: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self.apps = {}
        self.errors = []
        for path in sorted(self.apps_dir.rglob("*.y*ml")):
            try:
                spec = parse_manifest(path)
            except ManifestError as exc:
                self.errors.append(str(exc))
                continue
            if spec.slug in self.apps:
                self.errors.append(f"{path}: duplicate app slug '{spec.slug}'")
                continue
            spec.haystack = f"{spec.slug} {spec.name} {spec.description} {spec.category}".lower()
            if not spec.base_url:
                spec.base_url = infer_base_url(spec)
            self.apps[spec.slug] = attach_universal(spec)
        if self.registry_file.exists():
            with self.registry_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        spec = parse_registry_line(line, str(self.registry_file))
                    except (ManifestError, json.JSONDecodeError):
                        continue
                    if spec.slug in self.apps:
                        continue
                    spec.haystack = (
                        f"{spec.slug} {spec.name} {spec.description} {spec.category} "
                        + " ".join(a.slug for a in spec.actions if not a.universal)
                    ).lower()
                    if not spec.base_url:
                        spec.base_url = infer_base_url(spec)
                    self.apps[spec.slug] = attach_universal(spec)
        self._apply_managed_auth()

    def _apply_managed_auth(self) -> None:
        """Give the core providers their real OAuth metadata, once per load."""
        try:
            from . import provider_registry as managed
        except Exception:  # pragma: no cover - registry is optional
            return
        for spec in list(self.apps.values()):
            try:
                managed.apply(spec)
            except Exception as exc:  # noqa: BLE001 - a bad override must not kill the catalog
                self.errors.append(f"managed auth {spec.slug}: {type(exc).__name__}")
        try:
            managed.ensure_apps(self)
        except Exception:  # pragma: no cover
            pass


    # ── lookups ──────────────────────────────────────────────────────────
        self._mark_shadowed()
        self._apply_managed_aliases()

    def _apply_managed_aliases(self) -> None:
        """Duplicate imports of a managed app resolve to the managed one.

        Without this an agent can rank "googleapis-gmail" above "gmail", find no
        account attached to the stub, and wrongly tell the user Gmail is not
        connected. Runs after the shadow map so it is never overwritten.
        """
        try:
            from . import provider_registry as managed
        except Exception:  # pragma: no cover
            return
        self.alias_of = getattr(self, "alias_of", {})
        for slug in list(self.apps.keys()):
            try:
                canon = managed.canonical(slug)
            except Exception:  # noqa: BLE001
                continue
            if canon != slug and canon in self.apps:
                self.alias_of.setdefault(slug, canon)

    def _mark_shadowed(self) -> None:
        """Same product imported from several catalogs: keep the best, hide the rest.

        Nothing is deleted. A shadowed app still resolves by slug (so existing
        connections and code keep working); it just stops cluttering the browse
        view. Best = most real actions, then curated > registry, then has a logo.
        """
        src_rank = {"curated": 0, "openapi": 1, "nango": 2, "activepieces": 3, "n8n": 4, "pipedream": 5}
        groups: dict[str, list[AppSpec]] = {}
        for a in self.apps.values():
            key = re.sub(r"[^a-z0-9]+", "", a.name.lower())
            # tiny, generic names ("api", "client") are not safe to merge
            if len(key) >= 4:
                groups.setdefault(key, []).append(a)
        self.shadowed: set[str] = set()
        self.alias_of: dict[str, str] = {}
        for members in groups.values():
            if len(members) < 2:
                continue
            # Only merge when the twins share a vendor-ish identity (same name AND same category family)
            members.sort(key=lambda a: (-len(a.actions), src_rank.get(a.source, 9), 0 if a.logo else 1, a.slug))
            keeper = members[0]
            for dup in members[1:]:
                # never hide a different product that merely shares a name (e.g. two unrelated "Client" APIs)
                if dup.base_url and keeper.base_url and dup.base_url.split("/")[2:3] != keeper.base_url.split("/")[2:3]:
                    if dup.source == keeper.source:
                        continue
                self.shadowed.add(dup.slug)
                self.alias_of[dup.slug] = keeper.slug

    def get(self, slug: str) -> AppSpec | None:
        return self.apps.get(slug)

    def resolve(self, slug: str) -> AppSpec | None:
        """Look a slug up through the duplicate map.

        The same product is imported from several catalogs, so an agent that names
        "hacker-news" must land on the curated, keyless "hackernews" spec instead of
        the empty generated twin that then claims the app is not connected.
        """
        key = (slug or "").strip().lower()
        spec = self.apps.get(key) or self.apps.get(slug or "")
        alias = getattr(self, "alias_of", {}).get(key)
        if alias:
            keeper = self.apps.get(alias)
            if keeper is not None:
                # a connected account always wins over tidiness
                if spec is None or spec.auth.type != "none" or keeper.auth.type == "none":
                    return keeper
        return spec

    def search(self, query: str = "", category: str = "", tier: str = "",
               source: str = "", limit: int = 0, offset: int = 0,
               dedupe: bool = False) -> list[AppSpec]:
        q = (query or "").strip().lower()
        cat = (category or "").strip().lower()
        tier = (tier or "").strip().lower()
        src = (source or "").strip().lower()
        out = []
        hide = getattr(self, "shadowed", set())
        for app in self.apps.values():
            if dedupe and app.slug in hide and not q:
                continue
            if cat and app.category.lower() != cat:
                continue
            if tier and app.tier != tier:
                continue
            if src and app.source != src:
                continue
            if q:
                text = app.haystack + " " + self._action_text(app)
                if not all(tok in text for tok in q.split()):
                    continue
            out.append(app)
        def rank(a: AppSpec) -> tuple:
            name = a.name.lower()
            slug = a.slug.lower()
            if not q:
                rel = 0
            elif slug == q or name == q:
                rel = 0
            elif slug.startswith(q) or name.startswith(q):
                rel = 1
            elif q in name:
                rel = 2
            elif q in slug:
                rel = 3
            else:
                rel = 4
            tier_rank = 0 if a.tier == "actions" else 1 if a.tier == "proxy" else 2
            # Relevance first when searching; otherwise popular -> has a real logo -> built-in.
            feat = _FEATURED_RANK.get(a.slug.replace("_", "").replace("-", ""),
                                      _FEATURED_RANK.get(a.slug, 999))
            return (rel, feat, 0 if a.popular else 1, 0 if a.logo else 1, tier_rank,
                    len(a.name), a.name.lower())

        out.sort(key=rank)
        if offset:
            out = out[offset:]
        if limit:
            out = out[:limit]
        return out

    def _action_text(self, app: AppSpec) -> str:
        """Action names + parameter names, built once per app and cached."""
        text = self._act_cache.get(app.slug)
        if text is None:
            parts = []
            for a in app.actions:
                parts.append(a.slug)
                parts.append(a.name.lower())
                parts.append((a.description or "").lower())
                if a.params:
                    parts.append(" ".join(str(k).replace("_", " ").lower() for k in a.params))
            text = " ".join(parts)
            self._act_cache[app.slug] = text
        return text

    def find_action(self, name: str) -> tuple[AppSpec, ActionSpec] | None:
        """Resolve 'app.action', 'app__action', 'app_action' or a bare action slug."""
        name = name.strip()
        if not name:
            return None
        for sep in (".", "__"):
            if sep in name:
                head, _, tail = name.partition(sep)
                app = self.get(head)
                if app:
                    act = app.action(tail)
                    if act:
                        return app, act
        for app in self.apps.values():
            act = app.action(name)
            if act:
                return app, act
        # prefixed underscore form: github_list_repos
        for app in self.apps.values():
            if name.startswith(app.slug + "_"):
                act = app.action(name[len(app.slug) + 1:])
                if act:
                    return app, act
        return None

    def stats(self) -> dict[str, Any]:
        by_tier: dict[str, int] = {}
        by_source: dict[str, int] = {}
        actions = 0
        for a in self.apps.values():
            actions += len(a.actions)
            by_tier[a.tier] = by_tier.get(a.tier, 0) + 1
            by_source[a.source] = by_source.get(a.source, 0) + 1
        return {
            "apps": len(self.apps),
            "actions": actions,
            "categories": len({a.category for a in self.apps.values()}),
            "duplicates_hidden_in_browse": len(getattr(self, "shadowed", ())),
            "by_tier": by_tier,
            "by_source": by_source,
        }

    def categories(self) -> list[str]:
        return sorted({a.category for a in self.apps.values()})

    def category_counts(self) -> list[dict[str, Any]]:
        """[{name, count}] biggest first, 'Other' always last - for the catalogue sidebar."""
        counts: dict[str, int] = {}
        for a in self.apps.values():
            counts[a.category] = counts.get(a.category, 0) + 1
        rows = [{"name": k, "count": v} for k, v in counts.items()]
        rows.sort(key=lambda r: (r["name"] == "Other", -r["count"], r["name"]))
        return rows


catalog = Catalog()
