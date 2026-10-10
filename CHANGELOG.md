# Changelog

All notable changes to EVAC are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning once 1.0 is
released.

## [Unreleased]

### Changed

- Safety signs now use the official ISO 7010 artwork (E001, E002, E003, E007, W001), imported from
  `@iso-safety-signs/core` (MIT) by `npm run iso7010` instead of EVAC's own drawings. Inline styles become SVG
  attributes for the strict CSP. The build fails when the import is out of date.

### Added — evacuation fail-safe (Phase 3, part 10)

- *Readiness* page (ADR-0034): per screen whether it is online, has a current evacuation bundle, may play sound
  and passed its last self-test; the alarm key; fallback origins and bridges. `manage.py evac_selftest <event>
  --report` prints the same and exits 1 when a screen is not ready.
- Self-test: screens render every stage off screen, check the signature, sound permission and fallback origins
  and report back; optionally a visible test frame (never during an alarm). Button or `manage.py evac_selftest`.
- Watchdog: during an alarm the control room is alerted once per message when screens have not confirmed it
  within 30 s.
- Alarm key management: rotate (previous key valid for 24 hours) and export for bridges and secondary nodes
  (two-factor session, audit-logged), also `manage.py evac_alarm_key`.
- Hardware bridge fail-safe: heartbeat answers carry the signed state and each input's policy; the reference bridge
  serves the state to screens that lost the server and, with the exported key, signs an alarm itself when EVAC is
  unreachable (execute at once, arm after its escalation time, never an all clear). The server adopts it when the
  bridge reports back (`issued_seq`). Players reject an all clear issued by a bridge.
- The player's service worker keeps the evacuation speech; players report their bundle version and sound
  permission in the heartbeat.

### Added — propagation and acknowledgements (Phase 3, part 9)

- Screens acknowledge every evacuation message they render (seq, version, state, path, render time). The control
  page has a *Screens reached* card: "X of Y screens confirmed", offline and waiting screens, per zone, screens
  on the signed fallback, and the trigger-to-screen time (p95) for the current message and the last 24 hours,
  with a warning above the 2 s target (ADR-0035). The screens table shows each screen's confirmation and latency.
- Staff answers during an alarm from the staff app and the panic page: *I'm on it*, *Zone clear*, *Need help*
  (zone and note optional). Audit-logged, webhook `evacuation.staff_ack`; *Need help* alerts the control room.
- API: `GET /api/v1/events/<slug>/evacuation/coverage/`.

### Fixed

- Trigger policy resolution picked between two equally specific rules by their order when they differed only
  in an unused escalation time.

### Added — evacuation content on screens (Phase 3, part 8)

- ISO 7010 safety signs (`E001`, `E002`, `E003`, `E007`, `W001`, direction arrow with *auto*) as a layout
  element; template variables `{{ evac.text }}`, `{{ evac.direction }}`, `{{ evac.stage }}`, `{{ evac.drill }}`.
- Layout guardrails (ADR-0033) through a new plugin hook `r.layout_check`: required elements, text contrast and
  letter height for the viewing distance. The editor lists findings; publishing is refused while an error
  remains.
- *Screen content* page: per stage a layout or the built-in one, texts in rotation with an optional signs-only
  frame, sound and repeat time, spoken message pre-rendered with Piper.
- Players take over on shelter, evacuate and all clear (banner for attention and on *info* screens, ignored on
  *excluded* screens), above the dim overlay and in the screen's rotation, wake dimmed screens, loop the
  alarm sound and mark drills. Payloads are signed per event (Ed25519) and pushed on every change, and the
  built-in layout is used whenever an own layout fails.

### Added — hardware bridge and MQTT (Phase 3, part 7)

