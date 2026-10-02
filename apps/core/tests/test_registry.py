# SPDX-License-Identifier: AGPL-3.0-or-later
import types

import pytest

from apps.core import plugins
from apps.core.registry import Registry, RegistryError, registry


def test_builtin_plugins_registered():
    reg = registry.ensure_loaded()
    assert {"core", "events", "venues", "extensions", "webhooks"} <= set(reg.plugins)
    assert "venues.manage" in reg.permissions
    assert "webhooks" in reg.extensions
    assert "event.state_changed" in reg.webhook_events
    assert {"venue", "zone", "room"} <= set(reg.scope_kinds)
    assert reg.permissions["events.roles"].sensitive


def test_expand_patterns():
    keys = registry.expand(["*", "!events.delete"])
    assert "events.view" in keys and "events.delete" not in keys
    assert registry.expand(["*.view"]) >= {"events.view", "venues.view"}
    assert registry.expand(["nothing.*"]) == set()


def test_duplicates_are_rejected():
    r = Registry()
    r.module(plugins.ModuleSpec(key="x", name="X"))
    with pytest.raises(RegistryError):
        r.module(plugins.ModuleSpec(key="x", name="X again"))


def test_plugin_api_version_check(monkeypatch):
    r = Registry()
    mod = types.ModuleType("fakeapp.evac_plugin")
    mod.manifest = plugins.PluginManifest(key="fake", name="Fake", version="1", api_version=plugins.API_VERSION + 1)
    monkeypatch.setitem(__import__("sys").modules, "fakeapp", types.ModuleType("fakeapp"))
    monkeypatch.setitem(__import__("sys").modules, "fakeapp.evac_plugin", mod)
    with pytest.raises(RegistryError):
        r._load_app("fakeapp")


def test_plugin_without_manifest_is_rejected(monkeypatch):
    r = Registry()
    mod = types.ModuleType("bad.evac_plugin")
    monkeypatch.setitem(__import__("sys").modules, "bad", types.ModuleType("bad"))
    monkeypatch.setitem(__import__("sys").modules, "bad.evac_plugin", mod)
    with pytest.raises(RegistryError):
        r._load_app("bad")


def test_third_party_plugin_contributes_everything(monkeypatch):
    """A plugin registers through the same API the core uses (proves the API surface)."""
    r = Registry()
    mod = types.ModuleType("thirdparty.evac_plugin")
    mod.manifest = plugins.PluginManifest(key="tp", name="Third party", version="0.1")

    def register(reg):
        reg.module(plugins.ModuleSpec(key="tp", name="TP"))
        reg.permission(plugins.PermissionSpec("tp.view", "View"))
        reg.data_source(plugins.DataSourceSpec(key="tp.numbers", name="Numbers"))
        reg.widget(plugins.WidgetSpec(key="tp.counter", name="Counter", element="tp-counter"))
        reg.notification_channel(plugins.NotificationChannelSpec(key="tp.pager", name="Pager"))
        reg.evac_trigger(plugins.EvacTriggerSpec(key="tp.button", name="Button"))
        reg.webhook_event(plugins.WebhookEventSpec(key="tp.happened"))
        reg.cli_command(plugins.CliCommandSpec(name="tp", help="tp", configure=lambda p: None, run=lambda a, c: 0))
        reg.extension(plugins.ExtensionSpec(key="tp-ext", name="TP ext"))
        reg.nav(plugins.NavEntry(module="tp", label="TP", url_name="tp:index"))
        reg.outbox_handler("tp.job", lambda job: None)

    mod.register = register
    monkeypatch.setitem(__import__("sys").modules, "thirdparty", types.ModuleType("thirdparty"))
    monkeypatch.setitem(__import__("sys").modules, "thirdparty.evac_plugin", mod)
    r._load_app("thirdparty")
    assert r.plugin_apps["tp"] == "thirdparty"
    assert "tp.counter" in r.widgets and "tp.button" in r.evac_triggers and "tp" in r.cli_commands
    assert r.nav_entries[0].url_name == "tp:index"
