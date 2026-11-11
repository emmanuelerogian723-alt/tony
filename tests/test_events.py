import hashlib
import hmac
import json
import time

from tony import events


def _github_sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_github_signature_verifies_and_rejects():
    body = b'{"action":"opened"}'
    secret = "whsec_test"
    ok, why = events.verify("github", secret, body, {"x-hub-signature-256": _github_sig(secret, body)})
    assert ok, why
    ok, why = events.verify("github", secret, body, {"x-hub-signature-256": "sha256=deadbeef"})
    assert not ok and "mismatch" in why


def test_stripe_and_slack_signatures():
    body = b'{"id":"evt_1"}'
    ts = str(int(time.time()))
    secret = "whsec_stripe"
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    assert events.verify("stripe", secret, body, {"stripe-signature": f"t={ts},v1={sig}"})[0]

    secret = "slack_secret"
    sig = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:".encode() + body, hashlib.sha256).hexdigest()
    assert events.verify("slack", secret, body,
                         {"x-slack-signature": sig, "x-slack-request-timestamp": ts})[0]
    assert not events.verify("slack", secret, body,
                             {"x-slack-signature": sig, "x-slack-request-timestamp": "1"})[0]


def test_event_type_and_dedupe_extraction():
    assert events.event_type_of({"x-github-event": "pull_request"}, {"action": "opened"}) == \
        "pull_request.opened"
    assert events.event_type_of({}, {"type": "invoice.paid"}) == "invoice.paid"
    assert events.dedupe_key_of({"x-github-delivery": "abc"}, {}, b"{}") == "abc"
    assert events.dedupe_key_of({}, {"id": "evt_9"}, b"{}") == "evt_9"


def test_subscription_matching():
    assert events._matches("*", "anything")
    assert events._matches("pull_request", "pull_request.opened")
    assert events._matches("issues, push", "push")
    assert not events._matches("issues", "push")


def test_endpoint_ingest_dedupes_and_verifies(client):
    created = client.post("/v1/event-endpoints",
                          json={"source": "github", "scheme": "github"}).json()
    secret, url = created["secret"], created["url"]
    path = url.split("onrender.com")[-1] if "onrender.com" in url else f"/v1/hooks/{created['id']}"
    body = json.dumps({"action": "opened", "number": 12}).encode()

    bad = client.post(path, content=body, headers={"x-hub-signature-256": "sha256=00",
                                                   "x-github-event": "pull_request"})
    assert bad.status_code == 401

    headers = {"x-hub-signature-256": _github_sig(secret, body),
               "x-github-event": "pull_request", "x-github-delivery": "d-1",
               "content-type": "application/json"}
    first = client.post(path, content=body, headers=headers)
    assert first.status_code == 200 and first.json()["type"] == "pull_request.opened"

    second = client.post(path, content=body, headers=headers)
    assert second.json()["duplicate"] is True
    assert second.json()["event_id"] == first.json()["event_id"]

    shown = client.get(f"/v1/events/{first.json()['event_id']}").json()
    assert shown["type"] == "pull_request.opened"
    assert shown["signature_ok"] is True


def test_route_fans_out_to_subscription(client, monkeypatch):
    created = client.post("/v1/event-endpoints",
                          json={"source": "stripe", "scheme": "none"}).json()
    path = f"/v1/hooks/{created['id']}"
    sub = client.post("/v1/subscriptions",
                      json={"source": "stripe", "events": "invoice.paid",
                            "target_url": "https://example.com/hook"}).json()
    assert sub["fire_count"] == 0

    delivered = []

    async def fake_deliver(row, event_id, body, headers):
        delivered.append((row.id, json.loads(body)))
        return True

    monkeypatch.setattr(events, "deliver", fake_deliver)

    body = json.dumps({"id": "evt_route_1", "type": "invoice.paid"}).encode()
    ev = client.post(path, content=body, headers={"content-type": "application/json"}).json()
    fired = client.post(f"/v1/events/{ev['event_id']}/replay").json()

    assert fired["fired"] == 1
    assert delivered and delivered[0][1]["body"]["id"] == "evt_route_1"
    assert delivered[0][1]["type"] == "invoice.paid"


def test_subscription_starts_a_flow(client, monkeypatch):
    created = client.post("/v1/event-endpoints",
                          json={"source": "shopify", "scheme": "none"}).json()
    client.post("/v1/subscriptions", json={
        "source": "shopify", "events": "orders.create",
        "flow_spec": {"name": "on-order", "steps": [
            {"kind": "set", "save_as": "order", "value": "{{event.body.id}}"},
        ]},
    })
    body = json.dumps({"id": "ord_77", "event_type": "orders.create"}).encode()
    ev = client.post(f"/v1/hooks/{created['id']}", content=body,
                     headers={"content-type": "application/json"}).json()
    client.post(f"/v1/events/{ev['event_id']}/replay")

    listing = client.get("/v1/flows").json()["flows"]
    assert any(f["origin"] == f"event:{ev['event_id']}" for f in listing)


def test_ingest_rejects_unknown_endpoint(client):
    assert client.post("/v1/hooks/does-not-exist", content=b"{}").status_code == 404
