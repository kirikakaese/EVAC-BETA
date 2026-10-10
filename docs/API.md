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
| `/venues/`, `/buildings/`, `/floors/`, `/zones/`, `/rooms/`, `/points/`, `/edges/` | venue structure and route graph (`?venue=<slug>`) | `venues.view` / `venues.manage` (scoped) |
| `/venues/<slug>/routes/` | the way out from every point (`?blocked=<ids>&step_free=1`) | `venues.view` |
| `/tokens/` | your tokens | authenticated |
| `GET /extensions/[?event=<slug>]` | extensions and status | instance admin / `extensions.manage` |
| `POST /extensions/<key>/<id>/webhook/` | inbound webhooks (HMAC) | signature |
| `/events/<slug>/screens/` | list/get/update/delete screens; `health` is `online`/`stale`/`offline`/`unpaired`/`revoked` | `screens.view` / `screens.manage` (scoped), token scope `screens` |
| `POST /events/<slug>/screens/pair/` | claim a pairing code `{code, name?, screen?, tags?}` (`screen` = re-pair) | `screens.pair` |
| `POST /events/<slug>/screens/<id>/revoke/` | revoke the device token | `screens.manage` |
| `/events/<slug>/screen-groups/` | manual and dynamic screen groups | `screens.view` / `screens.manage` |
| `/events/<slug>/themes/` | themes; `tokens` (only values set here), `resolved`, `version` (send it back on `PATCH` to detect concurrent edits) | `content.view` / `content.edit`, token scope `content` |
| `/events/<slug>/fonts/` | font families; `POST` multipart `upload` (+ `name`, `category`, `licence`, `subset`) | `content.view` / `content.edit` |
| `/events/<slug>/layouts/` | layouts (`data` = format v1, see the Designer Guide/ADR-0015); `PATCH` with `data` saves a version (send `version` to detect concurrent edits); `POST …/<id>/publish/` (`at` to schedule) | `content.view` / `content.edit` / `content.publish` |
| `/events/<slug>/playlists/` | playlists; `items` (ordered, `layout` or nested `child`, `duration`, `weight`, `tags`, `condition`, `valid_from/until`) replaces all items when sent | `playlists.view` / `playlists.edit`, token scope `playlists` |
| `/events/<slug>/schedules/` | schedule rules: `playlist` or `layout`, `all_screens`/`groups`/`screens`, `weekdays` (0 = Monday), `start_time`/`end_time` (event time zone), `start_date`/`end_date`, `priority` 0–99 | `playlists.view` / `playlists.edit` |
| `/events/<slug>/overrides/` | live overrides (`?current=1`); `POST` pushes (`title`, `level` `urgent`/`override`/`emergency`, `message` or `layout`/`playlist`, targets, `starts_at`, `expires_at` empty = until cancelled); `POST …/<id>/cancel/` | `playlists.view` / `playlists.override` (scoped), `playlists.emergency` |
| `GET /events/<slug>/now-playing/` | what every paired screen shows now (source, entry, layout, until) | `playlists.view` |
| `GET /events/<slug>/sessions/` (`?day=YYYY-MM-DD`) | program sessions with stage, track, speakers, `planned_start`, `delay_minutes`, `status`, `overrides` | `program.view`, token scope `program` |
| `POST /events/<slug>/sessions/<id>/live/` | live change `{action: delay|cancel|move|restore, minutes, stage, note, shift_following}` | `program.live` |
| `/events/<slug>/incidents/` | incidents (`?status=open`); `POST` reports one, `PATCH` edits; `POST …/<id>/status/` `{status, note}`, `POST …/<id>/note/` `{text}` | `ops.view` / `ops.report` / `ops.manage`, token scope `ops` |
| `/events/<slug>/ops-log/` | the ops log, newest first; `POST` `{text, sender, recipient, important, incident, client_id}` | `ops.view` / `ops.report` |
| `/events/<slug>/occupancy/` | areas with `value`, `capacity`, `percent`, `state`; `POST …/<id>/count/` takes a sensor reading `{delta}` / `{in, out}` / `{value}` (+ `id`) | `crowd.view` / `crowd.count`, token scope `crowd` |
| `/events/<slug>/assets/` | asset library (`?kind=image`); `POST` multipart `upload` (+ `name`, `folder`); `urls` per variant | `content.view` / `content.edit` |

