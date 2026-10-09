# EVAC Roadmap

Phases → epics → tickets, derived from the product brief (`docs/BRIEF.md`, section numbers in brackets).
Each phase ends with: green CI, docs, CHANGELOG, attribution check, commit, push, summary, pause for
review. Every ticket also meets the **definition of done** (brief §18): behind its toggle with a tested
off-switch, permission-checked incl. scopes, audit-logged, API + UI + docs + tests, English strings wrapped
for translation, works offline at the venue node or degrades visibly, passes the a11y check, no
evacuation regressions, attribution check green.

Status: ✅ done · 🟡 partly done / deferred part noted · ⬜ planned

---

## Phase 0 — Foundation ✅

**Gate:** `docker compose up` → first-run wizard → logged-in admin with an event; all toggles work; tests
green. (Verified by `apps/portal/tests/test_portal.py::test_first_run_wizard` and the CI compose job.)

### Epic 0.1 — Repository, packaging, CI

| ID | Ticket | Acceptance criteria | Status |
|---|---|---|---|
| 0.1.1 | Scaffold (layout mirrors DIAL) | `evac/` settings base/dev/prod/test, `apps/*`, `extensions/*`, `docs/`, `deploy/`; `manage.py check` clean | ✅ |
| 0.1.2 | Docker image + compose | One image, roles web/channels/worker/beat via entrypoint; compose with postgres + redis healthchecks; migrate + optional seed on start | ✅ |
| 0.1.3 | Ansible role + systemd units | `deploy/ansible/roles/evac`, `deploy/systemd/evac-*.service` + `evac.target` | ✅ |
| 0.1.4 | CI | ruff, mypy (strict list), makemigrations check, pytest + coverage ≥ 85 %, PostgreSQL migrate/seed/deploy check, append-only audit check, a11y, OpenAPI drift, pip-audit, Docker build, compose smoke | ✅ |
| 0.1.5 | Attribution check | `scripts/check_attribution.py` fails on AI author/committer, co-author trailers, generated-with lines, AI credits in tracked files; CI job + `make attribution` + pre-commit hook | ✅ |
| 0.1.6 | Makefile targets | `dev migrate seed run test lint openapi e2e load chaos` (e2e/load/chaos are placeholders until Phases 1/3) | 🟡 e2e/load/chaos arrive with player/evacuation |
| 0.1.7 | Licence | AGPL-3.0-or-later `LICENSE`, SPDX headers in source files | ✅ |

### Epic 0.2 — Core platform

| ID | Ticket | Acceptance criteria | Status |
|---|---|---|---|
| 0.2.1 | Plugin registry API | `PluginManifest` + `register(registry)` per app; entry points `evac.plugins`; duplicate keys rejected; API version check; core uses the same API (ADR-0001) | ✅ |
| 0.2.2 | Modules + Settings → Modules | instance and per-event toggles, required modules, dependencies, nav/views disappear when off, audit + webhook on toggle | ✅ |
| 0.2.3 | Settings framework | JSON-schema namespaces, validation, generated forms, inheritance instance → venue → event → screen group → screen with provenance ("overridden here") | ✅ (screen levels used from Phase 1) |
| 0.2.4 | Audit log | append-only, SHA-256 hash chain, immutable in ORM + PostgreSQL trigger, verify (UI/CLI/API), filter, CSV/JSON export, drill flag | ✅ (ADR-0004) |
| 0.2.5 | Secrets at rest | Fernet/MultiFernet, key rotation command, never rendered back, never in audit | ✅ (ADR-0007) |
| 0.2.6 | Outbox | durable jobs with idempotency keys, backoff, dead-letter, beat drain, purge | ✅ |
| 0.2.7 | Realtime layer | Channels WebSocket per event, SSE fallback, long-poll fallback, resumable sequence numbers | ✅ (ADR-0008) |
| 0.2.8 | Observability | `/healthz`, `/readyz`, `/metrics` (Prometheus text, optional token), JSON logs (`LOG_FORMAT=json`) | ✅ (Sentry hook: documented, optional) |
| 0.2.10 | Early-access gate | shared password in front of everything (pages, API, WebSockets, wizard); probes, signed webhooks and service tokens exempt; password change invalidates cookies (ADR-0012) | ✅ |
| 0.2.9 | Rate limiting + CSP | per-IP limits on login/2FA/setup/webhooks; strict CSP with nonce | ✅ |

