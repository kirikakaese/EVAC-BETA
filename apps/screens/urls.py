# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "screens"
PORTAL_MOUNT = True  # /e/<slug>/screens/
#: mounted at the site root (prefix, urlconf, namespace): the player and the QR pairing entry point
ROOT_MOUNTS = [("player/", "apps.screens.player_urls", "player"),
               ("screens/", "apps.screens.global_urls", "screens_global")]
urlpatterns = [
    path("", views.index, name="index"),
    path("pair/", views.pair, name="pair"),
    path("groups/", views.groups, name="groups"),
    path("groups/<uuid:pk>/", views.group, name="group"),
    path("<uuid:pk>/", views.detail, name="detail"),
    path("<uuid:pk>/revoke/", views.revoke, name="revoke"),
    path("<uuid:pk>/delete/", views.delete, name="delete"),
    path("<uuid:pk>/command/<slug:name>/", views.command, name="command"),
]
