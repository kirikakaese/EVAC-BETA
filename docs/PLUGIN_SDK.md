# Plugin SDK

Every EVAC module and extension — built-in or third party — is a **plugin**: a Django app with an
`evac_plugin.py`. The core uses exactly the same API ([ADR-0001](adr/0001-architecture-and-plugin-model.md)).
Plugin API version: `apps.core.plugins.API_VERSION = 1`.

## Minimal plugin

```
my_plugin/
  __init__.py
  apps.py            # AppConfig(name="my_plugin", label="my_plugin")
  models.py
  urls.py            # optional; PORTAL_MOUNT = True mounts it at /e/<slug>/my_plugin/
  evac_plugin.py
  templates/my_plugin/...
```

```python
# my_plugin/evac_plugin.py
from apps.core.plugins import (ModuleSpec, NavEntry, PermissionSpec, PluginManifest, SettingsNamespace,
                               WidgetSpec, DataSourceSpec, WebhookEventSpec)
from apps.core.registry import Registry

manifest = PluginManifest(key="lostfound", name="Lost & found", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    r.module(ModuleSpec(key="lostfound", name="Lost & found", default_enabled=True, depends_on=("venues",)))
    r.permission(PermissionSpec("lostfound.view", "See lost & found items"))
    r.permission(PermissionSpec("lostfound.manage", "Record and hand out items", scopes=("venue",)))
    r.nav(NavEntry(module="lostfound", label="Lost & found", url_name="lostfound:index",
                   permission="lostfound.view", section="operations"))
    r.settings_namespace(SettingsNamespace(key="lostfound", title="Lost & found", module="lostfound",
        levels=("instance", "event"),
        schema={"type": "object", "properties": {
            "keep_days": {"type": "integer", "minimum": 1, "default": 30, "title": "Keep items for (days)"}}}))
    r.webhook_event(WebhookEventSpec("lostfound.item_found", "An item was registered", module="lostfound"))
    r.data_source(DataSourceSpec(key="lostfound.highlights", name="Lost & found highlights", module="lostfound"))
    r.widget(WidgetSpec(key="lostfound.board", name="Lost & found board", element="evac-lostfound-board",
                        data_sources=("lostfound.highlights",), module="lostfound"))
```

## Installing a third-party plugin

Package it and declare the entry point; EVAC adds the app to `INSTALLED_APPS` at start-up:

```toml
[project.entry-points."evac.plugins"]
lostfound = "my_plugin"
```

Then `pip install my-plugin`, `manage.py migrate`, restart. `EVAC_DISABLED_PLUGINS=my_plugin` uninstalls it
again without removing the package.

## Contribution types (`apps/core/plugins.py`)

