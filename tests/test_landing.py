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
