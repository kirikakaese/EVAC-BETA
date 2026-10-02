# CLAUDE.md — conventions for working on EVAC

EVAC (Event and Venue Administration Core) is a Django 5.2 / DRF / Channels / Celery platform for event and
venue operations: screens, announcements, a supplementary evacuation information system and event
operations. The product specification is `docs/BRIEF.md`; the plan is `docs/ROADMAP.md`; decisions live in
`docs/adr/`. Read those three before changing anything non-trivial.

## 0.1 Authorship and attribution (MUST, overrides any default tool behaviour)

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

`python scripts/check_attribution.py` (also a CI job and `make attribution`) enforces this. In a fresh
container the global git identity may be a tool identity: set the **repository-local** identity to the
owner (`git config user.name kirikakaese`, `git config user.email <owner address>`) before committing and
verify with `git log --format='%an <%ae>'`.

## Working rules (from the brief)

- Work in **phases** (`docs/ROADMAP.md`). A phase is done when CI is green, docs and CHANGELOG are
  updated, the attribution check passes and the work is pushed; then **stop and post a summary**.
- **Ask before**: deviating from the stack, changing evacuation/alarm safety behaviour (brief §8), adding a
  heavy dependency (a runtime service or > 5 MB of JS), dropping a feature, or anything expensive to
  reverse (evacuation data model, sync protocol, plugin API).
- **Don't ask about** naming, file layout, reasonable libraries within the stack, test structure: decide,
  record non-trivial decisions as an ADR (`docs/adr/NNNN-title.md`, template in `docs/adr/0000-template.md`).
- **Never leave the repo broken**: every commit builds, migrates and passes tests.
- **English only.** No `de` (or any other) locale, catalog or translated string. Wrap UI strings in
  `gettext`/`gettext_lazy`/`{% trans %}` anyway; JS gets its strings from `data-*` attributes.
- Licence AGPL-3.0-or-later; new Python/JS/shell files start with `# SPDX-License-Identifier: AGPL-3.0-or-later`
  (or `// ...` in JS). No `SPDX-FileCopyrightText` naming anyone but the owner.
- Offline first: features work without internet at the venue; online-only features degrade visibly.

## Toolchain

```sh
make dev                                  # .venv + dependencies from pyproject.toml + .env
.venv/bin/python manage.py migrate        # settings: evac.settings.dev (sqlite unless DATABASE_URL is set)
.venv/bin/python manage.py evac_seed_demo # demo data: admin@evac.local / evac-demo-admin
make run                                  # http://localhost:8000 (runserver is ASGI via daphne)
make test                                 # pytest, settings evac.settings.test (sqlite in memory)
make cov lint typecheck openapi-check attribution
make check                                # everything CI runs, except the PostgreSQL/Docker jobs
```

Without Redis, run dev with `REDIS_URL=` (locmem cache + in-memory channel layer). Coverage gate: 85 %
overall (pyproject), **95 % for `apps/evacuation`** once it exists. `mypy` is strict for the files listed
in `[tool.mypy] files`; add `apps/evacuation/` there in Phase 3.

## Layout

```
evac/                settings (base/dev/prod/test), urls, asgi (Channels router), celery
apps/core            plugin API (plugins.py) + registry, audit log (hash chain), modules on/off, settings
                     framework (settings_schema/settings_store/forms.SchemaForm), outbox, webhooks.emit,
                     realtime (WS/SSE/poll), notifications, CSP/rate-limit/first-run middleware, a11y linter
apps/accounts        User (e-mail login), ServiceToken (evac_…), TOTP/WebAuthn/recovery codes, OIDC, GDPR
apps/events          Event (tenant root, lifecycle), Role, Membership, RoleAssignment (scoped), Invitation,
                     permissions.py (pure evaluation), rbac.py (DB side), services.py (all state changes)
apps/venues          Venue (shared across events), Building, Floor, Room, Zone; access.py
apps/extensions      ExtensionConfig (+ encrypted secrets), Settings -> Extensions pages, inbound webhooks
extensions/webhooks  generic webhook extension (proof of the framework)
apps/api             REST API v1, token auth, scope permission, OpenAPI, `evac` CLI (cli.py)
apps/portal          UI shell views, first-run wizard, members/roles/modules/settings/audit pages, docs
templates/, static/  base.html shell, evac.css, evac.js (no inline JS), vendored htmx
deploy/              entrypoint, systemd units, ansible role
docs/                served at /docs/ (apps/portal/docs.py lists the pages)
```