### Epic 0.3 — Accounts

| ID | Ticket | Acceptance criteria | Status |
|---|---|---|---|
| 0.3.1 | E-mail login + lockout | argon2, per-account and per-IP lockout, audit | ✅ |
| 0.3.2 | Invitations | invite by e-mail with role (+ scope); accept with new or existing account | ✅ |
| 0.3.3 | OIDC SSO | code flow + PKCE, linking by verified e-mail, SSO-only mode, IdP logout, optional MFA trust (`amr`) | ✅ |
| 0.3.4 | TOTP + WebAuthn + recovery codes | enrolment, login step, replay protection, admin reset | ✅ |
| 0.3.5 | 2FA enforcement per role | roles with `require_2fa` and every `sensitive` permission only work in 2FA-verified sessions (also for tokens: `created_with_2fa`) | ✅ (ADR-0005) |
| 0.3.6 | Service tokens | `evac_…`, hashed, scopes `<module>:read|write`, event binding, expiry, last used | ✅ |
| 0.3.7 | GDPR | JSON export, erasure (anonymise), last-admin guards | ✅ |

### Epic 0.4 — Events, venues, RBAC

| ID | Ticket | Acceptance criteria | Status |
|---|---|---|---|
| 0.4.1 | Events + lifecycle | draft → setup → live → teardown → archived (one step back allowed), scheduled transitions (beat), branding, time zone | ✅ |
| 0.4.2 | Clone / export / import | clone with/without content; JSON export/import incl. plugin hooks; secrets never copied | ✅ |
| 0.4.3 | Venues (basic) | reusable venues, buildings, floors, rooms (capacity, step-free, lift, wheelchair), zones; UI + API | ✅ (floor plans/exits/routes: Phase 3) |
| 0.4.4 | RBAC | built-in roles admin/orga/control-room/security/helpdesk/crew/viewer, custom roles, glob patterns, scoped assignments (venue/zone/room; screen group/team later), UI + API | ✅ |

### Epic 0.5 — Extensions framework

| ID | Ticket | Acceptance criteria | Status |
|---|---|---|---|
| 0.5.1 | Extension contract | `ExtensionSpec` (schema, secrets, features, test, webhook handler, purge, custom views), instance/event/both scope | ✅ |
| 0.5.2 | Settings → Extensions | card grid with status; generated settings page: secrets, test connection (HTMX), health, log, feature toggles, webhook URL + secret (shown once), disconnect & purge | ✅ |
| 0.5.3 | Inbound webhooks | `POST /api/v1/extensions/<key>/<id>/webhook/`, HMAC-SHA256 constant-time, idempotency by delivery id | ✅ |
| 0.5.4 | Generic webhook extension | outbound signed deliveries for every registered event type via outbox; endpoint management; inbound store + signal | ✅ |

### Epic 0.6 — UI shell, API, CLI, docs, demo

| ID | Ticket | Acceptance criteria | Status |
|---|---|---|---|
| 0.6.1 | UI shell | top bar (event switcher, search, notifications, account), sidebar from enabled modules + permissions, dark/light, responsive, a11y linter clean | ✅ |
| 0.6.2 | First-run wizard | admin → venue → event → (screen: Phase 1) → done; optional setup token | 🟡 screen pairing step activates in Phase 1 |
| 0.6.3 | REST API + OpenAPI | events, roles, members, modules, audit, venues, tokens, extensions, registry; Swagger/ReDoc; schema committed and drift-checked | ✅ |
| 0.6.4 | CLI `evac` | health, whoami, events list/show/export/import/transition, modules, audit, audit-verify, tokens; plugin sub-commands | ✅ |
| 0.6.5 | In-portal docs | `/docs/` renders README, guides, ADRs, extension pages, search | ✅ |
| 0.6.6 | Demo seed | `EVAC_SEED_DEMO=1`: venue with buildings/floors/rooms/zones, event, one account per built-in role, scoped grant | 🟡 screens/themes/layouts/schedule/crew/announcements are seeded by their modules in later phases |
| 0.6.7 | Planning docs | `CLAUDE.md`, this roadmap, ADR-0001…0003 (+ further ADRs) | ✅ (ADR-0002/0003 are *Proposed*, awaiting review) |

