# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from apps.accounts import views as account_views

from . import admin_views, docs, views

app_name = "portal"
urlpatterns = [
    path("", views.home, name="home"),
    path("setup/", views.setup, name="setup"),
    path("about/", views.about, name="about"),
    path("search/", views.search, name="search"),
    path("invite/<str:token>/", account_views.invitation, name="invitation"),
    path("docs/", docs.index, name="docs_index"),
    path("docs/<slug:slug>/", docs.page, name="docs_page"),
    # instance administration
    path("events/new/", views.event_create, name="event_create"),
    path("events/import/", views.event_import, name="event_import"),
    path("settings/modules/", admin_views.instance_modules, name="instance_modules"),
    path("settings/general/", admin_views.instance_settings, name="instance_settings"),
    path("settings/general/<slug:ns>/", admin_views.instance_settings_ns, name="instance_settings_ns"),
    path("settings/audit/", admin_views.instance_audit, name="instance_audit"),
    path("settings/users/", admin_views.users, name="users"),
    path("settings/users/<uuid:pk>/", admin_views.user_action, name="user_action"),
    # event
    path("e/<slug:slug>/", views.event_dashboard, name="event_dashboard"),
    path("e/<slug:slug>/switch/", views.switch_event, name="switch_event"),
    path("e/<slug:slug>/settings/", views.event_settings, name="event_settings"),
    path("e/<slug:slug>/settings/lifecycle/", views.event_lifecycle, name="event_lifecycle"),
    path("e/<slug:slug>/settings/clone/", views.event_clone, name="event_clone"),
    path("e/<slug:slug>/settings/export/", views.event_export, name="event_export"),
    path("e/<slug:slug>/settings/modules/", admin_views.event_modules, name="event_modules"),
    path("e/<slug:slug>/settings/s/<slug:ns>/", admin_views.event_settings_ns, name="settings_ns"),
    path("e/<slug:slug>/settings/tokens/", admin_views.event_tokens, name="event_tokens"),
    path("e/<slug:slug>/members/", admin_views.members, name="members"),
    path("e/<slug:slug>/members/action/", admin_views.member_action, name="member_action"),
    path("e/<slug:slug>/roles/", admin_views.roles, name="roles"),
    path("e/<slug:slug>/roles/new/", admin_views.role_edit, name="role_create"),
    path("e/<slug:slug>/roles/<slug:key>/", admin_views.role_edit, name="role_edit"),
    path("e/<slug:slug>/audit/", admin_views.audit, name="audit"),
]
