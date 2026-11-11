# Universal engine (file uploads, typed actions, ranked discovery, safe execution)

Four modules were added without changing existing behaviour. Every existing
route, manifest and test keeps working; the new pieces are additive.

## 1. File engine — `tony/files.py`, routes in `tony/files_api.py`

Presigned uploads, file handles, MIME/size validation, sha256 dedupe, signed
download links, expiry and tenant isolation by workspace.

    POST /v1/files/upload        start an upload (declares size + mime)
    PUT  /v1/files/{id}/content  stream the bytes
    POST /v1/files/direct        one-shot upload for small files
    GET  /v1/files               list my files
    GET  /v1/files/{id}          metadata
    GET  /v1/files/{id}/url      time-limited download link
    DELETE /v1/files/{id}

Handles look like `file_ab12cd34...` and can be passed directly into typed
actions, so an agent never builds a multipart request by hand.

## 2. Typed connectors — `tony/connectors.py`

Curated actions that take human arguments instead of raw HTTP:

* `gmail.send_email` builds the MIME body, attachments included (file handles).
* `youtube.upload_video` uploads from a file handle.
* `slack.post_message`, `github.create_issue`, `linkedin.create_post`,
  `facebook.create_post`, `googlecalendar.create_event`.

Typed connectors are resolved before declarative manifest actions and are
indexed in search, so they win when the intent matches.

## 3. Ranked discovery — `tony/toolsearch.py`

Hybrid scoring over app and action text: token overlap, slug coverage, app
aliases (calendar to googlecalendar, mail to gmail), synonym expansion,
typo tolerance, name containment, rarity weighting, a penalty for catch-all
apps (api, proxy) and a boost for curated typed connectors. Called from
`GET /returns/actions?search=`; the old substring path remains the fallback.

## 4. Execution runtime — `tony/runtime.py`

* Failure classification: auth, permission, invalid_args, not_found, rate_limit,
  provider, network, unknown.
* Retry policy: read actions retry freely, writes only when idempotent.
* Idempotency keys claim a slot per workspace, so a repeated request replays
  the stored result instead of running twice.
* Per-provider concurrency limits and cooldowns after rate limits.

## Tests

`tests/test_files_engine.py`, `tests/test_toolsearch.py`,
`tests/test_runtime.py`, `tests/test_connectors.py`. Full suite: 207 passing.
