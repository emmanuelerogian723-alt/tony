import asyncio

from tony import power


def _client(client):
    return client


def test_greeting_answered_without_tools(client):
    r = client.post("/v1/agent", json={"goal": "hi", "max_steps": 2})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["answer"]
    assert d["steps"] == []
    assert d["engine"] in {"chat", "llm"}


def test_unmatched_goal_still_answers(client):
    r = client.post("/v1/agent", json={"goal": "what is an idempotency key?", "max_steps": 2})
    assert r.status_code == 200
    d = r.json()
    assert d["answer"] and len(d["answer"]) > 10


def test_direct_answer_falls_back_when_models_are_down(monkeypatch):
    async def no_models(*a, **k):
        return None
    monkeypatch.setattr(power, "_chat", no_models)
    text = asyncio.run(power._direct_answer("hi"))
    assert "here" in text.lower()
