"""Every manifest must be valid and usable."""
from tony.catalog import catalog


def test_catalogue_loads_without_errors():
    assert catalog.errors == [], f"manifest errors: {catalog.errors}"
    assert len(catalog.apps) >= 40


def test_every_app_has_actions_and_metadata():
    for app in catalog.apps.values():
        assert app.actions, f"{app.slug} has no actions"
        assert app.name and app.description
        assert app.auth.type in {"none", "oauth2", "api_key", "bearer", "basic", "custom", "path"}, app.auth.type
        if app.auth.type == "oauth2":
            assert app.auth.authorize_url and app.auth.token_url, f"{app.slug} oauth endpoints missing"


def test_action_lookup_forms():
    assert catalog.find_action("github.list_repos") is not None
    assert catalog.find_action("github__list_repos") is not None
    assert catalog.find_action("github_list_repos") is not None
    assert catalog.find_action("list_repos") is not None
    assert catalog.find_action("nope.nope") is None


def test_no_duplicate_action_names_within_app():
    for app in catalog.apps.values():
        slugs = [a.slug for a in app.actions]
        assert len(slugs) == len(set(slugs)), app.slug


def test_search_and_categories():
    assert catalog.search("bitcoin") != []
    assert "Developer" in catalog.categories()
    assert catalog.stats()["actions"] > 100
