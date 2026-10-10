# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import dashboard, staff, views

app_name = "ops"
PORTAL_MOUNT = True  # /e/<slug>/ops/
urlpatterns = [
    path("", views.index, name="index"),
    path("control/", dashboard.control, name="control"),
    path("control/panel/<str:key>/", dashboard.panel, name="panel"),
    path("new/", views.new, name="new"),
    path("<uuid:pk>/", views.incident, name="incident"),
    path("<uuid:pk>/edit/", views.edit, name="edit"),
    path("<uuid:pk>/status/", views.status, name="status"),
    path("<uuid:pk>/note/", views.note, name="note"),
    path("files/<uuid:pk>/", views.attachment, name="attachment"),
    path("log/", views.log_page, name="log"),
    path("tasks/", views.tasks, name="tasks"),
    path("tasks/<uuid:pk>/done/", views.task_done, name="task_done"),
    path("escalation/", views.rules, name="rules"),
    path("escalation/<uuid:pk>/", views.rules, name="rule"),
    path("escalation/<uuid:pk>/delete/", views.rule_delete, name="rule_delete"),
    path("report/", views.export, name="export"),
    path("staff/report/", staff.report, name="staff_report"),
    path("staff/log/", staff.log_entry, name="staff_log"),
    path("staff/<uuid:pk>/ack/", staff.acknowledge, name="staff_ack"),
]
