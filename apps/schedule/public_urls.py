# SPDX-License-Identifier: AGPL-3.0-or-later
"""The public program (no login): ``/public/<slug>/program/`` with iCal, JSON and frab XML."""
from django.urls import path

from . import views

app_name = "schedule_public"
urlpatterns = [
    path("<slug:slug>/program/", views.public, name="program"),
    path("<slug:slug>/program.ics", views.public_ics, name="ics"),
    path("<slug:slug>/program.json", views.public_json, name="json"),
    path("<slug:slug>/schedule.xml", views.public_frab, name="frab"),
]
