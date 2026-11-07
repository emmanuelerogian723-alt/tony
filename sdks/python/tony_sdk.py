"""Python SDK for Tony — https://github.com/emmanuelerogian723-alt/tony

    from tony_sdk import Tony

    tony = Tony("https://tony.example.com", api_key="tk_live_…")
    repos = tony.execute("github.list_repos", entity_id="user_42", args={"per_page": 5})
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

__all__ = ["Tony", "AsyncTony", "TonyError", "RunResult"]


class TonyError(RuntimeError):
    """Raised when Tony returns an error for a call."""

    def __init__(self, message: str, *, status: int = 0, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


@dataclass
class RunResult:
    ok: bool
    status: int
    latency_ms: int
    data: Any
    meta: dict[str, Any]
    error: str = ""
    run_id: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "RunResult":
        return cls(
            ok=bool(payload.get("ok")),
            status=int(payload.get("status") or 0),
            latency_ms=int(payload.get("latency_ms") or 0),
            data=payload.get("data"),
            meta=payload.get("meta") or {},
            error=payload.get("error") or "",
            run_id=payload.get("run_id") or "",
        )


class _Base:
    def __init__(self, base_url: str, api_key: str | None = None, *, timeout: float = 40.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._headers = {"Accept": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    # ── catalogue ──────────────────────────────────────────────────────────
    def apps(self, search: str = "", category: str = "") -> list[dict[str, Any]]:
        params = {k: v for k, v in {"search": search, "category": category}.items() if v}
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            return c.get(f"{self.base_url}/v1/apps", params=params).json().get("apps", [])

    def app(self, slug: str) -> dict[str, Any]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            return c.get(f"{self.base_url}/v1/apps/{slug}").json()

    def actions(self, search: str = "", app: str = "") -> list[dict[str, Any]]:
        params = {k: v for k, v in {"search": search, "app": app}.items() if v}
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            return c.get(f"{self.base_url}/v1/actions", params=params).json().get("actions", [])

    # ── connections ────────────────────────────────────────────────────────
    def connect_url(self, app: str, entity_id: str, redirect_after: str = "/app") -> str:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            resp = c.post(
                f"{self.base_url}/v1/connections/{app}/start",
                json={"entity_id": entity_id, "redirect_after": redirect_after},
            )
            resp.raise_for_status()
            return resp.json()["authorization_url"]

    def connections(self, entity_id: str) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            return c.get(f"{self.base_url}/v1/connections", params={"entity_id": entity_id}).json().get("connections", [])

    def disconnect(self, app: str, entity_id: str) -> None:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            c.delete(f"{self.base_url}/v1/connections/{app}", params={"entity_id": entity_id})

    # ── execution ──────────────────────────────────────────────────────────
    def execute(
        self,
        action: str,
        *,
        entity_id: str = "default",
        args: dict[str, Any] | None = None,
        approved: bool = False,
        dry_run: bool = False,
    ) -> RunResult:
        payload = {
            "action": action,
            "entity_id": entity_id,
            "args": args or {},
            "approved": approved,
            "dry_run": dry_run,
        }
        with httpx.Client(timeout=self.timeout + 15, headers=self._headers) as c:
            resp = c.post(f"{self.base_url}/v1/execute", json=payload)
        if resp.status_code == 402 or resp.status_code == 202:
            # approval needed — hand the caller the run id
            body = resp.json()
            return RunResult(False, resp.status_code, 0, body.get("preview"), {"needs_approval": True},
                             "approval required", body.get("run_id", ""))
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise TonyError(body.get("detail") or f"HTTP {resp.status_code}", status=resp.status_code, detail=body)
        return RunResult.from_payload(resp.json())

    def approve(self, run_id: str) -> RunResult:
        with httpx.Client(timeout=self.timeout + 15, headers=self._headers) as c:
            resp = c.post(f"{self.base_url}/v1/runs/{run_id}/approve")
        resp.raise_for_status()
        return RunResult.from_payload(resp.json())

    def runs(self, limit: int = 25) -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            return c.get(f"{self.base_url}/v1/runs", params={"limit": limit}).json().get("runs", [])

    def tools(self, fmt: str = "openai") -> list[dict[str, Any]]:
        with httpx.Client(timeout=self.timeout, headers=self._headers) as c:
            return c.get(f"{self.base_url}/v1/tools", params={"format": fmt}).json().get("tools", [])


class Tony(_Base):
    """Synchronous client."""


class AsyncTony(_Base):
    """Async client with the same surface (methods are awaitable)."""

    async def apps(self, search: str = "", category: str = "") -> list[dict[str, Any]]:  # type: ignore[override]
        params = {k: v for k, v in {"search": search, "category": category}.items() if v}
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._headers) as c:
            return (await c.get(f"{self.base_url}/v1/apps", params=params)).json().get("apps", [])

    async def execute(  # type: ignore[override]
        self,
        action: str,
        *,
        entity_id: str = "default",
        args: dict[str, Any] | None = None,
        approved: bool = False,
        dry_run: bool = False,
    ) -> RunResult:
        payload = {"action": action, "entity_id": entity_id, "args": args or {},
                   "approved": approved, "dry_run": dry_run}
        async with httpx.AsyncClient(timeout=self.timeout + 15, headers=self._headers) as c:
            resp = await c.post(f"{self.base_url}/v1/execute", json=payload)
        if resp.status_code in (202, 402):
            body = resp.json()
            return RunResult(False, resp.status_code, 0, body.get("preview"), {"needs_approval": True},
                             "approval required", body.get("run_id", ""))
        if resp.status_code >= 400:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise TonyError(body.get("detail") or f"HTTP {resp.status_code}", status=resp.status_code, detail=body)
        return RunResult.from_payload(resp.json())

    async def approve(self, run_id: str) -> RunResult:  # type: ignore[override]
        async with httpx.AsyncClient(timeout=self.timeout + 15, headers=self._headers) as c:
            resp = await c.post(f"{self.base_url}/v1/runs/{run_id}/approve")
        resp.raise_for_status()
        return RunResult.from_payload(resp.json())
