# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "venues"
PORTAL_MOUNT = True  # /e/<slug>/venues/
urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:venue_slug>/", views.detail, name="detail"),
    path("<slug:venue_slug>/map/", views.map_editor, name="map"),
    path("<slug:venue_slug>/map/data/", views.map_data, name="map_data"),
    path("<slug:venue_slug>/map/op/", views.map_op, name="map_op"),
    path("<slug:venue_slug>/floors/<uuid:floor_id>/plan/", views.plan_file, name="plan"),
    path("<slug:venue_slug>/floors/<uuid:floor_id>/plan/upload/", views.plan_upload, name="plan_upload"),
    path("<slug:venue_slug>/<str:part>/<uuid:pk>/delete/", views.part_delete, name="part_delete"),
]
