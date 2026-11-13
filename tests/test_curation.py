"""One honest entry per product, and no invented apps in the count."""
import pytest

from tony import curation
from tony.catalog import catalog


def test_the_catalogue_only_counts_apps_tony_can_call():
    stats = catalog.stats()
    assert stats["callable_apps"] >= 2000
    assert stats["callable_apps"] < stats["catalogue_total"], "the count is still padded"
    assert stats["apps"] == stats["callable_apps"] + stats["directory_apps"] + stats["placeholder_apps"]


def test_non_api_exports_are_not_presented_as_apps():
    """The Home Assistant export was 1,172 device integrations ('Yi', 'Baf', 'Ads')."""
    assert "yi" not in catalog.apps and "baf" not in catalog.apps
    left = [a for a in catalog.apps.values() if a.source == "homeassistant"]
    # the only row that may survive is Tony's own protected proxy entry
    assert all(a.slug in curation.PLATFORM_SLUGS for a in left), [a.slug for a in left]


def test_a_generic_label_is_never_a_product():
    class S:
        slug = "x"
        name = "API V1"
        source = "openapi"
        base_url = ""
        actions = []

    assert curation.is_junk(S())


def test_a_row_with_a_real_endpoint_is_never_junk():
    class S:
        slug = "adyen-accountservice"
        name = "Account Service"
        source = "openapi"
        base_url = "https://checkout-test.adyen.com"
        actions = []

    assert not curation.is_junk(S())


def test_duplicates_of_one_product_collapse_to_one_entry():
    names = [a.name.lower() for a in catalog.apps.values()]
    for duo in (("google_calendar", "google-calendar"), ("gmail", "google-mail")):
        live = [s for s in duo if s in catalog.apps]
        assert len(live) == 1, f"both {duo} still presented"


def test_a_merged_slug_still_resolves():
    """Old links, saved connections and agent output must never 404."""
    merged = catalog.curation.merged
    assert merged, "nothing was merged, so this pins nothing"
    dup, winner = next(iter(merged.items()))
    assert catalog.resolve(dup).slug == winner
    assert catalog.resolve("google-mail").slug == "gmail"


def test_mcp_apps_become_one_click_sign_in():
    """A vendor MCP server registers Tony itself, so no client id or secret is needed."""
    mcp = catalog.mcp
    assert len(mcp) >= 5
    attio = catalog.get("attio")
    assert attio.auth.registration_url.startswith("https://")
    assert attio.mcp_url.startswith("https://mcp.")
    assert attio.auth.type == "oauth2"


def test_a_managed_provider_is_never_overwritten_by_mcp():
    """Slack and Google already have curated, working OAuth apps."""
    slack = catalog.get("slack")
    assert slack.auth.authorize_url.startswith("https://slack.com/oauth")
    assert not slack.auth.registration_url, "MCP overwrote a working managed OAuth app"
    cal = catalog.get("google_calendar")
    assert not cal.auth.registration_url


def test_platform_tools_survive_curation():
    assert catalog.find_action("proxy.request") is not None


def test_a_key_only_product_is_still_findable():
    # "connect confluence" must find the product even though it needs a host and a key
    assert catalog.search("confluence")