- Hardware bridges (ADR-0032): per-event bridges with their own token, inputs mapped to stage and zone, HTTPS
  endpoints `/bridge/v1/heartbeat` and `/bridge/v1/input` with idempotent change ids. An active input raises its
  stage through the *Hardware bridge* source (arm by default); a contact returning to rest only tells the control
  room; wiring faults and bridges without a heartbeat for 30 s raise alerts, never public alarms.
- *Hardware bridges* page (add, inputs, new token, live input states).
- Reference software in `bridge/`: Raspberry Pi bridge (standard library, persistent queue, retries, heartbeat,
  simulate mode) and an ESP32 sketch with supervised loops (end-of-line resistor).
- MQTT extension (`extensions/mqtt`, off until configured): bridges over a broker you run; subscriber process
  `manage.py evac_mqtt` (entrypoint role `mqtt`, compose profile `mqtt`, systemd `evac-mqtt`); `paho-mqtt` added.

### Added — evacuation triggers and policies (Phase 3, part 6)

- Trigger sources with policies per source, stage and zone (ADR-0031): execute, arm (control room confirms; executes
  by itself after 120 s without an answer, configurable) or notify. Defaults: control room and panic page
  execute, API and hardware bridge arm, scheduled drills execute (always as drills).
- Two-person rule per stage (Settings → Evacuation): a second person confirms within 60 s or the request expires
  and the control room is alerted.
- Panic page for the staff app (big hold-to-confirm buttons, zone, drill), staff app card, requests waiting for a
  decision on the control page, *Triggers & drills* page with rules and scheduled drills.
- API: `GET /api/v1/events/<slug>/evacuation/` and `POST .../evacuation/trigger/` with idempotency keys; only
  people end alarms. MQTT follows with the hardware bridge (3.6).

### Added — evacuation models and screen directions (Phase 3, part 5)

- Evacuation model per event (ADR-0030): simple takeover (only evacuate), staged global (default), zones and
  routes (zone alarms). Changing the model never ends or hides an active alarm.
- Live blocking of exits, assembly points, doors and stairs (hold to confirm, audit-logged, webhook
  `evacuation.routes_changed`); routes recompute at once.
- Direction per screen: nearest point on its floor, then the route to the nearest open assembly point or exit,
  as an arrow relative to the people reading the screen; "Follow staff instructions" when there is no route; a
  fixed arrow and text per screen overrides it. Shown on the control page.

### Added — evacuation state machine (Phase 3, part 4)

- Evacuation module (off by default, depends on venues; ADR-0029): persisted state per event and per zone
  (normal, staff alert, attention, shelter in place, evacuate, all clear), highest severity wins, drills with a
  marker, never auto-clear (only an explicit all clear ends an alarm; the all-clear time is stored and survives
  restarts), direct step-down, event all clear with per-zone choice, a real alarm ends every drill and drills
  never mask real alarms.
- Control page with hold-to-confirm and history (real alarms / drills), Settings → Evacuation (states in use,
  names, all-clear time, drill marker), permissions `evacuation.view/trigger/clear/drill/manage` (sensitive,
  zone/venue scopes), webhook and realtime event `evacuation.state_changed`, audit actions `evacuation.*` with
  the drill flag.
- Pure state machine under mypy strict with every transition tested; 95 % coverage gate for
  `apps/evacuation` in `make cov` and CI. The demo seed switches the module on.

### Added — georeferencing and offline map tiles (Phase 3, part 3)

- Floors can be aligned with OpenStreetMap (ADR-0028): corner position and rotation typed in or set by dragging
  the map under the plan, plan opacity; the outdoor floor is drawn on the map at the venue's coordinates.
- Map tiles are proxied and cached by the server (`/maptiles/…`, fetched in the background), so maps viewed once
  work offline. *Settings → Maps*: tile server, attribution, maximum zoom, tiles on/off, area download for
  offline use (only for your own tile server; refused for the public OpenStreetMap servers).

### Added — map editor (Phase 3, part 2)

