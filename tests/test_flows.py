import json
from datetime import datetime, timedelta, timezone

from tony.db import session
from tony.flows import advance, render
from tony.flows import Flow


def test_render_keeps_types_and_walks_paths():
    ctx = {"event": {"body": {"n": 3, "list": [{"id": "a"}]}}, "steps": {"x": {"data": 7}}}
    assert render("{{event.body.n}}", ctx) == 3
    assert render("id-{{event.body.n}}", ctx) == "id-3"
    assert render("{{steps.x.data}}", ctx) == 7
    assert render("{{event.body.list[0].id}}", ctx) == "a"
    assert render(["{{event.body.n}}"], ctx) == [3]
    assert render("{{missing.path}}", ctx) is None


def test_flow_runs_set_steps_and_templates(client):
    created = client.post("/v1/flows", json={
        "name": "greet",
        "steps": [
            {"kind": "set", "save_as": "a", "value": "hello"},
            {"kind": "set", "save_as": "b", "value": "{{steps.a.data}} world"},
        ],
    }).json()
    assert created["status"] == "succeeded"
    assert [s["status"] for s in created["steps"]] == ["ok", "ok"]

    full = client.get(f"/v1/flows/{created['id']}").json()
    assert full["steps"][1]["result"] == "hello world"


def test_wait_step_parks_then_resumes(client):
    created = client.post("/v1/flows", json={
        "name": "later",
        "steps": [{"kind": "wait", "seconds": 3600},
                  {"kind": "set", "save_as": "done", "value": True}],
    }).json()
    assert created["status"] == "waiting"
    assert created["steps"][0]["status"] == "running"

    # pretend an hour passed
    with session() as s:
        flow = s.get(Flow, created["id"])
        flow.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    import asyncio
    asyncio.get_event_loop_policy()
    status = asyncio.run(advance(created["id"]))
    assert status == "succeeded"

    full = client.get(f"/v1/flows/{created['id']}").json()
    assert full["steps"][0]["status"] == "ok"
    assert full["steps"][1]["result"] is True


def test_unknown_action_lands_in_dlq_and_retry_is_clean(client):
    created = client.post("/v1/flows", json={
        "name": "bad",
        "steps": [{"kind": "action", "action": "nope.not_an_action"}],
    }).json()
    assert created["status"] == "dead"
    assert "Unknown action" in created["last_error"]

    dlq = client.get("/v1/flows/dlq").json()["dead"]
    assert any(f["id"] == created["id"] for f in dlq)

    retried = client.post(f"/v1/flows/{created['id']}/retry").json()
    assert retried["status"] == "dead"


def test_flow_cancel(client):
    created = client.post("/v1/flows", json={
        "name": "waiting", "steps": [{"kind": "wait", "seconds": 600}],
    }).json()
    cancelled = client.post(f"/v1/flows/{created['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"


def test_invalid_specs_are_rejected(client):
    assert client.post("/v1/flows", json={"steps": []}).status_code == 400
    assert client.post("/v1/flows", json={"steps": [{"kind": "action"}]}).status_code == 400
    assert client.post("/v1/flows", json={"steps": [{"kind": "wait", "seconds": "soon"}]}).status_code == 400
    assert client.post("/v1/flows", json={"steps": [{"kind": "teleport"}]}).status_code == 400
