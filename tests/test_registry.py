"""The imported registry: scale, integrity and icon policy."""
from tony.catalog import catalog


def test_registry_reaches_seven_thousand_apps():
    stats = catalog.stats()
    assert stats["apps"] >= 7000, stats
    assert stats["actions"] >= 15000, stats


def test_every_app_is_actionable_and_searchable():
    for app in catalog.apps.values():
        assert app.actions, f"{app.slug} has no actions"
        assert app.name and app.description
        assert app.tier in {"actions", "proxy", "directory"}, app.tier
        assert app.auth.type in {"none", "oauth2", "api_key", "bearer", "basic", "custom", "path"}
        if app.auth.type == "oauth2":
            assert app.auth.authorize_url and app.auth.token_url, f"{app.slug} incomplete oauth"
        # a logo is either brand data or empty (the UI draws a monogram)
        assert app.logo == "" or app.logo.startswith(("http://", "https://"))


def test_search_is_token_based_and_fast():
    import time

    t0 = time.perf_counter()
    hits = catalog.search("send email", limit=5)
    elapsed = time.perf_counter() - t0
    assert hits, "expected matches for 'send email'"
    assert elapsed < 1.0, f"search too slow: {elapsed:.3f}s"


def test_tier_filtering_works():
    built_in = catalog.search("", tier="actions", limit=5)
    assert built_in and all(a.tier == "actions" for a in built_in)
    directory = catalog.search("", tier="directory", limit=5)
    assert directory and all(a.tier == "directory" for a in directory)


def test_pagination_is_stable():
    page1 = catalog.search("", limit=10, offset=0)
    page2 = catalog.search("", limit=10, offset=10)
    assert len(page1) == 10 and len(page2) == 10
    assert {a.slug for a in page1}.isdisjoint({a.slug for a in page2})
