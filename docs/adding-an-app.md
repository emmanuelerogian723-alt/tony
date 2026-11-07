# Adding an app

An app is one YAML file in `tony/apps/`. Tony validates every manifest at boot and refuses
to serve one that is malformed, so a bad manifest fails loudly instead of breaking a run.

Scaffold one:

```bash
tony new-app acme --name "Acme CRM"
```

## Shape of a manifest

```yaml
slug: acme                       # stable id used everywhere (snake_case)
name: Acme CRM                   # display name
category: Productivity           # Developer | Productivity | Communication | Social | Commerce | Data | AI | Other
description: Contacts, deals and notes.
docs: https://developers.acme.com
logo: https://cdn.simpleicons.org/acme/000000
verified: false                  # true only after you ran the actions against a live account

auth:
  type: oauth2                   # oauth2 | bearer | api_key | basic | path | none
  authorize_url: https://acme.com/oauth/authorize
  token_url: https://acme.com/oauth/token
  scopes: [contacts:read, deals:read]
  client_id_env: ACME_CLIENT_ID
  client_secret_env: ACME_CLIENT_SECRET
  pkce: true                     # adds S256 code challenge + verifier
  scope_separator: " "           # some providers want "," instead
  authorize_params:
    prompt: consent

actions:
  - slug: list_contacts
    name: List contacts
    description: Return contacts for the signed-in workspace, newest first.
    method: GET
    url: https://api.acme.com/v1/contacts
    params:
      limit: {type: integer, default: 25, minimum: 1, maximum: 100}
      search: {type: string, description: Free-text filter}
    required: []
    response:
      path: data.contacts         # dot path into the JSON body
      max_items: 25               # cap list length
      max_chars: 12000            # hard character budget for the model
    tier: read                    # read | write | destructive
```

## Rules that keep the catalogue trustworthy

1. **One action, one call.** No hidden multi-step flows — the agent should see what it runs.
2. **Always set a response budget.** `max_chars` defaults to 12000. Apps that return megabytes
   must set `path` and `max_items` so a single call cannot blow up an agent's context.
3. **Tier honestly.** Anything that sends, publishes, deletes or charges is `write` or
   `destructive`. Tony asks for approval on those before running.
4. **Never hardcode secrets.** Credentials come from `client_id_env` / `client_secret_env`
   or from the connected account. Manifests are public.
5. **Mark `verified: true` only after a live run.** Unverified manifests still work, but the
   UI and README report them separately.

## Parameter placement

| Placement | How to declare | Example |
|-----------|----------------|---------|
| Query string | default for `GET`/`DELETE` | `?limit=25` |
| JSON body | default for `POST`/`PUT`/`PATCH` | `{"title": "..."}` |
| URL path | put `{name}` in the URL | `/contacts/{id}` |
| Header | `in: header` on the param | `X-Acme-Version` |

Credentials can also fill URL placeholders: if the stored credential has `shop`, `{shop}` in
the URL is replaced automatically (used by Shopify, Twilio and Telegram).

## Auth types

| Type | What Tony sends |
|------|-----------------|
| `oauth2` | `Authorization: Bearer <access_token>`, refreshed automatically |
| `bearer` | `Authorization: Bearer <token>` from a connected account or `<APP>_TOKEN` |
| `api_key` | key in a header or query param (`in: header|query`, `name:`) |
| `basic` | `Authorization: Basic base64(user:pass)` |
| `path` | token substituted into the URL (`/bot{token}/…`) |
| `none` | public endpoints, no credentials needed |

Single-tenant installs can skip the connect flow entirely: set `<APP>_TOKEN` (or the env name
declared in the manifest) and actions run with that key.

## Local checks

```bash
python -m pytest tests/test_catalog.py -q     # validates every manifest
tony actions --app acme                       # your actions as Tony sees them
tony execute acme.list_contacts --dry-run     # exact URL/body Tony would send
tony execute acme.list_contacts               # real call
```

Then run the same call once with `--arg` values that match what a user would pass, and set
`verified: true` in the manifest when it returns real data.
