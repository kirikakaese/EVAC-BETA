# EVAC — Event and Venue Administration Core

EVAC is a self-hostable, open-source **operations platform for events and venues**: hacker camps,
conferences, festivals, concerts, conventions and permanent venues that host many events over time.

It is being built in phases (see [the roadmap](docs/ROADMAP.md)):

- **Screens** — drive every info beamer, TV, projector, LED wall and kiosk with fully customizable,
  offline-capable content *(phase 1)*.
- **Announcements** across screens, push, ntfy, e-mail, Matrix, Telegram, Mastodon and phone *(phase 2)*.
- **Evacuation and alarm information** that keeps working when the network or the server fails *(phase 3)*.
- **Integrations** ("extensions"), first of all **DIAL — DECT & IP Administration Layer** *(phase 4)*, and optional
  modules for program, crew, incidents, crowd control, access, inventory and the helpdesk.

**Available now (phase 0, foundation):** multi-event platform with events and lifecycle, reusable venues,
accounts with e-mail login, invitations, OpenID Connect SSO, TOTP and WebAuthn two-factor authentication,
fine-grained roles with venue/zone/room scopes, a tamper-evident audit log, module toggles, a typed settings
framework, the plugin registry, the extension framework with a generic webhook extension, REST API with
OpenAPI, the `evac` CLI, realtime stream, in-portal documentation and a demo seed.

## Safety statement

> **EVAC is a supplementary information system.** It is **not** a certified fire alarm system, voice alarm
> system or evacuation system, and it does **not** comply with DIN 14675, DIN VDE 0833, EN 54 or similar
> standards. It complements — and never replaces — the legally required systems and procedures of your
> venue. Design and operate it as if lives depended on it anyway: redundancy, drills, tests.

## Quick start (Docker Compose)

```sh
git clone https://github.com/kirikakaese/EVAC-BETA.git evac && cd evac
cp .env.example .env            # set SECRET_KEY; generate EVAC_SECRETS_KEYS (see below)
docker compose up --build -d
open http://localhost:8000      # first-run wizard: admin account -> venue -> event
```

Generate a secrets key with `docker compose run --rm web python manage.py evac_genkey`.
For a clickable demo set `EVAC_SEED_DEMO=1` in `.env` and log in as `admin@evac.local` /
`evac-demo-admin` (one account per built-in role: `orga@`, `control@`, `security@`, `helpdesk@`, `crew@`,
`viewer@evac.local`, same password).

Services: `web` (HTTP + SSE), `channels` (WebSockets), `worker` and `beat` (Celery), `db` (PostgreSQL 16),
`redis`. Production notes, the reverse proxy layout and the venue node are in the
[operator handbook](docs/OPERATOR_HANDBOOK.md).

## Development

```sh
make dev                # virtualenv + dependencies + .env
REDIS_URL= make migrate seed run
make test lint typecheck
```

See [DEVELOPING.md](docs/DEVELOPING.md) and [CLAUDE.md](CLAUDE.md) for conventions.

## Documentation

All docs are served inside EVAC at `/docs/`:
[Operator handbook](docs/OPERATOR_HANDBOOK.md) ·
[Evacuation](docs/EVACUATION.md) ·
[Designer guide](docs/DESIGNER_GUIDE.md) ·
[Extensions](docs/EXTENSIONS.md) ·
[API & CLI](docs/API.md) ·
[Plugin SDK](docs/PLUGIN_SDK.md) ·
[Architecture](docs/ARCHITECTURE.md) ·
[Security & privacy](docs/SECURITY.md) ·
[Roadmap](docs/ROADMAP.md) ·
[Decisions](docs/adr/) ·
[Changelog](CHANGELOG.md)

## Licence

Copyright © kirikakaese. Licensed under the GNU Affero General Public License v3.0 or later
([LICENSE](LICENSE)). If you run a modified version for others over a network, you must offer them its
source code.
