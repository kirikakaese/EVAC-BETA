# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetches the current weather from Open-Meteo in the background (never inside a request)."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from celery import shared_task
from django.core.cache import cache

from apps.core import safefetch

API = "https://api.open-meteo.com/v1/forecast"


@shared_task(name="evac_weather.tasks.fetch")
def fetch(config_id: str, event_id: str) -> str:
    from apps.events.models import Event
    from apps.extensions import services as extensions
    from apps.extensions.models import ExtensionConfig

    from . import services
    from .models import Observation

    if not cache.add(f"evac_weather:fetch:{event_id}", 1, 60):
        return "already running"  # many screens ask at once: one fetch per minute and event
    config = ExtensionConfig.objects.filter(pk=config_id).first()
    event = Event.objects.filter(pk=event_id).first()
    if config is None or event is None:
        return "gone"
    s = config.settings
    if s.get("latitude") is None or s.get("longitude") is None:
        return "no location"
    url = API + "?" + urlencode({"latitude": s["latitude"], "longitude": s["longitude"],
                                 "current": "temperature_2m,weather_code,wind_speed_10m", "timezone": "UTC"})
    try:
        body = json.loads(safefetch.get(url).body)
        now = body["current"]
        services.record(event, temperature_c=float(now["temperature_2m"]),
                        condition=services.CODES.get(int(now["weather_code"]), "Unknown"),
                        wind_kmh=float(now["wind_speed_10m"]), source=Observation.Source.OPEN_METEO)
    except (safefetch.FetchError, ValueError, KeyError, TypeError) as exc:
        extensions.write_log(config, "error", f"Open-Meteo: {exc}")
        return "failed"
    return "ok"
