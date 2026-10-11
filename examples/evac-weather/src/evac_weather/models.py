# SPDX-License-Identifier: AGPL-3.0-or-later
import uuid

from django.conf import settings
from django.db import models


class Observation(models.Model):
    """Weather at the venue: typed in by staff (works offline) or fetched from Open-Meteo."""

    class Source(models.TextChoices):
        MANUAL = "manual", "Entered by staff"
        OPEN_METEO = "open-meteo", "Open-Meteo"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="weather_observations")
    observed_at = models.DateTimeField()
    temperature_c = models.FloatField()
    condition = models.CharField(max_length=80)
    wind_kmh = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-observed_at"]
        indexes = [models.Index(fields=["event", "-observed_at"], name="evac_weather_obs_recent")]

    def __str__(self) -> str:
        return f"{self.temperature_c:.0f} °C, {self.condition}"
