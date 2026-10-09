# SPDX-License-Identifier: AGPL-3.0-or-later
"""The public announcement feed (no login): ``/public/<slug>/announcements/`` plus RSS and JSON Feed."""
from django.urls import path

from . import views

app_name = "announcements_public"
urlpatterns = [
    path("<slug:slug>/announcements/", views.feed, name="feed"),
    path("<slug:slug>/announcements/feed.json", views.feed_json, name="feed_json"),
    path("<slug:slug>/announcements/rss.xml", views.feed_rss, name="feed_rss"),
]
