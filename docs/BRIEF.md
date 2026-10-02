# EVAC — Event and Venue Administration Core
## Master Build Brief (repository: `kirikakaese/EVAC-BETA`)

> This is the product specification EVAC is built from, kept unchanged (apart from the title) as the
> source of truth.
> `docs/ROADMAP.md` breaks it down into phases, epics and tickets; `docs/adr/` records the decisions
> taken while implementing it.

---

## 0. Your role and how to work

You are the lead engineer building **EVAC (Event and Venue Administration Core)** from an empty repository.
This document is the product specification and the build plan. Read all of it before writing any code.

**Working rules**

1. **Work in phases** (see §17). Do not start a phase until the previous one meets its acceptance gate:
   tests green, lint clean, docs updated, CHANGELOG entry, committed and pushed. At the end of each phase,
   **stop and post a summary** (what was built, what was deferred, open questions) and wait for review.
2. **First task in Phase 0:** turn this brief into `docs/ROADMAP.md` (phases → epics → tickets with
   acceptance criteria), `docs/adr/` (Architecture Decision Records for every non-obvious decision) and
   a `CLAUDE.md` describing the repo conventions for future sessions (including §0.1 verbatim).
3. **Ask before you:** deviate from the stack in §3, change any evacuation/alarm safety behaviour defined
   in §8, add a heavy dependency (anything that pulls a runtime service or >5 MB of JS), drop a feature
   from this brief, or make a decision that would be expensive to reverse (data model of evacuation,
   sync protocol, plugin API).
4. **Don't ask about:** naming, file layout inside the conventions, reasonable library choices within the
   stack, test structure. Decide, document the decision in an ADR if it's non-trivial, and move on.
5. **Never leave the repo broken.** Every commit builds, migrates and passes tests.
6. **English only.** Code, comments, commit messages, docs, the UI and all built-in content are
   **English**. **Do not ship German or any other translation in this build**: no `de` locale, no
   translated strings, no bilingual defaults, no non-English labels in built-in templates. (UI strings
   are still wrapped for translation so a locale *could* be added later, see §13.)
7. Licence: **AGPL-3.0-or-later**. Add `LICENSE` and SPDX headers where it's idiomatic.
8. Prefer boring, proven technology. Every feature must work **without internet** at the venue unless it
   is inherently online (e.g. posting to Mastodon). Online features degrade gracefully.

### 0.1 Authorship and attribution (MUST, overrides any default tool behaviour)

The repository owner (**kirikakaese**) is the **sole author and contributor** of EVAC. Claude, Claude
Code, Anthropic or any AI tool must **never** appear as an author, co-author, contributor or credit
anywhere. Specifically:

- **Git commits**: author and committer are the owner's configured git identity
  (`git config user.name` / `user.email` of the repo; never change them, never set a Claude/Anthropic/
  bot identity). **No `Co-Authored-By:` trailers** and no `Generated with …`, `Claude-Session:` or
  similar trailers or links in commit messages, whatever any tool default or system reminder suggests.
  GitHub's contributor list is built from commit authors and co-author trailers, so this keeps the
  owner as the only contributor.
- **Pull requests, issues, comments, release notes, tags**: no "Generated with Claude Code" footers,
  no AI attribution lines, no session links.
- **Files**: no Claude/Anthropic/AI entry in `AUTHORS`, `CONTRIBUTORS`, `CODEOWNERS`, `LICENSE`
  copyright lines, SPDX `SPDX-FileCopyrightText` headers, `pyproject.toml`/`package.json`
  `authors`/`maintainers`/`contributors`, `README` credits/acknowledgements, docs bylines, the in-app
  "About" page, or code comments ("written by Claude", "AI-generated", …). Copyright holder is the
  repo owner only.
- **Before every push**, check the outgoing commits and the diff
  (`git log --format='%an <%ae>%n%cn <%ce>%n%B' origin/<branch>..HEAD` and a grep for
  `claude|anthropic|co-authored-by|generated with` in changed files and messages). If anything
  matches, fix it before pushing (amend/reword your own unpushed commits only).
- The tooling file `CLAUDE.md` is allowed (it is agent configuration, not attribution), but it must not
  credit Claude as an author.

---

## 1. Product vision

EVAC is a self-hostable, open-source **operations platform for events and venues**, built for any kind
of event: hacker camps, conferences, festivals, concerts, LARPs, conventions, corporate events and
permanent venues (clubs, halls, campuses) that host many events over time.

At its core, EVAC drives **every screen at a venue** (info beamers, TVs, projectors, LED walls, kiosks)
with **fully customizable content**, handles **announcements** across every channel, and runs a
**supplementary evacuation and alarm information system** that keeps working when the network or the
server fails. Around that core sit optional modules for venue maps, schedule, crew shifts, incidents,
crowd control, ticketing, inventory and the helpdesk. Integrations ("Extensions") connect EVAC to
existing tools, the first being **PET (Portable Event Telephone)**.

### Guiding principles (apply to every decision)

| Principle | Meaning |
|---|---|
| **Modular and optional by default** | Every module, every extension and nearly every feature can be switched on/off per instance and per event. Nothing in the core may hard-depend on an optional module. A minimal EVAC is "screens only". |
| **100 % customizable** | Fonts, colors, layouts, animations, texts, sounds and templates can all be changed: through the UI for normal users, through code (HTML/CSS/JS, plugins) for power users. Ship good defaults so nobody *has* to customize. |
| **Everything is a data source** | Every module and every extension can expose data to screens. Users can build widgets from any data source without writing code. |
| **Offline-first, fail-safe** | The venue keeps working with no uplink. Screens keep working with no server. Safety-relevant state never silently resets. |
| **Multi-event, multi-venue** | One permanent service hosts many events and venues; every event is isolated (tenancy under `/e/<slug>/`). |
| **Auditable** | Every state-changing action, above all alarm and evacuation actions, is written to an immutable audit log. |
| **Accessible** | WCAG 2.2 AA for all UI; evacuation content is legible from a distance and colour-blind safe. |