---

## Phase 1 — Screens core 🟡

**Gate:** pair a screen, design a slide with an uploaded font, publish, override, unplug the network: the
screen keeps playing.

**Progress:** done: 1.1.1 (player shell, Vite build, size check in CI), 1.1.2 (pairing, device tokens),
1.1.3 (WebSocket/SSE/long-poll, heartbeat reports), 1.1.8 (OBS mode), 1.2.1 (screens, manual/dynamic groups,
tags, scope kind), 1.2.4 (health states, offline alerts to webhooks and notifications), ADR-0013.
Partly: 1.1.4 (service worker app cache + last config; the IndexedDB content bundle comes with layouts),
1.1.5 (clock offset; synchronised slide changes come with playlists), 1.2.3 (identify, reload, revoke,
re-pair). Next: the design system (1.3.1–1.3.3), then layouts, renderer and widgets.

### Epic 1.1 — Player (`player/`, TypeScript, < 300 kB gz) [§5.1]
| ID | Ticket | Acceptance criteria |
|---|---|---|
| 1.1.1 | Player shell + build | Vite build into `static/player/`, served at `/player/`; bundle-size check in CI |
| 1.1.2 | Pairing | short code + QR; staff assigns venue/zone/room/group/position; per-screen device token (revocable) |
| 1.1.3 | Realtime + heartbeat | WS with SSE fallback; 10 s heartbeat (setting); reports version, resolution, orientation, uptime, slide, errors, memory, last sync, evac ack |
| 1.1.4 | Offline cache | Service Worker app cache; IndexedDB content bundle (layouts, themes, fonts, assets by hash, data snapshots); keeps playing without server |
| 1.1.5 | Time sync | NTP-like offset; synchronised slide changes across screens (±50 ms on LAN) |
| 1.1.6 | Shared renderer | deterministic layout renderer used by player and editor (pixel-identical preview) |
| 1.1.7 | Resilience | per-widget error boundary, soft reload guard, crash auto-recovery |
| 1.1.8 | OBS / NDI mode | transparent background, no cursor URL mode |
| 1.1.9 | Pi kiosk recipe | `deploy/kiosk/` provisioning script + image recipe + README (Chromium kiosk, watchdog, autoplay, HW decode) |

### Epic 1.2 — Screen management [§5.2]
| ID | Ticket | Acceptance criteria |
|---|---|---|
| 1.2.1 | Screens, groups (manual/dynamic by tag/zone/room/venue), tags | CRUD + API, scope kind `screen_group` registered |
| 1.2.2 | Per-screen settings via settings framework (screen levels) | resolution, rotation, overscan, scale, keystone, dim/power schedule, audio, default playlist, emergency role |
| 1.2.3 | Remote management | screenshots, reload, hard refresh, clear cache, identify, re-pair, revoke, logs, test pattern, evac self-test |
| 1.2.4 | Health dashboard + offline alerts | online/offline/stale; alert to ops log + notification channels with thresholds |