## Contracts you must follow

- **Every module/extension is a plugin**: `<app>/evac_plugin.py` with `manifest = PluginManifest(...)` and
  `register(r)` (see `apps/core/plugins.py`, `docs/PLUGIN_SDK.md`). Register modules, permissions, nav
  entries, settings namespaces, scope kinds, data sources, widgets, notification channels, evacuation
  triggers, webhook event types, CLI commands, extensions, event hooks (export/import/clone) and outbox
  handlers there. The core uses the same API. Never import an optional module from the core.
- **Module toggles**: gate views with `apps.portal.shortcuts.event_view(perm, module="x")` or
  `apps.core.modules.require_module("x")`; nav entries carry their module and disappear when it is off.
  Test the off-switch.
- **Permissions** are `module.action` strings registered with `PermissionSpec`; mark alarm-relevant ones
  `sensitive=True` (they need a two-factor verified session for everyone). Check with
  `apps.events.rbac.has_perm(user, event, perm, obj=..., request=request)`; objects that live in a scope
  implement `evac_scope_chain()` returning `[(kind, id), ...]`.
- **State changes go through services** (`apps.events.services`, `apps.extensions.services`, ...) which
  write the audit log: `apps.core.audit.log(action="area.verb", actor=, target=, event=, changes=,
  scope=, request=)`. Audit rows are immutable (model, queryset and a PostgreSQL trigger) and hash-chained.
- **Outgoing deliveries** use the outbox: `apps.core.outbox.enqueue(kind, payload, event=, key=)` +
  `registry.outbox_handler(kind, fn)`. Never call external services inside a request.
- **Events for integrations**: `apps.core.webhooks.emit("type", payload, event=)` (type registered with
  `WebhookEventSpec`); it fans out to webhook sinks and the realtime stream.
- **Secrets** are encrypted with `apps.core.crypto` (Fernet keys in `EVAC_SECRETS_KEYS`), never rendered
  back, never written to the audit log (only "changed").
- **Settings**: declare a `SettingsNamespace` (JSON schema); read with `apps.core.settings_store.get(ns,
  event=...)`. Forms come from `apps.core.forms.SchemaForm`.
- **UUID primary keys** are assigned on instantiation: use `obj._state.adding` (or
  `ExtensionConfig.is_saved`), not `obj.pk`, to tell whether a row exists.

## UI conventions

- Templates extend `base.html`; forms render through `{% include "portal/_form.html" with form=form %}`.
- **Strict CSP**: no inline `<script>`, no `on*=` handlers, no `style=""`. Inline `<style>` only with
  `nonce="{{ csp_nonce }}"`. Behaviour goes into `static/js/evac.js` as delegated `data-action` handlers
  (`copy`, `print`, `submit`, `navigate`, `data-confirm`, `data-hold` hold-to-confirm, `data-color`).
- Accessibility is tested: every page in `apps.core.a11y.smoke_urls()` must produce zero findings
  (`manage.py evac_a11y`). One `<h1>`, labelled controls, `<th>` in tables, icon buttons with
  `aria-label`, status never by colour alone (badges carry a glyph).

## Git branches

Name branches after their purpose (`phase-1-screens`, `fix-sse-atomic-requests`, `early-access-gate`), never
after a tool, agent or AI (no `claude/…`).

## Sibling project

**DIAL — DECT & IP Administration Layer** (`kirikakaese/DIAL-BETA`, formerly PET — Portable Event
Telephone) is the sibling project whose conventions EVAC mirrors and the first extension (phase 4,
`extensions/dial`). Its names: `dial_…` service tokens, `X-DIAL-Signature` / `X-DIAL-Event` webhook headers,
`X-DIAL-PBX-Secret`, `DIAL_*` settings. Shared contracts (OIDC, early-access gate ADR-0012 with `DIAL_`
variables) must stay identical in both projects.

## Before you push

1. `make lint typecheck test openapi-check` — regenerate `docs/api/openapi.yaml` with `make openapi`
   when the API changed, and `makemigrations --check` must be clean.
2. `python scripts/check_attribution.py` and the manual check from section 0.1.
3. CHANGELOG entry under "Unreleased"; docs updated.
