# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "nodes_admin"
urlpatterns = [
    path("", views.nodes_page, name="index"),
]
