"""Tony Python SDK: zero dependencies, one client, every app.

    from tony_sdk import Tony
    tony = Tony("tk_live_...")
    tony.execute("github.list_repos", per_page=3)
    tony.batch([("hackernews.top_stories", {}), ("coingecko.price", {"ids": "bitcoin"})])
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Iterable


class TonyError(RuntimeError):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"{status}: {detail}")
        self.status, self.detail = status, detail


class Tony:
    def __init__(self, api_key: str, base_url: str = "https://tony-7su0.onrender.com",
                 session: str | None = None, timeout: float = 60.0):
        self.api_key, self.base_url, self.session, self.timeout = api_key, base_url.rstrip("/"), session, timeout

    # ── transport ─────────────────────────────────────────────
    def _call(self, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}
        if self.session:
            headers["X-Tony-Session"] = self.session
        req = urllib.request.Request(self.base_url + path, method=method, headers=headers,
                                     data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raise TonyError(e.code, e.read().decode()[:800]) from None

    # ── actions ───────────────────────────────────────────────
    def execute(self, action: str, approved: bool = False, **args: Any) -> dict[str, Any]:
        return self._call("POST", "/v1/execute", {"action": action, "args": args, "approved": approved})

    def batch(self, calls: Iterable[tuple[str, dict] | str]) -> dict[str, Any]:
        items = [{"action": c} if isinstance(c, str) else {"action": c[0], "args": c[1]} for c in calls]
        return self._call("POST", "/v1/batch", {"calls": items})

    def apps(self, q: str = "", limit: int = 50) -> dict[str, Any]:
        return self._call("GET", f"/v1/apps?q={urllib.parse.quote(q)}&limit={limit}")

    def actions(self, app: str, q: str = "") -> dict[str, Any]:
        return self._call("GET", f"/v1/apps/{app}/actions?q={urllib.parse.quote(q)}")

    def tools(self, fmt: str = "openai") -> dict[str, Any]:
        return self._call("GET", f"/v1/tools?fmt={fmt}")

    def connections(self) -> dict[str, Any]:
        return self._call("GET", "/v1/connections")

    def connect(self, app: str) -> dict[str, Any]:
        return self._call("POST", f"/v1/connections/{app}/start")

    def sessions(self) -> dict[str, Any]:
        return self._call("GET", "/v1/sessions")

    def create_session(self, entity_id: str, apps: list[str] | None = None,
                       tiers: list[str] | None = None, ttl_hours: int = 24) -> dict[str, Any]:
        return self._call("POST", "/v1/sessions", {"entity_id": entity_id, "apps": apps or [],
                                                   "tiers": tiers or ["read"], "ttl_hours": ttl_hours})

    def custom_tools(self) -> dict[str, Any]:
        return self._call("GET", "/v1/custom-tools")

    def create_custom_tool(self, slug: str, url: str, method: str = "GET", tier: str = "read",
                           secret: str = "", auth_style: str = "bearer", **extra: Any) -> dict[str, Any]:
        return self._call("POST", "/v1/custom-tools", {"slug": slug, "url": url, "method": method,
                                                       "tier": tier, "secret": secret,
                                                       "auth_style": auth_style, **extra})

    def rate(self, app: str, stars: int, review: str = "") -> dict[str, Any]:
        return self._call("POST", "/v1/ratings", {"app_slug": app, "stars": stars, "review": review})

    # ── framework adapters ────────────────────────────────────
    def langchain_tools(self):
        from langchain_core.tools import StructuredTool  # type: ignore

        out = []
        for t in self.tools()["tools"]:
            fn = t["function"]
            name, params = fn["name"], fn["parameters"].get("properties", {})
            out.append(StructuredTool.from_function(
                func=lambda _name=name, **kw: self.execute(_name.replace("__", ".", 1), **kw),
                name=name, description=fn.get("description", ""),
                args_schema=_schema(name, params)))
        return out

    def llamaindex_tools(self):
        from llama_index.core.tools import FunctionTool  # type: ignore

        return [FunctionTool.from_defaults(
            fn=lambda _n=t["function"]["name"], **kw: self.execute(_n.replace("__", ".", 1), **kw),
            name=t["function"]["name"], description=t["function"].get("description", ""))
            for t in self.tools()["tools"]]

    def crewai_tools(self):
        from crewai_tools import tool  # type: ignore

        made = []
        for t in self.tools()["tools"][:60]:
            name = t["function"]["name"]

            def _run(_name=name, **kw):
                return self.execute(_name.replace("__", ".", 1), **kw)

            made.append(tool(name.replace("__", "_"))(_run))
        return made


def _schema(name: str, params: dict):
    from pydantic import create_model  # type: ignore

    fields = {k: (str, "") for k in params}
    return create_model(f"{name}_args", **fields)
