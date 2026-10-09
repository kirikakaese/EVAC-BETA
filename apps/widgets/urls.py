# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "widgets"
PORTAL_MOUNT = True  # /e/<slug>/widgets/
ROOT_MOUNTS = [("player/api/widgets/", "apps.widgets.player_urls", "widgets_player")]
urlpatterns = [
    path("", views.index, name="index"),
    path("feeds/new/", views.feed, name="feed_new"),
    path("feeds/<uuid:pk>/", views.feed, name="feed"),
    path("feeds/<uuid:pk>/fetch/", views.feed_fetch, name="feed_fetch"),
    path("feeds/<uuid:pk>/delete/", views.feed_delete, name="feed_delete"),
    path("new/", views.widget, name="widget_new"),
    path("<uuid:pk>/", views.widget, name="widget"),
    path("<uuid:pk>/delete/", views.widget_delete, name="widget_delete"),
]
