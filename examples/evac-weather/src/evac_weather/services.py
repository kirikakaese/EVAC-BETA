# SPDX-License-Identifier: AGPL-3.0-or-later
"""State changes and the data source of the weather plugin. Like the core, every change is audited."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone

from apps.core.audit import log
from apps.extensions import services as extensions

from .models import Observation

KEY = "weather"
# WMO weather interpretation codes (Open-Meteo "weather_code") -> plain words
CODES = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
         51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
         66: "Freezing rain", 67: "Heavy freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow",
         77: "Snow grains", 80: "Rain showers", 81: "Rain showers", 82: "Violent rain showers", 85: "Snow showers",
         86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail"}


def config(event):
    """The weather configuration that applies to ``event`` (None when the extension is off there)."""
    return extensions.effective(KEY, event)


def record(event, *, temperature_c: float, condition: str, wind_kmh: float | None = None,
           source: str = Observation.Source.MANUAL, observed_at: dt.datetime | None = None,
           actor=None, request=None) -> Observation:
    obs = Observation.objects.create(event=event, temperature_c=temperature_c, condition=condition[:80],
                                     wind_kmh=wind_kmh, source=source, observed_at=observed_at or timezone.now(),
                                     created_by=actor if getattr(actor, "is_authenticated", False) else None)
    log(action="weather.recorded", actor=actor, target=obs, event=event, request=request,
        changes={"temperature_c": temperature_c, "condition": obs.condition, "source": source})
    return obs


def current(event) -> dict[str, Any]:
    """Payload of the ``weather.current`` data source (what screens show).

    Reads the database only. When the online mode is on and the last reading is older than the refresh interval
    a background fetch is queued; the screen shows the last known reading meanwhile (offline first).
    """
    cfg = config(event)
    obs = Observation.objects.filter(event=event).first()
    if cfg is not None and cfg.settings.get("online"):
        minutes = int(cfg.settings.get("refresh_minutes") or 30)
        if obs is None or obs.observed_at < timezone.now() - dt.timedelta(minutes=minutes):
            from . import tasks

            tasks.fetch.delay(str(cfg.pk), str(event.pk))
    if obs is None:
        return {"configured": cfg is not None, "observation": None}
    return {"configured": cfg is not None, "location": (cfg.settings.get("place") if cfg else "") or "",
            "observation": {"temperature_c": obs.temperature_c, "condition": obs.condition,
                            "wind_kmh": obs.wind_kmh, "source": obs.source,
                            "observed_at": obs.observed_at.isoformat()}}