- Floor plans per floor (PNG, JPEG, WebP, SVG sanitised, PDF via poppler's `pdftoppm`, now in the Docker image)
  and a map editor (ADR-0027): add, drag and connect points, zone outlines, screens with position and facing,
  scale by measuring a known distance (placed things keep their place), route arrows and points without a way
  out; side panel with lists and numeric fields.
- Plugin API: `r.map_layer(MapLayerSpec(...))`; screens are the first layer (`Screen.floor`, `position_x/y` in
  metres, `facing`; also in the screens API). Zone outlines travel with event export/import.
- The SVG sanitiser moved to `apps.core.svg`.

### Added — venue route graph (Phase 3, part 1)

- ADR-0002 (central/node sync) and ADR-0003 (alarm delivery redundancy) accepted with the review decisions:
  live actions proxied through central during a checkout, extension secrets on nodes opt-in, HTTP polling of
  fallback origins (multicast optional, off), hardware bridge triggers default to `arm`.
- Exits, assembly points, doors, waypoints, stairs and lifts with floor, zone, position (metres), capacity and
  step-free flag; route connections (one-way, length, step-free) on the venue page, in the API
  (`/api/v1/points/`, `/api/v1/edges/`) and in event export/import (ADR-0026).
- Routing: nearest assembly point (else exit) from every point, step-free alternative, blocked points;
  `GET /api/v1/venues/<slug>/routes/`; plan checks on the venue page; scope kind *assembly point*.

### Added — announcement audiences and time anchors (Phase 2, part 7)

- Audiences (ADR-0025): *Only these people* limits staff notifications of an announcement to members with
  chosen roles; other modules add audiences with `r.audience(AudienceSpec(...))`.
- Time anchors: announcements can be sent relative to an anchor ("10 min before the start of …") and follow it
  when it moves (`r.anchor_source(TimeAnchorSpec(...))`, signal `apps.core.signals.anchor_moved`); program items
  become anchors with the program module. API fields `audiences`, `anchor`, `anchor_edge`, `anchor_offset`.

### Added — screen packs (Phase 2, part 6)

- `.evacpack` import/export (ADR-0024): zip with manifest, hashed files and an Ed25519 signature; export of
  layouts, themes, files, fonts, custom widgets and playlists with everything they need; import as copies after a
  review page with origin, key fingerprint, contents and preview; upload, URL download or the built-in gallery
  (*Welcome board*, *Info board*, *Wayfinding*).
- Pack keys: this server's signing key and trusted keys (*Settings → Pack keys*); setting *Only import packs
  signed by a trusted key*. `manage.py evac_pack key|verify|export|import`.
- Plugin API: `r.pack_section(PackSectionSpec(...))`. The safe URL fetcher moved to `apps.core.safefetch`.

### Fixed

- Saving a malformed layout reports the format errors instead of failing while checking file references.

### Added — custom widgets (Phase 2, part 5)

- Data & widgets (ADR-0023): feeds from JSON, RSS/Atom, iCal and CSV URLs or built-in data sources, fetched on the
  server with SSRF protection, ETags and a kept last good snapshot; a widget builder with a clickable data tree,
  JSONPath item and field mapping and a live preview; visuals text, list, table, cards, counter, gauge, ticker and
  bars.
- Layout element *Data widget*; screens cache widget data offline and refresh when a feed changes.
- Plugin API: `r.editor_choices(key, fn, module=)`; data sources with `fetch(event)` (`announcements.on_air`,
  `event.info`). Instance setting *Allow feeds from private networks*.

### Added — spoken announcements (Phase 2, part 4)

- Offline speech (ADR-0022): levels can be *read aloud on screens* (urgent and emergency by default). When such an
  announcement is approved, Piper renders it on the server (cached by voice and text, AAC via ffmpeg); screens
  pre-fetch the file and speak it after the level's sound, also offline. *Spoken text* in the composer, a voice
  choice in *Settings → Announcements*, and a player on the announcement page.
- Piper is optional: `pip install -e .[tts]` or the image build argument `WITH_TTS=1` (`EVAC_WITH_TTS=1` with
  docker compose); `manage.py evac_tts install|list|status|say` manages voices. Settings `EVAC_PIPER_BINARY`,
  `EVAC_TTS_VOICES_DIR`.

### Added — staff app and Web Push (Phase 2, part 3)

- Staff app (PWA, ADR-0021): installable (`/manifest.webmanifest`, `/sw.js`), staff page per event with on-air
  announcements, approvals and quick send, full-screen alerts with sound for urgent and emergency announcements,
  and an offline queue that sends actions taken without network when the connection is back.
- Web Push: every in-app notification also reaches the user's subscribed phones and browsers (VAPID and RFC 8291
  encryption implemented with `cryptography`, no new dependency; checked against the RFC test vector). Push keys
  are created automatically; `EVAC_VAPID_SUBJECT` sets the contact address.
