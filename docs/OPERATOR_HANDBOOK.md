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
4. **First screen** — open `/player/` on a display and type the code it shows; the screen pairs and shows a
   welcome slide (skip with *Later*).

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
- **Scopes**: a role can be limited to a venue, zone, room or assembly point ("may control screens in Hall B
  only", "marshal of assembly point Car park").
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

## 4a. Venues, exits and routes

*Venues* lists the event's venues (shared with other events at the same place). A venue page holds buildings,
floors, zones and rooms, and the **route graph** used for evacuation arrows and wayfinding:

1. Add **points**: exits, assembly points, doors, waypoints, stairs and lifts, with their floor, zone and
   position in metres on the floor plan (the map editor will place them by clicking). Untick *step-free* for
   stairs and other places a wheelchair cannot pass.
2. Add **route connections** between points (both ways, or one way for exit-only doors). Without a length the
   straight distance is used, plus 5 m per floor.
3. **Ways out** shows, for every point, the next point and the nearest assembly point (or exit) with the
   distance, and the step-free alternative. Warnings list points without a way out.

During an evacuation, blocked exits are taken out and the routes recompute at once.

**Map** (button on the venue page) shows one floor at a time:

1. Upload the **floor plan** (PNG, JPEG, WebP, SVG or PDF). Then **Measure**: click both ends of a distance you
   know (a wall, a door width), type its length in metres and *Set scale*. Everything already drawn on the floor
   keeps its place.
2. **Add point** places exits, assembly points, doors, waypoints, stairs and lifts where you click;
   **Select** drags them. **Connect** joins two points (click both). Green arrows show each point's next step
   on the way out; a dashed red ring marks points without one.
3. **Zone outline**: choose a zone, click its corners, *Finish outline*.
4. **Place**: choose a screen and click where it hangs; turn *Facing* to the direction its display looks.
   Evacuation arrows on screens will use this.

The side panel lists all points and screens, with numeric positions for keyboard use. Everything is saved at once.

**Align with map** puts the floor plan on OpenStreetMap: type the position of the plan's top-left corner and its
rotation, or drag the map until streets and buildings match the plan (lower *Plan opacity* to see both). The
*Outdoors* floor uses the venue's own coordinates and is drawn straight onto the map, which suits open-air sites.

Tiles come through your EVAC server and are cached there, so a map viewed once works without internet at the
venue. New tiles take a moment the first time. *Settings → Maps* sets the tile server, attribution, maximum zoom
and whether tiles are shown at all. **Download area for offline use** fetches the whole area in advance; it only
works with a tile server you run yourself (and *Allow area download* ticked), because the public OpenStreetMap
servers forbid bulk downloads. With the public servers, open the map at the zoom levels you need before the
event instead.

## 4b. Evacuation (phase 3, in progress)

Switch the **Evacuation** module on (*Settings → Modules*; it is off by default) and read the safety statement
in [EVACUATION.md](EVACUATION.md) first: EVAC supplements, and never replaces, the venue's legally required systems.

**Evacuation** in the event menu is the control page:

- **Whole event** shows the current state; **Zones** shows each zone's own state and what its screens show
  (the more severe of the two).
- **Change the state**: choose where (whole event or a zone), the new state, *Drill* for exercises and an
  optional note, then **hold** the button until it confirms. Alarms can be raised, escalated and stepped down
  directly. Nothing returns to normal on its own: give the **All clear** (for the whole event it also clears the
  ticked zones), which shows for the configured time and then ends; *Back to normal now* ends it early.
- A real alarm ends every running drill. **History** lists every change; filter real alarms or drills.
- *Settings → Evacuation*: which states are used, their names, the all-clear time and the drill marker.

Screens, notifications, trigger sources (panic page, hardware bridge, DIAL, API) and the drill runbook arrive
with the next parts of phase 3.

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
- **Display settings** (*Screen → Display settings*, *Screen group → Display settings*, or per event under
  *Event settings → Display*): rotation, overscan, content scale, keystone, expected resolution (the screen page
  warns on a mismatch), dim and "screen off" times, sound and volume, the daily reload time and the evacuation
  role (used in phase 3). Values inherit instance → event → screen groups (in name order) → screen. Use portrait
  layouts on screens rotated by 90°.
- **Remote management** (*Screen → Remote management*): **Take screenshot** (a real capture of the screen; kiosks
  set up with `deploy/kiosk` allow it, other browsers report why not), **Fetch logs** (the player's last 300
  log lines), **Identify** (name for 10 s), **Test pattern** (colour bars, grid and circle for 30 s, to check
  overscan and colours), **Reload player**, **Clear cache and reload** (downloads everything again; the
  pairing stays).
- **Self-healing**: the player reloads itself when it gets into trouble (many errors, little memory, the daily
  reload time) but never more than three times in ten minutes, reports an unclean restart, and keeps showing
  content in the meantime.
- The player keeps its app and the last configuration offline: after a power cut without network it
  starts again and shows the last known content. `/player/?mode=obs` has a transparent background and no
  cursor, for OBS browser sources and video mixers.
- **Raspberry Pi kiosk**: `deploy/kiosk/` turns a Pi 4/5 into a screen that boots into the player, restarts a
  hung browser and survives power cuts (`sudo sh provision.sh https://<your EVAC>/player/`; see its README, also
  for building an SD-card image for many screens). Other kiosk browsers should start `/player/` in full
  screen with autoplay allowed (Chromium: `--kiosk --autoplay-policy=no-user-gesture-required
  --auto-accept-this-tab-capture`).

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

## 5d. Announcements

*Announcements* (module *Announcements*) are written once and go out through the channels you tick: **screens**,
the **public feed**, **staff notifications** (the bell), **webhooks**, and - once set up under *Settings →
Extensions* - **e-mail**, **ntfy**, **Matrix**, **Telegram** and **Mastodon** (see
[Announcement channels](extensions/notify.md)). Under *Own text per channel* you can write a shorter text for
chat and social media. Each occurrence and channel is a row in the announcement's **delivery report** (delivered, skipped,
failed, with recipients and retries).

