# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operations (brief §11.3, roadmap 6.1/6.2, ADR-0039): incidents, the ops log, tasks, escalation and the control
room dashboard."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
    StaffCardSpec,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="ops", name="Operations", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    from . import dashboard, services, staff
    from . import sync as node_sync

    r.module(ModuleSpec(key="ops", name=str(_("Incidents & control room")), order=45, category="operations",
                        description=str(_("Incident log with timeline and escalation, the radio-style ops log, "
                                          "tasks and the control room dashboard."))))
    r.permissions_([
        PermissionSpec("ops.view", str(_("See incidents, the ops log, tasks and the control room"))),
        PermissionSpec("ops.report", str(_("Report incidents and write ops log entries"))),
        PermissionSpec("ops.manage", str(_("Handle incidents: assign, change status, close; manage tasks"))),
        PermissionSpec("ops.escalation", str(_("Configure incident escalation"))),
        PermissionSpec("ops.export", str(_("Export the incident report"))),
    ])
    for label, url, perm, order in [
        (_("Control room"), "ops:control", "ops.view", 10),
        (_("Incidents"), "ops:index", "ops.view", 20),
        (_("Ops log"), "ops:log", "ops.view", 30),
        (_("Tasks"), "ops:tasks", "ops.view", 40),
    ]:
        r.nav(NavEntry(module="ops", label=str(label), url_name=url, permission=perm, section="operations",
                       order=order))
    r.settings_namespace(SettingsNamespace(
        key="ops", title=str(_("Incidents")), module="ops", order=45, permission="ops.escalation",
        levels=("instance", "event"),
        schema={"type": "object", "properties": {
            "categories": {"type": "array", "title": "Incident categories", "items": {"type": "string",
                                                                                      "maxLength": 40},
                           "maxItems": 30, "default": services.DEFAULT_CATEGORIES,
                           "description": "One per line, shown in this order."},
            "log_system_events": {"type": "boolean", "title": "System lines in the ops log", "default": True,
                                  "description": "Alarms, offline screens, DECT alerts, occupancy and program "
                                                 "changes are written to the ops log."},
        }},
    ))
    for key, desc in [
        ("incident.created", "An incident was reported."),
        ("incident.updated", "An incident was edited, assigned or changed status."),
        ("incident.escalated", "An escalation rule fired for an incident."),
    ]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="ops"))
    r.webhook_sink(services.sink)
    r.sync(node_sync.spec())
    from . import api

    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
    r.staff_card(StaffCardSpec(key="ops", title=str(_("Report")), template="ops/_staff_card.html",
                               context=staff.card, module="ops", order=30))
    for spec in dashboard.panels():
        r.dashboard_panel(spec)
