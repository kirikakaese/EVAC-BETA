# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "screens_global"
urlpatterns = [path("pair/", views.pair_global, name="pair")]