### Epic 1.3 — Designer [§5.3, §5.4]
| ID | Ticket |
|---|---|
| 1.3.1 | Themes (design tokens → CSS custom properties), inheritance event → layout |
| 1.3.2 | Fonts: upload WOFF2/WOFF/TTF/OTF, variable axes, subsetting, fallback stacks, licence note; curated open fonts incl. Atkinson Hyperlegible |
| 1.3.3 | Asset library: content-hashed storage, thumbnails, WebP/AVIF, video/audio transcoding (worker), usage tracking, shared library |
| 1.3.4 | Layout editor island (`editor/`, framework per ADR) — canvas, elements, responsive constraints, styling, text auto-fit, animations (reduced motion), layers, undo/redo |
| 1.3.5 | Versioning: every save a version, diff, rollback, draft/published, scheduled publish, optimistic locking |
| 1.3.6 | Code mode: sandboxed iframe, strict per-frame CSP, postMessage data API (permission-gated) |
| 1.3.7 | Template variables and expressions (`{{event.name}}`, filters, if/else) |

### Epic 1.4 — Widgets + data sources [§5.5]
| ID | Ticket |
|---|---|
| 1.4.1 | Widget contract (manifest + Web Component renderer, stale indicator staff-only) — consumes `WidgetSpec`/`DataSourceSpec` |
| 1.4.2 | Basic + time widgets (text, rich text, image, slideshow, video, audio, shape, ISO 7010 pictogram, QR, iframe, PDF, clock, countdown, date) |

### Epic 1.5 — Playlists, scheduling, overrides [§5.6]
| ID | Ticket |
|---|---|
| 1.5.1 | Playlists (ordered/weighted, durations, conditions, nesting) |
| 1.5.2 | Scheduling rules + calendar view + "preview any screen at any time" |
| 1.5.3 | Live overrides with priority levels and expiry; active override list; evacuation always highest |
| 1.5.4 | Wizard step "pair the first screen" + welcome slide (closes 0.6.2) |

---

## Phase 2 — Announcements ⬜

**Gate:** one announcement reaches screens + 3 channels with a delivery report; approval flow tested.

| ID | Ticket | Acceptance criteria |
|---|---|---|
| 2.1 | Priority levels (configurable) [§6] | display style, sound, min display time, repetition, default channels |
| 2.2 | Templates with variables + optional layout | English built-ins |
| 2.3 | Scheduling incl. relative to program items | |
| 2.4 | Targeting (venues, zones, rooms, groups, screens, audiences) | scoped permissions respected |
| 2.5 | Approval workflow | draft → approve/edit/reject; emergency bypass for permitted roles |
| 2.6 | `apps/notify` channel adapters | screens, public feed, Web Push (VAPID), ntfy, e-mail, Matrix, Telegram, Mastodon, webhook; per-channel text; outbox delivery report |
| 2.7 | Offline TTS (Piper, optional download) | pre-render + cache |
| 2.8 | Staff PWA basics | installable, alarm reception, announcements send/approve, offline queue |
| 2.9 | Custom widget builder (no-code) | HTTP JSON, RSS, iCal, MQTT, CSV sources; JSONPath mapping; visuals |
| 2.10 | `.evacpack` import/export (signed) | layouts, themes, widget configs, screen packs; gallery |

## Phase 3 — Venue + evacuation ⬜

**Gate:** all tests in brief §8.7 pass; a documented drill runbook works end to end. **ADR-0002 and
ADR-0003 must be accepted before implementation starts.**

