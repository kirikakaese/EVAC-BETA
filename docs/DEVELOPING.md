# Developing EVAC

Conventions, layout and workflow. Agents and humans: also read [CLAUDE.md](../CLAUDE.md).

## Toolchain

```sh
make dev                                    # .venv, dependencies from pyproject.toml, .env from the example
REDIS_URL= .venv/bin/python manage.py migrate
REDIS_URL= .venv/bin/python manage.py evac_seed_demo
REDIS_URL= make run                         # runserver (ASGI via daphne: WebSockets work too)
make test                                   # pytest (evac.settings.test, sqlite in memory, eager Celery)
make cov                                    # with coverage (gate 85 %)
make lint typecheck a11y openapi-check attribution
```

`REDIS_URL=` (empty) switches dev to the local-memory cache and the in-memory channel layer. With Redis and
PostgreSQL running, use `DATABASE_URL=postgres://…` and `REDIS_URL=redis://…`.

## Try it in the browser (GitHub Codespaces)

**Code → Codespaces → Create codespace** on the repository page starts EVAC with SQLite, no Redis and the
demo data; port 8000 opens by itself (log in as `admin@evac.local` / `evac-demo-admin`). The setup lives in
`.devcontainer/` (see its README). `EVAC_TRUST_PROXY_HEADERS=1` (dev settings only) makes Django trust the
Codespaces proxy's `X-Forwarded-Proto`/`-Host`, so CSRF checks and passkeys see the browser's HTTPS URL.

## Frontend (`frontend/`): player, renderer, layout editor

TypeScript + Vite. `src/renderer/` is the layout renderer and the built-in widgets (custom elements), shared
by `src/player/` (the screen app, built into `static/player/`: `player.js`, `player.css`, `sw.js`) and
`src/editor/` (the Lit layout editor island, built into `static/editor/`). The bundles are **committed** so that
EVAC runs without Node. After changing `frontend/src/` run `make frontend` (Node 22: `npm ci`, Vitest, type
check, build, size budgets: player 300 kB, editor 500 kB gzipped) and commit the result; CI rebuilds and fails
if the committed bundles differ. Editor UI strings are keys looked up in a list in
`apps/content/layout_views.py` (`EDITOR_STRINGS`); a test fails when a string is missing there. Django serves the page at `/player/` (`apps/screens/player_views.py`) with the UI
strings and settings in a JSON block, and the service worker at `/player/sw.js` (scope `/player/`).

## Layout

| Path | Contents |
|---|---|
| `evac/` | settings (`base`, `dev`, `prod`, `test`), `urls.py`, `asgi.py`, `celery.py` |
| `apps/core` | plugin API + registry, modules, settings framework, audit log, crypto, outbox, webhooks, realtime, notifications, middleware, a11y linter |
| `apps/accounts` | users, 2FA, OIDC, tokens, GDPR, invitations UI |
| `apps/events` | events, roles, memberships, permissions (pure) and RBAC, services, seed/export commands |
| `apps/venues` | venues, buildings, floors, rooms, zones |
| `apps/extensions` | extension configs, settings pages, inbound webhook verification |
| `extensions/webhooks` | generic webhooks extension |
| `apps/api` | REST API, auth, permissions, OpenAPI, CLI |
| `apps/portal` | shell pages, wizard, admin pages, docs renderer |
| `templates/`, `static/` | base layout, CSS, JS (vendored htmx) |
| `deploy/` | entrypoint, systemd, ansible |
| `docs/` | documentation (served at `/docs/`), ADRs, OpenAPI schema |

## Key helpers

```python
from apps.core.audit import log                      # log(action=, actor=, target=, event=, changes=, scope=, request=)
from apps.core import modules                        # modules.is_enabled("venues", event)
from apps.core import settings_store                 # settings_store.get("general", event=event)
from apps.core.webhooks import emit                  # emit("event.updated", {...}, event=event)
from apps.core import outbox                         # outbox.enqueue(kind, payload, event=, key=)
from apps.core.realtime import publish               # publish(event, type, data)
from apps.events import rbac                         # rbac.has_perm(user, event, "venues.manage", obj=zone, request=request)
from apps.events import services                     # create_event, assign_role, invite, clone_event, export_event, ...
from apps.portal.shortcuts import event_view         # @event_view("venues.view", module="venues")
```

## Tests

- pytest + pytest-django; shared fixtures in `conftest.py` (`admin`, `user`, `event`, `venue`, `member`,
  `orga`, `admin_client` = 2FA-verified admin session, `login_2fa(client, user)`).
- Property tests with Hypothesis for pure logic (hash chain, permission evaluation).
- `apps/core/tests/test_a11y.py` renders every page of `apps.core.a11y.smoke_urls()` as anonymous, member
  and admin and fails on any finding. Add new pages to that list.
- E2E (Playwright), load and chaos suites arrive with the player (phase 1) and evacuation (phase 3).

## Adding a module

1. `apps/<name>/` app with `apps.py`, models, `urls.py` (`PORTAL_MOUNT = True`), templates.
2. `evac_plugin.py` registering module, permissions, nav entries, settings, scope kinds, …
3. Add the app to `EVAC_CORE_APPS` (always installed) or `EVAC_BUILTIN_PLUGINS` (removable) in
   `evac/settings/base.py`.
4. Services that audit-log; API viewsets (declare `scope_module`); tests including the module off-switch;
   docs; CHANGELOG.

## API schema

After API changes: `make openapi` and commit `docs/api/openapi.yaml`; CI fails on drift.

## Git

Commits are authored by the repository owner only (see CLAUDE.md, section 0.1). `scripts/check_attribution.py`
runs in CI and as a pre-commit hook (`pre-commit install`).
