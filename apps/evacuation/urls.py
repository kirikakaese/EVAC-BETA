# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "evacuation"
PORTAL_MOUNT = True  # /e/<slug>/evacuation/
ROOT_MOUNTS = [("bridge/v1/", "apps.evacuation.bridge_urls", "evacuation_bridge"),
               ("player/api/evacuation/", "apps.evacuation.player_urls", "evacuation_player"),
               ("evac/", "apps.evacuation.fallback_urls", "evacuation_fallback")]
urlpatterns = [
    path("", views.index, name="index"),
    path("change/", views.change, name="change"),
    path("end-all-clear/", views.end_all_clear, name="end_all_clear"),
    path("history/", views.history, name="history"),
    path("propagation/", views.propagation, name="propagation"),
    path("answer/", views.answer, name="answer"),
    path("block/", views.block, name="block"),
    path("panic/", views.panic, name="panic"),
    path("policies/", views.policies, name="policies"),
    path("bridges/", views.bridges_page, name="bridges"),
    path("content/", views.content_page, name="content"),
    path("requests/<uuid:pk>/confirm/", views.decide, {"verdict": "confirm"}, name="confirm"),
    path("requests/<uuid:pk>/reject/", views.decide, {"verdict": "reject"}, name="reject"),
    path("screens/<uuid:pk>/direction/", views.hint, name="hint"),
]
