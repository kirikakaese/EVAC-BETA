# SPDX-License-Identifier: AGPL-3.0-or-later
"""The public help page (no login): ``/public/<slug>/help/`` with the FAQ, found items and the forms."""
from django.urls import path

from . import views

app_name = "helpdesk_public"
urlpatterns = [
    path("<slug:slug>/help/", views.public, name="help"),
    path("<slug:slug>/help/<str:what>/", views.public_form, name="form"),
    path("<slug:slug>/help/status/<str:token>/", views.public_status, name="status"),
]
