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


def test_site_seed_is_a_page_not_a_sitemap(client):
    """A site crawl must fetch its seed as HTML, not try to expand it as XML."""
    jid = reader.create_job("ws", site="https://site.example.com", max_pages=4)
    page = reader._next_pending(jid, 1)[0]
    assert page["url"] == "https://site.example.com/"
    assert page["kind"] == "pending"


def test_brief_compresses_and_cites_sources():
    from tony.db import session
    from tony.models import ReadJob, ReadPage
    from tony import summarise

    body = ("The registry publishes zone data every day. Registry operators must sign the root zone. "
            "Zone signing protects the delegation chain. " * 12)
    with session() as s:
        job = ReadJob(workspace_id="ws_brief", status="done", seed_url="https://ex.example.com/", max_pages=5)
        s.add(job); s.flush()
        jid = job.id
        for i in range(3):
            s.add(ReadPage(job_id=jid, url=f"https://ex.example.com/{i}", status="done",
                           title=f"Page {i}", content=body, word_count=len(body.split())))
        s.flush()
    brief = summarise.build_brief(jid, "ws_brief", max_points=4)
    assert brief["pages_used"] == 3
    assert brief["points"] and brief["sources"]
    assert brief["compression"] > 5
    assert brief["themes"] and brief["themes"][0]["pages"] == 3  # identical content collapses
    md = summarise.brief_markdown(brief)
    assert "## Key points" in md and "https://ex.example.com/0" in md


def test_read_budget_is_reported(client):
    r = client.get("/v1/billing/me")
    assert r.status_code in (200, 401)
    if r.status_code == 200:
        body = r.json()
        assert "read_pages" in body.get("limits", {}) or "read_pages" in body.get("usage", {})


def test_throttled_page_is_requeued_not_failed(client, monkeypatch):
    """A 429 is the host asking for patience, not a dead URL: the page must come back."""
    class ThrottleResp:
        status_code = 429
        headers = {"retry-after": "0.01"}
        text = "slow down"
        content = b"slow down"
        encoding = "utf-8"

    class FakeClient:
        async def get(self, url, **kw):
            return ThrottleResp()

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    reader._HOST_COOLDOWN.clear()

    jid = reader.create_job("ws", urls=["https://slow.example.com/a"], max_pages=1)
    page = reader._next_pending(jid, 1)[0]
    job = {"id": jid, "workspace_id": "ws", "seed_url": "https://slow.example.com/a",
           "depth": 0, "max_pages": 1, "follow_links": False}
    out = asyncio.run(reader._fetch_one(FakeClient(), job, page))
    assert out.get("requeued") == 429
    again = reader._next_pending(jid, 1)[0]
    assert again["attempts"] == 1, "the requeue must be counted so it cannot loop forever"


def test_throttle_gives_up_only_after_the_retry_budget(client, monkeypatch):
    page = {"id": "p1", "url": "https://slow.example.com/a", "attempts": reader.THROTTLE_REQUEUES}
    jid = reader.create_job("ws", urls=["https://slow.example.com/b"], max_pages=1)
    page["id"] = reader._next_pending(jid, 1)[0]["id"]
    out = reader._requeue_throttled(page, 429)
    assert out == {"failed": 429}


def test_brief_themes_ignore_dates_and_keep_points_short():
    """A weblog archive must not theme itself around month names, and a point is one sentence."""
    from tony.db import session
    from tony.models import ReadJob, ReadPage
    from tony import summarise

    bodies = [
        "September 3, 2026 posted by Sarah. The Django Security Team shipped patched releases for the "
        "authentication backend, closing a session fixation hole in the password reset flow. "
        "Administrators should upgrade immediately to protect user accounts.",
        "September 18, 2026 posted by Tim. Contributor outreach grew sharply this quarter as the "
        "community team opened mentoring cohorts for first time contributors. New mentors joined "
        "from three regional conferences and the programme now covers twelve time zones.",
        "September 29, 2026 posted by Natalia. The foundation announced funding for the fellowship "
        "programme, which pays a full time fellow to manage releases, security reports and community "
        "support for the framework. Sponsors renewed their commitments for another year.",
    ]
    with session() as s:
        job = ReadJob(workspace_id="ws_brief2", status="done", seed_url="https://ex.example.com/", max_pages=5)
        s.add(job)
        s.flush()
        jid = job.id
        for i, body in enumerate(bodies):
            s.add(ReadPage(job_id=jid, url=f"https://ex.example.com/{i}", status="done",
                           title=f"Post {i}", content=body, word_count=len(body.split())))
        s.flush()

    brief = summarise.build_brief(jid, "ws_brief2", max_points=6)
    labels = " ".join(t["theme"].lower() for t in brief["themes"])
    assert "september" not in labels, labels
    assert "posted" not in labels, labels
    for point in brief["points"]:
        assert len(point["point"]) <= 262, point["point"]
        assert point["point"].count(". ") <= 1, point["point"]


def test_brief_drops_site_furniture_repeated_on_every_page():
    """A sponsor strip on every page must never become a theme or a key point."""
    sponsor = ("Skip to main content Read the Docs supports Django and hosts documentation for open "
               "and closed source projects. Get live previews for every docs pull request. ")
    bodies = [
        sponsor + "The security team shipped patched releases closing a session fixation hole in the "
                  "password reset flow. Administrators should upgrade immediately.",
        sponsor + "Contributor outreach grew as the community team opened mentoring cohorts for first "
                  "time contributors across three regional conferences.",
        sponsor + "The foundation announced funding for the fellowship programme, which pays a full time "
                  "fellow to manage releases and security reports for the framework.",
        sponsor + "Release notes describe a new database backend option and a faster migration planner "
                  "for large projects with many tables.",
    ]
    from tony.db import session
    from tony.models import ReadJob, ReadPage
    from tony import summarise

    with session() as s:
        job = ReadJob(workspace_id="ws_brief3", status="done", seed_url="https://ex.example.com/", max_pages=6)
        s.add(job)
        s.flush()
        jid = job.id
        for i, body in enumerate(bodies):
            s.add(ReadPage(job_id=jid, url=f"https://ex.example.com/{i}", status="done",
                           title=f"Post {i}", content=body, word_count=len(body.split())))
        s.flush()

    brief = summarise.build_brief(jid, "ws_brief3", max_points=6)
    haystack = " ".join([t["theme"] for t in brief["themes"]] + [p["point"] for p in brief["points"]]).lower()
    assert "skip to main content" not in haystack
    assert "live previews for every docs" not in haystack
    assert len(brief["points"]) >= 3