- Plugin API: `r.staff_card(StaffCardSpec(...))` for cards on the staff page.
- `make e2e` runs a staff app test on a phone-sized screen (install, offline approval, emergency alert).

### Added — announcement channels (Phase 2, part 2)

- Extensions for e-mail, ntfy, Matrix, Telegram and Mastodon (ADR-0020, docs/extensions/notify.md): settings and
  encrypted tokens per instance or event, *Test connection*, and a channel in the announcement composer where
  the extension is on. Priorities follow the announcement level (ntfy priority, silent Telegram messages for
  info, high importance e-mails for urgent and emergency).
- Own text per channel (`channel_texts` in the API) with the channel's length limit (Mastodon 500 characters).
- Delivery report: refusals (4xx) fail at once and are logged on the extension; network errors, rate limits and
  server errors are retried by the outbox. Matrix and Mastodon deliveries are idempotent.
- Plugin API: `NotificationChannelSpec.available(event)` and `max_length`.
- Base images are configurable (`PYTHON_IMAGE` build argument; `EVAC_PYTHON_IMAGE`, `EVAC_POSTGRES_IMAGE`,
  `EVAC_REDIS_IMAGE` in docker-compose; defaults unchanged). CI pulls them from the ECR public mirror because of
  Docker Hub's anonymous pull limit.

### Added — announcements (Phase 2, part 1)

- Announcements module (ADR-0019): write once, deliver to screens, the public feed, staff notifications and
  webhooks, with a delivery report per channel and occurrence (sent through the outbox, with retries).
- Configurable priority levels per event (built in: info ticker, important banner with chime, urgent card with
  gong repeated every 10 minutes, emergency full screen with alert tone), English templates with `{{variables}}`
  and an optional full-screen layout, scheduling (start, end, daily/weekly until a day), targeting of venues,
  zones, rooms, screen groups and screens within the sender's role scopes.
- Approval workflow: drafts, approval queue, four-eyes approve/reject with a note, cancel; emergency
  announcements need the new sensitive permission `announcements.emergency` and skip approval. Notifications to
  approvers and authors; webhook events `announcement.pending`, `announcement.published`, `announcement.cancelled`.
- Screens: banners, tickers and cards drawn over the running content, full-screen announcements as program
  entries above live overrides (emergency) or above urgent overrides; sounds synthesised in the player. They are
  part of the screen's seven-day program, so they appear and disappear on time without network.
- Public feed page with RSS and JSON Feed (off by default; *Settings → Announcements*).
- REST API: `/api/v1/events/<slug>/announcements/` (create, edit drafts, `submit`, `approve`, `reject`,
  `cancel`), `…/announcement-levels/`, `…/announcement-templates/`; token scope `announcements`.
- Plugin API: `r.program_source(fn)` adds entries, messages and overlays to every screen's program.
- `make e2e` also runs the phase 2 gate in a browser (`frontend/e2e/phase2.mjs`): a helpdesk announcement goes
  through approval and reaches a screen (banner) plus feed, staff and webhook channels with a delivery report;
  an urgent card and an emergency takeover appear and disappear on the screen.

