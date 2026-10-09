# ADR-0012: Early-access gate

- Status: Accepted
- Date: 2026-10-02

## Context

EVAC (and its sibling DIAL, formerly PET) go onto a public server under their real domain before they
are ready for everyone. Until then the whole site must be behind a simple shared password — including the
first-run wizard, which would otherwise let the first visitor create the instance admin.

## Decision

An application-level gate, configured by environment variables, identical in EVAC and DIAL:

| Variable | Default | Meaning |
|---|---|---|
| `EVAC_EARLY_ACCESS_PASSWORD` | empty (off) | shared access password |
| `EVAC_EARLY_ACCESS_DAYS` | 30 | how long a browser stays unlocked |
| `EVAC_EARLY_ACCESS_MESSAGE` | built-in text | text on the gate page |

- Middleware (`apps.core.early_access`) sends visitors without a valid gate cookie to `/early-access/`
  (HTML) or answers `401` (API). WebSockets get the same check in an ASGI wrapper (close code 4401).
- The cookie is signed with `SECRET_KEY` and contains an HMAC fingerprint of the current password:
  changing the password locks every browser out again; nothing about the password is readable from it.
  HttpOnly, SameSite=Lax, Secure on HTTPS.
- Password comparison is constant-time; the gate form is rate-limited (10 POST/min/IP) and attempts are
  logged on `evac.security`.
- **Not gated**, because they carry their own secret or must work for infrastructure: static files,
  `/healthz`, `/readyz`, `/metrics` (protect with `EVAC_METRICS_TOKEN`), signed inbound webhooks, and
  requests with an `evac_` service token (an invalid token is rejected by the API anyway).
- The gate is a barrier in front of the normal login, not an account system.

## Alternatives considered

- HTTP Basic Auth at the reverse proxy: zero code, but it also blocks webhooks, health checks and
  WebSockets of screens unless every exception is maintained in proxy config on each server, the browser
  dialog cannot be styled or explained, and there is no "log out". Still a valid extra layer for operators
  who prefer it.
- IP allowlists: event teams work from changing networks.

## Consequences

- Screens authenticate with device tokens: `/player/` and the screen WebSocket `/ws/screen/` are exempt
  from the gate (ADR-0013), like `/prov/` for phones in DIAL.
- DIAL implements the same contract (variable names prefixed `DIAL_`).
