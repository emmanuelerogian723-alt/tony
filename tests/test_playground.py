"""The post-signup query page, the survey and the Agent Playground."""
import pytest


def test_query_is_recorded_and_matched(client):
    r = client.post("/v1/queries", json={"text": "send an email to my customer", "source": "signup"})
    assert r.status_code == 200
    d = r.json()
    assert d["action"] == "gmail.send_email", d
    assert d["confidence"] > 50
    assert d["app"]["slug"] == "gmail"
    assert d["needs_connection"] is True


def test_unmatched_query_still_saved(client):
    d = client.post("/v1/queries", json={"text": "xyzzy plugh quux", "source": "playground"}).json()
    assert d["id"]
    assert d["action"] is None


def test_listing_shows_what_people_asked(client):
    client.post("/v1/queries", json={"text": "upload this video to youtube", "source": "playground"})
    rows = client.get("/v1/queries?all=1").json()["queries"]
    assert any("youtube" in q["text"] for q in rows)
    assert any(q["action"] == "youtube.upload_video" for q in rows)


def test_survey_is_stored(client):
    assert client.post("/v1/survey", json={"how_found": "LLM search (ChatGPT, Claude, etc.)"}).json()["ok"]
    rows = client.get("/v1/queries?all=1").json()["queries"]
    assert any(q["source"] == "survey" for q in rows)


@pytest.mark.parametrize("path,needle", [
    ("/query", "What do you want Tony to do?"),
    ("/playground", "Agent Playground"),
    ("/welcome", "How did you hear about Tony?"),
])
def test_pages_render(client, path, needle):
    r = client.get(path)
    assert r.status_code == 200
    assert needle in r.text
    assert "<svg" in r.text          # the Tony mark is on every page