### Screen player API

Used by `/player/`, authenticated with the per-screen device token (`Authorization: Screen evacscreen_…`):

| Method & path | Purpose |
|---|---|
| `POST /player/api/pair/` | ask for a pairing code → `{id, code, secret, expires_in, pair_url}` (no auth, rate limited) |
| `POST /player/api/pair/<id>/` | poll with header `X-Pairing-Secret` → `pending` / `expired` / once `paired` with `token` |
| `GET /player/api/config/` | screen, event, settings, resolved display settings, server time, last message sequence |
| `POST /player/api/heartbeat/` | `{"data": {version, resolution, orientation, uptime, slide, errors, …}}` → server time |
| `POST /player/api/upload/<screenshot|logs>/` | answers to staff requests: an image body (or JSON `{error}`) / JSON `{lines}`; refused (409) unless requested in the last two minutes |
| `GET /player/api/stream/` | SSE of messages for this screen (`Last-Event-ID` / `?since=`) |
| `GET /player/api/poll/?since=` | long-poll fallback |
| `GET /player/api/content/theme/` | resolved theme: tokens, CSS variables, `@font-face` rules of the fonts it uses |
| `GET /player/api/content/bundle/` | offline bundle: theme, fonts, published layouts, asset entries with per-screen signed URLs |
| `GET /player/api/playlists/program/` | the screen's program for 7 days: entries with priority and time windows, playlists, layout durations, message layouts (ADR-0016) |
| `GET /player/api/schedule/` | program sessions from 12 h ago to 48 h ahead, stages, recent changes, the screen's room (refetched on `schedule.changed`) |
| `GET /player/api/content/files/<sha>/<name>` | asset and font files of the screen's event or the shared library |
| WebSocket `/ws/screen/` | first message `{"type": "auth", "token": …, "since": <seq>}`; then `heartbeat`, `ping`; server sends `hello`, `heartbeat.ack`, messages (`config.changed`, `program.changed`, `schedule.changed`, `identify`, `reload`, `clear_cache`, `test_pattern`, `screenshot`, `logs`), `revoked` |

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

## Evacuation

- `GET /api/v1/events/<slug>/evacuation/`: model, event and zone states (with drill flag), requests waiting for a
  decision, blocked points. Scope `evacuation:read`.
- `POST /api/v1/events/<slug>/evacuation/trigger/` with `{"state": "evacuate", "zone": "<uuid>", "drill": false,
  "reason": "...", "key": "<idempotency key>", "source": "api"}`. Scope `evacuation:write`; the token must be created
  in a two-factor session and its owner needs `evacuation.trigger` (or `evacuation.drill`). The source's policy
  applies (default *arm*); the answer says `executed`, `armed`, `notified` or `duplicate`. The API cannot end
  alarms. See [ADR-0031](adr/0031-evacuation-triggers-and-policies.md).

## Venue node API

`/api/v1/node/` is for venue nodes only (ADR-0036). Requests are signed by the node (`Authorization: Node …`,
`X-EVAC-Node-Timestamp`, `X-EVAC-Node-Signature`).

| Method | Path | Purpose |
|---|---|---|
| POST | `enrol/` | the node presents its one-time code and public keys, and gets its token |
| GET | `events/` | the events checked out to the node |
| GET | `events/<id>/snapshot/` | configuration snapshot (`ETag`, `If-None-Match`) |
| POST | `events/<id>/snapshot/confirm/` | the node applied a version |
| GET | `events/<id>/files/<path>` | a media file (`Range: bytes=N-` resumes) |
| POST | `events/<id>/oplog/` | live changes `{"entries": [...]}`; answers `{"applied_seq"}` |
| GET / POST | `events/<id>/actions/`, `events/<id>/actions/<n>/` | actions forwarded from central, and their results |
| POST | `events/<id>/checkin/` | hand the event back (`final_seq`, `alarm_seq`) |
