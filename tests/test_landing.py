import re


def test_landing_renders_live_numbers_and_the_console_mark(client):
    html = client.get("/").text
    # typography contract for the rebuilt page
    assert "Inter+Tight" in html and "JetBrains+Mono" in html
    # no unrendered template tokens
    assert not re.findall(r"__[A-Z_]+__", html)
    # the console's own mark is embedded (open ring plus orange core), not a stand-in
    assert "#E2542B" in html and "stroke-dasharray=\"62 19.7\"" in html
    assert len(re.findall(r'class="tier[ "]', html)) == 3
    # true black, not a tinted dark
    assert "background:#000" in html


def test_landing_names_real_endpoints_not_slogans(client):
    html = client.get("/").text
    assert "/v1/connect-links" in html and "/v1/execute" in html
    assert "PKCE" in html
    # the hosted consent experience is shown on the page
    assert "never sees your password" in html


def test_landing_uses_the_console_icon_files(client):
    html = client.get("/").text
    assert "/static/brand/tony-mark.svg" in html


def test_hero_uses_real_provider_icons(client):
    import re
    from pathlib import Path

    html = client.get("/").text
    slugs = set(re.findall(r"/static/brand/icons/([a-z]+)\.svg", html))
    assert {"github", "gmail", "slack", "notion", "stripe"} <= slugs
    assert len(slugs) >= 12
    icons = Path(__file__).resolve().parents[1] / "tony" / "static" / "brand" / "icons"
    for slug in slugs:
        p = icons / f"{slug}.svg"
        assert p.exists(), f"missing icon asset for {slug}"
        assert "<path" in p.read_text(), f"{slug} is not a real vector icon"


def test_every_icon_is_served(client):
    for slug in ("github", "gmail", "notion", "figma"):
        r = client.get(f"/static/brand/icons/{slug}.svg")
        assert r.status_code == 200 and "svg" in r.headers.get("content-type", "")


def test_provider_setup_page_is_owner_only(client):
    assert client.get("/providers", follow_redirects=False).status_code in (307, 303)
    client.post("/v1/account/signup", json={"email": "prov@example.com", "password": "Tony-tour-9271"})
    html = client.get("/providers").text
    assert "Hosted OAuth providers" in html
    assert "/v1/account/providers" in html
    assert "/oauth/callback" in html
