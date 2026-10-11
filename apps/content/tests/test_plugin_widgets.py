# SPDX-License-Identifier: AGPL-3.0-or-later
"""Widgets of third-party plugins (ADR-0045): bundle, data source endpoints, editor choices, layout format."""
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.content import layout_format, layout_views, plugin_widgets
from apps.core import modules
from apps.core.plugins import DataSourceSpec, WidgetSpec
from apps.core.registry import registry
from conftest import login_2fa

from .test_layouts import screen_token

CALLS = []


def _fetch(event):
    CALLS.append(event.pk)
    return {"temp": 21, "event": event.slug}


@pytest.fixture
def plugin(monkeypatch):
    reg = registry.ensure_loaded()
    monkeypatch.setitem(reg.data_sources, "x.weather", DataSourceSpec(
        key="x.weather", name="Weather", ttl_seconds=120, fetch=_fetch, module="core"))
    monkeypatch.setitem(reg.data_sources, "x.secret", DataSourceSpec(
        key="x.secret", name="Not for widgets", fetch=lambda e: {"no": 1}, module="core"))
    monkeypatch.setitem(reg.widgets, "x.weather", WidgetSpec(
        key="x.weather", name="Weather", element="evac-x-weather", script="evac_x/weather.js",
        data_sources=("x.weather",), module="core", description="Today's weather",
        settings_schema={"type": "object", "properties": {"unit": {"type": "string", "enum": ["C", "F"]}}}))
    cache.clear()
    CALLS.clear()
    return reg


def publish_with(event, admin, widget):
    from apps.content import layout_format
    from apps.content import services as content

    data = layout_format.empty(1920, 1080)
    data["elements"].append({"id": "w", "type": "plugin", "frame": {"x": 0, "y": 0, "w": 50, "h": 50},
                             "props": {"widget": widget, "settings": {}}})
    lay = content.create_layout(event, name="Plugin", key="plugin-" + widget.replace(".", "-"), actor=admin, data=data)
    content.publish_layout(lay, actor=admin)


def test_layout_format_accepts_plugin_elements():
    data = layout_format.empty(1920, 1080)
    data["elements"].append({"id": "w", "type": "plugin", "frame": {"x": 0, "y": 0, "w": 50, "h": 50},
                             "props": {"widget": "x.weather", "settings": {"unit": "C"}}})
    assert layout_format.validate(data) == []
    data["elements"][0]["props"]["widget"] = "Not a key!"
    assert layout_format.validate(data)


@pytest.mark.django_db
def test_widgets_skip_builtins_and_disabled_modules(plugin, event, monkeypatch):
    found = {k: v for k, v in plugin_widgets.widgets(event).items() if k.startswith("x.")}  # installed ones aside
    assert set(found) == {"x.weather"}
    assert "program" not in plugin_widgets.widgets(event)  # widgets the renderer draws itself are not plugins
    w = found["x.weather"]
    assert w["element"] == "evac-x-weather" and w["script"].endswith("evac_x/weather.js")
    assert w["sources"] == ["x.weather"] and w["ttl"] == 120
    assert "x.weather" in plugin_widgets.readable_sources(event)
    assert "x.secret" not in plugin_widgets.readable_sources(event)
    monkeypatch.setitem(plugin.widgets, "x.weather", WidgetSpec(
        key="x.weather", name="Weather", element="evac-x-weather", script="evac_x/weather.js", module="program"))
    modules.set_event(event, "program", False)
    assert "x.weather" not in plugin_widgets.widgets(event)


@pytest.mark.django_db
def test_player_bundle_and_source_endpoint(plugin, client, admin, event):
    _, token = screen_token(client, admin, event)
    dev = APIClient()
    dev.credentials(HTTP_AUTHORIZATION=f"Screen {token}")
    bundle = dev.get("/player/api/content/bundle/").json()["bundle"]
    assert bundle["plugins"]["x.weather"]["element"] == "evac-x-weather"
    assert "schema" not in bundle["plugins"]["x.weather"]  # the player needs no forms
    assert dev.get("/player/api/content/sources/x.weather/").status_code == 404  # no published layout uses it
    publish_with(event, admin, "x.weather")
    r = dev.get("/player/api/content/sources/x.weather/")
    assert r.status_code == 200 and r.json() == {"key": "x.weather", "data": {"temp": 21, "event": "demo"}}
    dev.get("/player/api/content/sources/x.weather/")
    assert CALLS == [event.pk]  # cached for the source's ttl
    assert dev.get("/player/api/content/sources/x.secret/").status_code == 404  # not declared by a widget
    assert dev.get("/player/api/content/sources/nope/").status_code == 404
    assert APIClient().get("/player/api/content/sources/x.weather/").status_code == 401
    modules.set_event(event, "content", False)
    assert dev.get("/player/api/content/sources/x.weather/").status_code == 404


@pytest.mark.django_db
def test_editor_choices_and_portal_source(plugin, client, admin, user, event, monkeypatch):
    choices = [c for c in layout_views.editor_choices(event)["pluginWidgets"] if c["value"] == "x.weather"]
    assert choices[0]["value"] == "x.weather" and choices[0]["schema"]["properties"]["unit"]["enum"] == ["C", "F"]
    assert choices[0]["element"] == "evac-x-weather"
    cfg = plugin_widgets.preview_config(event)
    assert cfg["sources"] == "/e/demo/content/sources/" and "x.weather" in cfg["widgets"]
    login_2fa(client, admin)
    r = client.get("/e/demo/content/sources/x.weather/")
    assert r.status_code == 200 and r.json()["data"]["temp"] == 21
    assert client.get("/e/demo/content/sources/x.secret/").status_code == 404
    monkeypatch.setitem(plugin.data_sources, "x.weather", DataSourceSpec(
        key="x.weather", name="Weather", fetch=_fetch, permission="helpdesk.manage"))
    cache.clear()
    login_2fa(client, user)
    from apps.events import services as event_services
    from apps.events.models import Role

    event_services.assign_role(event, user, Role.objects.get(event=event, key="viewer"))
    assert client.get("/e/demo/content/sources/x.weather/").status_code == 404  # needs the source's permission
    login_2fa(client, admin)
    assert client.get("/e/demo/content/sources/x.weather/").status_code == 200
