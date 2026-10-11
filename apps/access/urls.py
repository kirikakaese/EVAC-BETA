# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "access"
PORTAL_MOUNT = True  # /e/<slug>/access/
urlpatterns = [
    path("", views.index, name="index"),
    path("export.csv", views.export, name="export"),
    path("import/", views.import_view, name="import"),
    path("attendees/new/", views.attendee, name="attendee_new"),
    path("attendees/<uuid:pk>/", views.attendee, name="attendee"),
    path("types/", views.types, name="types"),
    path("types/<uuid:pk>/", views.type_edit, name="type"),
    path("zones/<uuid:pk>/", views.zone_edit, name="zone"),
    path("badges/", views.badges_view, name="badges"),
    path("scan/", views.stations, name="stations"),
    path("scan/sync/", views.scan_sync, name="scan_sync"),
    path("scan/<uuid:pk>/", views.scanner, name="scanner"),
    path("scan/<uuid:pk>/list/", views.scan_list, name="scan_list"),
]
