# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "schedule_player"
urlpatterns = [path("", views.player_data, name="data")]
