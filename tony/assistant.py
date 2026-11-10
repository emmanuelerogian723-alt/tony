"""Tony's in-product expert.

A scoped assistant: it only knows Tony (the product, this workspace, these
actions), never general chit-chat. Answers come from a curated knowledge base
plus the caller's live state, so "how many runs do I have left?" is answered
with real numbers. Unknown questions are logged as gaps, and failing actions
are rolled up into a weekly fix list, which is how Tony learns.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .db import session
from .models import ActionRun, AssistantGap, CustomTool, User

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])

KB: list[dict[str, Any]] = [
    {
        "topic": "pricing",
        "keys": "price pricing cost plan plans subscription billing pay how much naira pro business free tier upgrade downgrade cancel refund annual yearly",
        "answer": (
            "Tony has three plans.\n\n"
            "*Free*: every app and every action, writes included. 5,000 runs a month, 15 connected accounts, "
            "5 end-user identities, 3 keys, 3 triggers, 5 sessions, 5 custom tools.\n"
            "*Pro* (₦7,500/month): 150,000 runs, 100 accounts, 50 identities, 25 keys and sessions, 25 custom tools.\n"
            "*Business* (₦25,000/month): 1,000,000 runs plus the top limits on everything.\n\n"
            "Every new account starts on a 14-day Pro trial, no card. Annual billing gives two months free. "
            "You can cancel from Console → Billing; the plan runs to the end of the period and your data stays."
        ),
    },
    {
        "topic": "usage",
        "keys": "usage runs left quota limit remaining how many i have used meter reset month",
        "answer": "usage:{usage}",
    },
    {
        "topic": "connect",
        "keys": "connect app account oauth sign in login authorize integration link add app key api key token credential",
        "answer": (
            "Open Console → Apps, pick the app, press *Connect*, and sign in on the provider's own page. "
            "Tony stores the token encrypted; you never paste a key for OAuth apps.\n\n"
            "If an app needs a token instead of OAuth, press Connect and Tony shows the exact field and where "
            "to find it. Self-hosted or internal services can be wrapped as a *custom tool* instead, which is "
            "usually faster than waiting for an official API."
        ),
    },
    {
        "topic": "keys",
        "keys": "api key keys tk_live bearer authenticate owner owner of key rotate revoke create secret",
        "answer": (
            "Your workspace keys live in Console → Keys. Every key is bound to your account and workspace, so "
            "the calls it makes, the runs it spends and the connections it reaches are yours alone. "
            "Create one per environment (server, staging), rotate by creating the new key then revoking the old "
            "one. Keys are shown once; Tony keeps only a hash."
        ),
    },
    {
        "topic": "agent_tokens",
        "keys": "agent token scoped key read only read-only permission permissions restrict narrow expiry expire ttl least privilege give an ai a key hand off delegate claude cursor sub agent",
        "answer": (
            "Mint a scoped agent token instead of sharing your workspace key:\n\n"
            "```\nPOST /v1/agent-tokens\n{\"name\":\"cursor\",\"apps\":[\"hackernews\",\"notion\"],"
            "\"tiers\":[\"read\"],\"ttl_days\":7}\n```\n\n"
            "It returns a token starting `tony_at_`. Send it as `Authorization: Bearer tony_at_...`; the same "
            "token works over REST, the agent and MCP. Tony refuses calls outside the grant before touching the "
            "app, and the refusal names what the token does allow. `apps` empty means every app, `tiers` defaults "
            "to read only, and the token dies on its own at `ttl_days`. An agent token cannot mint another token. "
            "Check your own scope with `GET /v1/agent-tokens/scopes`."
        ),
    },
    {
        "topic": "sessions",
        "keys": "session sessions per user end-user multi-tenant scope allowlist entity budget ttl x-tony-session",
        "answer": (
            "Sessions scope Tony to one of *your* end-users. Create one in Console → Sessions with an identity, "
            "an optional app allowlist, allowed tiers, a TTL and a run budget. Send the id as "
            "`X-Tony-Session` and the call cannot leave that lane: no other app, no higher tier, no extra runs. "
            "Your workspace key stays on your server; the session is what your users' requests carry."
        ),
    },
    {
        "topic": "custom_tools",
        "keys": "custom tool own api internal endpoint webhook http tool define my api private service",
        "answer": (
            "A custom tool turns any HTTPS endpoint into a first-class action. In Console → Tools (or "
            "`POST /v1/custom-tools`) give it a slug, method, URL with `{placeholders}`, headers, a body "
            "template and how it authenticates. Tony then exposes it as `custom.<slug>` with the same quota, "
            "the same approval gate on writes and the same tool-schema export as the catalogue. "
            "Use it for internal APIs, partner endpoints, or any app we do not list yet."
        ),
    },
    {
        "topic": "batch",
        "keys": "batch multiple actions many calls at once bulk parallel loop twenty",
        "answer": (
            "`POST /v1/batch` takes up to 20 calls and runs them in order, returning one result per call. "
            "Quota, approval gates and session scoping apply to each call exactly as if you had sent it alone. "
            "Use it for fan-out work like enriching a list of leads."
        ),
    },
    {
        "topic": "approval",
        "keys": "approval approve write destructive pending_approval gate delete send post safety confirm",
        "answer": (
            "Anything that writes stops and asks. The first call returns `pending_approval` with a run id and "
            "a preview; send the same call again with `approved: true` (or approve it in Console → Runs) and it "
            "executes. Reads never wait. If you want zero prompts on a trusted agent, set "
            "`TONY_REQUIRE_APPROVAL=0` on your own deployment, which is a decision you own."
        ),
    },
    {
        "topic": "mcp",
        "keys": "mcp claude cursor desktop model context protocol server tools connect ai ide endpoint stdio",
        "answer": (
            "Tony is an MCP server. Add `https://tony-7su0.onrender.com/mcp` as a streamable HTTP MCP server "
            "in Claude Desktop, Cursor or any MCP client; for stdio-only clients use the bundled bridge "
            "(`python mcp_bridge/tony_mcp.py`). Tools are named `app__action`, and the server also exposes "
            "prompts (`connect_app`, `safe_write`, `weekly_digest`) and resources (`tony://meta`, "
            "`tony://connections`, `tony://approvals`)."
        ),
    },
    {
        "topic": "sdks",
        "keys": "sdk python typescript javascript node go java library client package install pip npm",
        "answer": (
            "Official clients: Python (`pip install tony-gateway`), TypeScript/JavaScript, Go and Java, plus "
            "plain REST and MCP. Every SDK wraps the same four calls: `execute`, `batch`, `tools` and "
            "`connections`. Grab the source from /sdk in the console; each file is dependency-light on purpose "
            "so you can vendor it."
        ),
    },
    {
        "topic": "errors",
        "keys": "error errors 401 402 403 429 500 failing failed broken timeout not working unauthorized rate limit debug",
        "answer": (
            "The codes mean specific things: 401 is a missing or revoked key, 403 means the session is scoped "
            "to another app or tier, 402 means a quota is spent (the body names which one and the plan that "
            "raises it), 429 is the per-minute rate limit, 422 is an argument mismatch against the action "
            "schema, and 504 means the provider did not answer inside the execution deadline. "
            "Console → Runs shows the exact request, response and latency for every call."
        ),
    },
    {
        "topic": "triggers",
        "keys": "trigger triggers schedule cron polling webhook event recurring every background",
        "answer": (
            "Triggers run an action on an interval and post the result to your webhook, signed so you can "
            "verify it. Create one from Console → Triggers or `POST /v1/triggers` with the action, interval "
            "and webhook URL. Minimum interval is 60 seconds; each fire counts as a run."
        ),
    },
    {
        "topic": "security",
        "keys": "security secure encryption encrypted tokens storage privacy safe vault aes audit logs",
        "answer": (
            "Credentials are encrypted at rest with AES-256-GCM derived from `TONY_SECRET_KEY` and are only "
            "decrypted in memory for the call that needs them. API keys are stored as hashes. Every action is "
            "logged with its request, response, status and latency, and approvals are part of that record. "
            "Self-host and the data never leaves your infrastructure."
        ),
    },
    {
        "topic": "selfhost",
        "keys": "self host selfhost docker deploy render run locally install server own infrastructure mit license",
        "answer": (
            "Tony is MIT and self-hostable: `docker run -p 8000:8000 -v tony:/data -e TONY_SECRET_KEY=...`. "
            "SQLite by default, set `DATABASE_URL` for Postgres. One Render service plus a 4-minute ping is "
            "enough for a small team, which is what this deployment does."
        ),
    },
    {
        "topic": "revenue",
        "keys": "revenue share sharing earn money payout sell integration builder paid apps commission",
        "answer": (
            "Builders who publish a verified integration or a custom tool pack earn a share of the runs their "
            "work generates. Revenue share is tracked per workspace and shown in Console → Ecosystem with the "
            "month, amount, status and payout date. Ratings and security reviews are what qualify a listing for "
            "the paid pool."
        ),
    },
    {
        "topic": "ratings",
        "keys": "rating ratings review reviews stars community feedback vote quality rate app",
        "answer": (
            "Every app carries community ratings and a security verdict. Rate an app from its page "
            "(`POST /v1/ratings`) and Tony rolls the scores into the catalogue so the next developer sees which "
            "integrations actually work before connecting one."
        ),
    },
    {
        "topic": "catalogue",
        "keys": "apps app catalogue catalog how many tools actions available list search find discover",
        "answer": "catalogue:{catalogue}",
    },
    {
        "topic": "frameworks",
        "keys": "framework langchain llamaindex crewai autogen vercel ai sdk openai agents claude codex cursor plugin",
        "answer": (
            "Tony ships adapters for LangChain, LlamaIndex, CrewAI, the Vercel AI SDK, OpenAI Agents and "
            "Anthropic tool use, plus a CLI (`tony`) and an MCP server for Claude, Codex and Cursor. "
            "Because every action is a typed JSON schema, any framework that takes tool definitions works "
            "with no adapter at all."
        ),
    },
    {
        "topic": "start",
        "keys": "start started begin first quickstart hello how do i use setup get going tutorial",
        "answer": (
            "Four steps: create a key in Console → Keys, connect one app in Console → Apps, call an action with "
            "curl or an SDK, then wrap your end-users in sessions. The first useful call is usually a read:\n\n"
            "`curl -X POST https://tony-7su0.onrender.com/v1/execute -H \"Authorization: Bearer $TONY_KEY\" "
            "-H \"content-type: application/json\" -d '{\"action\":\"github.list_repos\"}'`"
        ),
    },
]

STOP = {"the", "a", "an", "is", "are", "do", "does", "i", "my", "to", "of", "how", "what", "can", "you",
        "and", "in", "on", "for", "with", "it", "this", "that", "tony", "me", "we", "have", "get"}


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_]+", (text or "").lower()) if w not in STOP and len(w) > 1}


def _score(q: set[str], keys: str) -> int:
    return len(q & _tokens(keys))


def _usage_ctx(ws: str) -> dict[str, Any]:
    from .billing import PLANS, summary

    b = summary(ws)
    plan = PLANS[b["plan_id"]]
    return {"plan": plan, "billing": b, "usage": b["usage"], "remaining": b["remaining"]}


def _render_answer(topic: str, ws: str) -> str:
    from .catalog import catalog

    entry = next(k for k in KB if k["topic"] == topic)
    text = entry["answer"]
    if "{usage}" in text:
        c = _usage_ctx(ws)
        used, cap = c["usage"].get("runs", 0), c["plan"]["runs"]
        pct = round(used / cap * 100) if cap else 0
        text = (
            f"You are on *{c['plan']['name']}*"
            + (f" ({c['billing']['status']}, {c['billing'].get('days_left', 0)} days left)" if c["billing"].get("days_left") else "")
            + f" and have used *{used:,} of {cap:,} runs* this month ({pct}%).\n\n"
            f"Connected accounts: {c['usage'].get('connected_accounts', 0)}/{c['plan']['connected_accounts']}. "
            f"Keys: {c['usage'].get('keys', 0)}/{c['plan']['keys']}. "
            f"Sessions: {c['usage'].get('sessions', 0)}/{c['plan']['sessions']}. "
            f"Custom tools: {c['usage'].get('custom_tools', 0)}/{c['plan']['custom_tools']}.\n\n"
            "Counters reset on the first of the month. Console → Billing shows the same meters live."
        )
    if "{catalogue}" in text:
        apps = len(catalog.apps)
        actions = sum(len(a.actions) for a in catalog.apps.values())
        text = (f"{apps:,} apps and {actions:,} typed actions right now, across curated, OpenAPI, proxy and "
                "directory layers. Search them from the landing page or `GET /v1/apps?q=`; each app tells you "
                "which layer it sits in, so a failure is never a mystery.")
    return text


def _suggestions(topic: str) -> list[str]:
    pool = {
        "pricing": ["What does Pro add?", "How do I cancel?", "How many runs are left?"],
        "usage": ["How do I raise my limit?", "Which app uses the most runs?"],
        "connect": ["Connect GitHub", "How do sessions work?"],
        "sessions": ["Create a session", "What tiers can I allow?"],
        "custom_tools": ["Show a custom tool example", "Can it write to my API?"],
        "agent_tokens": ["Give Cursor read-only access", "How long should a token last?"],
    }
    return pool.get(topic, ["How do I connect an app?", "What are my limits?", "How do I use this in Claude?"])


async def _llm_reply(question: str, grounding: str, history: list[dict[str, str]]) -> str | None:
    """Optional polish layer. Without a key the curated answer stands alone."""
    key = os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    if os.getenv("GROQ_API_KEY"):
        url, model, hdr = ("https://api.groq.com/openai/v1/chat/completions",
                           os.getenv("TONY_ASSISTANT_MODEL", "llama-3.3-70b-versatile"),
                           {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"})
    elif os.getenv("OPENAI_API_KEY"):
        url, model, hdr = ("https://api.openai.com/v1/chat/completions",
                           os.getenv("TONY_ASSISTANT_MODEL", "gpt-4o-mini"),
                           {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"})
    else:
        url, model, hdr = ("https://openrouter.ai/api/v1/chat/completions",
                           os.getenv("TONY_ASSISTANT_MODEL", "openai/gpt-4o-mini"),
                           {"Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}"})
    sys = ("You are Tony, the assistant inside the Tony console. You are genuinely useful: answer whatever the "
           "person actually needs, in their own terms. That includes Tony specifics (plans, quotas, connecting "
           "apps, keys, sessions, custom tools, batch, approvals, MCP, SDKs, triggers, errors, security, the agent "
           "runtime), hands-on developer work (HTTP, OAuth, auth flows, JSON, curl, Python, JavaScript, webhooks, "
           "data shapes), and everyday thinking and writing: explain a concept, draft a message or post, plan a "
           "piece of work, suggest an approach, review code, summarise something they paste. When the request can "
           "be done with an app action, name the exact app.action and the arguments you would pass, and offer to "
           "run it through the agent. Runtime facts you may rely on: POST /v1/agent plans and executes across "
           "apps; GET /v1/tools exports tool schemas; POST /v1/execute runs one action; /v1/proxy reaches raw "
           "endpoints; /v1/memory stores per-entity state; /v1/usage and /v1/audit report runs; MCP is at /mcp. "
           "Never invent console menus or settings pages: the console sections are Overview, Apps, Connections, "
           "Keys, Runs, Triggers, Billing and Docs. When asked how to give an AI limited access, describe "
           "POST /v1/agent-tokens and the tony_at_ bearer token, never a provider key. "
           "Prefer giving the answer over explaining that you cannot. If you truly do not know a specific fact, "
           "say so plainly and give the most useful next step. Be direct and concrete, up to 180 words when the "
           "question deserves it, no markdown headings. Ground Tony-specific claims in the reference text and "
           "point to Console → Docs when it does not cover something.")
    msgs = [{"role": "system", "content": sys},
            {"role": "user", "content": f"Reference:\n{grounding}\n\nQuestion: {question}"}]
    for turn in history[-4:]:
        if turn.get("role") in {"user", "assistant"} and turn.get("content"):
            msgs.insert(-1, {"role": turn["role"], "content": turn["content"][:600]})
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, headers={**hdr, "content-type": "application/json"},
                             json={"model": model, "messages": msgs, "temperature": 0.25, "max_tokens": 520})
            if r.status_code >= 400:
                return None
            return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


@router.post("")
async def ask(body: AskIn, request: Request) -> dict[str, Any]:
    from .auth import workspace_from_request

    ws, _ = workspace_from_request(request)
    q = _tokens(body.message)
    ranked = sorted((( _score(q, e["keys"]), i) for i, e in enumerate(KB)), reverse=True)
    best_score, idx = ranked[0]
    topic = KB[idx]["topic"] if best_score >= 1 else "fallback"

    curated = _render_answer(topic, ws) if topic != "fallback" else ""
    if topic == "fallback":
        with session() as s:
            s.add(AssistantGap(workspace_id=ws, question=body.message[:500]))
        grounding = (
            "No curated entry matched this question, so answer from your own knowledge as Tony's assistant. "
            "Be concrete, and say plainly when you are unsure. Runtime facts you may rely on: 7,923 apps and "
            "40,692 typed actions; POST /v1/agent to plan and execute; POST /v1/execute for a single action; "
            "GET /v1/tools for tool schemas; /mcp for MCP clients; POST /v1/agent-tokens gives an AI its own "
            "token with named apps, tiers (read/write/destructive) and ttl_days, sent as Bearer tony_at_... and "
            "enforced on every call; "
            "with app names, tiers and expiry; authenticator two-factor and Firebase sign-in on accounts; "
            "/v1/proxy for raw endpoints."
        )
    else:
        grounding = curated

    polished = await _llm_reply(body.message, grounding, body.history)
    answer = polished if (polished and len(polished) > 40) else (curated or (
        "I can help with Tony itself (plans, quotas, connecting apps, keys, sessions, custom tools, batch, "
        "approvals, MCP, SDKs, triggers, errors, security) and with general developer or writing work. "
        "Ask again in a moment, or open Console then Docs for the full reference."))

    return {
        "answer": answer,
        "topic": topic,
        "confidence": round(min(1.0, best_score / 3), 2),
        "grounded": topic != "fallback",
        "suggestions": _suggestions(topic if topic != "fallback" else "start"),
        "scope": "tony-only",
    }


@router.get("/insights")
def insights(request: Request) -> dict[str, Any]:
    """What Tony is bad at right now: unanswered questions and failing actions."""
    from .auth import workspace_from_request

    ws, _ = workspace_from_request(request)
    with session() as s:
        gaps = s.execute(
            select(AssistantGap.question, func.count(AssistantGap.id).label("n"))
            .where(AssistantGap.workspace_id == ws)
            .group_by(AssistantGap.question).order_by(func.count(AssistantGap.id).desc()).limit(10)
        ).all()
        fails = s.execute(
            select(ActionRun.app_slug, ActionRun.action_slug, func.count(ActionRun.id).label("n"))
            .where(ActionRun.workspace_id == ws, ActionRun.status == "error")
            .group_by(ActionRun.app_slug, ActionRun.action_slug)
            .order_by(func.count(ActionRun.id).desc()).limit(10)
        ).all()
        total = int(s.scalar(select(func.count(ActionRun.id)).where(ActionRun.workspace_id == ws)) or 0)
        errors = int(s.scalar(select(func.count(ActionRun.id)).where(
            ActionRun.workspace_id == ws, ActionRun.status == "error")) or 0)
    return {
        "questions_without_answers": [{"question": g[0], "count": g[1]} for g in gaps],
        "failing_actions": [{"app": f[0], "action": f[1], "failures": f[2],
                             "hint": "Check the connection first, then the action schema."} for f in fails],
        "success_rate": round((1 - errors / total) * 100, 1) if total else 100.0,
        "total_runs": total,
        "learned": "Gaps and failures feed the weekly fix list; each release ships fixes for the top three.",
    }
