# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "heartbeat"
PORTAL_MOUNT = True  # /e/<slug>/heartbeat/
ROOT_MOUNTS = [("settings/heartbeat/", "apps.heartbeat.admin_urls", "heartbeat_admin")]
urlpatterns = [
    path("", views.index, name="index"),
    path("check-in/", views.check_in, name="checkin"),
]
