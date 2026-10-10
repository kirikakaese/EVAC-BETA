# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "maptiles"
urlpatterns = [path("<int:z>/<int:x>/<int:y>.png", views.tile, name="tile")]
