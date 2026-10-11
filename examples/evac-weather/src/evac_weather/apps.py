# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class WeatherConfig(AppConfig):
    name = "evac_weather"
    label = "evac_weather"
    verbose_name = "Weather (example plugin)"
    default_auto_field = "django.db.models.BigAutoField"
