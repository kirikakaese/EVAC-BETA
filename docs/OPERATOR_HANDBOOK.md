# Operator Handbook

How to install and run EVAC for one or many events. This handbook grows with every phase; sections for
screens, announcements, evacuation drills and the kiosk image are added when those modules ship.

## Safety statement

EVAC is a **supplementary information system**. It is not a certified fire alarm, voice alarm or
evacuation system and does not comply with DIN 14675, DIN VDE 0833, EN 54 or similar standards. It
complements, and never replaces, the legally required systems and procedures of your venue. Operators
acknowledge this once per event when they enable the evacuation module (phase 3).

## 1. Installation

### Docker Compose (single server or laptop)

```sh
cp .env.example .env
# edit .env: SECRET_KEY, EVAC_SECRETS_KEYS, EVAC_PUBLIC_URL, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
docker compose up --build -d
docker compose logs -f web
```

| Service | Role | Port |
|---|---|---|
| `web` | HTTP pages, API, SSE (gunicorn + ASGI workers); runs migrations on start | 8000 |
| `channels` | WebSockets (Daphne) | 8001 |
| `worker` | Celery: outbox deliveries, background jobs | – |
| `beat` | Celery beat: outbox drain (5 s), scheduled lifecycle transitions (60 s), purges | – |
| `db` | PostgreSQL 16 | – |
| `redis` | cache, Celery broker, channel layer | – |

Generate keys: `docker compose run --rm web python manage.py evac_genkey` (put it into
`EVAC_SECRETS_KEYS`). **Back up this key with the database** — without it stored secrets (extension
credentials, TOTP seeds) cannot be decrypted.

### One server for EVAC and DIAL (production)

`deploy/server/` contains a complete setup for running EVAC and DIAL side by side on one fresh
Debian/Ubuntu server: bootstrap script (Docker, Caddy, firewall), compose overrides binding both apps to
localhost, a Caddyfile with automatic HTTPS, production `.env` values and nightly backups. Follow
`deploy/server/README.md`.

### Behind a reverse proxy (production)

Terminate TLS in Caddy or nginx. Route `/ws/` to `channels:8001` (WebSocket upgrade), everything else to
`web:8000`; leave `EVAC_REALTIME_URL` empty and set `SESSION_COOKIE_SECURE=1`, `CSRF_COOKIE_SECURE=1`.

```caddy
evac.example.org {
    reverse_proxy /ws/* 127.0.0.1:8001
    reverse_proxy 127.0.0.1:8000
}
```

### Ansible / systemd

`deploy/ansible/roles/evac` installs EVAC into `/opt/evac` with the units from `deploy/systemd/`
(`evac.target` groups web, channels, worker and beat). See `deploy/ansible/README.md`.

### Early access (public server, not public yet)

Set `EVAC_EARLY_ACCESS_PASSWORD` before the server is reachable from the internet. Every visitor then has
to enter that password once per browser (valid `EVAC_EARLY_ACCESS_DAYS`, default 30) before they see
anything — including the first-run wizard. Share the password with your team; change it to lock everyone
out again; remove it to go public. Health probes, `/metrics`, signed webhooks and API calls with a service
token keep working. Optional `EVAC_EARLY_ACCESS_MESSAGE` replaces the text on the gate page.
([ADR-0012](adr/0012-early-access-gate.md))

## 2. First run

Open EVAC in a browser. Until the first account exists every page redirects to the **first-run wizard**:

1. **Admin account** — the instance administrator. If the server is reachable by others before you finish,
   set `EVAC_SETUP_TOKEN` and enter it here.
2. **Venue** — where it happens (can be skipped; venues are reusable across events).
3. **Event** — name, short name (used in URLs: `/e/<short name>/`), time zone, dates.
4. **First screen** — follows later in phase 1.

The wizard cannot be re-run once an account exists.

## 3. Events

- **Lifecycle**: Draft → Setup → Live → Teardown → Archived. One step back is allowed to correct mistakes.
  Archiving needs the `events.delete` permission (admin role, two-factor verified session).
- **Scheduled transitions**: *Event settings → Lifecycle → Schedule*; beat applies them within a minute.
- **Clone**: copies settings, roles, module switches and venues; optionally members (and, later, module
  content). Extension secrets are never copied.
