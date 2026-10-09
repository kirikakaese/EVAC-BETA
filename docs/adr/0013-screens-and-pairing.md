# ADR-0013: Screens, pairing and device tokens

- Status: Accepted
- Date: 2026-10-09

## Context

Phase 1 needs screens (players in kiosk browsers, TVs, Raspberry Pis, OBS) that staff pair with a short
code or QR (brief §5.1), place in a venue/zone/room, group (§5.2), and watch (health dashboard, offline
alerts). Screens are unattended devices: they cannot log in, cannot type the early-access password and must
keep working when the server or the network is gone.

## Decision

- **Ownership**: a screen belongs to one **event** (the tenant root), like every other module object, so
  RBAC, audit, export and module switches work unchanged. It may point to a venue, zone and room of the
  event. Moving hardware to the next event = re-pair (one code, a minute of work).
- **Pairing**: the player `POST /player/api/pair/` gets a 6-character code (alphabet without 0/O/1/I/L),
  a random secret and the QR target `<EVAC_PUBLIC_URL>/screens/pair/?code=…`. It polls
  `POST /player/api/pair/<id>/` with header `X-Pairing-Secret`. A member with `screens.pair` claims the
  code in the portal or API; EVAC creates the screen (or re-pairs an existing one) and stores the new
  **device token** encrypted on the pairing request until the player picks it up — exactly once, then it is
  deleted. Codes expire after 30 minutes; old requests are purged hourly.
- **Device token**: `evacscreen_<32 random bytes>`, stored as SHA-256, shown nowhere, revocable; re-pairing
  replaces it. HTTP: `Authorization: Screen <token>`. WebSocket `/ws/screen/`: browsers cannot send headers
  and URLs end up in logs, so the token is the **first message** (`{"type": "auth", …}`), else close 4401
  after 5 s. Revocation closes open sockets (4401).
- **Realtime to screens**: a channel-layer group and a 50-message cache ring buffer per screen (WebSocket,
  SSE via `fetch` with the auth header, long-poll). Best effort; the player re-reads `/player/api/config/`
  after reconnecting.
- **Health**: heartbeats (default every 10 s, `general.heartbeat_seconds`) store a whitelisted report
  (version, resolution, orientation, uptime, slide, errors, memory, last sync, evac ack). Online ≤ 3
  heartbeats, stale until `screens.offline_after_seconds` (60), then offline. A beat task every 15 s detects
  transitions, emits `screen.offline` / `screen.online` webhooks + realtime and notifies screen managers.
- **Groups**: manual (pick screens) or dynamic (tags, venues, zones, rooms; manual picks stay members).
  `screen_group` is a registered scope kind, so roles can be limited to groups.
- `/player/` and `/ws/screen/` are exempt from the early-access gate (ADR-0012) and the first-run redirect;
  pairing endpoints are rate limited per IP.

## Consequences

- One event per screen keeps the permission model simple; instance-wide "screen fleets" across events would
  need a later extension of the model (screens could gain a nullable event).
- Tokens in the browser's storage are as safe as the kiosk device; revocation is one click.
- Evacuation (Phase 3) builds on the same channel with signed messages and LAN fallbacks (ADR-0003).

## Alternatives considered

- Screens as user accounts or service tokens: wrong lifecycle, wrong permissions, would show up in member
  lists and could be granted roles.
- Long-lived pairing codes typed into the player: needs a keyboard on the screen; the code-on-screen flow
  works with a remote or nothing at all.
