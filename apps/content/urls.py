# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import layout_views, views

app_name = "content"
PORTAL_MOUNT = True  # /e/<slug>/content/
ROOT_MOUNTS = [("content/", "apps.content.file_urls", "content_files"),
               ("player/api/content/", "apps.content.player_urls", "content_player")]
urlpatterns = [
    path("", views.index, name="index"),
    path("themes/", views.themes, name="themes"),
    path("themes/<uuid:pk>/", views.theme, name="theme"),
    path("fonts/", views.fonts, name="fonts"),
    path("fonts/<uuid:pk>/delete/", views.font_delete, name="font_delete"),
    path("fonts.css", views.fonts_css, name="fonts_css"),
    path("assets/", views.assets, name="assets"),
    path("assets/<uuid:pk>/", views.asset, name="asset"),
    path("layouts/", layout_views.layouts, name="layouts"),
    path("layouts/<uuid:pk>/", layout_views.layout, name="layout"),
    path("layouts/<uuid:pk>/edit/", layout_views.layout_edit, name="layout_edit"),
    path("layouts/<uuid:pk>/save/", layout_views.layout_save, name="layout_save"),
    path("layouts/<uuid:pk>/publish/", layout_views.layout_publish, name="layout_publish"),
]
