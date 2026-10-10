# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plugin manifest and contribution types - the stable plugin API.

Every module and every extension (built-in or third party) is a plugin: a Django app that ships an
``evac_plugin.py`` module with

    manifest = PluginManifest(key="screens", name="Screens", version="1.0", kind="module")

    def register(r: Registry) -> None:
        r.module(ModuleSpec(key="screens", name="Screens", ...))
        r.permission(PermissionSpec("screens.control", "Control screens", scopes=("venue", "zone")))
        r.nav(NavEntry(module="screens", label="Screens", url_name="screens:index", permission="screens.view"))
        ...

The core uses exactly the same API for its own features. Everything here is plain data (frozen
dataclasses) plus callables; nothing imports Django models, so the API stays importable in tools and
tests. See docs/PLUGIN_SDK.md for the full contract and versioning rules (``API_VERSION``).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

#: Bumped on breaking changes to anything in this module. Plugins declare the API version they target.
API_VERSION = 1

PluginKind = Literal["core", "module", "extension"]
NavSection = Literal["event", "operations", "content", "settings", "admin"]
ScopeLevel = Literal["instance", "venue", "event", "screen_group", "screen"]
SETTINGS_LEVELS: tuple[ScopeLevel, ...] = ("instance", "venue", "event", "screen_group", "screen")

JSONSchema = Mapping[str, Any]


@dataclass(frozen=True)
class PluginManifest:
    key: str
    name: str
    version: str
    kind: PluginKind = "module"
    description: str = ""
    api_version: int = API_VERSION
    homepage: str = ""


@dataclass(frozen=True)
class ModuleSpec:
    """A feature area that can be switched on/off globally and per event (Settings -> Modules).

    ``required`` modules cannot be switched off (the core). ``depends_on`` lists module keys that must be
    enabled for this one to be active; switching a dependency off makes dependants inactive too.
    """

    key: str
    name: str
    description: str = ""
    default_enabled: bool = True
    required: bool = False
    depends_on: tuple[str, ...] = ()
    event_toggle: bool = True
    category: str = "general"
    order: int = 100


@dataclass(frozen=True)
class PermissionSpec:
    """A ``module.action`` permission string.

    ``scopes`` lists the scope kinds a grant of this permission may be restricted to (e.g. "venue",
    "zone"). ``sensitive`` permissions (alarm triggers, role management) are only effective in a session
    that passed two-factor authentication, for every user including instance admins.
    """

    key: str
    label: str
    description: str = ""
    scopes: tuple[str, ...] = ()
    sensitive: bool = False

    @property
    def module(self) -> str:
        return self.key.split(".", 1)[0]


@dataclass(frozen=True)
class NavEntry:
    module: str
    label: str
    url_name: str
    permission: str = ""
    section: NavSection = "event"
    order: int = 100
    icon: str = ""
    #: url_name patterns (fnmatch) that mark this entry active; default: the entry's own namespace
    active: tuple[str, ...] = ()
    #: True = URL takes no event slug (instance-wide page)
    global_: bool = False


@dataclass(frozen=True)
class SettingsNamespace:
    """A typed group of settings described by a JSON schema (object with ``properties``).

    ``levels`` are the scope levels at which values may be set; values inherit along
    instance -> venue -> event -> screen_group -> screen.
    """

    key: str
    title: str
    schema: JSONSchema
    levels: tuple[ScopeLevel, ...] = ("instance", "event")
    module: str = "core"
    permission: str = "settings.manage"
    order: int = 100


@dataclass(frozen=True)
class ScopeKind:
    """A kind of object RBAC grants can be scoped to (venue, zone, room, screen group, team, ...).

    ``choices(event)`` returns ``[(id, label), ...]`` for the role assignment UI;
    ``chain(obj)`` returns the ``[(kind, id), ...]`` scopes an object lives in (most general first).
    """

    key: str
    label: str
    choices: Callable[[Any], Sequence[tuple[str, str]]]
    module: str = "core"


@dataclass(frozen=True)
class DataSourceSpec:
    """Something screens can display. Modules and extensions register data sources (Phase 1 consumes)."""

    key: str
    name: str
    schema: JSONSchema = field(default_factory=dict)
    mode: Literal["poll", "push", "webhook", "websocket", "mqtt"] = "poll"
    ttl_seconds: int = 60
    permission: str = ""
    fetch: Callable[..., Any] | None = None
    module: str = "core"
    description: str = ""


@dataclass(frozen=True)
class WidgetSpec:
    key: str
    name: str
    version: str = "1"
    settings_schema: JSONSchema = field(default_factory=dict)
    data_sources: tuple[str, ...] = ()
    element: str = ""  # custom element tag name of the renderer (Web Component)
    script: str = ""  # static path of the renderer bundle
    module: str = "core"
    description: str = ""


@dataclass(frozen=True)
class NotificationChannelSpec:
    """An announcement channel (ADR-0019). ``send(delivery) -> {"status", "recipients", "detail"}`` runs in the
    outbox (raise to retry). ``available(event) -> bool`` hides it where it is not set up (e.g. an extension that
    is off); ``max_length`` > 0 offers a shorter per-channel text in the composer."""

    key: str
    name: str
    send: Callable[..., Any] | None = None
    module: str = "core"
    description: str = ""
    available: Callable[[Any], bool] | None = None
    max_length: int = 0


@dataclass(frozen=True)
class StaffCardSpec:
    """A card on the staff page (PWA, ADR-0021). ``context(request, event) -> dict | None`` returns the template
    context, or None to hide the card for this user; ``template`` renders it (one ``<section class="card">``)."""

    key: str
    title: str
    template: str
    context: Callable[[Any, Any], Mapping[str, Any] | None]
    module: str = "core"
    order: int = 100


