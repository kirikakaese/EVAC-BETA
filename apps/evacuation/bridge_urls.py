# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import bridge_api

app_name = "evacuation_bridge"
urlpatterns = [
    path("heartbeat", bridge_api.heartbeat, name="heartbeat"),
    path("input", bridge_api.input_changed, name="input"),
]
