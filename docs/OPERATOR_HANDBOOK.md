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
4. **First screen** — available with the screens module (phase 1).

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