### Changed

- The screen program no longer needs the playlists module: with playlists switched off, screens show the
  default layout plus announcements; only switching off *Content* empties it.

### Added — code mode and the phase 1 acceptance run (Phase 1, part 7: phase 1 complete)

- Code elements in layouts (ADR-0018): your own HTML, CSS and JavaScript in a sandboxed frame without network,
  with a small data API (`evac.data`, `evac.onData`, `evac.now`, `evac.log`) for the data kinds the element
  declares; works offline. New permission `content.code`; code changes are audit-logged with hashes.
- `make e2e` and a CI job run the phase 1 acceptance gate in a real browser: pair a screen, upload a font,
  design and publish a slide with a code element, push and cancel an override, stop the server, reload offline;
  the code element's escape attempts (page, storage, network) must fail.

### Fixed

- Offline restart of a freshly set-up screen: the service worker now caches the player's script and styles when
  it installs. They were loaded before the worker took control on the first visit, so a screen that lost
  network and power before its first online reload stayed on "Starting…" (found by `make e2e`; the build now
  also fails if the worker bundle contains `import`/`export`).
- Offline boot: the player shows the last known content immediately and refreshes in the background; theme
  fonts and images load cache-first with a timeout, so a hanging network cannot keep a screen blank.

### Added — screen operations (Phase 1, part 6)

- Display settings per event, screen group and screen (ADR-0017): rotation, overscan, content scale, keystone,
  expected resolution, dim and "screen off" times, sound and volume, daily reload time, evacuation role;
  screens apply changes within seconds.
- Remote management on the screen page: real screenshots (tab capture), the player's log, test pattern,
  clear cache and reload, plus identify and reload; uploads are only accepted when requested and images are
  re-encoded.
- Self-healing player: render fallback, reload guard (at most 3 reloads in 10 minutes), crash detection,
  reloads on error storms, memory pressure and at a daily time, resync after frozen timers.
- Raspberry Pi kiosk recipe `deploy/kiosk/` (cage + Chromium, watchdog, hardware watchdog, read-only option,
  pi-gen stage for images).
- The setup wizard pairs the first screen; the first screen of an event without layouts shows a welcome slide.

### Fixed

- Property tests of the audit hash chain no longer fail on slow CI runners (no Hypothesis deadline).

### Added — playlists, schedules and live overrides (Phase 1, part 5)

