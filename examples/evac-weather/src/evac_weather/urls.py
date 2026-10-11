# SPDX-License-Identifier: AGPL-3.0-or-later
# Mounted by EVAC at /e/<event>/settings/extensions/weather/x/ (ExtensionSpec.urls); views get ``key`` and ``slug``.
from django.urls import path

from . import views

urlpatterns = [path("", views.index, name="index"), path("fetch/", views.fetch_now, name="fetch")]
