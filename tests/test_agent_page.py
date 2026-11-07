def test_console_has_agent_page():
    from tony.ui import dashboard_html
    html = dashboard_html()
    assert 'id="page-agent"' in html
    assert 'async function runAgent' in html
    assert 'Allow writes' in html
    assert "'/v1/agent'" in html or '"/v1/agent"' in html
