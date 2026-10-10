# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "crew"
PORTAL_MOUNT = True  # /e/<slug>/crew/
urlpatterns = [
    path("", views.index, name="index"),
    path("widgets/", views.install_widgets, name="install_widgets"),
    path("shifts/new/", views.shift_edit, name="shift_new"),
    path("shifts/<uuid:pk>/", views.shift, name="shift"),
    path("shifts/<uuid:pk>/edit/", views.shift_edit, name="shift_edit"),
    path("shifts/<uuid:pk>/delete/", views.shift_delete, name="shift_delete"),
    path("shifts/<uuid:pk>/signup/", views.sign_up, name="signup"),
    path("people/<uuid:pk>/", views.assignment, name="assignment"),
    path("mine/<uuid:pk>/", views.mine, name="mine"),
    path("scan/<str:token>/", views.scan, name="scan"),
    path("teams/", views.teams, name="teams"),
    path("members/new/", views.member, name="member_new"),
    path("members/<uuid:pk>/", views.member, name="member"),
]
