# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "evacuation"
PORTAL_MOUNT = True  # /e/<slug>/evacuation/
urlpatterns = [
    path("", views.index, name="index"),
    path("change/", views.change, name="change"),
    path("end-all-clear/", views.end_all_clear, name="end_all_clear"),
    path("history/", views.history, name="history"),
]
