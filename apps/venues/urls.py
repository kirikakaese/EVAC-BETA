# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "venues"
PORTAL_MOUNT = True  # /e/<slug>/venues/
urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:venue_slug>/", views.detail, name="detail"),
    path("<slug:venue_slug>/<str:part>/<uuid:pk>/delete/", views.part_delete, name="part_delete"),
]
