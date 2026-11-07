def test_landing_renders_numbers_and_fonts(client):
    html = client.get("/").text
    assert "Instrument Serif" in html and "JetBrains Mono" in html
    assert "__APPS__" not in html and "__PRICING__" not in html
    assert "hands" in html
    assert html.count('class="tier') == 3
