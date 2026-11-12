"""Icons, counts, credentials vocabulary and the filters the assistant promises."""


def test_icon_route_always_returns_an_image(client):
    for slug in ("slack", "openai", "linkedin", "sendgrid", "twilio", "groq",
                 "mondaydotcom", "totally_unknown_app"):
        r = client.get(f"/v1/icon/{slug}")
        assert r.status_code == 200, slug
        assert r.headers["content-type"].startswith("image/"), slug
        assert len(r.content) > 60, slug


def test_local_mark_is_visible_on_a_tile():
    from tony import icons

    path = icons.local_mark("slack")
    assert path is not None
    svg = icons.wrap_mark(path.read_text(), "slack").decode()
    assert "<rect" in svg            # a tile behind the mark
    assert 'fill="#F3F0E9"' not in svg   # the invisible off-white fill is gone


def test_simpleicons_is_never_the_first_remote_call():
    from tony import icons
    from tony.catalog import catalog

    spec = catalog.get("slack")
    urls = icons.remote_candidates(spec, "slack")
    assert urls and "cdn.simpleicons.org" not in urls[0]


def test_counts_agree_everywhere(client):
    stats = client.get("/v1/stats").json()
    cov = client.get("/v1/coverage").json()
    assert cov["apps_total"] == stats["apps"]
    assert cov["registry_apps"] + cov["unregistered_apps"] == stats["apps"]


def test_coverage_states_the_real_oauth_split(client):
    cov = client.get("/v1/coverage").json()
    for key in ("oauth_one_click", "oauth_byo", "mcp_dcr", "api_key", "public"):
        assert key in cov
    assert cov["oauth_byo"] + cov["api_key"] + cov["public"] + cov["mcp_dcr"] <= cov["apps_total"]
    assert "one click" in cov["claim"]


def test_apps_auth_prefix_filter_works(client):
    d = client.get("/v1/apps", params={"q": "auth:none", "limit": 10}).json()
    assert d["total"] > 100
    assert all(a["auth"]["type"] == "none" or a["strategy"] == "public" for a in d["apps"])
    named = client.get("/v1/apps", params={"auth": "none", "limit": 5}).json()
    assert named["total"] == d["total"]


def test_actions_accepts_q(client):
    a = client.get("/v1/actions", params={"q": "send email", "limit": 5}).json()
    b = client.get("/v1/actions", params={"search": "send email", "limit": 5}).json()
    assert a["total"] == b["total"] and a["total"] > 0


def test_read_accepts_url_like_the_console_form(client):
    r = client.post("/v1/read", json={"url": "https://example.com", "max_pages": 1})
    assert r.status_code == 200, r.text
    assert r.json()["job_id"]


def test_read_accepts_seed_too(client):
    r = client.post("/v1/read", json={"seed": "https://example.com", "max_pages": 1})
    assert r.status_code == 200, r.text
