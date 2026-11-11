"""Live GitHub checks. Skipped unless GITHUB_TOKEN is set.

Read-only by design: these hit api.github.com with a real token and prove the
whole path (manifest -> auth -> request -> shaping) against the real provider.
No repository is modified.
"""
import os

import pytest

from tony.catalog import catalog
from tony.executor import execute

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_ACCESS_TOKEN") or ""
CREDS = {"token": TOKEN, "access_token": TOKEN}

pytestmark = pytest.mark.skipif(not TOKEN, reason="GITHUB_TOKEN not set")


async def _run(name, args=None, creds=None):
    spec, act = catalog.find_action(name)
    return await execute(spec, act, args or {}, creds or CREDS)


def test_live_whoami():
    import asyncio

    r = asyncio.run(_run("github.me"))
    assert r.ok, r.data
    assert r.data.get("login"), r.data
    assert r.status == 200


def test_live_list_repos():
    import asyncio

    r = asyncio.run(_run("github.list_repos", {"per_page": 5}))
    assert r.ok, r.data
    assert isinstance(r.data, list)


def test_live_repo_info():
    import asyncio

    r = asyncio.run(_run("github.repo_info", {"owner": "emmanuelerogian723-alt", "repo": "tony"}))
    assert r.ok, r.data
    assert r.data.get("full_name") == "emmanuelerogian723-alt/tony"


def test_live_proxy_read_reaches_github():
    import asyncio

    spec, act = catalog.find_action("proxy.request")
    creds = {"base_url": "https://api.github.com", "api_key": TOKEN}
    r = asyncio.run(execute(spec, act, {"path": "/rate_limit", "method": "GET"}, creds))
    assert r.ok, r.data
    assert (r.data or {}).get("resources", {}).get("core", {}).get("limit")


@pytest.mark.skipif(os.environ.get("TONY_LIVE_WRITE") != "1",
                    reason="set TONY_LIVE_WRITE=1 to exercise a real write")
def test_live_write_honours_verb():
    """A real PATCH. The description is written back unchanged, so nothing moves;
    before the method fix this call went out as a GET and reported success."""
    import asyncio

    spec, act = catalog.find_action("proxy.request")
    creds = {"base_url": "https://api.github.com", "api_key": TOKEN}

    async def go():
        info = await execute(spec, act, {"path": "/repos/emmanuelerogian723-alt/tony", "method": "GET"}, creds)
        assert info.ok, info.data
        desc = info.data.get("description") or ""
        patched = await execute(spec, act, {
            "path": "/repos/emmanuelerogian723-alt/tony",
            "method": "PATCH", "body": {"description": desc}}, creds)
        return patched

    r = asyncio.run(go())
    assert r.ok, r.data
