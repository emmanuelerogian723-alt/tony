# Security model

Tony holds credentials for other people's apps. That sets the bar.

## Credentials at rest

* Connected-account secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using a 256-bit key
  derived by SHA-256 from `TONY_SECRET_KEY`.
* Only the encrypted blob is stored. Listing connections never returns a secret — the API
  shows a label, the scopes and the expiry.
* Rotating `TONY_SECRET_KEY` invalidates every stored credential on purpose: users reconnect.
  There is no silent fallback.
* `TONY_SECRET_KEY` must be 32+ random bytes. `tony keygen` prints one.

## Access control

* Every request needs a workspace API key. Keys are stored as SHA-256 hashes; the plaintext
  exists only in the response that created it.
* End-user data is partitioned by `entity_id` inside a workspace. One entity cannot read or
  execute against another entity's connected account.
* `TONY_ADMIN_TOKEN` is required to mint workspaces when the demo is closed. It is never
  accepted on data routes.

## Outbound calls

* **SSRF guard.** Every URL is resolved before the request; loopback, link-local, private
  ranges and cloud-metadata addresses are refused. Set `TONY_ALLOW_PRIVATE=1` only for a
  fully trusted single-tenant install talking to internal services.
* **Redirects** are followed by httpx but the final host is re-checked against the same rules.
* **No arbitrary method/URL from the client.** The only thing a caller can choose is which
  action runs and its declared parameters. The URL comes from a reviewed manifest.
* **Response budget.** Every response is capped (`max_chars`), so a malicious or broken API
  cannot be used to exhaust the caller's context window or memory.

## Approvals

* `read` actions run immediately.
* `write` and `destructive` actions return a preview and a `run_id`; nothing is sent until
  `POST /v1/runs/{run_id}/approve`. The stored call is immutable once queued.
* Set `TONY_REQUIRE_APPROVAL=0` only in a trusted automation context.

## Logging

* The audit log records the action, entity, status, latency and the character budget used.
* Authorization headers are redacted before anything is logged. Request bodies are stored for
  approvals; responses are trimmed to the same budget the model saw.

## Reporting

Found a hole? Email emmanuelerogian723@gmail.com with steps to reproduce. Please do not open a
public issue for an unpatched vulnerability.
