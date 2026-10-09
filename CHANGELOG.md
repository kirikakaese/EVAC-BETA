# Changelog

All notable changes to EVAC are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning once 1.0 is
released.

## [Unreleased]

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
