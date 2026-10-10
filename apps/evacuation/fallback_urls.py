# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import player_api

app_name = "evacuation_fallback"
urlpatterns = [path("<slug:slug>/state", player_api.fallback_state, name="state")]
