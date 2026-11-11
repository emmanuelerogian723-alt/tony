"""The four sidebar surfaces must be real pages, in one order, not anchors."""


def test_every_sidebar_destination_is_a_page(client):
    for path in ("/catalog", "/integrations", "/connections", "/logs", "/playground"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "Tony" in r.text


def test_playground_nav_points_at_real_routes(client):
    html = client.get("/playground").text
    for href in ('href="/catalog"', 'href="/integrations"', 'href="/connections"',
                 'href="/logs"', 'href="/playground"'):
        assert href in html, href
    # the old dead links must be gone
    assert 'href="/#catalog"' not in html
    assert 'href="/app"' not in html


def test_pages_share_the_same_nav_order(client):
    for path in ("/catalog", "/integrations", "/connections", "/logs"):
        html = client.get(path).text
        order = [html.index(h) for h in ('href="/playground"', 'href="/catalog"',
                                         'href="/integrations"', 'href="/connections"',
                                         'href="/logs"')]
        assert order == sorted(order), path


def test_old_dashboard_is_still_reachable_as_an_alias(client):
    assert client.get("/connections/classic").status_code == 200


def test_icons_are_served_as_image_bytes(client):
    r = client.get("/v1/icon/github")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert len(r.content) > 100
    tile = client.get("/v1/icon/a-made-up-app")
    assert tile.status_code == 200 and "svg" in tile.headers["content-type"]


def test_api_exposes_icon_urls(client):
    app = client.get("/v1/apps?limit=1").json()["apps"][0]
    assert app["icon"].startswith("/v1/icon/")
    assert app["icon_tile"].startswith("/v1/icon-tile/")
