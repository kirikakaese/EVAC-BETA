# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "helpdesk"
PORTAL_MOUNT = True  # /e/<slug>/helpdesk/
ROOT_MOUNTS = [("public/", "apps.helpdesk.public_urls", "helpdesk_public")]
urlpatterns = [
    path("", views.index, name="index"),
    path("requests/new/", views.ticket_new, name="ticket_new"),
    path("requests/<uuid:pk>/", views.ticket, name="ticket"),
    path("lost-found/", views.lost_found, name="lost_found"),
    path("lost-found/new/", views.lf_edit, name="lf_new"),
    path("lost-found/<uuid:pk>/", views.lf, name="lf"),
    path("lost-found/<uuid:pk>/edit/", views.lf_edit, name="lf_edit"),
    path("lost-found/<uuid:pk>/action/", views.lf_action, name="lf_action"),
    path("faq/", views.faq, name="faq"),
    path("faq/<uuid:pk>/", views.faq, name="faq_edit"),
]
