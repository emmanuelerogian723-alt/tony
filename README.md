# Tony

**Connect any app once. Let any agent act on it.**

Tony is an open-source integration gateway — the plumbing layer between AI agents and the
apps people actually use. Your users sign in to their own accounts, Tony stores the tokens
encrypted, and from that moment *any* model, script or MCP client can read real data and
take real actions through one small, predictable API.

```bash
pip install -r requirements.txt
export TONY_SECRET_KEY=$(openssl rand -hex 32)
uvicorn tony.main:app --reload
```

Open <http://localhost:8000> for the dashboard. No signup, no hosted account, no per-action bill.

---

## Why this exists

Hosted integration platforms solve a real problem, then charge per connected user and lock
the OAuth apps to their own client IDs. Tony takes the opposite position:

| | Hosted aggregator | **Tony** |
|---|---|---|
| Pricing | Per connected user, per month | **Free — self-hosted** |
| OAuth client | Theirs, shared and rate-limited | **Yours, per app** |
| Add a new app | Wait for a vendor release | **One YAML manifest** |
| Agent protocol | Proprietary SDK | **MCP + OpenAPI** |
| Data residency | Their cloud | **Your server** |
| Destructive actions | Trust the caller | **Approval queue + audit log** |

## What is in the box

- **9,877 apps / 22,107 actions** out of the box — the largest open integration
  catalogue you can self-host. It is built from four layers, and the UI labels every app
  with the layer it came from:

  | Layer | Apps | What you get |
  |---|---|---|
  | Curated | 65 | Hand-written, live-tested actions for the apps people ask for first |
  | OpenAPI | 2,329 | Real endpoints parsed from published specs, 5–10 actions each |
  | API proxy | 730 | Base URL + auth mode known, so any path can be called directly |
  | Directory | 4,730 | Every app in the open catalogues; connect with its API base + token |

  Layer is not a marketing detail — it tells you what works with zero setup. Curated and
  OpenAPI apps execute immediately; proxy apps need their documented host; directory apps
  need a base URL at connect time. `GET /v1/stats` reports the split as `by_tier`. 
- **OAuth 2.0 engine** with PKCE, automatic token refresh and per-provider client credentials.
- **Credential vault**: every token encrypted with Fernet before it touches the database.
- **Universal REST connector** — any API with a key or bearer token works on day one.
- **No-API fallback** — fetch a page, extract its readable text, or search the web.
- **MCP server** at `/mcp` (JSON-RPC 2.0) so Claude Desktop, Cursor or any MCP client sees
  every action as a tool.
- **OpenAI / Anthropic tool schemas** at `/v1/tools?fmt=openai|anthropic`.
- **Approval tiers**: `read` runs immediately, `write` and `destructive` need an explicit
  `approved: true` (or an approval in the dashboard).
- **Triggers**: poll any action, webhook your server (HMAC-signed) when the result changes.
- **Response budgeting**: path extraction, item caps and byte limits keep payloads small
  enough for a context window — with a `truncated` flag instead of silent loss.
- **SSRF guard** on every outbound request (including every read-job page and followed link),
  hashed API keys that can be scoped to named apps and to reads only, per-workspace isolation,
  HSTS/CSP on every response and visible `X-RateLimit-*` budget headers.

## Quickstart

### 1. Connect an app

```bash
curl -X POST "http://localhost:8000/v1/connections/github/start?entity_id=user_42"
# → { "authorization_url": "https://github.com/login/oauth/authorize?..." }
```

Send the user to that URL. Tony finishes the dance at `/oauth/callback`, stores the tokens
encrypted, and refreshes them before they expire.

### 2. Run an action

```bash
curl -X POST http://localhost:8000/v1/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer tk_live_..." \
  -d '{"action":"github.list_repos","entity_id":"user_42","args":{"per_page":5}}'
```

```json
{"ok":true,"status":200,"latency_ms":180,"data":[{"full_name":"acme/site", "...":"..."}]}
```

### 3. Point an agent at it

```json
{
  "mcpServers": {
    "tony": { "url": "https://your-tony.example.com/mcp" }
  }
}
```

## API at a glance

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/apps` | Paginated catalogue search (q, category, tier, limit, offset) |
| `GET` | `/v1/apps/{slug}` | One app with its full action list |
| `GET` | `/v1/actions` | Flat action search |
| `GET` | `/v1/tools?fmt=openai\|anthropic` | Tool schemas for function calling |
| `POST` | `/v1/connections/{app}/start` | Begin OAuth (or public access) |
| `POST` | `/v1/connections/{app}/key` | Store a pasted API key |
| `GET` | `/v1/connections` | Connected accounts (secrets redacted) |
| `POST` | `/v1/execute` | Run an action |
| `POST` | `/v1/runs/{id}/approve` | Approve a pending write |
| `GET` | `/v1/runs` | Audit log with latency and size |
| `POST` | `/v1/triggers` | Create a polling trigger + webhook |
| `POST` | `/mcp` | MCP JSON-RPC (initialize, tools/list, tools/call) |

Full OpenAPI: `/docs`.

## Adding an app

One file, `tony/apps/<slug>.yaml`:

```yaml
slug: weather
name: Weather
category: Data
description: Current conditions for a coordinate.
docs: https://open-meteo.com/en/docs
logo: https://cdn.simpleicons.org/openstreetmap/7EBC6F
auth:
  type: none            # none | oauth2 | api_key | bearer | basic | custom | path
