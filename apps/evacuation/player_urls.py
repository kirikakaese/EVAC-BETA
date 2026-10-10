# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import player_api

app_name = "evacuation_player"
urlpatterns = [
    path("state/", player_api.state, name="state"),
    path("ack/", player_api.ack, name="ack"),
    path("selftest/", player_api.selftest, name="selftest"),
    path("speech/<str:name>", player_api.speech, name="speech"),
]