- **Levels** decide how an announcement looks on screens and whether it sounds: *Info* scrolls in a ticker,
  *Important* is a banner with a chime, *Urgent* a card with a gong, repeated every 10 minutes, *Emergency*
  takes over the whole screen with an alert tone. Change colours, display, sound, display time, repetition and
  default channels under *Announcements → Levels*. Full-screen levels sit between live and urgent overrides;
  emergency announcements are above live overrides, only evacuation is higher.
- **Templates** hold reusable texts with blanks such as `{{desk}}`; *Quick start from a template* asks only for
  the blanks. Built in: lost child, doors open soon, severe weather warning, keep exits clear, lost and found.
  A template can use a layout for its full-screen look (`{{ announcement.title }}`, `{{ announcement.text }}`).
- **Where**: everywhere, or chosen venues, zones, rooms, screen groups or screens. Staff limited to a zone or a
  screen group (role scope) can only address those. *Only these people* limits the staff notifications (bell and
  phone) to members with the chosen roles; screens and public channels are not affected.
- **When**: now or at a time, until a time (empty: the level's display time, or until cancelled when the level
  repeats), once, daily or weekly until a day. Screens know scheduled announcements in advance and show them on
  time without network. Once a module offers time anchors (the program, phase 5), *Relative to* sends an
  announcement e.g. 10 minutes before an item starts and follows the item when it moves; `{{anchor}}` in the text
  becomes the item's name.
- **Approval**: the helpdesk role may write drafts; they wait under *Waiting for approval* until someone else
  with the approve permission (control room, orga) approves or rejects them with a note. Tick *Every announcement
  needs approval* under *Settings → Announcements* to require it for everyone, or per level. Emergency
  announcements never wait, need the emergency permission and a two-factor verified session.
- **Public feed**: switch it on under *Settings → Announcements*; published announcements sent to the feed
  channel appear at `/public/<event>/announcements/` with RSS (`rss.xml`) and JSON Feed (`feed.json`).