- **Export / import**: JSON with event, roles, members (by e-mail), module switches, settings and the venue
  structure. Import reuses venues with the same short name and reports members without an account.

## 4. People, roles and two-factor authentication

- **Members** are added by e-mail: existing accounts get the role at once, new addresses receive an
  invitation link (valid 7 days, `EVAC_INVITATION_TTL_HOURS`).
- **Built-in roles**: admin, orga, control-room, security, helpdesk, crew, viewer. Custom roles combine
  permissions with patterns such as `screens.*`, `*.view` or `!events.delete`.
- **Scopes**: a role can be limited to a venue, zone or room ("may control screens in Hall B only").
- **Two-factor authentication** (authenticator app or security key, plus recovery codes) is **required**
  for admin, orga, control-room and security by default. Without it those roles are inactive and a banner
  says so. Alarm-relevant (*sensitive*) permissions always need a two-factor verified session, also for
  instance admins. Admins can reset a user's second factors under *Instance → Users*.
- **Single sign-on**: set `EVAC_OIDC_*` (redirect URI `<EVAC_PUBLIC_URL>/accounts/oidc/callback/`). EVAC
  and DIAL can use the same identity provider. Accounts are linked by verified e-mail address;
  `EVAC_OIDC_ALLOW_PASSWORD_LOGIN=0` makes SSO the only login. `EVAC_OIDC_TRUST_MFA=1` accepts the IdP's
  multi-factor login (`amr` claim) as EVAC two-factor.

## 5. Modules and settings

- **Instance → Modules** switches modules for the whole instance; **Event → Modules** switches them off (or
  back to the instance setting) per event. Pages, navigation and API of a module disappear when it is off.
- **Settings** are typed and inherited: instance → venue → event → screen group → screen. Pages show
  whether a value is *overridden here* or *inherited*.

## 5a. Screens

- **Pair**: open `<your EVAC>/player/` in the screen's browser (kiosk mode, TV browser, Raspberry Pi). It shows
  a six-character code and a QR code. Under *Screens → Pair a screen* type the code (or scan the QR with your
  phone), give the screen a name, a place (venue, zone, room), groups and tags. The screen receives its own
  device token and connects. Codes are valid for 30 minutes.
- **Re-pair** (new hardware, next event): *Screen → Re-pair to a new device*; the old device stops working.
  **Revoke token** stops a lost or stolen device at once.
- **Health**: the screen list shows *online* (heartbeat within three intervals), *stale* and *offline*
  (after *Settings → Screens → Offline after*, default 60 s). Going offline notifies everyone who manages the
  screen (switchable) and sends the `screen.offline` webhook.
- **Groups**: manual groups list screens; dynamic groups also take every screen with a tag or in a venue,
  zone or room. Roles can be limited to a screen group ("may run the foyer screens only").
- `/player/` works behind the early-access password: screens use their device token instead.
- **Identify** flashes the screen's name on the screen for 10 seconds; **Reload player** reloads it.
- The player keeps its app and the last configuration offline: after a power cut without network it
  starts again and shows the last known content. `/player/?mode=obs` has a transparent background and no
  cursor, for OBS browser sources and video mixers.
- Kiosk browsers should start `/player/` in full screen with autoplay allowed (Chromium:
  `--kiosk --autoplay-policy=no-user-gesture-required`); a Raspberry Pi recipe follows in `deploy/kiosk/`.

## 5b. Design & assets

- **Themes** (*Design & assets → Themes*): colours for dark and light mode, fonts, text sizes, spacing, corner
  radius, shadows, background (colour, gradient, image), logo and slide transitions. A theme can inherit
  from another; ticked *inherited* fields come from the parent. *Use for this event's screens* switches every
  screen of the event at once. If two people edit the same theme, the second save is refused with a notice.
- **Fonts**: upload WOFF2, WOFF, TTF or OTF (variable fonts included). *Keep Latin characters only* makes
  files much smaller (arrows and symbols stay). Note the licence. Atkinson Hyperlegible (made for
  legibility, recommended for safety screens) and Inter are built in.
