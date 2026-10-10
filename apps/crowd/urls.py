# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "crowd"
PORTAL_MOUNT = True  # /e/<slug>/crowd/
urlpatterns = [
    path("", views.index, name="index"),
    path("<uuid:pk>/", views.area, name="area"),
    path("<uuid:pk>/state.json", views.state, name="state"),
    path("count/", views.counts, name="counts"),
    path("count/<uuid:pk>/", views.counter, name="counter"),
]