- Sound on screens follows the screen's display settings (sound on/off, volume).
- **Spoken announcements** (optional, offline): levels marked *read aloud on screens* (urgent and emergency by
  default) are spoken by screens with sound after the level's tone. The speech is generated on your server by
  Piper when the announcement is approved, and screens keep it for offline playback; the announcement page lets
  you listen to it. Setup:
  1. install Piper: build the image with `EVAC_WITH_TTS=1 docker compose build` (or `pip install -e .[tts]`);
  2. install a voice, e.g. `docker compose exec web python manage.py evac_tts install` (British English
     "alba", from the Piper voices on Hugging Face) or any voice URL or file;
  3. check with `evac_tts status` and `evac_tts say "Doors open in ten minutes."`.
  Choose the voice under *Settings → Announcements*; *Spoken text* in the composer replaces the default
  "Level. Title. Text.".
- Webhooks: `announcement.published` (per occurrence), `announcement.pending`, `announcement.cancelled`.

## 5e. Staff app (PWA)

Staff open **Staff app** in the event menu (`/e/<event>/staff/`) on their phone and install it with the
browser's *Add to home screen*. The page shows

- **This device**: *Switch on notifications* subscribes the phone to Web Push. Every notification of the bell
  (approvals, announcements to staff, later alarms) then also arrives as a phone notification; emergencies stay
  on screen until dismissed. *Send a test* checks it. Requires HTTPS; on iPhone the app must be on the home
  screen first.
- **Announcements**: what is on air, announcements waiting for your approval with *Approve* / *Reject*, and quick
  send from templates.
- **Alerts**: while the page is open, urgent and emergency announcements cover the screen with a tone and
  vibration until *Got it*.
- **Offline**: the page works without network. Approvals and other actions taken offline are kept on the phone
  ("1 action waiting to be sent") and sent automatically when the connection is back.

Set `EVAC_VAPID_SUBJECT` (e.g. `mailto:ops@example.org`) so push services can reach you; the push keys are
created automatically.

## 5f. Data & widgets

**Data & widgets** in the event menu shows external data on screens without code.

1. **Add a feed**: a URL with JSON, RSS/Atom, iCal or CSV, or a built-in source (on-air announcements, event
   info). EVAC fetches it on the server every few minutes (at least 60 s) and keeps the last good copy when the
   source is down; the feed page shows the status, the last error and the data as a tree. An *Authorization
   header* (for example `Bearer …`) is stored encrypted.
2. **Build a widget**: choose the feed, click the list in the tree to set *Items*, then click fields for title,
   value, time and so on. Pick a visual (text, list, table, cards, counter, gauge, ticker, bars) and options
   (number of items, heading, unit, only upcoming items). The preview updates as you go.
3. **Place it**: in the layout editor add a **Data widget** element and choose the widget.

Screens keep the latest data offline and update when the feed changes. Feeds can only reach public addresses;
an instance administrator can allow private networks (venue sensors) under *Settings → General → Data feeds* (instance settings).
MQTT sources follow in phase 6.

## 5g. Screen packs

**Screen packs** in the event menu moves content between events and servers as `.evacpack` files.

- **Export**: choose layouts, themes, files, fonts, custom widgets or playlists. What they need comes along (a
  playlist brings its layouts, a layout its pictures, fonts, theme and widgets). A playlist with its layouts is a
  "screen pack". Packs are signed with this server's key; authorization headers of data feeds are never exported.
- **Import**: upload a file, give a URL (the server downloads it) or pick a pack from the **gallery**. You first
  see where it comes from, its contents and a preview; *Import into this event* then creates copies (nothing
  existing changes). Unsigned packs and packs from unknown keys need a tick on *I trust where this pack comes
  from*. Notes list what was skipped, e.g. a feed that needs its authorization header again.
- **Pack keys** (instance admins, *Settings → Pack keys*): this server's public key and fingerprint to give to
  others, and the keys you trust. *Settings → General → Screen packs* sets the signer name, *Only import packs
  signed by a trusted key*, URL import, private networks for pack URLs and the size limit.
- On the command line: `manage.py evac_pack key`, `verify <file>`, `export <event> <file> --layouts=<id,…>`,
  `import <event> <file> [--yes]`.

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