- **Files**: images, SVG, video, audio, PDF and Lottie. EVAC creates optimised versions (WebP/AVIF images,
  MP4 and WebM video with poster, loudness-normalised audio), removes photo metadata such as GPS positions
  and cleans SVGs. Large videos convert in the background (worker). Give images an *alternative text*.
- Files are only visible to members of the event and its screens, never public by URL. The instance-wide
  **shared library** (instance admins: tick *Add to the shared library* when uploading) is visible to every
  event.
- **Layouts** are designed in the layout editor (see the [Designer Guide](DESIGNER_GUIDE.md)); screens show
  published layouts (through playlists, schedules and overrides, see 5c; without them the event's default
  layout) and keep them, with all their files, for offline playback.
  Publishing can be scheduled (needs the beat service).
- *Settings → Screen content*: maximum upload size (default 512 MB), largest image edge, AVIF, VP9.

## 5c. Playback: playlists, schedules and overrides

*Playback* (modules *Playlists*, *Schedules*, *Live overrides*; each can be switched off per event) decides what
every screen shows. Highest wins:

1. evacuation (phase 3, always highest),
2. **emergency** override (permission `playlists.emergency`, two-factor verified session),
3. **live** override,
4. **urgent** override,
5. **schedules** (when two overlap, the higher *priority* 0–99 wins),
6. the **default playlist**, otherwise the default layout.

- **On screens now** lists every paired screen with what it shows and why, and the active overrides with a
  *Cancel* button each.
- **Playlists** play layouts in turn (in order, shuffled or weighted), each for its own duration, the layout's
  duration or the playlist default. Items can be limited to screens with a tag, to a condition
  (`screen.zone == "North"`), to a time window, be paused or be another playlist (nesting). Make one playlist
  the event's default.
- **Schedules**: "Stage screens 18:00–20:00 → Concert playlist": a playlist or layout for all screens, screen
  groups or single screens, on weekdays and/or a date range, in the event time zone; a slot ending before it
  starts runs past midnight. The **calendar** shows per screen group what wins when in a week.
- **Overrides**: push a message, layout or playlist to all screens, groups or single screens, now or later,
  for 5 minutes to 4 hours, until a time or until cancelled. Screens switch within a second. Operators limited
  to a screen group (role scope) can only push to that group.
- **Preview** shows any screen at any moment (also in the future): the slide rendered as on the screen, the
  list of entries that apply and which one wins, the next 24 hours and the next slides.
- Screens receive their program for seven days and change slides by themselves with the server clock, so all
  screens of a group change at the same moment and keep playing (and following schedules) without network.
- Webhooks: `override.started`, `override.cancelled`.

## 6. Extensions

*Settings → Extensions* (instance for admins, per event for orgas) lists integrations with their status.
Each extension page has connection settings, secrets (stored encrypted, never shown again), **Test
connection**, health and log, feature switches, the inbound webhook URL with its secret (shown once), and
**Disconnect & purge data**. See [EXTENSIONS.md](EXTENSIONS.md).

## 7. Audit log

Every state change is recorded with actor, time, scope and before/after values in a hash-chained log.
*Instance → Audit log → Verify hash chain* (or `manage.py evac_audit_verify`) proves nothing was altered or
removed. Event audit logs can be filtered and exported as CSV or JSON (`audit.export`).

## 8. Monitoring

- `GET /healthz` (process alive), `GET /readyz` (database and cache), `GET /metrics` (Prometheus; protect
  with `EVAC_METRICS_TOKEN` or the proxy).
- `LOG_FORMAT=json` for structured logs. The outbox depth metric shows stuck deliveries.

## 9. Venue node

Running EVAC on a mini PC at the venue (`EVAC_MODE=node`) so the venue keeps working without uplink is
designed in [ADR-0002](adr/0002-central-node-sync.md) and ships with phase 3. Until then, for a single
offline event run the normal stack on a local server.

## 10. Backups and upgrades

Back up PostgreSQL (`pg_dump`), the `media` volume and `.env` (with `EVAC_SECRETS_KEYS`). Upgrades:
`git pull && docker compose up --build -d` — migrations run automatically on start of `web`.
Rotate secrets keys: prepend a new key to `EVAC_SECRETS_KEYS`, restart, run
`manage.py evac_rotate_secrets`, then drop the old key.
