# SPDX-License-Identifier: AGPL-3.0-or-later
"""The example plugin, installed with pip: entry point, widget, data source, extension page (Phase 9 gate).

Run from the EVAC checkout after ``pip install ./examples/evac-weather``:
``pytest examples/evac-weather/tests``.
"""
import json
from unittest import mock

import pytest
from django.core.cache import cache
from evac_weather import services, tasks
from evac_weather.models import Observation
from rest_framework.test import APIClient

from apps.content import layout_views, plugin_widgets
from apps.content.tests.test_layouts import screen_token
from apps.core import safefetch
from apps.core.models import AuditLog
from apps.core.registry import registry
from apps.extensions import services as ext
from conftest import login_2fa

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()


def configure(event, **values):
    spec = registry.get_extension("weather")
    cfg = ext.get_or_new(spec, event)
    return ext.save_config(cfg, settings_values={"place": "Meadow", **values}, secret_values={},
                           features={"widget": True}, enabled=True)


def test_installed_through_the_entry_point(settings):
    assert "evac_weather" in settings.INSTALLED_APPS
    reg = registry.ensure_loaded()
    assert reg.plugins["weather"].version == "1.0.0"
    assert "weather.current" in reg.data_sources and "weather" in reg.extensions
    assert reg.widgets["weather.current"].element == "evac-x-weather"


def test_widget_reaches_the_editor_and_the_player(client, admin, event):
    configure(event)
    services.record(event, temperature_c=18.5, condition="Light rain", wind_kmh=12, actor=admin)
    choices = {c["value"]: c for c in layout_views.editor_choices(event)["pluginWidgets"]}
    assert choices["weather.current"]["schema"]["properties"]["unit"]["enum"] == ["C", "F"]
    from apps.content.tests.test_plugin_widgets import publish_with

    publish_with(event, admin, "weather.current")
    _, token = screen_token(client, admin, event)
    dev = APIClient()
    dev.credentials(HTTP_AUTHORIZATION=f"Screen {token}")
    info = dev.get("/player/api/content/bundle/").json()["bundle"]["plugins"]["weather.current"]
    assert info["script"].endswith("evac_weather/weather.js") and info["sources"] == ["weather.current"]
    data = dev.get("/player/api/content/sources/weather.current/").json()["data"]
    assert data["location"] == "Meadow"
    assert data["observation"]["temperature_c"] == 18.5 and data["observation"]["condition"] == "Light rain"
    assert plugin_widgets.source_payload(event, "weather.current") == data


def test_extension_page_records_readings(client, admin, event):
    configure(event)
    login_2fa(client, admin)
    url = "/e/demo/settings/extensions/weather/x/"
    page = client.get(url)
    assert page.status_code == 200 and b"Weather at the venue" in page.content
    r = client.post(url, {"temperature_c": "21", "condition": "Sunny", "wind_kmh": ""})
    assert r.status_code == 302
    obs = Observation.objects.get(event=event)
    assert obs.temperature_c == 21 and obs.created_by == admin and obs.source == "manual"
    assert AuditLog.objects.filter(action="weather.recorded", event_id=event.pk).exists()


def test_page_needs_a_saved_configuration(client, admin, event):
    login_2fa(client, admin)
    assert client.get("/e/demo/settings/extensions/weather/x/").status_code == 404


def test_online_mode_fetches_in_the_background(client, admin, event):
    cfg = configure(event, online=True, latitude=52.5, longitude=13.4)
    with mock.patch.object(tasks.fetch, "delay") as delay:
        assert services.current(event)["observation"] is None
    delay.assert_called_once_with(str(cfg.pk), str(event.pk))  # stale: queued, not fetched in the request
    body = {"current": {"temperature_2m": 9.4, "weather_code": 61, "wind_speed_10m": 20.2}}
    fetched = safefetch.Fetched(200, json.dumps(body).encode(), "application/json", "")
    with mock.patch.object(safefetch, "get", return_value=fetched) as get:
        assert tasks.fetch(str(cfg.pk), str(event.pk)) == "ok"
        assert tasks.fetch(str(cfg.pk), str(event.pk)) == "already running"  # one fetch a minute
    assert "latitude=52.5" in get.call_args.args[0]
    obs = Observation.objects.get(event=event)
    assert (obs.condition, obs.source, obs.temperature_c) == ("Light rain", "open-meteo", 9.4)
    with mock.patch.object(tasks.fetch, "delay") as delay:
        services.current(event)
    delay.assert_not_called()  # fresh


def test_failed_fetch_is_logged(event):
    cfg = configure(event, online=True, latitude=1, longitude=2)
    with mock.patch.object(safefetch, "get", side_effect=safefetch.FetchError("offline")):
        assert tasks.fetch(str(cfg.pk), str(event.pk)) == "failed"
    assert cfg.logs.filter(level="error").exists()
    assert not Observation.objects.exists()
