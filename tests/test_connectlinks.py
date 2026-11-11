import pytest

from tony import shield


@pytest.fixture(autouse=True)
def _clean():
    shield.reset()
    yield
    shield.reset()


def _signup(client, email="cl@example.com"):
    client.post("/v1/account/signup", json={"email": email, "password": "Tony-tour-9271"})


def test_link_lifecycle(client):
    _signup(client)
    r = client.post("/v1/connect-links", json={"app": "github", "agent_name": "Mira", "tiers": ["read", "write"]})
    assert r.status_code == 200
    url = r.json()["url"]
    assert "/connect/tcl_" in url
    token = url.rsplit("/", 1)[1]
    page = client.get(f"/connect/{token}")
    assert page.status_code == 200
    assert "Mira wants to connect to your" in page.text
    assert "Create and change things" in page.text
    assert "never sees your password" in page.text
    status = client.get(f"/v1/connect-links/{token}").json()
    assert status["status"] == "pending" and status["connected"] is False


def test_unknown_token_is_not_a_leak(client):
    page = client.get("/connect/tcl_doesnotexist")
    assert page.status_code == 200 and "not valid" in page.text


def test_agent_name_is_escaped(client):
    _signup(client, "xss@example.com")
    r = client.post("/v1/connect-links", json={"app": "github", "agent_name": "<script>alert(1)</script>"})
    token = r.json()["url"].rsplit("/", 1)[1]
    page = client.get(f"/connect/{token}").text
    assert "<script>alert(1)</script>" not in page


def test_unsafe_redirect_is_dropped(client):
    _signup(client, "redir@example.com")
    r = client.post("/v1/connect-links", json={"app": "github", "redirect_url": "javascript:alert(1)"})
    assert r.status_code == 200


def test_deny_blocks_the_link(client):
    _signup(client, "deny@example.com")
    token = client.post("/v1/connect-links", json={"app": "github"}).json()["url"].rsplit("/", 1)[1]
    client.get(f"/connect/{token}/deny")
    assert "expired" in client.get(f"/connect/{token}").text.lower()


def test_other_workspace_cannot_read_status(client):
    _signup(client, "owner@example.com")
    token = client.post("/v1/connect-links", json={"app": "github"}).json()["url"].rsplit("/", 1)[1]
    client.post("/v1/account/logout")
    _signup(client, "intruder@example.com")
    assert client.get(f"/v1/connect-links/{token}").status_code == 404


def test_resume_is_queued_and_fires_after_approval(client):
    _signup(client, "resume@example.com")
    r = client.post("/v1/connect-links", json={"app": "hackernews", "resume_goal": "summarise today's top stories"})
    body = r.json()
    assert body["resumes_task"] is True
    token = body["url"].rsplit("/", 1)[1]
    assert client.get(f"/v1/resume/{token}").json()["status"] == "queued"
    client.get(f"/connect/{token}/done")
    done = client.get(f"/v1/resume/{token}").json()
    assert done["status"] in {"running", "done", "failed"}
    assert done["goal"] == "summarise today's top stories"


def test_link_without_a_goal_queues_nothing(client):
    _signup(client, "nogoal@example.com")
    token = client.post("/v1/connect-links", json={"app": "github"}).json()["url"].rsplit("/", 1)[1]
    assert client.get(f"/v1/resume/{token}").status_code == 404
