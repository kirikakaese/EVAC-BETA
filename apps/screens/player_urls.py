# SPDX-License-Identifier: AGPL-3.0-or-later
"""``/player/``: the screen player app and its device API (mounted by ``ROOT_MOUNTS`` in ``urls.py``)."""
from django.urls import path

from . import player_api

app_name = "player"
urlpatterns = [
    path("api/pair/", player_api.pair_start, name="pair_start"),
    path("api/pair/<uuid:pk>/", player_api.pair_status, name="pair_status"),
    path("api/config/", player_api.config, name="config"),
    path("api/heartbeat/", player_api.heartbeat, name="heartbeat"),
    path("api/stream/", player_api.stream, name="stream"),
    path("api/poll/", player_api.poll, name="poll"),
]
