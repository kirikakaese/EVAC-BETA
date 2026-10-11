# SPDX-License-Identifier: AGPL-3.0-or-later
"""The plugin's whole contract with EVAC (docs/PLUGIN_SDK.md): a manifest and ``register(r)``.

It adds, without any change to EVAC itself:
* a data source ``weather.current`` (the latest observation of the event),
* a screen widget ``weather.current`` (the custom element <evac-x-weather> from static/evac_weather/weather.js),
* an extension "Weather" under Settings -> Extensions with its own page (enter readings, fetch now).
"""
from __future__ import annotations

from apps.core.plugins import (
    ConnectionResult,
    DataSourceSpec,
    ExtensionFeature,
    ExtensionSpec,
    PluginManifest,
    WidgetSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="weather", name="Weather", version="1.0.0", kind="extension",
                          description="Example plugin: weather at the venue on screens.",
                          homepage="https://github.com/kirikakaese/EVAC-BETA/tree/main/examples/evac-weather")


def _current(event):
    from . import services

    return services.current(event)


def _test(config) -> ConnectionResult:
    s = config.settings
    if s.get("online") and (s.get("latitude") is None or s.get("longitude") is None):
        return ConnectionResult(False, "Set latitude and longitude to fetch the weather online.")
    return ConnectionResult(True, "Ready. Screens show the latest reading.")


def register(r: Registry) -> None:
    r.data_source(DataSourceSpec(
        key="weather.current", name="Weather at the venue", ttl_seconds=60, fetch=_current,
        description="The latest weather observation: entered by staff or fetched from Open-Meteo.",
        schema={"type": "object", "properties": {"observation": {"type": ["object", "null"]}}}))
    r.widget(WidgetSpec(
        key="weather.current", name="Weather", element="evac-x-weather", script="evac_weather/weather.js",
        data_sources=("weather.current",), version="1",
        description="Temperature and conditions at the venue.",
        settings_schema={"type": "object", "properties": {
            "title": {"type": "string", "title": "Heading", "maxLength": 60, "default": "Weather"},
            "unit": {"type": "string", "title": "Unit", "enum": ["C", "F"], "default": "C"},
            "wind": {"type": "boolean", "title": "Show wind", "default": True},
        }}))
    r.extension(ExtensionSpec(
        key="weather", name="Weather", version="1.0.0", scope="event",
        description="Weather at the venue for screens: type readings in (works offline) or fetch them from "
                    "Open-Meteo.",
        settings_schema={"type": "object", "properties": {
            "place": {"type": "string", "title": "Place name shown on screens", "maxLength": 60, "default": ""},
            "online": {"type": "boolean", "title": "Fetch from Open-Meteo", "default": False,
                       "description": "Needs internet at the server. Without it, staff enter readings."},
            "latitude": {"type": "number", "title": "Latitude", "minimum": -90, "maximum": 90},
            "longitude": {"type": "number", "title": "Longitude", "minimum": -180, "maximum": 180},
            "refresh_minutes": {"type": "integer", "title": "Refresh every (minutes)", "minimum": 10,
                                "maximum": 720, "default": 30},
        }},
        features=(ExtensionFeature("widget", "Weather widget", kind="widget"),),
        test_connection=_test, urls="evac_weather.urls"))
