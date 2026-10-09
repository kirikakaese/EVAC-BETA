# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "announcements"
PORTAL_MOUNT = True  # /e/<slug>/announcements/
ROOT_MOUNTS = [("public/", "apps.announcements.public_urls", "announcements_public")]
urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.compose, name="new"),
    path("levels/", views.levels, name="levels"),
    path("levels/<uuid:pk>/", views.level, name="level"),
    path("templates/", views.templates, name="templates"),
    path("templates/new/", views.template, name="template_new"),
    path("templates/<uuid:pk>/", views.template, name="template"),
    path("<uuid:pk>/", views.detail, name="detail"),
    path("<uuid:pk>/edit/", views.compose, name="edit"),
    path("<uuid:pk>/submit/", views.submit, name="submit"),
    path("<uuid:pk>/approve/", views.approve, name="approve"),
    path("<uuid:pk>/reject/", views.reject, name="reject"),
    path("<uuid:pk>/cancel/", views.cancel, name="cancel"),
    path("<uuid:pk>/delete/", views.delete, name="delete"),
]
