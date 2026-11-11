"""A plan that stalls on a bare id list must finish the job, not report missing data."""

import json


def _reply(content=None, tool_calls=None):
    msg = {"role": "assistant", "content": content or ""}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _call(name, args):
    return {"id": "c1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def test_agent_finishes_a_plan_that_stopped_on_ids(client, monkeypatch):
    """Turn 1 the model lists stories, turn 2 it gives up. Tony must fetch the detail anyway."""
    from tony import power

    seen = []

    async def fake_chat(messages, tools=None, temperature=0.2, fast=False):
        seen.append([m.get("role") for m in messages])
        if tools and len(seen) == 1:
            return _reply(tool_calls=[_call("hackernews__top_stories", {})])
        if tools:
            return _reply("I cannot provide the title because the details were not returned.")
        return _reply("Top story fetched with author and score from the tool results.")

    monkeypatch.setattr(power, "_chat", fake_chat)

    r = client.post("/v1/agent", json={"goal": "get the top hacker news story title and score",
                                       "apps": ["hackernews"], "max_steps": 4})
    assert r.status_code == 200
    d = r.json()
    actions = [s.get("action") for s in d["steps"]]
    assert "top_stories" in actions
    assert "story" in actions, f"plan stalled after {actions}"
    assert "cannot provide" not in d["answer"].lower()
