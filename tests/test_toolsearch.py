"""Tool discovery must put the RIGHT action in the top results."""
import pytest

from tony.catalog import catalog
from tony.toolsearch import search_actions


def top(query, n=5):
    return [h["action"] for h in search_actions(catalog, query, limit=n)]


@pytest.mark.parametrize("query,expected_app", [
    ("send an email to my customer", "gmail"),
    ("email my boss the report", "gmail"),
    ("upload this video to youtube", "youtube"),
    ("post a message in slack", "slack"),
    ("create a github issue", "github"),
])
def test_right_app_ranks_high(query, expected_app):
    hits = top(query, 5)
    apps = [h.split(".")[0] for h in hits]
    assert expected_app in apps, f"{expected_app} missing from {hits}"


def test_email_beats_scim_noise():
    hits = top("send an email to my customer", 8)
    apps = [h.split(".")[0] for h in hits]
    assert apps[0] == "gmail" or "gmail" in apps[:2]


def test_verb_object_intent():
    facts = top("upload video", 5)
    assert any("upload" in f for f in facts), facts


def test_typo_tolerance():
    hits = top("upolad vidoe", 5)
    assert hits, "typo query returned nothing"


def test_empty_query_is_safe():
    assert search_actions(catalog, "", limit=5) == []


def test_scoring_is_deterministic():
    a = top("create calendar event", 5)
    b = top("create calendar event", 5)
    assert a == b
