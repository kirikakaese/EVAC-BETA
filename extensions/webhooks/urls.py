# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

urlpatterns = [
    path("endpoints/", views.endpoints, name="endpoints"),
    path("endpoints/<uuid:pk>/delete/", views.endpoint_delete, name="endpoint_delete"),
]
