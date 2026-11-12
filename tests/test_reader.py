"""Read Anything and the fetch governor: deterministic tests, no live network."""

import asyncio
import json

from tony import reader


def test_extract_drops_chrome_and_tracking():
    html = ("<html lang='en'><head><title> Hello  World </title>"
            "<meta name='description' content='A page'></head>"
            "<body><nav>menu junk</nav><h1>Heading</h1><p>Body copy.</p>"
            "<script>bad()</script><a href='/x?utm_source=news&id=7'>Link</a></body></html>")
    out = reader.extract(html, "https://example.com/a/b")
    assert out["title"] == "Hello World"
    assert "menu junk" not in out["text"] and "bad()" not in out["text"]
    assert "Body copy." in out["text"]
    assert out["links"][0]["url"] == "https://example.com/x?id=7"


def test_tidy_url_collapses_duplicates():
    a = reader.tidy_url("https://Example.com/post/?utm_source=x&utm_medium=y")
    b = reader.tidy_url("https://example.com/post/")
    assert a == b == "https://example.com/post/"


def test_robots_rules():
    assert reader.allowed_by_robots("/pricing", ["/admin"], []) is True
    assert reader.allowed_by_robots("/admin/x", ["/admin"], []) is False
    assert reader.allowed_by_robots("/admin/public", ["/admin"], ["/admin/public"]) is True


def test_governor_serialises_one_host():
    from tony.governor import GOVERNOR, HOST_CONCURRENCY

    async def run():
        active = {"now": 0, "peak": 0}
        async def task():
            async with GOVERNOR.slot("example.org", "ws"):
                active["now"] += 1
                active["peak"] = max(active["peak"], active["now"])
                await asyncio.sleep(0.01)
                active["now"] -= 1
        await asyncio.gather(*[task() for _ in range(8)])
        return active["peak"]

    peak = asyncio.run(run())
    assert peak <= HOST_CONCURRENCY


def test_read_job_stores_deduped_pages(client, monkeypatch):
    html = "<html><head><title>Same</title></head><body><p>Identical content here.</p></body></html>"

    async def fake_fetch(client_, job, page):
        data = reader.extract(html, page["url"])
        digest = reader._hash(data["text"])
        dup = False
        with __import__("tony.db", fromlist=["session"]).session() as s:
            from sqlalchemy import select
            from tony.models import ReadPage
            dup = bool(s.scalar(select(ReadPage.id).where(
                ReadPage.job_id == job["id"], ReadPage.content_hash == digest, ReadPage.status == "done")))
        reader._save_page(page["id"], status="duplicate" if dup else "done", http_status=200,
                          title=data["title"], content="" if dup else data["text"],
                          content_hash=digest, word_count=data["word_count"])
        return {"ok": True}

    monkeypatch.setattr(reader, "_fetch_one", fake_fetch)

    created = client.post("/v1/read", json={"urls": ["https://a.example.com/1", "https://a.example.com/2"],
                                            "max_pages": 5})
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]
    asyncio.run(reader.run_job(job_id))

    state = client.get(f"/v1/read/{job_id}").json()
    assert state["status"] == "done"
    assert state["done"] == 1 and state["duplicate"] == 1
    pages = client.get(f"/v1/read/{job_id}/pages").json()["pages"]
    assert len(pages) == 2 and any(p["status"] == "duplicate" for p in pages)


def test_read_rejects_empty_request(client):
    r = client.post("/v1/read", json={"max_pages": 5})
    assert r.status_code == 400


def test_fanout_caps_and_reports(client):
    r = client.post("/v1/fanout", json={"calls": [{"action": "nope.missing"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1 and body["succeeded"] == 0


def test_proxy_requires_known_app(client):
    r = client.post("/v1/proxy/not-a-real-app", json={"path": "/x"})
    assert r.status_code == 404


def test_sitemap_seed_keeps_kind_and_expands(monkeypatch):
    """A sitemap seed must keep its kind through the claim, then expand into pages."""
    xml = ("<?xml version='1.0'?><urlset>"
           "<url><loc>https://a.example.com/one</loc></url>"
           "<url><loc>https://a.example.com/two</loc></url></urlset>")

    class FakeResp:
        status_code = 200
        text = xml
        content = xml.encode()
        headers = {"content-type": "application/xml"}
        encoding = "utf-8"

    class FakeClient:
        async def get(self, url, **kw):
            return FakeResp()

    jid = reader.create_job("ws", sitemap="https://a.example.com/sitemap.xml", max_pages=10)
    page = reader._next_pending(jid, 1)[0]
    assert page["kind"] == "sitemap"
    job = {"id": jid, "workspace_id": "ws", "seed_url": "https://a.example.com",
           "depth": 1, "max_pages": 10, "follow_links": True}
    out = asyncio.run(reader._expand_sitemap(FakeClient(), job, page["url"], jid))
    assert [u for u, _ in out] == ["https://a.example.com/one", "https://a.example.com/two"]
