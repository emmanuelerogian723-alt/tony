# API reference

Base URL: your Tony instance (`http://localhost:8000` in development).
Auth: `Authorization: Bearer tk_…` or `X-API-Key: tk_…`. Interactive docs at `/docs`.

## Catalogue

### `GET /v1/apps`
Query: `search`, `category`.

```json
{"apps": [{"slug": "github", "name": "GitHub", "category": "Developer",
           "auth": "oauth2", "actions": 8, "verified": false,
           "connected": true}], "total": 65}
```

### `GET /v1/apps/{slug}`
Full manifest including the action list and JSON-Schema parameters.

### `GET /v1/actions?search=&app=`
Flat list of every action.

### `GET /v1/tools?format=openai|anthropic|mcp`
Tool schemas for the major agent runtimes.

## Accounts

### `POST /v1/connections/{app}/start`
```json
{"entity_id": "user_42", "redirect_after": "/app?connected=github"}
```
Returns `{"authorization_url": "https://…"}`. Send the user there; the callback stores the
credentials encrypted and redirects back.

### `POST /v1/connections/{app}/key`
For API-key apps: `{"entity_id": "user_42", "credentials": {"api_key": "…"}, "label": "work"}`.

### `GET /v1/connections?entity_id=user_42`
Lists connected accounts — never returns secret values, only scopes, labels and expiry.

### `DELETE /v1/connections/{app}?entity_id=user_42`
Revokes and deletes the stored credentials.

## Execution

### `POST /v1/execute`
```json
{"action": "github.list_repos", "entity_id": "user_42",
 "args": {"per_page": 5}, "dry_run": false, "approved": false}
```

`dry_run: true` returns the exact URL/query/body without sending anything — handy for tests
and for showing users what an agent is about to do.

Read actions run immediately. Write and destructive actions return HTTP 202 with a preview
and a `run_id`; approve with:

### `POST /v1/runs/{run_id}/approve`
Runs the stored call and returns the same shape as `/v1/execute`.

### `GET /v1/runs?limit=50&entity_id=&app=`
Audit log: status, latency, bytes, character budget used, error detail.

## MCP

`POST /mcp` speaks JSON-RPC 2.0 — `initialize`, `tools/list`, `tools/call`, `ping`.
Tool names are `app__action`, e.g. `github__list_repos`. Point Claude Desktop, Cursor or any
MCP client at `<base>/mcp` with an `Authorization: Bearer` header.

## Triggers

```json
POST /v1/triggers
{"app": "github", "action": "search_issues", "args": {"q": "is:open label:bug"},
 "entity_id": "user_42", "interval_seconds": 300,
 "webhook_url": "https://yourapp.com/hooks/tony"}
```
Tony polls on the interval, compares a content hash, and POSTs a signed payload
(`X-Tony-Signature: sha256=…`) only when something changed.

## Admin

`POST /v1/workspaces` (requires `TONY_ADMIN_TOKEN`) creates a workspace and returns its key
once. `POST /v1/workspaces/{id}/keys` mints additional keys.