- Modules *Playlists*, *Schedules* and *Live overrides* under **Playback** (ADR-0016): ordered, shuffled
  and weighted playlists with per-item durations, tag/condition/time filters and nesting; a default playlist
  per event; schedule rules (weekdays, times across midnight, date ranges, priorities, groups or single
  screens) with a week calendar; overrides (message, layout or playlist; urgent, live or emergency level;
  start later, expiry or until cancelled; scoped to the operator's screen groups) with one-click cancel.
- "On screens now" dashboard and a preview of any screen at any time (rendered slide, why it wins, next 24
  hours, next slides).
- Screens get a 7-day program (`/player/api/playlists/program/`) and resolve it themselves with the
  synchronised clock: slide changes are simultaneous on all screens and continue offline; overrides arrive in
  well under a second (`program.changed`).
- REST API: `/events/<slug>/playlists/`, `schedules/`, `overrides/` (`…/cancel/`), `now-playing/`; webhooks
  `override.started`, `override.cancelled`; permissions `playlists.view|edit|override|emergency`.

### Added — layouts, renderer, widgets and the layout editor (Phase 1, part 4)

- Layouts (format v1, validated JSON) with versions on every save, publish now or scheduled, publish any
  version, restore old versions, change summary per version, optimistic locking and a "someone is editing"
  notice; default layout per event; REST API `/events/<slug>/layouts/` (ADR-0015).
- Shared renderer for editor and screens (container-query units, identical preview) with built-in widgets:
  text (auto-fit, line clamp, ticker), rich text, image, synchronised slideshow, video, audio, shape, QR code,
  clock, date, countdown; per-widget error boundary; entrance animations respecting reduced motion.
- Template variables and conditions (`{{ event.name|upper }}`, `{% if screen.zone %}`), "show only if".
- Layout editor (Lit): drag, resize, snapping guides, layers, properties, alignment, undo/redo, copy/paste
  between layouts, keyboard shortcuts, save and publish.
- Screens play the event's default layout from an offline bundle; files are prefetched and cached by the
  service worker via per-screen signed URLs.
- `player/` became `frontend/` (player, renderer, editor); `make frontend` builds all bundles.

### Security

- API: the nested event endpoints (`/events/<slug>/roles/`, `members/`, `modules/`, `audit/`) did not check
  the scopes of service tokens; a read-only token of a user with the right permissions could change roles.
  They now enforce token scopes like every other endpoint (regression test added).

### Added — screens (Phase 1, part 1: pairing, groups, health)

- New `screens` module: screens with venue/zone/room, tags and position; manual and dynamic screen groups
  (scope kind `screen_group`); pairing with a six-character code and QR (`/screens/pair/?code=…`), per-screen
  device tokens (`evacscreen_…`, hashed, revocable, re-pair to new hardware).
- Player device API under `/player/api/` (pairing, config, heartbeat, SSE, long-poll) and WebSocket
  `/ws/screen/` (token in the first message); exempt from the early-access gate (ADR-0013).
- Health: heartbeat reports (version, resolution, uptime, slide, errors, …), online/stale/offline with a
  configurable threshold, beat task that emits `screen.offline` / `screen.online` webhooks and notifies screen
  managers. Portal pages for screens, pairing and groups; REST API `/events/<slug>/screens/` and
  `/screen-groups/`. Plugins can mount urlconfs at the site root (`ROOT_MOUNTS`).

### Added — design system (Phase 1, part 3: themes, fonts, asset library)

- New `content` module (*Design & assets*, depends on `screens`): themes with design tokens (dark/light
  palettes, fonts, type scale, spacing, radius, shadow, background colour/gradient/image, logo, transitions),
  inheritance, live preview, optimistic locking and "use for this event's screens" (ADR-0014).
- Fonts: WOFF2/WOFF/TTF/OTF upload incl. variable fonts, optional Latin subsetting, stored as WOFF2, licence
  note; built in: Atkinson Hyperlegible and Inter (SIL OFL 1.1).
- Asset library: images, SVG, video, audio, PDF, Lottie; content-hashed storage with de-duplication, folders,
  tags, alt text, credits, usage; derivatives in the worker (thumbnail, WebP, AVIF; MP4/H.264 + WebM/VP9 +
  poster; loudness-normalised AAC); EXIF rotation and metadata removal; SVG sanitising; access-checked file
  serving (no public media URLs); shared instance library.
- Player applies the event theme and its fonts and keeps them for offline use.
- Docker image includes ffmpeg; new dependencies Pillow (explicit), fontTools, defusedxml.

### Added — screen player (Phase 1, part 2)

- `/player/`: TypeScript player (Vite build in `static/player/`, 12.5 kB gzipped, CI checks the committed
  bundle and the 300 kB budget): pairing view with code and QR, WebSocket → SSE → long-poll with resume and
  backoff, heartbeats with health report, NTP-like clock offset, idle slide with event clock, identify
  overlay, reload, automatic re-pairing when the token is revoked, OBS mode (`?mode=obs`).
- Offline: a service worker keeps the app shell; the last configuration is kept on the device, so a screen
  restarts without network.
- Remote commands *Identify* and *Reload player* on the screen page (permission `screens.control`, audit-logged).

### Added — production server bundle

- `deploy/server/`: run EVAC and DIAL on one server behind Caddy (automatic HTTPS): bootstrap script
  (Docker, Caddy, ufw, unattended upgrades), compose overrides binding both apps to localhost and keeping
  DIAL's Asterisk off the public server, production `.env` values, nightly backup timer, step-by-step README.
- `www.evac.pm` and `www.dial.pm` redirect permanently to the bare domains (Caddyfile).

### Added — GitHub Codespaces

- `.devcontainer/`: one-click EVAC in the browser (SQLite, no Redis, demo data, port 8000 private to the
  codespace owner). Dev setting `EVAC_TRUST_PROXY_HEADERS` trusts the Codespaces proxy headers.

### Changed

- The sibling project PET was renamed to **DIAL — DECT & IP Administration Layer**; brief, roadmap, ADRs,
  docs and UI texts now say DIAL (phase 4 is the DIAL extension, `extensions/dial`, `X-DIAL-*` headers,
  `dial_` tokens).

### Added

- Early-access gate (`EVAC_EARLY_ACCESS_PASSWORD`): a shared password in front of the whole instance,
  incl. the first-run wizard and WebSockets, for running on the public domain before launch (ADR-0012).

### Added — Phase 0 (foundation)

- Project scaffold mirroring PET: `evac/` settings (base/dev/prod/test), ASGI with Channels, Celery + beat.
- Plugin registry API (`apps/core/plugins.py`, `apps/core/registry.py`): modules, permissions, nav
  entries, settings namespaces, scope kinds, data sources, widgets, notification channels, evacuation
  triggers, webhook event types, CLI commands, extensions, event hooks, outbox handlers; discovery via
  `evac_plugin.py` and the `evac.plugins` entry point group.
- Module toggles (instance and per event, dependencies, required modules) with Settings → Modules.
- Typed settings framework (JSON schema, generated forms, instance → venue → event → screen group → screen
  inheritance with provenance markers).
- Tamper-evident audit log (SHA-256 hash chain, immutable in ORM and via PostgreSQL trigger, verify,
  CSV/JSON export, drill flag).
- Accounts: e-mail login with lockout, invitations, OpenID Connect SSO (PKCE, account linking, SSO-only
  mode, optional IdP-MFA trust), TOTP + WebAuthn + recovery codes, per-role and per-permission
  two-factor enforcement, service tokens (`evac_…`, scopes, event binding, expiry), GDPR export and
  erasure.
- Events with lifecycle (draft/setup/live/teardown/archived), scheduled transitions, branding, clone
  (with/without content), JSON export/import.
- Venues reusable across events: buildings, floors, rooms (capacity, accessibility), zones.
- RBAC: built-in roles, custom roles with glob patterns, scoped role assignments (venue/zone/room).
- Extension framework and Settings → Extensions (instance and event level): generated settings pages,
  encrypted secrets, test connection, health and log, feature toggles, inbound webhook URL + secret,
  disconnect & purge; signed inbound webhooks with idempotency.
- Generic webhooks extension: signed outbound deliveries for every registered event type via the durable
  outbox, endpoint management, inbound webhook store + signal.
- Durable outbox with retries/backoff/dead-letter; realtime stream (WebSocket, SSE, long-poll).
- UI shell (event switcher, search, notifications, sidebar from enabled modules, dark/light mode), first-run
  wizard, dashboards, members/roles/modules/settings/audit/token/user pages; strict CSP; a11y linter in tests.
- REST API v1 with OpenAPI (Swagger/ReDoc), `evac` CLI, health/readiness/Prometheus metrics, JSON logs.
- In-portal documentation, demo seed, Dockerfile, docker-compose, Ansible role, systemd units, CI
  (lint, types, tests + coverage, PostgreSQL checks, a11y, OpenAPI drift, dependency audit, Docker build,
  attribution check).
- Planning: roadmap, ADR-0001…0011 (ADR-0002 central/node sync and ADR-0003 alarm delivery redundancy are
  proposals awaiting review).
