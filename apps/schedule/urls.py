# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "schedule"
PORTAL_MOUNT = True  # /e/<slug>/schedule/
ROOT_MOUNTS = [("public/", "apps.schedule.public_urls", "schedule_public"),
               ("player/api/schedule/", "apps.schedule.player_urls", "schedule_player")]
urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.session, name="new"),
    path("stages/", views.stages, name="stages"),
    path("stages/<uuid:pk>/delete/", views.stage_delete, name="stage_delete"),
    path("<uuid:pk>/", views.session, name="session"),
    path("<uuid:pk>/delete/", views.session_delete, name="delete"),
    path("<uuid:pk>/live/", views.live, name="live"),
]
