# API & CLI

EVAC exposes a REST API under `/api/v1/`, documented with OpenAPI:

- Schema: `/api/schema/` (YAML; committed as [`docs/api/openapi.yaml`](api/openapi.yaml), drift-checked in CI)
- Swagger UI: `/api/docs/` · ReDoc: `/api/redoc/` (both load their viewer from a CDN; the schema works offline)

## Authentication

- **Session** (the browser, with CSRF), or
- **Service token**: `Authorization: Bearer evac_…`. Create tokens under *Account → API tokens*, per event
  under *Event → API tokens*, with `POST /api/v1/tokens/` (logged-in session only) or
  `manage.py evac_token <email> <name> [--scopes …] [--event slug]`.

Tokens are stored hashed, can expire, can be bound to one event and never exceed the owner's rights.
**Scopes**: `<module>:read`, `<module>:write` (implies read), `<module>:*`, `*`; empty = all of the owner's
rights. Modules: `events`, `venues`, `audit`, … (each endpoint declares its module). A token minted in a
two-factor verified session may use *sensitive* permissions; other tokens may not.

## Endpoints

| Method & path | Purpose | Permission |
|---|---|---|
| `GET /health/` | status, version, mode | none |
| `GET /me/` | current user, token, events | authenticated |
| `GET /registry/` | plugins, modules, permissions, scope kinds, webhook events, extensions, data sources, widgets, channels, triggers | authenticated |
| `GET/POST /events/`, `GET/PATCH /events/<slug>/` | events (create: instance admin) | `events.view` / `events.manage` |
| `POST /events/<slug>/transition/` | lifecycle `{state, reason}` | `events.manage` (`events.delete` to archive) |
| `GET /events/<slug>/export/`, `POST /events/import/`, `POST /events/<slug>/clone/` | JSON export/import, clone | `events.manage` / instance admin |
| `/events/<slug>/roles/` | list/create/update/delete roles (`permissions` = patterns) | `events.members` (read), `events.roles` |
| `/events/<slug>/members/`, `POST …/members/assign/` | members; assign role by e-mail (invites unknown addresses), optional `scope_kind`/`scope_id` | `events.members` |
| `GET /events/<slug>/modules/`, `PATCH …/modules/<key>/` | module states; `{"event": true|false|null}` | `events.view` / `modules.manage` |
| `GET /events/<slug>/audit/` | audit entries (filters `action`, `drill`, `target_type`, search) | `audit.view` |
| `GET /audit/verify/` | verify the hash chain | instance admin |
| `/venues/`, `/buildings/`, `/floors/`, `/zones/`, `/rooms/` | venue structure (`?venue=<slug>`) | `venues.view` / `venues.manage` (scoped) |
| `/tokens/` | your tokens | authenticated |
| `GET /extensions/[?event=<slug>]` | extensions and status | instance admin / `extensions.manage` |
| `POST /extensions/<key>/<id>/webhook/` | inbound webhooks (HMAC) | signature |
| `/events/<slug>/screens/` | list/get/update/delete screens; `health` is `online`/`stale`/`offline`/`unpaired`/`revoked` | `screens.view` / `screens.manage` (scoped), token scope `screens` |
| `POST /events/<slug>/screens/pair/` | claim a pairing code `{code, name?, screen?, tags?}` (`screen` = re-pair) | `screens.pair` |
| `POST /events/<slug>/screens/<id>/revoke/` | revoke the device token | `screens.manage` |
| `/events/<slug>/screen-groups/` | manual and dynamic screen groups | `screens.view` / `screens.manage` |
| `/events/<slug>/themes/` | themes; `tokens` (only values set here), `resolved`, `version` (send it back on `PATCH` to detect concurrent edits) | `content.view` / `content.edit`, token scope `content` |
| `/events/<slug>/fonts/` | font families; `POST` multipart `upload` (+ `name`, `category`, `licence`, `subset`) | `content.view` / `content.edit` |
| `/events/<slug>/assets/` | asset library (`?kind=image`); `POST` multipart `upload` (+ `name`, `folder`); `urls` per variant | `content.view` / `content.edit` |

### Screen player API

Used by `/player/`, authenticated with the per-screen device token (`Authorization: Screen evacscreen_…`):

| Method & path | Purpose |
|---|---|
| `POST /player/api/pair/` | ask for a pairing code → `{id, code, secret, expires_in, pair_url}` (no auth, rate limited) |
| `POST /player/api/pair/<id>/` | poll with header `X-Pairing-Secret` → `pending` / `expired` / once `paired` with `token` |
| `GET /player/api/config/` | screen, event, settings, server time, last message sequence |
| `POST /player/api/heartbeat/` | `{"data": {version, resolution, orientation, uptime, slide, errors, …}}` → server time |
| `GET /player/api/stream/` | SSE of messages for this screen (`Last-Event-ID` / `?since=`) |
| `GET /player/api/poll/?since=` | long-poll fallback |
| `GET /player/api/content/theme/` | resolved theme: tokens, CSS variables, `@font-face` rules of the fonts it uses |
| `GET /player/api/content/files/<sha>/<name>` | asset and font files of the screen's event or the shared library |
| WebSocket `/ws/screen/` | first message `{"type": "auth", "token": …, "since": <seq>}`; then `heartbeat`, `ping`; server sends `hello`, `heartbeat.ack`, messages, `revoked` |

## Webhooks out

Configure endpoints in the Webhooks extension ([docs](extensions/webhooks.md)). Payload envelope
`{type, sent_at, event, data}`, headers `X-EVAC-Event`, `X-EVAC-Delivery`, `X-EVAC-Signature`.

## Realtime

Per-event live stream of the same events (plus module messages later):

- WebSocket `ws(s)://<host>/ws/e/<slug>/` (session auth); send `{"type": "resume", "since": <seq>}` to
  replay buffered messages, `{"type": "ping"}` → `pong`.
- SSE `GET /sse/e/<slug>/` (`Last-Event-ID` resumes) · long-poll `GET /poll/e/<slug>/?since=<seq>`.

Messages: `{"seq": 12, "type": "event.state_changed", "data": {...}, "ts": 1790000000.0}`.

## CLI

```sh
export EVAC_URL=https://evac.example.org EVAC_TOKEN=evac_...
evac health
evac whoami
evac events list | show demo | export demo -o demo.json | import demo.json --new-slug demo2
evac events transition demo live
evac modules demo --set venues=off
evac audit demo --limit 20
evac audit-verify
evac tokens
evac --json events show demo
```

Installed with the package (`pip install .` provides the `evac` script) or run as
`python -m apps.api.cli`. Plugins add sub-commands (`CliCommandSpec`), e.g. `evac drill` in phase 3.
