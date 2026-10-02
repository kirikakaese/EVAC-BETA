# Webhooks extension

Generic webhooks in both directions, available at instance and event level. It is the reference
implementation of the extension framework.

## Outbound

Add **endpoints** under *Webhooks → Manage*: name, URL, active flag and the event types to receive (none
ticked = all). Each endpoint gets its own signing secret, shown once.

Every delivery is a `POST` with

```http
Content-Type: application/json
X-EVAC-Event: event.state_changed
X-EVAC-Delivery: 6f0c…                      (unique per delivery; use it to deduplicate)
X-EVAC-Signature: sha256=<hex HMAC-SHA256 of the raw body with the endpoint secret>

{"type": "event.state_changed", "sent_at": "2026-10-02T12:00:00+00:00", "event": "demo",
 "data": {"slug": "demo", "from": "setup", "to": "live"}}
```

Deliveries go through the durable outbox: a failed delivery (non-2xx, timeout) is retried with
exponential backoff (10 s, 20 s, 40 s … up to 1 h) until `EVAC_OUTBOX_MAX_ATTEMPTS`. The endpoint list
shows the last status and recent attempts. Instance-level endpoints receive events of **all** events;
event-level endpoints only their event's.

Event types available in phase 0 (more are registered by later modules, e.g. `evac.state_changed`,
`announcement.published`, `screen.offline`): `event.created`, `event.updated`, `event.state_changed`,
`member.added`, `member.removed`, `module.toggled`, `webhook.ping`. `GET /api/v1/registry/` lists all.

**Test connection** sends a signed `webhook.ping` to every active endpoint.

Verifying a signature (Python):

```python
import hashlib, hmac
expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
ok = hmac.compare_digest(expected, request.headers["X-EVAC-Signature"])
```

## Inbound

Enable the *Inbound webhooks* feature, generate the secret and send signed requests to the URL shown on the
settings page (see [EXTENSIONS.md](../EXTENSIONS.md)). Accepted payloads are stored (shown under
*Manage*) and announced inside EVAC with the Django signal
`extensions.webhooks.delivery.inbound_webhook` so modules can react (e.g. an evacuation trigger in phase 3).

## Settings

| Setting | Default | Meaning |
|---|---|---|
| Timeout (seconds) | 5 | per delivery |
| Verify TLS certificates | on | switch off only for self-signed receivers on a trusted LAN |

**Disconnect & purge** deletes the endpoints, their delivery history and stored inbound payloads.