| ID | Ticket | Acceptance criteria |
|---|---|---|
| 3.1 | Exits, assembly points, doors/waypoints, route graph [§10] | models + API + scope kinds |
| 3.2 | Map editor (`mapeditor/`) | upload PDF/SVG/PNG, georeference, OSM tiles cached offline; draw zones, exits, waypoints, screens with facing |
| 3.3 | Evacuation state machine [§8.2] | persisted per event and zone, highest severity wins, drills, never auto-clear; 100 % transition tests; mypy strict |
| 3.4 | Models: simple takeover, staged global, zones and routes [§8.1] | per-event switch; blocked exits recompute routes; partial evacuation |
| 3.5 | Triggers + policies [§8.3] | web control room + PWA panic page with hold-to-confirm, two-person rule, API/MQTT, scheduled drills, policy execute/arm/notify per source/stage/zone with auto-escalation |
| 3.6 | Hardware bridge (`bridge/`) | Pi GPIO + ESP32 reference, authenticated MQTT/HTTPS, supervised line heartbeat |
| 3.7 | Evacuation content [§8.4] | guardrail linter (contrast, size, required elements), non-deletable fallback layout (ISO 7010 + English), text rotation, arrows per screen with manual override, audio loop |
| 3.8 | Propagation + acks [§8.5] | ≤ 2 s p95 on LAN, measured; X of Y confirmed / Z offline per zone; staff acks |
| 3.9 | Fail-safe [§8.6] | evacuation bundle cached per screen; stays in alarm offline; signed state from secondary node/bridge (ADR-0003); watchdog; self-test |
| 3.10 | Venue node + sync | `EVAC_MODE=node`, checkout/checkin, config snapshots with ETags, op-log with idempotency keys, resumable assets (ADR-0002) |
| 3.11 | Safety acknowledgement | once per event when enabling the module; shown on settings page and in the wizard |
| 3.12 | Tests [§8.7] | unit, property (routing), Playwright E2E, chaos (kill web/channels, partition), load (500 WS players); `make e2e load chaos` |

## Phase 4 — DIAL extension ⬜ [§9]

**Gate:** against a running DIAL demo: webhook → evac arm; evac → DIAL broadcast; phone-recorded
announcement → approval queue; DIAL widgets render.

| ID | Ticket |
|---|---|
| 4.1 | Link config + test connection (`/api/v1/health/?event=`, `/api/v1/me/`), token scopes documented |
| 4.2 | Inbound: `X-DIAL-Signature`, `X-DIAL-Event`; emergency.triggered → trigger policy; page.updated; announcement.recorded → draft (optional Whisper); dect.* → data source + ops log |
| 4.3 | Outbound: emergency broadcast + messaging broadcast via outbox; delivery report |
| 4.4 | Data sources + widgets: phonebook, important numbers, info pages, DECT status, "call X for Y" |
| 4.5 | Shared OIDC IdP docs; manual DIAL-role → EVAC-role mapping table |

## Phase 5 — Program ⬜ [§11.1]
**Gate:** imported schedule shows now/next on screens; live change propagates < 5 s.
| ID | Ticket |
|---|---|
| 5.1 | Program module (rooms/stages, sessions, speakers, tracks, live changes, public page, iCal/JSON/frab export) |
| 5.2 | pretalx, frab/Pentabarf, iCal extensions with conflict handling |
| 5.3 | Program widgets |

## Phase 6 — Ops + crowd ⬜ [§11.3, §11.4]
**Gate:** "Room full" appears automatically at the threshold.
| ID | Ticket |
|---|---|
| 6.1 | Incidents, ops log, tasks, escalation |
| 6.2 | Control room dashboard |
| 6.3 | Occupancy: PWA counter (offline queue), MQTT/HTTP sensors, capacity rules → screens + alerts, history |

## Phase 7 — Crew, inventory, helpdesk ⬜ [§11.2, §11.6, §11.7]
**Gate:** shift board on screens; lend/return with QR.
| ID | Ticket |
|---|---|
| 7.1 | Crew & shifts (+ Engelsystem extension), scope kind `team` |
| 7.2 | Inventory with QR labels, lend/return |
| 7.3 | Lost & found, requests, FAQ |

## Phase 8 — Access ⬜ [§11.5]
**Gate:** offline check-in syncs; access zone counts feed occupancy.
| ID | Ticket |
|---|---|
| 8.1 | Attendee lists, ticket types, badges (layout editor), offline check-in app |
| 8.2 | pretix extension |

## Phase 9 — Hardening and ecosystem ⬜
**Gate:** 1,000 simulated screens; SDK example plugin adds a widget + data source + extension page without
core changes.
| ID | Ticket |
|---|---|
| 9.1 | Full staff PWA |
| 9.2 | Public plugin SDK docs + example plugin (pip, entry point) |
| 9.3 | Template gallery |
| 9.4 | Tauri player wrapper; info-beamer hosted package |
| 9.5 | Performance/load tuning; security review; handbook polish; video walls (stretch) |
