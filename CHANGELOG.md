# Changelog

All notable changes to EVAC are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning once 1.0 is
released.

## [Unreleased]

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
