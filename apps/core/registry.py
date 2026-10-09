# SPDX-License-Identifier: AGPL-3.0-or-later
"""The plugin registry: collects contributions from every installed plugin.

Plugins are discovered lazily (first access) by importing ``<app>.evac_plugin`` for every installed
Django app and calling its ``register(registry)``. Duplicate keys raise ``RegistryError`` so two plugins
can never silently shadow each other.
"""
from __future__ import annotations

import fnmatch
import importlib
import logging
import threading
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from .plugins import (
    API_VERSION,
    CliCommandSpec,
    DataSourceSpec,
    EvacTriggerSpec,
    EventHook,
    ExtensionSpec,
    ModuleSpec,
    NavEntry,
    NotificationChannelSpec,
    OutboxHandler,
    PermissionSpec,
    PluginManifest,
    ProgramSource,
    ScopeKind,
    SettingsNamespace,
    StaffCardSpec,
    WebhookEventSpec,
    WebhookSink,
    WidgetSpec,
)

log = logging.getLogger("evac.plugins")

T = TypeVar("T")


class RegistryError(Exception):
    pass


class Registry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._loaded = False
        self._current: str = ""
        self.plugins: dict[str, PluginManifest] = {}
        self.plugin_apps: dict[str, str] = {}
        self.modules: dict[str, ModuleSpec] = {}
        self.permissions: dict[str, PermissionSpec] = {}
        self.nav_entries: list[NavEntry] = []
        self.settings_namespaces: dict[str, SettingsNamespace] = {}
        self.scope_kinds: dict[str, ScopeKind] = {}
        self.data_sources: dict[str, DataSourceSpec] = {}
        self.widgets: dict[str, WidgetSpec] = {}
        self.notification_channels: dict[str, NotificationChannelSpec] = {}
        self.evac_triggers: dict[str, EvacTriggerSpec] = {}
        self.webhook_events: dict[str, WebhookEventSpec] = {}
        self.cli_commands: dict[str, CliCommandSpec] = {}
        self.extensions: dict[str, ExtensionSpec] = {}
        self.event_hooks: list[EventHook] = []
        self.outbox_handlers: dict[str, OutboxHandler] = {}
        self.webhook_sinks: list[WebhookSink] = []
        self.program_sources: list[ProgramSource] = []
        self.staff_cards: dict[str, StaffCardSpec] = {}
        self.websocket_routes: list[Any] = []
        self.api_routes: list[tuple[str, Any, str]] = []

    # ------------------------------------------------------------------ loading
    def ensure_loaded(self) -> Registry:
        if self._loaded:
            return self
        with self._lock:
            if self._loaded:
                return self
            from django.apps import apps

            for cfg in apps.get_app_configs():
                self._load_app(cfg.name)
            self._loaded = True
        return self

    def _load_app(self, app_name: str) -> None:
        try:
            mod = importlib.import_module(f"{app_name}.evac_plugin")
        except ModuleNotFoundError as exc:
            if exc.name != f"{app_name}.evac_plugin":
                raise
            return
        manifest = getattr(mod, "manifest", None)
        if not isinstance(manifest, PluginManifest):
            raise RegistryError(f"{app_name}.evac_plugin has no PluginManifest 'manifest'")
        if manifest.api_version > API_VERSION:
            raise RegistryError(
                f"plugin {manifest.key} needs plugin API {manifest.api_version}, this EVAC provides {API_VERSION}"
            )
        self._add(self.plugins, manifest.key, manifest, "plugin")
        self.plugin_apps[manifest.key] = app_name
        self._current = manifest.key
        try:
            register = getattr(mod, "register", None)
            if callable(register):
                register(self)
        finally:
            self._current = ""
        log.debug("loaded plugin %s %s from %s", manifest.key, manifest.version, app_name)

    def reset(self) -> None:
        """Forget everything (tests only)."""
        with self._lock:
            self.__init__()  # type: ignore[misc]

    @staticmethod
    def _add(store: dict[str, T], key: str, value: T, what: str) -> None:
        if key in store:
            raise RegistryError(f"duplicate {what} {key!r}")
        store[key] = value

    # ------------------------------------------------------------------ registration API
    def module(self, spec: ModuleSpec) -> None:
        self._add(self.modules, spec.key, spec, "module")

    def permission(self, spec: PermissionSpec) -> None:
        self._add(self.permissions, spec.key, spec, "permission")

    def permissions_(self, specs: Iterable[PermissionSpec]) -> None:
        for spec in specs:
            self.permission(spec)

    def nav(self, entry: NavEntry) -> None:
        self.nav_entries.append(entry)

    def settings_namespace(self, ns: SettingsNamespace) -> None:
        self._add(self.settings_namespaces, ns.key, ns, "settings namespace")

    def scope_kind(self, kind: ScopeKind) -> None:
        self._add(self.scope_kinds, kind.key, kind, "scope kind")

    def data_source(self, spec: DataSourceSpec) -> None:
        self._add(self.data_sources, spec.key, spec, "data source")

    def widget(self, spec: WidgetSpec) -> None:
        self._add(self.widgets, spec.key, spec, "widget")

    def notification_channel(self, spec: NotificationChannelSpec) -> None:
        self._add(self.notification_channels, spec.key, spec, "notification channel")

    def evac_trigger(self, spec: EvacTriggerSpec) -> None:
        self._add(self.evac_triggers, spec.key, spec, "evacuation trigger")

    def webhook_event(self, spec: WebhookEventSpec) -> None:
        self._add(self.webhook_events, spec.key, spec, "webhook event")

    def cli_command(self, spec: CliCommandSpec) -> None:
        self._add(self.cli_commands, spec.name, spec, "CLI command")

    def extension(self, spec: ExtensionSpec) -> None:
        self._add(self.extensions, spec.key, spec, "extension")

    def event_hook(self, hook: EventHook) -> None:
        self.event_hooks.append(hook)

    def outbox_handler(self, kind: str, handler: OutboxHandler) -> None:
        self._add(self.outbox_handlers, kind, handler, "outbox handler")

    def webhook_sink(self, sink: WebhookSink) -> None:
        self.webhook_sinks.append(sink)

    def program_source(self, fn: ProgramSource) -> None:
        """Contribute entries/overlays to every screen's program (see ``plugins.ProgramSource``)."""
        self.program_sources.append(fn)

    def staff_card(self, spec: StaffCardSpec) -> None:
        """A card on the staff page (PWA)."""
        self._add(self.staff_cards, spec.key, spec, "staff card")

    def websocket_route(self, route: Any) -> None:
        self.websocket_routes.append(route)

    def api_route(self, prefix: str, viewset: Any, basename: str) -> None:
        """Register a DRF viewset under ``/api/v1/<prefix>/``."""
        self.api_routes.append((prefix, viewset, basename))

    # ------------------------------------------------------------------ queries
    def permission_keys(self) -> list[str]:
        return sorted(self.ensure_loaded().permissions)

    def expand(self, patterns: Iterable[str]) -> set[str]:
        """Expand glob patterns (``screens.*``, ``*.view``, ``!events.delete``) to registered permission keys.

        Negated patterns remove matches; order does not matter (all removals apply after all additions).
        """
        keys = self.permission_keys()
        allow: set[str] = set()
        deny: set[str] = set()
        for pat in patterns:
            target = deny if pat.startswith("!") else allow
            pat = pat.lstrip("!")
            target.update(k for k in keys if fnmatch.fnmatchcase(k, pat))
        return allow - deny

    def sensitive_permissions(self) -> set[str]:
        return {k for k, p in self.ensure_loaded().permissions.items() if p.sensitive}

    def nav_for(self, section: str | None = None) -> list[NavEntry]:
        entries = self.ensure_loaded().nav_entries
        if section is not None:
            entries = [e for e in entries if e.section == section]
        return sorted(entries, key=lambda e: (e.order, e.label))

    def hooks(self) -> list[EventHook]:
        return sorted(self.ensure_loaded().event_hooks, key=lambda h: h.order)

    def get_extension(self, key: str) -> ExtensionSpec | None:
        return self.ensure_loaded().extensions.get(key)

    def call_sinks(self, event_type: str, payload: dict[str, Any], event: Any) -> None:
        for sink in self.ensure_loaded().webhook_sinks:
            sink(event_type, payload, event)


registry = Registry()


def plugin_of(fn: Callable[..., Any]) -> str:
    """Best-effort plugin key of a callable's module (for error messages)."""
    mod = getattr(fn, "__module__", "") or ""
    for key, app in registry.plugin_apps.items():
        if mod.startswith(app):
            return key
    return ""
