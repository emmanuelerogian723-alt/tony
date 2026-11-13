"""One place that decides whether a host is safe to call.

An outbound fetch happens in three different shapes (a read job, a directory
app's base URL, an OAuth token exchange). Each used to carry its own regex, and
the read path had none at all: `169.254.169.254` was accepted, opened against a
host that never answers, and the job sat in "running" holding a worker slot.

Two layers here, on purpose:

* the literal check is cheap and synchronous, so it runs while validating a body
  and while following links inside a crawl;
* the resolved check runs at fetch time and looks at the actual A/AAAA records,
  which is what catches a public name that points at 127.0.0.1.

Self-hosters pointing Tony at an internal API can set TONY_ALLOW_PRIVATE_URLS=1
(TONY_ALLOW_PRIVATE_BASE_URLS is still honoured for the old base-URL path).
"""
from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import socket
from urllib.parse import urlsplit

# Hostnames that are metadata services rather than websites, before DNS.
_METADATA_NAMES = {
    "metadata", "metadata.google.internal", "metadata.goog", "instance-data",
    "metadata.azure.internal", "kubernetes.default", "kubernetes.default.svc",
}

# Names that only ever resolve inside a cloud or a LAN.
_INTERNAL_SUFFIXES = (".internal", ".local", ".localhost", ".localdomain",
                      ".svc", ".cluster.local", ".home.arpa", ".lan", ".intranet")

_blocked_networks = [
    ipaddress.ip_network(n) for n in (
        "0.0.0.0/8",          # "this network"
        "10.0.0.0/8",         # RFC1918
        "100.64.0.0/10",      # carrier NAT
        "127.0.0.0/8",        # loopback
        "169.254.0.0/16",     # link-local, includes the cloud metadata address
        "172.16.0.0/12",      # RFC1918
        "192.0.0.0/24",       # IETF protocol assignments
        "192.0.2.0/24",       # TEST-NET-1
        "192.88.99.0/24",     # 6to4 relay anycast
        "192.168.0.0/16",     # RFC1918
        "198.18.0.0/15",      # benchmarking
        "198.51.100.0/24",    # TEST-NET-2
        "203.0.113.0/24",     # TEST-NET-3
        "224.0.0.0/4",        # multicast
        "240.0.0.0/4",        # reserved, includes 255.255.255.255
        "::/128", "::1/128",  # unspecified, loopback
        "::ffff:0:0/96",      # IPv4-mapped: checked again as IPv4
        "64:ff9b::/96",       # NAT64
        "100::/64",           # discard-only
        "fc00::/7",           # unique local
        "fe80::/10",          # link-local
        "ff00::/8",           # multicast
    )
]

# A DNS answer we already paid for, so a crawl does not resolve every page twice.
_DNS_CACHE: dict[str, tuple[float, str | None]] = {}
_DNS_TTL = 60.0


class Blocked(ValueError):
    """A URL that must not be fetched. The message is safe to show a caller."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def allow_private() -> bool:
    for name in ("TONY_ALLOW_PRIVATE_URLS", "TONY_ALLOW_PRIVATE_BASE_URLS"):
        if os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def blocked_ip(value: str) -> str:
    """Reason this address is off limits, or '' when it is a normal public address."""
    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return ""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return f"{ip} is a private or link-local address"
    if ip.is_multicast:
        return f"{ip} is a multicast address"
    if ip.is_reserved or ip.is_unspecified:
        return f"{ip} is a reserved address"
    for net in _blocked_networks:
        if ip.version == net.version and ip in net:
            return f"{ip} is inside {net}, which is not reachable from the internet"
    return ""


def blocked_host(host: str) -> str:
    """Reason this literal host is off limits (no DNS), or ''."""
    name = (host or "").strip().lower().strip("[]").rstrip(".")
    if not name:
        return "A host is required"
    if name in _METADATA_NAMES:
        return f"{name} is a cloud metadata service, not a website"
    reason = blocked_ip(name)
    if reason:
        return reason
    if any(name.endswith(suffix) for suffix in _INTERNAL_SUFFIXES):
        return f"{name} is an internal-only name"
    # A single label ("intranet", "wiki") resolves through search domains.
    if "." not in name:
        return f"{name} is not a public hostname"
    return ""


def _split(raw: str) -> tuple[str, str, int]:
    value = (raw or "").strip()
    if not value:
        raise Blocked("A URL is required")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"}:
        raise Blocked(f"{parts.scheme}:// is not fetchable; use http or https")
    if parts.username or parts.password:
        raise Blocked("Credentials in the URL are not accepted")
    host = (parts.hostname or "").strip()
    if not host:
        raise Blocked("That URL has no host")
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError:
        raise Blocked("That URL has an invalid port") from None
    return parts.scheme.lower(), host, port


def check_url(raw: str, *, allow: bool | None = None) -> str:
    """Validate a URL without DNS. Returns it normalised; raises Blocked."""
    scheme, host, port = _split(raw)
    if allow if allow is not None else allow_private():
        return f"{scheme}://{host.lower()}{':' + str(port) if port not in (80, 443) else ''}"
    reason = blocked_host(host)
    if reason:
        raise Blocked(reason)
    return f"{scheme}://{host.lower()}{':' + str(port) if port not in (80, 443) else ''}"


def resolve_blocked(host: str, port: int = 0) -> str:
    """Resolve a host and return the reason its addresses are off limits, or ''."""
    if allow_private():
        return ""
    name = (host or "").strip().lower().strip("[]").rstrip(".")
    import time as _t

    cached = _DNS_CACHE.get(name)
    if cached and _t.time() - cached[0] < _DNS_TTL:
        return cached[1] or ""
    try:
        infos = socket.getaddrinfo(name, port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # A name that does not resolve is not proof of anything: DNS can be slow
        # or the record transient. Only a positive private-address answer blocks.
        _DNS_CACHE[name] = (_t.time(), "")
        return ""
    except OSError:
        _DNS_CACHE[name] = (_t.time(), "")
        return ""
    seen = []
    for info in infos:
        addr = str(info[4][0])
        seen.append(addr)
        reason = blocked_ip(addr)
        if reason:
            msg = f"{name} resolves to {reason}"
            _DNS_CACHE[name] = (_t.time(), msg)
            return msg
    if not seen:
        _DNS_CACHE[name] = (_t.time(), "")
        return ""
    _DNS_CACHE[name] = (_t.time(), "")
    return ""


async def check_url_resolved(raw: str) -> str:
    """Full check: shape, literal host, then the addresses it resolves to."""
    check_url(raw)
    if allow_private():
        return raw
    _scheme, host, port = _split(raw)
    if blocked_ip(host):
        return raw          # already rejected by check_url; unreachable in practice
    loop = asyncio.get_running_loop()
    reason = await loop.run_in_executor(None, resolve_blocked, host, port)
    if reason:
        raise Blocked(reason)
    return raw


def check_url_resolved_sync(raw: str) -> str:
    """Blocking form of :func:`check_url_resolved` for threadpool callers."""
    check_url(raw)
    if allow_private():
        return raw
    _scheme, host, port = _split(raw)
    reason = resolve_blocked(host, port)
    if reason:
        raise Blocked(reason)
    return raw


def safe(raw: str, *, allow: bool | None = None) -> bool:
    try:
        check_url(raw, allow=allow)
        return True
    except Blocked:
        return False


__all__ = ["Blocked", "allow_private", "blocked_host", "blocked_ip", "check_url",
           "check_url_resolved", "check_url_resolved_sync", "resolve_blocked", "safe"]