---

## 2. Safety statement (non-negotiable)

EVAC is a **supplementary information system**. It is **not** a certified fire alarm system, voice alarm
system or evacuation system (DIN 14675, DIN VDE 0833, EN 54 and similar do not apply, and EVAC must
never claim compliance). It **complements** the legally required systems and procedures and never
replaces them.

- State this clearly in the README, the operator handbook, the evacuation settings page and the first-run
  wizard (operators must acknowledge it once per event when enabling the evacuation module).
- Use **ISO 7010** safety pictograms (E001/E002 emergency exit, arrows, assembly point E007, and so on)
  as built-in assets. Ship them as SVG from a licence-compatible source, or draw them ourselves to the spec.
- Design as if lives depend on it anyway: redundancy, fail-safe defaults, tests and drills.

---

## 3. Tech stack and architecture

Match the conventions of the sibling project **PET** (`kirikakaese/PET-BETA`) so that code, operating
know-how and integration are natural. Read PET's `README.md`, `docs/ARCHITECTURE.md` and
`docs/DEVELOPING.md` for conventions before you start.

| Layer | Choice |
|---|---|
| Backend | **Python 3.12+, Django 5.2, Django REST Framework**, drf-spectacular (OpenAPI) |
| Database | **PostgreSQL 16** (SQLite only for dev and unit tests) |
| Async / jobs | **Redis + Celery + Celery beat** (durable outbox pattern for outgoing deliveries, like PET's `PBXJob`) |
| Realtime | **Django Channels** (ASGI, Daphne/Uvicorn) over WebSockets, with **SSE** fallback and long-poll as the last resort |
| Admin / staff UI | Server-rendered Django templates + **HTMX** + small vanilla/Alpine.js islands; dark mode; no inline handlers (strict CSP) |
| Rich editors | The **screen layout editor** and the **floor plan editor** are separate TypeScript apps (Vite build, framework of your choice; justify it in an ADR. Lit or Svelte preferred for small bundles), mounted as islands |
| Screen player | **One framework-light TypeScript bundle** (`/player/`), runs in any modern browser; Service Worker + IndexedDB for offline |
| Auth | E-mail login, argon2, **OpenID Connect SSO** (authorization code + PKCE, same approach as PET), **TOTP + WebAuthn 2FA**, scoped service tokens |
| Packaging | Dockerfile, `docker-compose.yml` (web, worker, beat, channels, postgres, redis), Ansible role, systemd units |
| Quality | pytest, pytest-django, Playwright (E2E for player, editor, evacuation), ruff, mypy (strict on the evacuation core), pre-commit, GitHub Actions CI |

### 3.1 Repository layout (mirror PET)

```
evac/                 settings (base/dev/prod/test), urls, asgi, celery
apps/core             audit log, feature flags, module registry, rate limiting, settings framework
apps/accounts         users, OIDC, 2FA, service tokens, GDPR export/delete
apps/events           events, lifecycle, memberships, roles, RBAC
apps/venues           venues, buildings, floors, rooms, zones, exits, routes, floor plans
apps/screens          screens, groups, pairing, player API, remote management
apps/designer         themes, fonts, assets, layouts, slides, templates, versioning
apps/widgets          widget registry, built-in widgets, data sources, custom widget builder
apps/playlists        playlists, schedules, overrides, priorities
apps/announcements    announcements, templates, approval, channels
apps/evacuation       alarm state machine, triggers, stages, routes, drills, acknowledgements
apps/notify           channel adapters (push, ntfy, Matrix, Telegram, Mastodon, e-mail, SMS via extensions)
apps/program          schedule/program, rooms, speakers, imports
apps/crew             volunteers, teams, shifts, skills, check-in
apps/ops              incidents, tasks, ops log, control room
apps/crowd            occupancy, counters, sensors, capacity rules
apps/access           ticketing / attendees / wristbands / access zones
apps/inventory        resources, lending, tracking
apps/helpdesk         lost & found, requests, FAQ
apps/extensions       extension framework + Extensions settings page
extensions/pet        the PET extension (first-party, removable)
extensions/…          further first-party extensions (pretalx, pretix, Engelsystem, Matrix, …)
apps/api              API root, auth, permissions, CLI (`evac`)
apps/portal           shared UI shell, navigation, dashboards
player/               screen player (TypeScript)
editor/               layout editor (TypeScript)
mapeditor/            floor plan / zone / route editor (TypeScript)
pwa/                  staff PWA shell (or part of portal; decide in ADR)
bridge/               reference hardware trigger bridge (Python for Pi + ESP32 sketch)
deploy/               compose, ansible, venue-node, kiosk images
docs/                 documentation (served inside the portal at /docs/, like PET)
```

### 3.2 Central service + venue node

Like PET, EVAC runs as **one permanent service under a fixed domain** hosting many events. Venues can
run an **EVAC venue node**: the same codebase in `EVAC_MODE=node`, on a small server or mini PC at the
venue, so that screens, announcements, evacuation and ops keep working without an uplink.

- An event can be **checked out** to a venue node. While checked out, the node is authoritative for
  **live operational state** (screen state, overrides, announcements, evacuation state, incidents,
  counters). Central remains authoritative for **configuration** (layouts, themes, users), and those
  changes sync down.
- Sync runs over HTTPS (outbound from the node, so no inbound ports are needed at the venue): versioned snapshots with
  ETags for config (as in PET's venue agent), an append-only event log with idempotency keys for
  operational data, and resumable asset sync (content-hashed files).
- Screens at the venue connect **to the node**, not to central (local DNS name or mDNS discovery,
  configured at pairing).
- Write **ADR-0002 "Central/node sync"** before implementing; ask for review.

### 3.3 Module, extension and plugin model

- **Module** = a built-in feature area (Screens, Announcements, Evacuation, Crew, …). Toggle under
  **Settings → Modules**, globally and per event.
- **Extension** = an integration with an external system (PET, pretalx, pretix, Matrix, …). Configured
  under **Settings → Extensions** (§7).
- **Plugin** = the packaging mechanism. Every module and extension, built-in or third-party, is a plugin:
  a Django app plus a `evac_plugin.toml`/`AppConfig` manifest registering models, URLs, nav entries,
  permissions, settings schema, data sources, widgets, notification channels, evacuation triggers,
  webhooks and CLI commands through a **stable registry API**. Third parties install plugins via pip
  (entry points `evac.plugins`). The core uses the same API, so the API is proven from day one.

---

## 4. Core platform (Phase 0)

- **Events**: lifecycle `draft → setup → live → teardown → archived`, scheduled transitions, cloning
  (with or without content), JSON export/import, per-event branding (name, logo, colours, default theme),
  time zone.
- **Venues** are reusable across events (a permanent venue hosts many events); an event references
  one or more venues.
- **Users and accounts**: e-mail login, invitations, OIDC SSO (Keycloak/Authentik/Zitadel/…; account
  linking by verified e-mail; optional SSO-only mode), TOTP + WebAuthn 2FA (**enforceable per role**;
  enforced by default for every role allowed to trigger alarms), GDPR export/delete.
- **RBAC, fine-grained**: built-in roles (admin, orga, control-room, security, helpdesk, crew, viewer)
  plus **custom roles per event**. Permissions are `module.action` strings and can be **scoped** to venues,
  zones, rooms, screen groups or teams (e.g. "may control screens in Hall B only", "may trigger
  pre-alarm in Zone North only"). Roles and permissions are editable in the UI.
- **Audit log**: append-only, tamper-evident (hash-chained rows), filterable and exportable. Every
  evacuation/alarm action, override, approval and permission change is logged with actor, time, scope,
  before/after.
- **Feature flags / settings framework**: a typed settings registry (JSON schema → auto-generated forms)
  with instance → venue → event → screen-group → screen inheritance and visible "overridden here" markers.
- **Service tokens** (`Authorization: Bearer evac_…`, hashed, scoped `<module>:read|write`, optional event
  binding and expiry), the same model as PET.
- **First-run wizard**: create admin → create venue → create event → pair the first screen → show the
  welcome slide. Under 5 minutes from `docker compose up` to a screen showing content.
- **Demo seed** (`EVAC_SEED_DEMO=1`): demo venue with floor plan, zones, exits, screens, themes,
  layouts, schedule, crew and announcements, so everything is clickable on a laptop (all demo content in English).

---

## 5. Info beamer / screen system (Phases 1–2)

### 5.1 Screen player

- Single TypeScript web app at `/player/`. It has to run on several kinds of client; ship them in this order:
  1. **Any browser in kiosk mode** (reference target; Chromium/Firefox/WebKit, TVs with a browser).
  2. **Raspberry Pi / mini-PC kiosk**: a provisioning script and an image recipe (Raspberry Pi OS Lite +
     Chromium kiosk + watchdog + auto-login + autoplay flags + hardware video decode), plus a
     `deploy/kiosk/README.md`.
  3. **OBS browser source / NDI**: a URL mode with transparent background and no cursor for
     streaming and video mixing setups.
  4. **Optional native wrapper** (later phase; Tauri preferred over Electron): watchdog, OS-level
     screenshots, display power control (CEC/DDC), autostart, local cache outside the browser.
  5. **info-beamer hosted package** (later phase, extension): a package that renders an EVAC
     screen URL or fetches EVAC data.
- **Pairing**: the player shows a short code and QR; staff enter or scan it in the admin and assign the
  screen to a venue/zone/room/group and a location on the floor plan (needed for evacuation arrows). The player
  receives a per-screen device token.
- **Offline**: the Service Worker caches the player app; IndexedDB caches the **content bundle** (layouts,
  themes, fonts, assets by content hash, data snapshots) and the **evacuation bundle** (§8.6). The player
  keeps playing the last known content with no server connection.
- **Realtime channel**: WebSocket (Channels) with SSE fallback; heartbeat every 10 s (configurable).
  The player reports app version, resolution, orientation, uptime, current slide, errors, memory, last sync,
  online/offline and evacuation state ack.
- **Server time sync** (NTP-like offset), so that **synchronised playback** across screens (same slide at the
  same moment, video walls) works.
- **Rendering engine**: a deterministic layout renderer shared by player and editor (same code, so the
  preview is pixel-identical to what screens show).
- **Resilience**: global error boundary per widget (a failing widget shows a fallback, never a blank
  screen), memory-leak guard (scheduled soft reload during idle slides), auto-recovery after crashes.

### 5.2 Screen management (all features switchable)

- Screens, **screen groups** (manual, or dynamic by tag/zone/room/venue), tags.
- Per-screen settings: resolution, orientation/rotation (0/90/180/270), **overscan/safe area** for
  projectors, scale, keystone hint, brightness/dim schedule (where hardware allows), power schedule,
  local audio on/off and volume, default playlist, emergency role (does this screen participate in
  evacuation, and is it audio-capable).
- **Remote management**: live screenshot thumbnails (periodic + on demand), reload, hard refresh,
  clear cache, **identify** (flash a big ID overlay), rename, move, re-pair, revoke, view logs,
  "show test pattern", "show evac self-test".
- **Health dashboard**: online/offline/stale, last heartbeat, version, errors, plus alerts when a screen
  goes offline (to the ops log and notification channels; thresholds configurable).

### 5.3 Design system: themes, fonts, assets

- **Themes** hold design tokens: colour palettes (light/dark variants), typography scale, spacing, radii,
  shadows, backgrounds (colour, gradient, image, video, animated), transitions, sound set and logos.
  Layouts inherit the event theme and can override any token. Tokens compile to CSS custom properties.
- **Fonts**: upload WOFF2/WOFF/TTF/OTF, including variable fonts with axis controls. Fonts are self-hosted
  (no Google Fonts at runtime, which would fail offline), with optional subsetting, fallback stacks, per-element font
  family/weight/style/size/letter-spacing/line-height/text-transform/features (ligatures, tabular
  numbers), and a font licence note field. Ship a curated set of open-licence fonts by default (one with
  excellent legibility for the evacuation templates, e.g. Atkinson Hyperlegible or Inter).
- **Asset library**: images, SVG, video, audio, PDF, Lottie; content-hashed storage, automatic
  transcoding/optimisation (thumbnails, WebP/AVIF, H.264/VP9 fallbacks, audio normalisation),
  folders, tags, usage tracking ("used in 3 layouts"), per-event and global/shared libraries.

### 5.4 Layout editor ("100 % customizable")

Three authoring levels, all producing the same stored layout format:

1. **Visual drag-and-drop editor**
   - Canvas at the target resolution with zoom, rulers, guides, grid and snap; preview at several
     resolutions and orientations at once.
   - Elements: text, rich text, image, video, shape, icon/pictogram, container (free/absolute,
     flex, grid), widget, embedded layout (component), HTML block.
   - **Responsive constraints** (anchors, min/max, aspect lock, auto-layout containers), so one layout
     adapts to 16:9, 9:16, 4:3, 32:9 LED strips and custom resolutions.
   - Per-element styling: every CSS-relevant property exposed in a property panel (font, colour, border,
     background, filters, opacity, blend mode, shadow, padding, …), bound to theme tokens or set freely.
   - **Text features**: auto-fit (shrink text to box), line clamp, marquee/ticker, template variables.
   - **Animations**: entrance/exit/emphasis animations, slide transitions, timing curves, and the ability to
     respect `prefers-reduced-motion` and a global "no animation" switch.
   - Layers panel, groups, lock/hide, multi-select, align/distribute, copy/paste between layouts,
     keyboard shortcuts, **undo/redo**.
   - **Versioning**: every save is a version, with diff view, rollback, draft vs. published, and
     "scheduled publish".
   - **Collaborative editing is not required**; use optimistic locking with a clear "someone else is
     editing" notice.
2. **Theme/token level**: change the event look globally without touching layouts.
3. **Raw code mode** (permission-gated): HTML + CSS + JS per slide, template or widget, with a code
   editor (CodeMirror) and live preview. Runs in a **sandboxed iframe** with a strict CSP and no network
   except allowlisted origins. It gets data only through a documented `postMessage` data API (the same
   one widgets use).

- **Template variables and expressions**: `{{event.name}}`, `{{screen.zone.name}}`, `{{now|time}}`,
  `{{program.room.current.title}}`, `{{data.<source>.<path>}}`, with filters (date/time formatting,
  truncate, upper, default) and conditions (`if`/`else`) for showing or hiding elements.
- **Template marketplace / sharing**: export and import layouts, themes, widget configs and whole
  "screen packs" as signed `.evacpack` files (zip + manifest + assets + hashes); a gallery of built-in
  packs; optional import from a URL; an instance-wide shared library across events.

### 5.5 Widgets and data sources

**Widget contract** (used by built-in widgets, extensions and third-party plugins alike):

- `manifest`: id, name, version, icon, description, **settings JSON schema** (auto-generates the
  settings form in the editor), required data sources, supported sizes, refresh policy, offline
  behaviour.
- `renderer`: a Web Component (custom element) receiving `settings`, `data`, `theme`, `screen`
  context; must render a sensible fallback when data is missing or stale (with a stale indicator
  that is visible only to staff, never to the public).
- **Data source** contract: id, schema of the data, fetch/push mode (poll interval, webhook, websocket,
  MQTT), caching/TTL, offline snapshot, and permission scope. **Every module and every extension
  can register data sources and widgets.**

**No-code custom widget builder**: pick any data source (built-in, extension, generic HTTP JSON,
RSS, iCal, MQTT topic, CSV/Google-Sheet export URL), explore the data with a tree view, map fields
(JSONPath), choose a visual (text, list, table, card grid, counter, gauge, chart, ticker, map pin),
and style it in the layout editor. Save it as a reusable widget available to the whole event or
instance.

**Built-in widgets (minimum set)**

| Category | Widgets |
|---|---|
| Basic | text, rich text, image, image slideshow, video, audio, shape, ISO 7010 pictogram, QR code, iframe/web page, PDF page(s) |
| Live media | HLS/DASH livestream, WebRTC/WHEP stream, local camera/capture (for kiosk wrappers) |
| Time | clock (analog/digital, multiple time zones), countdown/count-up, date, timeline |
| Info | ticker/news crawl, RSS/Atom, Mastodon/Fediverse wall (with moderation queue), announcement banner, FAQ rotator, weather (Open-Meteo, cached offline), sun/moon times |
| Program | now/next per room, room schedule, full-day grid, speaker card, "starting soon", schedule changes ticker |
| Venue | floor plan with "you are here", wayfinding arrow to a target, room occupancy/"room full", evacuation route arrow (§8) |
| Ops | shift board ("needed now"), crew call ("Team X to Desk"), lost & found highlights, open helpdesk queue (staff screens) |
| Data | generic JSON value/list/table, MQTT value, chart (line/bar/gauge), counter |
| PET (via extension) | important numbers, "call 1234 for …", phonebook highlights, DECT network status, PET info pages |

### 5.6 Playlists, scheduling and overrides (all optional and switchable)

- **Playlists**: ordered or weighted slides with per-slide duration, conditions (only show if data
  non-empty, only on screen tag Y), shuffle, and nested playlists.
- **Scheduling**: rules like "Stage screens 18:00–20:00 → Concert playlist", recurring and day-specific
  slots, date ranges, priority resolution, a calendar view of what each screen group shows when, and
  a "preview any screen at any time" tool.
- **Live overrides**: push a slide, layout, playlist or announcement to one screen, a group, a zone or
  everything, instantly, with **priority levels** (§6), expiry time or "until cancelled",
  and a clear list of active overrides with one-click cancel.
- Priority order (highest wins): **evacuation/alarm > emergency announcement > live override >
  urgent announcement > schedule > default playlist**. Configurable below the evacuation level;
  evacuation is always highest.

---

## 6. Announcements (Phase 2)

- **Priority levels** (configurable names, colours, sounds, templates): default `info`, `important`,
  `urgent`, `emergency`. Each level defines the display style (banner/ticker, overlay card,
  full takeover), sound/gong, minimum display time, repetition, and which channels it uses by default.
- **Templates** with variables (e.g. "Lost child: {{description}} — please contact {{desk}}",
  "Doors open in {{minutes}} min", "Severe weather warning"). Templates can carry a pre-designed layout.
  All built-in templates are English.
- **Scheduling**: send now, at a time, recurring, or relative to program items ("10 min before
  {{talk}}").
- **Targeting**: everything, venues, zones, rooms, screen groups, single screens, and
  per-channel audiences (crew teams, roles, attendee groups).
- **Approval workflow** (optional per event and per level): helpers draft → orga approves/edits/rejects;
  approver roles configurable; `emergency` level and evacuation **bypass approval** for permitted roles.
- **Multi-channel delivery** via `apps/notify` channel adapters (each optional): screens, public web
  page/PWA feed, Web Push (VAPID), ntfy, e-mail, Matrix, Telegram, Mastodon/Fediverse, generic webhook,
  and through the **PET extension**: DECT SMS / phone broadcast / IVR announcement. Each channel has a
  per-channel text variant (short text for SMS, long text for web), delivery status tracking
  through a durable outbox with retries, and a delivery report.
- **TTS**: optional offline TTS (Piper, English voice) to generate audio for screens with speakers and
  for PET phone broadcasts; pre-render and cache.
- Everything is archived and searchable, can be re-sent, and is exported in the event export.

---

## 7. Extensions framework and the Extensions settings page (Phase 0 framework, extensions in later phases)

Build the extension framework **and the Settings → Extensions page in Phase 0**, so that every later
integration plugs into it.

- **Settings → Extensions** (global for admins, per event for orgas): a card grid of available
  extensions with status (not configured / enabled / disabled / error), description, version and
  required permissions.
- **Per-extension settings page**, generated from the extension's settings schema plus optional custom
  views. It contains connection settings, **secrets stored encrypted at rest** (Fernet/libsodium key from
  env, never shown again after save), a **"Test connection" button**, health status, last sync and
  error log, a **feature toggles** section listing what this extension contributes (data sources,
  widgets, triggers, channels, imports) so each can be enabled individually, a webhook URL + secret
  display for inbound webhooks, and a "disconnect & purge data" action.
- Extensions can be instance-wide (configured once, used by many events) or per event (each event
  links its own external instance).
- Planned first-party extensions (each its own phase/ticket): **PET** (§9), **pretalx / frab / iCal**
  (program import), **pretix** (ticketing/check-in), **Engelsystem** (crew/shifts import), **Matrix**,
  **Telegram**, **ntfy**, **Mastodon**, **SMTP**, **generic webhooks in/out**, **MQTT broker**,
  **OIDC IdP** (shared with PET), **Open-Meteo weather warnings**, **info-beamer hosted**.

---

## 8. Evacuation and alarm system (Phase 3)

The entire module is optional (off by default and enabled per event, with the §2 safety
acknowledgement). Every trigger type is optional too.

### 8.1 Selectable evacuation models (per event, switchable)

1. **Simple takeover**: one button; every participating screen switches to the full-screen evacuation
   layout until cancelled.
2. **Staged, global**: stages applied to the whole event, the same message everywhere, with an
   optional fixed exit hint per screen (text/arrow configured per screen).
3. **Zones and routes**: the venue is divided into zones (§10); each screen knows its location; exits
   and routes are modelled; each screen shows a **direction arrow and text to the nearest open
   exit/assembly point**; exits can be **blocked live** (routes recompute instantly); **partial
   evacuation** of individual zones is possible.

### 8.2 States / stages

Configurable per event, with sensible defaults:

| State | Default meaning |
|---|---|
| `normal` | regular content |
| `staff_alert` (pre-alarm) | silent: staff channels only (PWA, ntfy, PET SMS), screens unchanged or a discrete staff-only marker |
| `attention` | public "please pay attention to announcements" overlay |
| `shelter_in_place` | stay inside / severe weather layout |
| `evacuate` | full evacuation layout with routes |
| `all_clear` | "all clear" layout for a configurable time, then back to `normal` |

- Implement this as an explicit, **persisted state machine** per event and per zone (zone states
  override the event state for screens in that zone; "highest severity wins").
- **Drill mode**: any state can run as a drill. Screens show a clearly visible "DRILL" marker
  (text configurable), notifications are prefixed, and the audit and reports keep drills separate.
- **Never auto-clear**: no state goes back to `normal` by timeout, reconnect or restart; only an
  explicit `all_clear` by an authorised person does that.

### 8.3 Triggers (all optional, configurable per event)

- **Manual, web**: control room page and a mobile **panic page** in the PWA, both with a big confirm
  slider/hold-to-confirm, zone selection and stage selection.
- **Two-person rule** (optional per stage): a second authorised person confirms within N seconds.
- **Hardware bridge**: reference implementation in `bridge/` for Raspberry Pi GPIO / an ESP32 (dry
  contact from a fire alarm panel relay, physical mushroom buttons, key switches). It talks to the node
  via authenticated MQTT or HTTPS and supervises its line (a heartbeat, so a dead bridge raises an alert).
- **PET**: `emergency.triggered` webhook or a configured feature code (via the PET extension, §9).
- **API / MQTT**: authenticated endpoint for external systems (BMA gateways, weather warnings,
  other tools).
- **Scheduled drills**.
- Each trigger source has a **policy**: `execute` (switch immediately), `arm` (raise an alarm to the
  control room, which must confirm within N seconds, with optional auto-escalation if nobody responds)
  or `notify only`. Policies are per source, per stage and per zone.

### 8.4 Evacuation content

- Evacuation layouts are built with the normal editor (fully customizable), **with guardrails**:
  minimum contrast check, minimum text size relative to screen size and viewing distance,
  required elements (pictogram + text + arrow for the zone model), and a linter that shows warnings
  in the editor and blocks publishing for hard failures.
- A **built-in, non-deletable fallback evacuation layout** (ISO 7010 pictograms + English text) is always
  cached on every screen and used if a custom layout fails to render or is missing.
- **Text/pictogram rotation**: an evacuation layout can cycle through several operator-written text
  variants (cycle time configurable), plus a pictograms-only option. Built-in text is English only;
  any additional variants are content the operator writes.
- Arrows are computed per screen from its position/orientation on the floor plan to the
  next waypoint, with manual per-screen override ("arrow left, text 'Exit B'").
- **Audio/PA**: screens with speakers play the configured gong/siren and pre-rendered messages (TTS or
  recordings) in a loop; kiosk setup docs cover autoplay flags. Optional PA integration: relay output
  via the hardware bridge, and phone broadcast via PET.

### 8.5 Propagation and notifications

- On a state change, push immediately to all affected screens, the staff PWA (Web Push + in-app
  alarm with sound/vibration, overriding silent mode where the platform allows), ntfy, Matrix,
  Telegram, e-mail, and **PET** (emergency broadcast: phone announcement + DECT SMS).
- Target latency: **≤ 2 s from trigger to rendered state on 95 % of online screens on the LAN**,
  measured and shown.
- **Acknowledgements**: every screen confirms "evac layout rendered" (with the version hash). The control
  room sees a live **"X of Y screens confirmed / Z offline"** view and a per-zone breakdown; staff can
  acknowledge alarms in the PWA ("I'm on it", "zone clear"), and zone-clear reports feed the control room.

### 8.6 Fail-safe behaviour

- Every participating screen keeps an **evacuation bundle** in cache: all stage layouts, its own
  routes for every combination of blocked exits it can precompute (or a minimal on-device route
  computation), fonts, pictograms and audio.
- If a screen loses its connection while in an alarm state, it **stays** in that state. If it loses
  its connection in `normal`, it keeps playing normal content and shows a staff-only offline marker.
- The venue node is the authority during a live event. The fallback when the node dies: screens accept
  signed state messages from a **secondary node** or the hardware bridge over the LAN (signed with the
  event's alarm key; design this in ADR-0003, "Alarm delivery redundancy").
- **Watchdog**: missing heartbeats raise alerts; a dashboard shows each screen's evac readiness
  (bundle version current? audio OK? last self-test?).
- **Self-test**: a scheduled or on-demand per-screen test that renders the evac layout briefly
  (or in a staff-only preview) and reports back.

### 8.7 Testing requirements (hard gate for Phase 3)

- Unit tests for the state machine (every transition, permission and two-person/arm timeout).
- Property tests for routing (blocked exits, unreachable zones produce a "follow staff instructions" fallback).
- Playwright E2E: trigger → screens render evac → ack → all-clear.
- **Chaos tests**: kill the web/channels process during an evacuation; screens must remain in the evac state;
  restart; state resumes; no auto-clear. Network partition simulation for player and node.
- Load test: 500 simulated players (WebSocket) receive a state change within the latency target.

---

## 9. PET extension (Phase 4): "small but deep"

PET (`kirikakaese/PET-BETA`) is a Django/DRF event phone network manager. **Read PET's `docs/API.md`
and its OpenAPI schema (`/api/schema/`) before implementing**, and verify every endpoint and payload
below against them. The extension lives in `extensions/pet`, can be disabled, and nothing outside it
imports it.

**Link configuration (per EVAC event, Settings → Extensions → PET)**
- PET base URL, PET event slug, **PET service token** (`Authorization: Bearer pet_…`, minted at
  `/e/<slug>/orga/tokens/`; document the needed scopes, e.g. `pages:read`, `phonebook:read`,
  `dect:read`, `emergency:*`), webhook secret.
- "Test connection" calls PET `GET /api/v1/health/?event=<slug>` and `GET /api/v1/me/`.
- EVAC shows the inbound webhook URL to paste into PET (`/e/<slug>/orga/webhooks/`).

**Inbound webhooks** (`POST /api/v1/extensions/pet/<link-id>/webhook/`)
- Verify `X-PET-Signature: sha256=<HMAC-SHA256(raw body)>` with constant-time comparison; dispatch on
  `X-PET-Event`; payload envelope `{type, sent_at, data}`; idempotent handling.
- `emergency.triggered` → evacuation trigger (policy per §8.3: execute / arm / notify).
- `page.updated` → refresh the PET info page data source.
- `announcement.recorded` (`data = {extension, event, audio, file, duration, imported}`) → **"announce
  by phone"**: an orga calls PET, records a message, and EVAC imports the audio, optionally transcribes
  it (offline Whisper, English model, optional), and creates a **draft announcement** in the approval queue
  (or auto-publishes when the calling extension is on an allowlist with auto-publish enabled).
- `dect.rfp.down|rfp.up|sync.degraded` → DECT status data source + ops log entries.

**Outbound**
- Evacuation/emergency announcements → PET `POST /api/v1/emergency/broadcast/`
  (`{event, announcement, group?}`): rings handsets with the announcement. Messaging broadcast
  (`POST /api/v1/messaging/broadcast/`) for DECT SMS where PET has the `messaging` flag enabled.
- Delivered through the durable outbox, with retries, status shown in the announcement delivery report.

**Data sources and widgets**: phonebook (search, highlights), important/emergency numbers,
PET info pages (Markdown rendered), DECT network status, and a "call X for Y" widget.

**SSO**: document and support using the **same OIDC IdP** for EVAC and PET; optionally map PET event
roles to EVAC roles (manual mapping table, no automatic privilege escalation).

---

## 10. Venue and floor plans (Phase 3, before evacuation zones)

- Hierarchy: venue → site/building → floor → room/area, with **zones** (may cross rooms, may be
  outdoor), **exits**, **assembly points**, **doors/waypoints**, capacities and accessibility attributes
  (step-free route, lift, wheelchair spaces).
- **Map editor** (`mapeditor/`): upload a floor plan (PDF/SVG/PNG, scaled and georeferenced) or use
  OpenStreetMap tiles (cached for offline use) for open-air sites; draw zones, place exits, waypoints and
  screens (position + facing direction), draw route graph edges.
- The route graph is used for evacuation arrows, wayfinding widgets and the "you are here" map.
- Live layers: blocked exits, occupancy, incidents, screen status (control room map).

---

## 11. Further modules (Phases 5–8, each optional)

### 11.1 Schedule / program
Rooms/stages (linked to venue rooms), sessions, speakers, tracks, live changes
(delays, cancellations, room changes) pushed instantly to screens and to a public schedule page and
feeds (iCal, JSON, frab XML-compatible export). **Import/sync** from pretalx, frab/Pentabarf XML and iCal
via extensions, with conflict handling (local overrides survive re-sync).

### 11.2 Crew and shifts
Volunteers ("angels"), teams, team leads, shift types, shifts with needed headcount and skills/
certifications (first aid, forklift, …), self sign-up with rules (max hours, rest time), check-in/out
(QR on the PWA), "needed now" board on screens, no-show handling, and an Engelsystem import extension. Crew
calls ("Team Build to Info Desk") are sent as announcements to team channels.

### 11.3 Incidents and control room
Incident log (security, medical, technical, lost child, …) with categories, severity, location
(map pin/zone), assignment, status, timeline, attachments and linked announcements/evacuations; a
radio-style **ops log**; tasks; and a **control room dashboard** (single page, large-screen friendly) with map,
active alarms, open incidents, screen health, occupancy, PET/DECT status and recent announcements.
Configurable incident escalation to notification channels. Export for post-event reports.

### 11.4 Crowd and occupancy
Live headcount per zone/room from a **manual counter** (PWA clicker for door staff: in/out, multi-device
aggregation, offline queue), sensors (generic MQTT/HTTP counter input) and ticket scanner check-ins
(access module). Capacity rules with thresholds, so screens automatically show "Room full / use Hall C",
staff get alerts, and occupancy history is charted.

### 11.5 Ticketing and access
**pretix extension** (attendee/check-in sync) **or** EVAC's own lightweight attendee lists: ticket
types, wristbands/badges (print templates using the layout editor), check-in app (QR, offline), access
zones (backstage, crew-only) with scanner rules and occupancy feed.

### 11.6 Resources and inventory
Items (radios, keys, vehicles, tools, laptops, …), categories, serial/asset tags with printable QR labels,
lend/return with signature/photo, who-has-what view, due-back reminders, maintenance notes, and
locations on the map.

### 11.7 Lost and found / helpdesk
Lost & found with photos, categories, storage location, claim process, matching of found items to
lost reports, privacy-aware public listing; attendee requests/tickets; and a FAQ (rendered on screens and
the public page).

---

## 12. Staff PWA (basic in Phase 2–3, full in Phase 9)

Installable, offline-capable PWA for crew: alarm reception with full-screen alert and sound,
panic page (permission-gated), announcements (send/approve), incidents, counter clicker, shift
check-in, inventory scan, lost & found entry, and my shifts. Web Push (VAPID) plus ntfy as fallback.
Offline queue for actions, with clear sync state.

---

## 13. Cross-cutting requirements

**Language**: the whole build is **English only**: UI, emails, PWA, docs, demo data, built-in
templates, fallback evacuation layout, TTS voice. **No German (or any other) locale or translation
files are created.** UI strings are still wrapped in Django `gettext`/JS message helpers so a locale
could be added later without refactoring, but only `en` is configured in `LANGUAGES`. Layouts support
RTL text rendering for operator-entered content.

**Accessibility**: WCAG 2.2 AA in admin, PWA and public pages; automated a11y checks in the test suite
(as PET's `pet_a11y`); keyboard navigation; reduced motion; high-contrast mode; colour-blind-safe status
colours (never colour only).

**Security**: strict CSP; CSRF; argon2; rate limits; 2FA enforcement for alarm roles; scoped tokens;
per-screen device tokens (revocable); encrypted secrets; signed `.evacpack` files; sandboxed custom
code; HMAC on all webhooks in and out; dependency audit in CI; threat model doc (`docs/SECURITY.md`)
with special attention to **"who can make every screen say anything"** and **false evacuation alarms**.

**Privacy / GDPR**: data minimisation, retention policies per module (auto-purge after the event),
GDPR export/delete, privacy notes for counters/sensors (no personal data in occupancy).

**API**: complete REST API (DRF) for every module + OpenAPI + Swagger/ReDoc; outbound webhooks
(HMAC, retries, delivery log) for all important events (`evac.state_changed`, `announcement.published`,
`screen.offline`, `incident.created`, …); realtime subscription API (WebSocket) for integrations;
**CLI** `evac` (tokens, export/import, screens, announcements, trigger drill).

**Observability**: structured logs, Prometheus metrics (screens online, evac propagation latency, outbox
depth), health endpoints, Sentry-compatible error reporting (optional).

**Performance targets**: 1,000 screens per instance, 200 per venue node on a Raspberry Pi 5–class
device, admin pages < 300 ms server time, player bundle < 300 kB gzipped (excluding widgets loaded on
demand).

---

## 14. UI/UX

- One shell: top bar (event switcher, search, notifications, user), sidebar generated from enabled
  modules, dark/light mode, responsive down to phone width.
- Dashboards: per event (what's on screens now, active overrides, alarms, health) and the control room (§11.3).
- "Preview as screen" everywhere content is edited.
- Empty states that teach; contextual help linking into the in-portal docs.
- Destructive and safety actions: explicit confirmation, hold-to-confirm for alarms, and undo where possible.
- The "About" page credits the repository owner only (§0.1).

---

## 15. Documentation (English only; grows with every phase, served in-portal at `/docs/`)

`README.md`, `docs/ARCHITECTURE.md`, `docs/OPERATOR_HANDBOOK.md` (running EVAC at an event, the venue
node, kiosk setup, evacuation drills, the safety statement), `docs/DESIGNER_GUIDE.md` (themes, fonts,
editor, widgets, code mode), `docs/EVACUATION.md` (models, states, triggers, fail-safe, testing,
limitations), `docs/EXTENSIONS.md` + one page per extension (PET first), `docs/PLUGIN_SDK.md`,
`docs/API.md`, `docs/SECURITY.md`, `docs/DEVELOPING.md`, `docs/adr/`, `CHANGELOG.md`.
No document carries an AI byline or credit (§0.1).

---

## 16. Testing and CI

- pytest for everything server-side; ≥ 85 % coverage overall, **≥ 95 % on `apps/evacuation`**.
- Playwright E2E: pairing, editor round-trip (edit → publish → screen shows it), override, announcement
  approval, evacuation flows, offline player.
- Visual regression snapshots for built-in layouts and the fallback evac layout.
- Load/chaos tests (§8.7) runnable locally via `make` targets and nightly in CI.
- CI: lint (ruff, eslint), type checks (mypy, tsc), tests, a11y check, OpenAPI drift check, Docker build,
  and an **attribution check** that fails if commit messages or tracked files contain
  `Co-Authored-By`, "Generated with Claude", or Claude/Anthropic credits (§0.1; allowlist `CLAUDE.md`'s
  filename and this check's own pattern list).
- Makefile targets mirroring PET: `dev`, `migrate`, `seed`, `run`, `test`, `lint`, `openapi`, `e2e`,
  `load`, `chaos`.

---

## 17. Phased roadmap (each phase ends with: green CI, docs, CHANGELOG, attribution check, commit, push, summary, pause)

| Phase | Scope | Acceptance gate |
|---|---|---|
| **0 Foundation** | Scaffold, Docker Compose, CI (incl. attribution check), settings framework, accounts (e-mail, OIDC, 2FA, tokens), events + venues (basic), RBAC + scopes, audit log, module registry + **Settings → Modules**, plugin registry API, **extension framework + Settings → Extensions page** (with a generic webhook extension as proof), translatable-string setup (English only), UI shell, API skeleton + OpenAPI, CLI, in-portal docs, demo seed, `CLAUDE.md`, ROADMAP, ADRs 0001–0003 | `docker compose up` → wizard → logged-in admin with event; all toggles work; tests green |
| **1 Screens core** | Player (browser kiosk + OBS mode), pairing, groups, themes, **fonts**, assets, layout editor (visual + tokens + code mode), widget contract + basic widgets, playlists, scheduling, overrides, remote management, offline caching, time sync, Pi kiosk recipe | Pair a screen, design a slide with an uploaded font, publish, override, unplug the network: the screen keeps playing |
| **2 Announcements** | Priorities, templates, approval, scheduling, targeting, notify channels (Web Push, ntfy, e-mail, Matrix, Telegram, Mastodon, webhook), offline TTS, staff PWA basics, custom widget builder, `.evacpack` import/export | One announcement reaches screens + 3 channels with a delivery report; approval flow tested |
| **3 Venue + evacuation** | Floor plan/map editor, zones, exits, routes; evacuation module (all three models, states, drills, triggers incl. hardware bridge, policies, two-person rule, guardrail linter, fallback layout, text rotation, audio, acks, fail-safe, watchdog, self-test), venue node mode + sync | All tests in §8.7 pass; a documented drill runbook works end to end |
| **4 PET extension** | Everything in §9 | Against a running PET demo instance (`docker compose up` in PET-BETA): webhook → evac arm; evac → PET broadcast; phone-recorded announcement → approval queue; PET widgets render |
| **5 Program** | Program module + pretalx/frab/iCal extensions + program widgets | Imported schedule shows now/next on screens; live change propagates < 5 s |
| **6 Ops + crowd** | Incidents, ops log, control room dashboard, occupancy (counter PWA, MQTT sensors, capacity rules → screens) | "Room full" appears automatically at the threshold |
| **7 Crew, inventory, helpdesk** | §11.2, §11.6, §11.7 + Engelsystem extension | Shift board on screens; lend/return with QR |
| **8 Access** | §11.5 + pretix extension | Offline check-in syncs; access zone counts feed occupancy |
| **9 Hardening and ecosystem** | Full staff PWA, public plugin SDK + docs + example plugin, template gallery, Tauri player wrapper, info-beamer hosted package, performance/load tuning, security review, operator handbook polish | 1,000 simulated screens; SDK example plugin adds a widget + data source + extension page without core changes |

---

## 18. Definition of done (every feature)

- Behind its module/extension/feature toggle, off-switch tested.
- Permission-checked (including scopes) and audit-logged where state changes.
- Has an API endpoint (if it's data), a UI, docs and tests; all user-facing text is English and wrapped
  as translatable strings.
- Works offline at the venue node (or degrades gracefully with a visible indication).
- Accessible (passes the automated a11y check).
- No regressions in evacuation tests.
- Commits authored solely by the repository owner; attribution check passes (§0.1).

---

## 19. Assumptions (flag if wrong, don't block on them)

- Single organisation per instance; multi-organisation billing/SaaS features are out of scope.
- Video walls (one layout spanning several synchronised screens) are a stretch goal in Phase 9.
- Hardware trigger bridge firmware is a reference implementation, not a certified product.
- Speech-to-text and TTS run locally (Whisper/Piper, English models) and are optional downloads, not
  baked into the default image.
