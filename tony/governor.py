"""Per-host politeness and global concurrency for anything Tony fetches at scale.

One agent asking for 20,000 pages must not look like a denial-of-service to the
sites it reads, and one customer must not starve another. Every fetch in the
reader, the proxy and the fan-out path goes through a ticket from here:

* a global in-flight cap (memory/CPU guard on a 512MB worker)
* a per-host in-flight cap, so ten thousand pages across one domain trickle
  instead of hammering it
* a per-host token bucket, so request *rate* is bounded too, not just overlap
* a per-workspace cap, so a noisy tenant cannot take every slot

All numbers are env-tunable; the defaults are deliberately polite.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, "") or default))
    except ValueError:
        return default


GLOBAL_CONCURRENCY = _env_int("TONY_READ_GLOBAL_CONCURRENCY", 12)
HOST_CONCURRENCY = _env_int("TONY_READ_HOST_CONCURRENCY", 2)
HOST_RATE_PER_SEC = _env_float("TONY_READ_HOST_RATE", 4.0)
WORKSPACE_CONCURRENCY = _env_int("TONY_READ_WORKSPACE_CONCURRENCY", 12)


@dataclass
class _Bucket:
    rate: float
    capacity: float
    tokens: float = field(default=0.0)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
    updated: float = field(default_factory=time.monotonic)

    def take(self) -> float:
        """Return seconds to wait before a token is available (0 when ready)."""
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        missing = 1.0 - self.tokens
        self.tokens = 0.0
        return missing / self.rate if self.rate else 0.05


class Governor:
    """Shared limiter. Create once per process."""

    def __init__(self) -> None:
        self._global = asyncio.Semaphore(GLOBAL_CONCURRENCY)
        self._hosts: dict[str, asyncio.Semaphore] = {}
        self._workspaces: dict[str, asyncio.Semaphore] = {}
        self._buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(rate=HOST_RATE_PER_SEC, capacity=HOST_RATE_PER_SEC))
        self.stats: dict[str, int] = defaultdict(int)

    def _host_sem(self, host: str) -> asyncio.Semaphore:
        sem = self._hosts.get(host)
        if sem is None:
            sem = asyncio.Semaphore(HOST_CONCURRENCY)
            self._hosts[host] = sem
        return sem

    def _ws_sem(self, workspace: str) -> asyncio.Semaphore:
        sem = self._workspaces.get(workspace)
        if sem is None:
            sem = asyncio.Semaphore(WORKSPACE_CONCURRENCY)
            self._workspaces[workspace] = sem
        return sem

    def slot(self, host: str, workspace: str = "") -> "_Slot":
        """Async context manager yielding after the politeness wait."""
        return _Slot(self, (host or "").lower(), workspace or "_")

    async def acquire(self, host: str, workspace: str = "") -> None:
        host = (host or "").lower()
        wait = self._buckets[host].take()
        if wait:
            self.stats["throttled"] += 1
            await asyncio.sleep(wait)
        await self._ws_sem(workspace or "_").acquire()
        await self._host_sem(host).acquire()
        await self._global.acquire()
        self.stats["grants"] += 1

    def release(self, host: str, workspace: str = "") -> None:
        host = (host or "").lower()
        self._global.release()
        self._host_sem(host).release()
        self._ws_sem(workspace or "_").release()

    def snapshot(self) -> dict[str, object]:
        return {
            "global_concurrency": GLOBAL_CONCURRENCY,
            "host_concurrency": HOST_CONCURRENCY,
            "host_rate_per_sec": HOST_RATE_PER_SEC,
            "workspace_concurrency": WORKSPACE_CONCURRENCY,
            "hosts_tracked": len(self._hosts),
            "grants": self.stats.get("grants", 0),
            "throttled": self.stats.get("throttled", 0),
        }


class _Slot:
    def __init__(self, gov: Governor, host: str, workspace: str) -> None:
        self.gov, self.host, self.workspace = gov, host, workspace

    async def __aenter__(self) -> "_Slot":
        await self.gov.acquire(self.host, self.workspace)
        return self

    async def __aexit__(self, *exc) -> None:
        self.gov.release(self.host, self.workspace)


GOVERNOR = Governor()
