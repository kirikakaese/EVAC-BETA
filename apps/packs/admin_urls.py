# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "packs_admin"
urlpatterns = [
    path("", views.keys, name="keys"),
    path("<uuid:pk>/remove/", views.untrust, name="untrust"),
]
