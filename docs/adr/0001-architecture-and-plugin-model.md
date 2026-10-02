# ADR-0001: Architecture and plugin model

- Status: Accepted
- Date: 2026-10-02

## Context

EVAC must be modular down to "screens only" (brief §1), let third parties add modules, widgets, data
sources, extensions and evacuation triggers (§3.3), and run one permanent multi-event service plus venue
nodes (§3.2). The sibling project PET sets the conventions (Django/DRF, `apps/<area>`, per-app UIs under
`/e/<slug>/<app>/`, outbox, service tokens).

## Decision

1. **Stack as in the brief**: Python 3.12, Django 5.2, DRF + drf-spectacular, Channels (ASGI), Celery +
   beat on Redis, PostgreSQL 16 (SQLite for dev/tests), server-rendered templates + HTMX.
2. **Everything is a plugin.** A plugin is a Django app with an `evac_plugin.py` module exposing
   `manifest: PluginManifest` and `register(registry)`. Contributions are frozen dataclasses defined in
   `apps/core/plugins.py` (the stable API, versioned by `API_VERSION`): `ModuleSpec`, `PermissionSpec`,
   `NavEntry`, `SettingsNamespace`, `ScopeKind`, `DataSourceSpec`, `WidgetSpec`,
   `NotificationChannelSpec`, `EvacTriggerSpec`, `WebhookEventSpec`, `CliCommandSpec`, `ExtensionSpec`,
   `EventHook` (export/import/clone), outbox handlers, webhook sinks, WebSocket and API routes.
3. The **registry** (`apps/core/registry.py`) loads lazily on first use by importing `<app>.evac_plugin`
   for every installed app; duplicate keys raise. Third-party plugins are installed with pip and listed
   under the entry point group `evac.plugins` (value = Django app module), which settings read at start-up.
   `EVAC_DISABLED_PLUGINS` uninstalls a plugin; *switching a module off* is a runtime toggle (ADR in code:
   `apps/core/modules.py`).
4. The **core uses the same API** (core, accounts, events, venues, extensions, portal all have
   `evac_plugin.py`), so the API is exercised from day one. The core never imports an optional module.
5. UI mounting follows PET: an app's `urls.py` with `PORTAL_MOUNT = True` is mounted at
   `/e/<slug>/<label>/`. The sidebar is generated from registered `NavEntry`s filtered by module state and
   permissions.
6. Brief §3.3 mentions `evac_plugin.toml`; we use a Python module instead (no second manifest format,
   type-checked, can register callables). A TOML manifest can be generated from it later if a
   marketplace needs static metadata.

## Consequences

- Adding a module = adding an app + `evac_plugin.py`; no core edits.
- Contribution types are the compatibility surface: changing them requires bumping `API_VERSION` and a
  CHANGELOG note.
- Registry loading happens inside Django's app registry; plugins must not query the database at import.

## Alternatives considered

- Django signals only: no discoverability, no typed contract.
- Separate microservices per module: contradicts "boring, proven", offline venue nodes and the PET model.