| Type | Registered with | Used for |
|---|---|---|
| `PluginManifest` | module attribute `manifest` | identity, version, kind, `api_version` |
| `ModuleSpec` | `r.module` | Settings → Modules toggle; `required`, `default_enabled`, `depends_on`, `event_toggle` |
| `PermissionSpec` | `r.permission` | `module.action` keys; `scopes` it may be limited to; `sensitive` (needs 2FA) |
| `NavEntry` | `r.nav` | sidebar link; hidden when the module is off or the permission missing |
| `SettingsNamespace` | `r.settings_namespace` | typed settings with inheritance and generated forms |
| `ScopeKind` | `r.scope_kind` | objects role assignments can be scoped to |
| `DataSourceSpec`, `WidgetSpec` | `r.data_source`, `r.widget` | screen content; a data source with `fetch(event)` returning JSON-like data can feed custom widgets (ADR-0023) |
| `NotificationChannelSpec` | `r.notification_channel` | announcement channels: `send(delivery) -> {"status", "recipients", "detail"}`, called from the outbox (raise to retry); `available(event)` hides it where it is not set up; `max_length` offers an own text per channel (ADR-0019, ADR-0020; example: `extensions/notify`) |
| `EvacTriggerSpec` | `r.evac_trigger` | alarm trigger sources (phase 3) |
| `WebhookEventSpec` | `r.webhook_event` | outbound event types (`apps.core.webhooks.emit`) |
| `CliCommandSpec` | `r.cli_command` | `evac <name>` sub-commands |
| `ExtensionSpec` | `r.extension` | Settings → Extensions page, secrets, test, inbound webhooks, purge, custom views |
| `EventHook` | `r.event_hook` | your data in event export/import/clone |
| outbox handler | `r.outbox_handler(kind, fn)` | durable outgoing deliveries |
| staff card | `r.staff_card(StaffCardSpec(key, title, template, context))` | a card on the staff page (PWA); `context(request, event)` returns the template context or `None` to hide it (ADR-0021) |
| program source | `r.program_source(fn)` | `fn(event, target, start, end) -> {"entries", "messages", "overlays"}`: extra content in every screen's program (announcements; evacuation in phase 3) |
| editor choices | `r.editor_choices(key, fn, module=)` | `fn(event)` returns data the layout editor receives under `choices[key]` while the module is on (widget list for the data element) |
| pack section | `r.pack_section(PackSectionSpec(key, title, choices, dump, load, requires=, module=, order=))` | your objects in `.evacpack` files: `dump` returns JSON items (and packs files), `load` creates them through your services and fills `ctx.ids`; `requires` names what an object needs (ADR-0024) |
| time anchors | `r.anchor_source(TimeAnchorSpec(key, title, choices, resolve))` | items announcements can be timed relative to ("10 min before …"); send `apps.core.signals.anchor_moved` when one moves (ADR-0025) |
| audiences | `r.audience(AudienceSpec(key, title, choices, members))` | groups of people channels that reach people can be limited to (built in: roles) |
| map layer | `r.map_layer(MapLayerSpec(key, title, items, place=, rescale=))` | your things on the venue map: `items(event, venue)` lists them with position and facing, `place(...)` stores a move (ADR-0027; screens) |
| webhook sink | `r.webhook_sink(fn)` | receive every emitted event (used by the webhooks extension) |
| WebSocket / API routes | `r.websocket_route`, `r.api_route(prefix, viewset, basename)` | realtime consumers, REST endpoints |

Duplicate keys raise `RegistryError`; a plugin needing a newer `api_version` refuses to load.

## Rules for plugin code

- Check module state (`event_view(perm, module=...)` / `require_module`) and permissions
  (`apps.events.rbac.has_perm`). Give scoped objects an `evac_scope_chain()` method.
- Change state in service functions that call `apps.core.audit.log(...)`.
- Deliver to external systems through `apps.core.outbox.enqueue(...)`, never inside the request.
- Store secrets with `apps.core.crypto` (or as extension secrets); never log them.
- English UI text wrapped in `gettext`; templates pass the a11y linter; no inline JavaScript (strict CSP).
- Do not import other optional plugins; talk to them through the registry (data sources, webhook events,
  signals).

## Extensions

```python
from apps.core.plugins import ConnectionResult, ExtensionFeature, ExtensionSpec, WebhookResult

def test(config):            # config: apps.extensions.models.ExtensionConfig
    token = config.secret("api_token")
    ...
    return ConnectionResult(True, "Connected to Foo 2.1")

def on_webhook(config, headers, body, payload):
    ...
    return WebhookResult(200, {"ok": True})

SPEC = ExtensionSpec(
    key="foo", name="Foo", scope="event",
    settings_schema={"type": "object", "required": ["base_url"],
                     "properties": {"base_url": {"type": "string", "format": "uri", "title": "Foo URL"}}},
    secret_fields=(("api_token", "API token"),),
    features=(ExtensionFeature("rooms", "Room import", "import"),),
    inbound_webhooks=True, signature_header="X-Foo-Signature",
    test_connection=test, handle_webhook=on_webhook, purge=lambda config: ...,
    urls="foo_ext.urls",  # optional custom views at .../extensions/foo/x/
)
```

Use `apps.extensions.services.effective(key, event)` to get the configuration that applies to an event
(own connection or the instance-wide one) and `config.feature_enabled("rooms")` before doing work.