@dataclass(frozen=True)
class PackSectionSpec:
    """A kind of content in ``.evacpack`` files (ADR-0024), e.g. layouts or widgets.

    * ``choices(event) -> [(id, label)]``: what can be exported from the event.
    * ``requires(event, ids) -> {section: ids}``: what these objects need (``"*"``: ids of any section, e.g.
      UUIDs inside layout data); the export adds them.
    * ``dump(event, ids, files) -> [item]``: JSON items (each with ``id`` and ``name``); ``files.add(path,
      name) -> ref`` puts a file into the pack.
    * ``load(event, items, ctx) -> [label]``: creates the objects through the module's services; ``ctx.ids`` maps
      pack ids to new ids (fill it for every created object), ``ctx.remap(value)`` rewrites ids in JSON,
      ``ctx.file(ref)`` opens a packed file, ``ctx.warn(text)`` reports skipped parts.

    Sections load in ``order`` (dependencies first)."""

    key: str
    title: str
    choices: Callable[[Any], list[tuple[str, str]]]
    dump: Callable[[Any, set[str], Any], list[dict[str, Any]]]
    load: Callable[[Any, list[dict[str, Any]], Any], list[str]]
    requires: Callable[[Any, set[str]], Mapping[str, set[str]]] | None = None
    module: str = "core"
    order: int = 100
    #: offered on the export page (False: only exported as a dependency, e.g. files)
    selectable: bool = True


@dataclass(frozen=True)
class EvacTriggerSpec:
    """A source that can raise an evacuation/alarm state change (consumed by the Phase 3 module)."""

    key: str
    name: str
    description: str = ""
    module: str = "core"


@dataclass(frozen=True)
class WebhookEventSpec:
    """An outbound webhook event type (``evac.state_changed``, ``event.created``, ...)."""

    key: str
    description: str = ""
    module: str = "core"


@dataclass(frozen=True)
class CliCommandSpec:
    """A sub-command of the ``evac`` CLI. ``configure(parser)`` adds arguments; ``run(args, client)``."""

    name: str
    help: str
    configure: Callable[[Any], None]
    run: Callable[[Any, Any], int]
    module: str = "core"


@dataclass(frozen=True)
class EventHook:
    """Per-event lifecycle hooks a plugin contributes (export/import/clone of its own data).

    ``export(event) -> dict``, ``import_(event, data, user)``, ``clone(src, dst, with_content)``.
    """

    module: str
    export: Callable[[Any], Any] | None = None
    import_: Callable[[Any, Any, Any], None] | None = None
    clone: Callable[[Any, Any, bool], None] | None = None
    order: int = 100


OutboxHandler = Callable[[Any], None]
WebhookSink = Callable[[str, Mapping[str, Any], Any], None]
#: ``fn(event, target, start, end) -> {"entries": [...], "messages": {...}, "overlays": [...]}``: extra content for
#: a screen's program (announcements, evacuation). ``target`` describes the screen or screen group asking, times
#: are aware datetimes; entries use the format of ``apps/playlists/engine.py``.
ProgramSource = Callable[[Any, Any, Any, Any], Mapping[str, Any]]


@dataclass(frozen=True)
class ExtensionFeature:
    """Something an extension contributes that can be switched on/off individually on its settings page."""

    key: str
    name: str
    kind: Literal["data_source", "widget", "trigger", "channel", "import", "webhook", "other"] = "other"
    description: str = ""
    default_enabled: bool = True


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    message: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookResult:
    """What an extension's inbound webhook handler returns (rendered as JSON to the caller)."""

    status: int = 200
    body: Mapping[str, Any] = field(default_factory=lambda: {"ok": True})


@dataclass(frozen=True)
class ExtensionSpec:
    """An integration with an external system, configured under Settings -> Extensions.

    * ``scope``: "instance" (configured once, used by many events), "event" (each event links its own
      external instance) or "both".
    * ``settings_schema``: JSON schema of the non-secret connection settings (auto-generated form).
    * ``secret_fields``: names of secret values (encrypted at rest, never shown again after save).
    * ``test_connection(config) -> ConnectionResult`` powers the "Test connection" button.
    * ``handle_webhook(config, headers, body: bytes, payload) -> WebhookResult`` handles inbound webhooks
      after EVAC verified the HMAC signature (header ``signature_header``, ``sha256=<hex>``).
    * ``purge(config)`` deletes data the extension imported ("disconnect & purge").
    * ``urls``: dotted path of an optional urlconf with custom views, mounted below the settings page.
    """

    key: str
    name: str
    description: str = ""
    version: str = "1.0"
    scope: Literal["instance", "event", "both"] = "both"
    settings_schema: JSONSchema = field(default_factory=lambda: {"type": "object", "properties": {}})
    secret_fields: tuple[tuple[str, str], ...] = ()  # (name, label)
    features: tuple[ExtensionFeature, ...] = ()
    permissions: tuple[str, ...] = ()
    inbound_webhooks: bool = False
    signature_header: str = "X-EVAC-Signature"
    event_header: str = "X-EVAC-Event"
    delivery_header: str = "X-EVAC-Delivery"
    test_connection: Callable[[Any], ConnectionResult] | None = None
    handle_webhook: Callable[[Any, Mapping[str, str], bytes, Any], WebhookResult] | None = None
    purge: Callable[[Any], None] | None = None
    urls: str = ""
    docs: str = ""
    icon: str = ""
