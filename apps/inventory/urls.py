# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "inventory"
PORTAL_MOUNT = True  # /e/<slug>/inventory/
urlpatterns = [
    path("", views.index, name="index"),
    path("new/", views.item_edit, name="item_new"),
    path("labels/", views.labels, name="labels"),
    path("t/<str:tag>/", views.tag, name="tag"),
    path("<uuid:pk>/", views.item, name="item"),
    path("<uuid:pk>/edit/", views.item_edit, name="item_edit"),
    path("<uuid:pk>/lend/", views.lend, name="lend"),
    path("<uuid:pk>/return/", views.give_back, name="return"),
    path("<uuid:pk>/note/", views.note, name="note"),
]
