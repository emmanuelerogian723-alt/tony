def test_landing_renders_numbers_and_fonts(client):
    html = client.get("/").text
    assert "Bricolage Grotesque" in html and "IBM Plex Mono" in html
    assert "__APPS__" not in html and "__PRICING__" not in html
    assert "executes" in html
    assert html.count('class="tier') == 3
    assert "2f6bff" in html  # the blue is part of the design contract
