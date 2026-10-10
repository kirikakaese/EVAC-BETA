# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "dial"
PORTAL_MOUNT = True

urlpatterns = [
    path("", views.status, name="status"),
    path("test-broadcast/", views.test_broadcast, name="test_broadcast"),
    path("widgets/", views.install_widgets, name="install_widgets"),
    path("roles/", views.role_mapping, name="roles"),
]
