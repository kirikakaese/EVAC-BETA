# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views
from .realtime import views as rt

app_name = "core"
urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("metrics", views.metrics, name="metrics"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
    path("sse/e/<slug:slug>/", rt.sse, name="sse"),
    path("poll/e/<slug:slug>/", rt.poll, name="poll"),
]
