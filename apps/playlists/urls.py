# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "playlists"
PORTAL_MOUNT = True  # /e/<slug>/playlists/
ROOT_MOUNTS = [("player/api/playlists/", "apps.playlists.player_urls", "playlists_player")]
urlpatterns = [
    path("", views.index, name="index"),
    path("lists/", views.playlists, name="playlists"),
    path("lists/<uuid:pk>/", views.playlist, name="playlist"),
    path("schedules/", views.schedules, name="schedules"),
    path("schedules/new/", views.schedule, name="schedule_new"),
    path("schedules/<uuid:pk>/", views.schedule, name="schedule"),
    path("calendar/", views.calendar, name="calendar"),
    path("overrides/", views.overrides, name="overrides"),
    path("overrides/<uuid:pk>/cancel/", views.override_cancel, name="override_cancel"),
    path("preview/", views.preview, name="preview"),
]