actions:
  - slug: current
    name: Current weather
    description: Temperature and wind right now.
    method: GET
    url: https://api.open-meteo.com/v1/forecast
    params:
      latitude: {type: number, required: true}
      longitude: {type: number, required: true}
      current: {type: string, default: "temperature_2m,wind_speed_10m"}
```

Restart Tony and the app is live in the dashboard, the REST API, and the MCP tool list.
See [docs/adding-an-app.md](docs/adding-an-app.md) for the full manifest reference.

## Verified vs. untested manifests

Manifests carry `verified: true` only when the author has called them against the real
service. The rest are wired to documented endpoints but have not been exercised with live
credentials — expect to adjust a field or two on first use. That flag is visible in the API
(`verified`), so your code can treat it as a hint, not a promise.

Currently verified live (no account required): Hacker News, CoinGecko, Wikipedia,
Open-Meteo, ExchangeRate.host, npm, PyPI, Hugging Face, Mastodon, Open Library,
World Bank, arXiv, NASA (DEMO_KEY), and the built-in web connector.

## Architecture

```
tony/
  apps/*.yaml      declarative app + action manifests (the catalogue)
  catalog.py       manifest loading + validation + lookup
  executor.py      request building, auth injection, retries, response shaping
  oauth.py         OAuth 2.0 / PKCE / token refresh / credential vault
  api.py           REST v1
  mcp.py           MCP JSON-RPC server
  triggers.py      polling triggers + signed webhooks
  ui.py            dashboard and landing page (server-rendered, no build step)
  models.py        workspace, entity, connection, run, trigger
```

Nothing app-specific lives in Python. If an integration breaks, you edit YAML.

## Deployment

- **Docker**: `docker build -t tony . && docker run -p 8000:8000 --env-file .env tony`
- **Render**: `render.yaml` is included; push and connect the repo.
- **Any VPS**: `uvicorn tony.main:app --host 0.0.0.0 --port 8000` behind nginx/Caddy.
- **Postgres**: set `DATABASE_URL`. SQLite is the default for local use.

Production checklist: set `TONY_SECRET_KEY`, set `TONY_ADMIN_TOKEN`, set `TONY_DEMO_OPEN=0`,
put HTTPS in front (OAuth callbacks require the exact public URL in `TONY_BASE_URL`).

## Security model

- Credentials are encrypted with Fernet (AES-128-CBC + HMAC) and never returned by the API.
- API keys are stored as SHA-256 hashes; only a 16-character prefix is kept for lookup.
- Outbound requests resolve DNS first and refuse private, loopback, link-local and
  cloud-metadata addresses.
- Write and destructive actions are tiered in the manifest and gated behind approval.
- Webhook deliveries are signed: `X-Tony-Signature: t=<ts>,v1=<hmac>` over `<ts>.<body>`.

See [docs/security.md](docs/security.md).

## Tests

```bash
python -m pytest tests/ -q      # 57 tests, no network required
```

Covers manifest validation, request building, auth injection, response budgeting,
SSRF protection, the REST surface, approvals, MCP handshake/tools, OAuth lifecycle and
the credential vault.

## SDKs

```python
from tony_sdk import Tony
t = Tony("http://localhost:8000", "tk_live_...")
t.execute("github.list_repos", entity_id="user_42", args={"per_page": 5})
```

`sdks/python/tony_sdk.py` (sync + async) and `sdks/js/tony.mjs` are dependency-free.

## Roadmap

- Webhook-sourced triggers for providers that push (Stripe, GitHub, Slack events)
- Response caching with per-action TTL
- Multi-region token sharding
- Manifest registry so `tony install <app>` fetches community apps

## License

Apache-2.0. Built by MUTYINT.

## The registry

`tony/registry/apps.jsonl` is the generated long tail: one JSON object per app, produced by
`scripts/build_registry.py` from open sources — APIs.guru's OpenAPI directory, Nango's
provider catalogue, Pipedream's app directory, Activepieces and n8n community nodes, and
Home Assistant integrations. `tony/apps/*.yaml` stays the curated, hand-written layer and
always wins when the slugs collide.

```bash
python scripts/build_registry.py            # rebuild from the live sources (~30s)
python -m tony.cli apps --tier actions      # see what works with zero setup
```

Why it is split this way: a catalogue that claims 7,000 integrations and delivers 200 real
ones is a demo. Tony ships all 9,877, but tells you which layer each app is in, so an agent
(or a human) never wonders why an action failed.
