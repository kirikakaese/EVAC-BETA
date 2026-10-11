# ADR-0045: Plugin widgets on screens and the public plugin SDK

- Status: Accepted
- Date: 2026-10-11

## Context

Phase 9 (ticket 9.2) asks for public plugin SDK docs and an example plugin installed with pip through an entry
point. The gate: *the SDK example plugin adds a widget, a data source and an extension page without core changes*.

Data sources, extension pages and entry-point discovery (`evac.plugins`) existed since Phase 0. `WidgetSpec` had
`element` and `script` fields, but only the built-in widgets of the shared renderer used them, and screens could not
load code from a plugin. Custom widgets of Phase 2 (ADR-0023) are configuration, not code.

Constraints:
- Screens run a strict CSP and must keep working offline (brief §6).
- Plugin code must not be able to read other data than it declared.
- No heavy dependency, no build step forced on plugin authors.

## Decision

- **A plugin widget is a custom element in an ES module** from the plugin's static files:
  `WidgetSpec(key, name, element="evac-x-…", script="<app>/widget.js", data_sources=(…), settings_schema={…})`.
  Widgets whose script is the renderer's own bundle (`player/player.js`) are built-ins and never listed as plugins.
- **New layout element type `plugin`** with `props = {"widget": key, "settings": {…}}` (format unchanged otherwise).
  The renderer's `PluginWidget` loads the module once with `import()`, creates the element and sets `settings`,
  `vars` and `data = {source key: payload}`. Sources are refreshed every `ttl_seconds` of the slowest declared source
  (at least 10 s). A missing widget shows a placeholder; errors go to the usual element error path.
- **Data reaches the element only through EVAC.** Screens read `GET /player/api/content/sources/<key>/` (screen
  token), the editor and previews `/e/<event>/content/sources/<key>/` (`content.view`). Only sources declared by a
  plugin widget are readable there, only while the content module and the source's module are on. Payloads are
  cached per event for the source's TTL, so 1,000 screens cause one `fetch(event)` per TTL.
- **Offline:** the content bundle lists the plugin widgets; the player prefetches their scripts (the service worker
  caches `/static/` cache-first) and keeps the last payload of each source in memory and `localStorage`.
- **Editor:** `r.editor_choices("pluginWidgets", …)` offers the widgets with their settings schema; the editor
  builds a form for string, number, integer, boolean and enum properties.
- **Example plugin** `examples/evac-weather` (own package, `pyproject.toml` entry point, model, migration, Celery
  task, extension page, widget, tests). CI installs it with pip into a clean environment and runs its tests, which
  is the gate's proof that no core change is needed.

## Consequences

- Plugin JavaScript runs in the player's page, not in a sandboxed frame like code elements (ADR-0018). Installing a
  plugin is an administrator's decision on the server, like installing any Django app, so it is trusted the same
  way; layout authors only choose and configure installed widgets.
- Plugin authors write plain JavaScript modules; no bundler, no EVAC JS package. The contract is three properties.
- Styling must respect the CSP (constructed style sheets or CSSOM); documented in `docs/PLUGIN_SDK.md`.
- A data source's `fetch(event)` runs inside a request; plugins must keep it to database reads and fetch from the
  internet in Celery (the example shows the pattern).

## Alternatives considered

- **Sandboxed iframes for plugin widgets** (as code elements): safer against a hostile plugin, but plugins already
  run server-side Python with full access, so it buys nothing and costs memory per widget on small players.
- **Let elements fetch their own data:** would leak the screen token to plugin code and break offline caching.
- **A JS SDK package with a base class:** a build step and a version to keep in sync for authors; custom elements
  are a browser standard already.
