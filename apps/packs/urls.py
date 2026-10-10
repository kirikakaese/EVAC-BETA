# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "packs"
PORTAL_MOUNT = True  # /e/<slug>/packs/
ROOT_MOUNTS = [("settings/packs/", "apps.packs.admin_urls", "packs_admin")]
urlpatterns = [
    path("", views.index, name="index"),
    path("export/", views.export, name="export"),
    path("upload/", views.upload, name="upload"),
    path("from-url/", views.from_url, name="from_url"),
    path("gallery/<slug:key>/", views.from_gallery, name="gallery"),
    path("imports/<uuid:pk>/", views.review, name="review"),
    path("imports/<uuid:pk>/discard/", views.discard, name="discard"),
]
