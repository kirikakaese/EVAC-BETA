# Operator Handbook

How to install and run EVAC for one or many events. This handbook grows with every phase; sections for
screens, announcements, evacuation drills and the kiosk image are added when those modules ship.

## Safety statement

EVAC is a **supplementary information system**. It is not a certified fire alarm, voice alarm or
evacuation system and does not comply with DIN 14675, DIN VDE 0833, EN 54 or similar standards. It
complements, and never replaces, the legally required systems and procedures of your venue. Operators
accept this once per event when they enable the evacuation module.

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
- **Single sign-on**: set `EVAC_OIDC_*` (redirect URI `<EVAC_PUBLIC_URL>/accounts/oidc/callback/`). Accounts are
  linked by the IdP subject, then by verified e-mail address; `EVAC_OIDC_ALLOW_PASSWORD_LOGIN=0` makes SSO the only
  login. `EVAC_OIDC_TRUST_MFA=1` accepts the IdP's multi-factor login (`amr` claim) as EVAC two-factor.
- **One identity provider for EVAC and DIAL**: register EVAC and DIAL at the same IdP (two clients, or one client
  with both redirect URIs: `<EVAC_PUBLIC_URL>/accounts/oidc/callback/` and `<DIAL_PUBLIC_URL>/accounts/oidc/callback/`)
  and set the same issuer in `EVAC_OIDC_ISSUER` and `DIAL_OIDC_ISSUER`, with scopes `openid email profile` in both.
  Both link by subject and verified e-mail, so a person has one login. Roles are not taken from the IdP in either
  system; DIAL roles can be mapped to EVAC roles by hand on the event's DIAL page
  ([extensions/dial.md](extensions/dial.md#single-sign-on-and-roles)).

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

Switch the **Evacuation** module on (*Settings → Modules*; it is off by default). For each event an organiser
reads and accepts the **safety statement** once (when switching it on for the event, in the wizard, on
*Settings → Evacuation*, or on the first evacuation page): EVAC supplements, and never replaces, the venue's
legally required systems ([EVACUATION.md](EVACUATION.md)).

**Evacuation** in the event menu is the control page:

- **Whole event** shows the current state; **Zones** shows each zone's own state and what its screens show
  (the more severe of the two).
- **Change the state**: choose where (whole event or a zone), the new state, *Drill* for exercises and an
  optional note, then **hold** the button until it confirms. Alarms can be raised, escalated and stepped down
  directly. Nothing returns to normal on its own: give the **All clear** (for the whole event it also clears the
  ticked zones), which shows for the configured time and then ends; *Back to normal now* ends it early.
- A real alarm ends every running drill. **History** lists every change; filter real alarms or drills.
- *Settings → Evacuation*: the **model** (simple takeover, staged global, zones and routes), which states are
  used, their names, the all-clear time and the drill marker.
- **Zones and routes**: zones get their own alarms (partial evacuation). *Exits and passages* lists exits,
  assembly points, doors and stairs: **Block** one (hold) when it cannot be used and every route avoids it;
  *Open again* when it is clear. *Screens* shows where each screen sends people. Place each screen on the venue
  map with its facing, and put a waypoint near it, so it gets an arrow; otherwise it says "Follow staff
  instructions".
- **Panic page** (*Staff app → Evacuation → Raise an alarm*, or *Panic page* on the control page): one big button
  per stage, hold until it confirms; choose the zone and tick *drill* for exercises.
- **Waiting for a decision**: alarms from the API or the hardware bridge (and any source set to *arm*) wait on the
  control page. *Hold to confirm* or *Reject*; without an answer they execute by themselves after 120 s.
  Requests under the two-person rule wait for a second person and expire if nobody confirms.
- **Triggers & drills**: change what each source does per stage and zone (execute, arm with or without
  auto-escalation, notify), and plan drills that start by themselves. The two-person rule is set in
  *Settings → Evacuation*.
- **Fixed direction** per screen (any model): choose an arrow and a text such as "Exit B" in the *Screens* table;
  it overrides the computed route.

- **Hardware bridges** (*Triggers & drills → Hardware bridges*): add a bridge, copy its token (shown once) into
  the bridge's configuration and list its inputs (`key; label; stage; zone`). See `bridge/README.md`.
- **Screen content**: per stage a layout or the built-in one, the texts shown in turn, sound and spoken message.
  Evacuation layouts must pass the guardrails (signs, text, direction, contrast and letter size for the viewing
  distance set in *Settings → Evacuation*). Per screen, *Settings → Screens → Evacuation role* chooses whether it
  takes part, only shows a banner (info) or is excluded.
- **Screens reached** on the control page: how many screens confirmed the current message, which are offline or
  still waiting, per zone, and how long it took (p95; target ≤ 2 s on the venue LAN). Staff answer from the staff
  app or panic page: *I'm on it*, *Zone clear*, *Need help* (alerts the control room).
- **Readiness** (button on the control page): before every event, run the **self-test** and fix each screen marked
  *problem*: offline, evacuation bundle not current, sound blocked by the browser (set the kiosk up with
  `deploy/kiosk`), self-test failures. The **alarm key** is managed here: export it for hardware bridges and
  secondary nodes that serve the signed state to screens without the server, and rotate it when such a device
  is lost.
- During an alarm the **watchdog** alerts the control room when screens have not confirmed it after 30 s.

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

## 5h. Program

**Program** in the event menu holds the event's sessions on stages, with speakers and tracks (ADR-0038).

- **Stages and tracks**: create stages (a stage can belong to a venue room; screens in that room show its sessions
  in *now and next*) and tracks with a colour.
- **Sessions**: *New session*, or import them (below). The day view lists each day's sessions. *On the stages now*
  shows what runs and what is next.
- **Live changes** (permission `program.live`, e.g. the stage manager): *Change* on a session row offers +5/+10/+15/
  +30 minutes (optionally *also later sessions on this stage*), *Move* to another stage, *Cancel session* and *Back
  to plan*. Screens, the public page, webhooks and announcements timed relative to the session follow within a
  second. *Recent changes* lists them, and the audit log records who made them.
- **Import** from pretalx, frab/Pentabarf or iCal: Settings → Extensions ([program-import](extensions/program-import.md)).
  Local changes survive every sync. *Follow the source again* undoes that for one session.
- **On screens**: in the layout editor add a **Program** element (*Now and next*, *The day's sessions* or *Live
  changes*).
- **Public page**: Settings → Program → *Public program page* publishes `/public/<event>/program/` with iCal, JSON
  and frab XML exports. Sessions marked not public (e.g. crew briefings) never appear there or on screens.
- **Announcements** can be timed relative to a session ("10 minutes before *Opening*"). They move when the session
  is delayed.

Imports only reach public addresses. Set `EVAC_IMPORT_ALLOW_PRIVATE=1` for a pretalx or calendar server on the venue
network.

## 5i. Incidents, ops log and the control room

The **Operations** part of the event menu (module *Incidents & control room*, ADR-0039) holds the control room's
tools. The built-in roles *Control room* and *Security* have all of it, and *Viewer* can read it.

- **Incidents**: *Report an incident*. Give a title, a category (Settings → Incidents lists them), a severity, a
  room or zone and where exactly, who reported it, and whom it is assigned to.
  - Each incident gets a number (#1, #2, …) and a timeline: notes, photos and files (up to 10 MB), status changes,
    assignments, escalations.
  - Status runs *New → Acknowledged → In progress → Resolved → Closed*. Whoever may report may also acknowledge.
    A closed incident can be reopened.
  - *Report (CSV/JSON)* exports one row per incident, with the times to acknowledge and resolve, for the
    post-event report.
- **Ops log**: the radio log. Write "from → to: message" entries, mark the important ones, and link an incident.
  The system adds lines for alarms, staff answers, offline screens, DECT alerts, announcements, overrides,
  occupancy and program changes. Settings → Incidents can switch the system lines off.
- **Tasks**: things to do, with whom, by when and for which incident. *Done* ticks them off, and the assignee is
  notified.
- **Escalation** (*Incidents → Escalation*, permission `ops.escalation`): rules like "high or critical: notify the
  control room at once" or "not acknowledged after 5 minutes: notify security and the ntfy topic".
  - Members of the chosen roles get a notification, which is a push on their phone with the staff app installed.
  - Channels set up under Settings → Extensions also get the message: ntfy, Matrix, Telegram, e-mail, or DIAL
    DECT messages.
  - Each rule fires once per incident.
- **Staff app**: the *Incidents* card lists what is new and assigned to you, with *I'm on it*. It also has
  *Report an incident* and *Ops log entry* forms. Both work offline and are sent once the phone is back online.
- **Control room** (`/e/<event>/ops/control/`): one page for a big screen, with *Full screen*. Panels refresh by
  themselves every few seconds:
  - alarms;
  - open incidents;
  - a zone map with incidents;
  - occupancy;
  - screen health;
  - announcements;
  - DIAL/DECT;
  - the ops log;
  - open tasks.

  Panels of switched-off modules are not shown.

## 5j. Occupancy

**Occupancy** in the event menu (module *Occupancy*, ADR-0040) counts people per area: a room, a zone or any place
such as a queue or a tent.

1. **Add an area**: a name, the room or zone, and the capacity (empty: the room's). Then set the thresholds:
   - *busy from* (80 %);
   - *full from* (100 %);
   - *open again below* (90 %). "Full" ends only below this, so the sign does not flicker.

   Choose:
   - *Send people to*: another area to suggest while it has space;
   - extra screen groups (e.g. the foyer screens);
   - a custom text;
   - roles and channels to alert.
2. **Count**:
   - **Door staff**: in the staff app, *Door counter → the area* gives big **+1 in** and **−1 out** buttons.
     Several phones can count the same area, and the numbers add up. Without network, the clicks are kept and
     sent later, and the page shows how many are waiting.
     Door staff need the permission `crowd.count` (*Control room* has it; add it to a crew role).
   - **Sensors**: `POST /api/v1/events/<event>/occupancy/<id>/count/` with a service token (scope `crowd`).
     Send `{"in": 3, "out": 1}`, `{"delta": 2}` or `{"value": 140}`. Over MQTT, use
     `<prefix>/crowd/<event>/<sensor key>` (docs: [mqtt](extensions/mqtt.md)).
   - **Corrections**: on the area page, *Set count*. *Reset all to 0* is for the start of a day. Both are audited.
3. **When an area is full**:
   - screens in its room or zone (and the chosen groups) show a red banner, for example "Foyer is full. Please
     use Hall B.", within a second;
   - the chosen roles get an alert, and the ops log gets a line.

   When the count falls below the release threshold, the banner goes away and an "open again" alert follows.
4. **History**: the area page charts the last 2 to 48 hours with the busy and full lines.

Occupancy holds no personal data. Clicks and sensors record a device label, not who clicked.

## 5n. Access: attendees, badges and check-in

**Attendees** and **Check-in** in the event menu (module *Access*, ADR-0044).

1. **Ticket types and zones** (*Attendees → Ticket types and zones*):
   - **Access zones** are the places with a scanner: the *Main entrance* (tick *checks in* and *every valid
     ticket*), *Backstage*, a *Crew area* … Untick *re-entry allowed* where a ticket may only go in once. Choose
     an **occupancy area** to have the zone's scans count people there (module *Occupancy*).
   - **Ticket types** have a colour and *grant* zones beyond those open to every ticket (e.g. *Crew* grants
     *Backstage* and *Crew area*).
2. **Attendees**: add them one by one, **Import CSV** (`name, ticket_type`, optionally `email, company, code`;
   unknown ticket types are created; an existing code updates that person), or connect **pretix**
   ([pretix](extensions/pretix.md)). Each attendee has a ticket code (QR code on their page). *Block* or *Cancel*
   makes scanners refuse it. *Export CSV* lists the current filter.
3. **Badges**: on a ticket type, *Create a badge layout* opens an A6 badge in the layout editor with the
   attendee's name, organisation, ticket type and the ticket's QR code; design it like any layout. *Print new
   badges* on the attendee page prints all badges not printed yet (2 per A4 page); *Mark as printed* afterwards.
   Ticket types without a layout use the built-in badge.
4. **Check-in**: on a phone or tablet, *Check-in → zone → Entry* (or *Exit*). The page loads the ticket list
   and works **offline** from then on:
   - scan with a hardware scanner (it types into the field), type the code, or use *Camera* (Chrome on Android);
   - the answer is immediate: **✓ OK / Welcome**, **✕ Ticket not valid**, **✕ Not allowed** (ticket type does
     not grant the zone), **! Already inside** (no re-entry), **? Unknown ticket**;
   - without network, scans are kept on the device ("5 scans waiting") and sent when it is back; if another gate
     let the same ticket in meanwhile, the log shows "Server: … Already inside";
   - give each device a name (*Gate A left*) so the scan history shows where people came in.

   Gate staff need `access.scan` (*Control room*, *Security* and *Helpdesk* have it); scope it to one zone
   (Roles → assign with scope *Access zone*) for a door that should scan only there. The staff app shows the
   zones a person may scan.
5. **Who is where**: the attendee page lists checked-in counts, people inside per zone, refused scans and the
   latest scans; the control room has a *Check-in* panel; occupancy areas linked to zones go up and down with
   every entry and exit.

The offline list on scanner devices holds names and ticket types, not e-mail addresses or ticket codes (only
hashes of them). Delete attendees after the event according to your retention rules (export and purge the event).

## 5k. Crew and shifts

**Shift board** in the event menu (module *Crew*, ADR-0041).

1. **Teams and crew** (*Teams and crew*): add teams with a colour, a meeting point and their leads, and skills
   such as *First aid* or *Forklift*. Add crew members with a name and a contact (phone or DECT); link an account
   when the person logs in to EVAC. Members can belong to several teams. Team leads manage their own team without
   any other role; for more, grant `crew.manage` or `crew.checkin` scoped to a team (Roles → assign with scope
   *Team*).
2. **Shifts**: *New shift* with team, title, room or place, start and end, people needed, skills, and whether crew
   may sign up themselves. The board shows each day, the people per shift and a **Needed now** list.
3. **Rules** (Settings → Crew): at most 10 hours a day, 30 minutes rest between shifts, sign-up up to 30 minutes
   after the start, cancel until 60 minutes before, no-show after 15 minutes, "needed now" looks 3 hours ahead.
   A lead can add someone anyway (*anyway* on the shift page); the audit log records it.
4. **Check-in**:
   - **QR code**: every shift page has a QR code; *Print QR code* prints a sheet for the meeting point. Crew scan
     it with the phone camera and press *Check in* (and later *Check out*). Someone who is not on the shift joins
     it if the rules allow ("walk-in").
   - **Staff app**: *My shifts* has *Check in*, *Check out* and *Cancel*; *Help needed* signs up with one tap.
     Both work offline and are sent when the phone is back.
   - **Team lead**: on the shift page, *Check in*, *Check out*, *No-show*, *Remove* per person.
5. **No-shows**: a sign-up not checked in 15 minutes after the start becomes a no-show; the team leads get a
   notification and the ops log a line, and the shift is "needed" again.
6. **On screens**: *Add shift board widgets for screens* on the shift board creates *Crew: needed now* and
   *Crew: shift board*. Put one on a layout with a **Data widget** element (Design → Layouts) and show the layout
   on the crew-room screen. Sign-ups and check-ins appear there within seconds.
7. **Engelsystem**: Settings → Extensions → *Engelsystem* imports angel types, shifts and sign-ups
   ([engelsystem](extensions/engelsystem.md)). *Sync now* is also on the shift board.

## 5l. Inventory

**Inventory** in the event menu (module *Inventory*, ADR-0042): radios, keys, vehicles, tools, laptops.

1. **Items**: *New item* with a name, a category (with its usual loan time), serial number, where it is kept and a
   photo. Leave the asset tag empty for the next number (`EV-0001`; the prefix is in Settings → Inventory).
   *How many* creates identical items (e.g. 20 radios) with consecutive tags.
2. **Labels**: *Print QR labels* (all, a category, or the items just created) prints a sheet with QR code, tag and
   name. Stick them on the items. The QR code opens the item's page on any phone of someone with
   `inventory.view`.
3. **Lend**: scan the label (or open the item). Enter who gets it (a name, or choose an account), a contact, the
   due time (pre-filled from the category), optionally take a photo, and let them sign on the screen with a
   finger. *Lend*. Settings → Inventory can make the signature required.
4. **Take back**: scan the label again, choose the condition (OK, damaged, incomplete), optionally a note and a
   photo, *Take back*. Damaged or incomplete items go to *maintenance* with a note; set them *available* again
   from *Notes and maintenance* when fixed.
5. **Who has what** is at the top of the inventory page; overdue loans are marked. Borrowers with an account and
   whoever lent the item get one reminder when it is overdue; the ops log gets a line. The control room has a
   *Lent out* panel, and the staff app shows each person what they have.
6. **Map**: items can be placed on the floor plans (Venues → Map, layer *Inventory*).

Lending needs `inventory.lend`; adding items, labels and maintenance need `inventory.manage`.

## 5m. Helpdesk: lost & found, requests, FAQ

**Helpdesk** and **Lost & found** in the event menu (module *Helpdesk*, ADR-0043).

- **Public help page** `/public/<event>/help/` (link on the helpdesk page, e.g. as a QR code on screens and
  posters): the FAQ, found items (what, category, colour and day only), *Ask the helpdesk* and *I lost something*.
  Visitors get a status link that shows the state and your replies; they need no account. Settings → Helpdesk
  switches the page, the forms and the found list off.
- **Requests**: new requests notify the helpdesk; accessibility requests also go to the ops log. Open one to
  assign it, set its status (new, in progress, waiting, done) and add notes. Tick *Reply* to show a note to the
  requester on their status page. The desk can also log a request from someone at the counter (*New request*).
- **Lost & found**: *Found item* logs what was handed in (what, category, colour, where and when, a photo, where it
  is kept, the finder). *Lost report* records what someone lost and how to reach them. Each item page suggests
  look-alikes of the other kind (same category and colour, shared words); *Match* links them, the visitor's
  status page then says "Probably found: please come to the helpdesk". *Hand over* records to whom (check their
  ID). *Close* ends an item that is not handed over (e.g. given to the police).
- **FAQ**: questions with an answer and a topic. *On the public help page* and *on screens* choose where they
  appear (data source *Helpdesk: FAQ* for a custom widget).

Contacts of visitors are only visible to the helpdesk. Delete them after the event (export and purge the event, or
delete the rows) according to your retention rules.

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

A venue node is EVAC on a small computer at the venue (`EVAC_MODE=node`, same image or package). While an event
is *checked out* to it, screens, announcements, overrides and evacuation run there, with or without the uplink
([ADR-0036](adr/0036-venue-node-sync.md)).

1. Install the node like a normal instance with `EVAC_MODE=node` in its environment (its own database and
   secrets).
2. On central, *Venue nodes → Add a node*: copy the enrolment code (valid 24 hours).
3. On the node: `manage.py evac_node enrol --central https://central.example.org --code …`, then start the sync
   (`docker compose --profile node up -d`, or `systemctl enable --now evac-node-sync`).
4. On central, in the event: *Venue node → Check out*. Within seconds the node has the configuration, the people
   of the event (they sign in on the node with their usual password and second factor), the media and the
   current live state. Pair the venue's screens with the node.
5. During the event, change configuration (layouts, playlists, settings) on central: it follows within 30 s.
   Alarms and announcements raised on central are sent to the node and run there. Without the uplink everything
   keeps working at the venue; central catches up when the link is back.
6. Afterwards, *Request check-in*: the node sends what is left and hands the event back. If the node is lost,
   *Force check-in* (hold, reason; audit-logged) takes the event back at the last position central received.

`manage.py evac_node status` on the node shows what it holds and what is still to send.

## 10. Backups and upgrades

Back up PostgreSQL (`pg_dump`), the `media` volume and `.env` (with `EVAC_SECRETS_KEYS`). Upgrades:
`git pull && docker compose up --build -d` — migrations run automatically on start of `web`.
Rotate secrets keys: prepend a new key to `EVAC_SECRETS_KEYS`, restart, run
`manage.py evac_rotate_secrets`, then drop the old key.
