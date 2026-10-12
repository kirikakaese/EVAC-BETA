# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heartbeat (ADR-0052): a health monitor for everything that should be alive (screens, venue node, bridges, DIAL,
Celery, outbox, … – each module registers its own ``r.health_check``), an alive indicator for screens and an
optional operator check-in with escalation. It only watches and reports; it never changes evacuation or alarm
states."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    DashboardPanelSpec,
    DataSourceSpec,
    HealthCheckSpec,
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
    StaffCardSpec,
    WebhookEventSpec,
    WidgetSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="heartbeat", name="Heartbeat", version="1.0.0", kind="module")

STATES = ["draft", "setup", "live", "teardown"]
STATE_LABELS = ["Draft", "Setup", "Live", "Teardown"]


def _roles(title: str, default: list[str], description: str) -> dict[str, object]:
    return {"type": "array", "title": title, "default": default, "maxItems": 20,
            "items": {"type": "string", "maxLength": 50}, "description": description}


SCHEMA = {"type": "object", "properties": {
    "grace_seconds": {"type": "integer", "title": "Report “down” after (seconds)", "minimum": 15, "maximum": 3600,
                      "default": 60, "description": "Something must be down (or back up) this long before anyone is "
                                                    "told, so short blips do not alert."},
    "alert_states": {"type": "array", "title": "Alert while the event is", "default": ["setup", "live"],
                     "items": {"type": "string", "enum": STATES, "x-enum-labels": STATE_LABELS},
                     "description": "Teardown is left out by default: screens and bridges go off on purpose then."},
    "notify_roles": _roles("Notify roles", ["control-room"],
                           "Role short names (e.g. control-room, orga): their members get an in-app notification "
                           "(and Web Push) when something goes down or comes back."),
    "alert_channels": {"type": "array", "title": "Also alert through channels", "default": [], "maxItems": 10,
                       "items": {"type": "string", "maxLength": 40},
                       "description": "Staff alert channel keys (ntfy, matrix, telegram, email, dial_sms); the "
                                      "heartbeat page lists the ones this event has."},
    "checkin_enabled": {"type": "boolean", "title": "Operator check-in", "default": False,
                        "description": "Someone of the check-in roles confirms “I'm here” regularly; missed "
                                       "check-ins are escalated."},
    "checkin_live_only": {"type": "boolean", "title": "Check-in only while the event is live", "default": True,
                          "description": "Off: also during setup and teardown."},
    "checkin_interval_minutes": {"type": "integer", "title": "Check in every (minutes)", "minimum": 5, "maximum": 720,
                                 "default": 30},
    "checkin_grace_minutes": {"type": "integer", "title": "Escalate every (minutes)", "minimum": 1, "maximum": 120,
                              "default": 5, "description": "Time between the reminder and each escalation step."},
    "checkin_roles": _roles("Roles that check in", ["control-room"],
                            "Role short names; any member of these roles can check in for the event."),
    "checkin_escalation": _roles("Escalation chain", ["orga", "admin"],
                                 "Role short names in order: the first is told one interval of grace after a missed "
                                 "check-in, the next one after another, and so on."),
    "checkin_channels": {"type": "array", "title": "Escalate also through channels", "default": [], "maxItems": 10,
                         "items": {"type": "string", "maxLength": 40},
                         "description": "Staff alert channel keys for escalation steps (not for the reminder)."},
}}


def register(r: Registry) -> None:
    from . import checks, panels

    r.module(ModuleSpec(key="heartbeat", name=str(_("Heartbeat")), order=44, category="operations",
                        description=str(_("Watches screens, the venue node, bridges, DIAL, the background worker and "
                                          "the outbox and alerts the control room when something goes down; an "
                                          "alive indicator for screens; optional operator check-in."))))
    r.permissions_([
        PermissionSpec("heartbeat.view", str(_("See the health of screens, nodes, bridges and services"))),
        PermissionSpec("heartbeat.manage", str(_("Configure the heartbeat and operator check-in; check in"))),
    ])
    r.nav(NavEntry(module="heartbeat", label=str(_("Heartbeat")), url_name="heartbeat:index",
                   permission="heartbeat.view", section="operations", order=15))
    r.nav(NavEntry(module="heartbeat", label=str(_("Heartbeat")), url_name="heartbeat_admin:index",
                   permission="admin", section="admin", order=36, global_=True, active=("heartbeat_admin:*",)))
    r.settings_namespace(SettingsNamespace(key="heartbeat", title=str(_("Heartbeat")), module="heartbeat",
                                           levels=("instance", "event"), permission="heartbeat.manage", order=44,
                                           schema=SCHEMA))
    for key, desc in [
        ("heartbeat.down", "Something the heartbeat watches is down (after the grace period)."),
        ("heartbeat.recovered", "Something that was reported down is back."),
        ("heartbeat.checked_in", "An operator checked in (“I'm here”)."),
        ("heartbeat.checkin_missed", "A check-in was missed and escalated to the next role."),
    ]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="heartbeat"))
    r.health_check(HealthCheckSpec(key="celery", name=str(_("Background worker")), check=checks.celery,
                                   module="heartbeat", scope="both", order=90, while_checked_out=True,
                                   description=str(_("Celery worker and beat run the periodic tasks."))))
    r.data_source(DataSourceSpec(key="heartbeat.alive", name=str(_("Alive indicator")), module="heartbeat",
                                 ttl_seconds=checks.ALIVE_TTL, fetch=checks.alive,
                                 description=str(_("The server's time: screens notice when it stops changing."))))
    r.widget(WidgetSpec(
        key="heartbeat.alive", name=str(_("Alive indicator")), element="evac-heartbeat-alive",
        script="heartbeat/alive.js", data_sources=("heartbeat.alive",), module="heartbeat",
        description=str(_("A small pulsing dot with the time; grey with “offline since” when the screen lost the "
                          "server.")),
        settings_schema={"type": "object", "properties": {
            "label": {"type": "string", "title": "Text next to the dot", "maxLength": 30, "default": ""},
            "seconds": {"type": "boolean", "title": "Show seconds", "default": False},
            "pulse": {"type": "boolean", "title": "Pulse", "default": True},
        }}))
    r.dashboard_panel(DashboardPanelSpec(key="heartbeat.health", title=str(_("Heartbeat")),
                                         template="heartbeat/panel.html", context=panels.dashboard,
                                         module="heartbeat", order=12, refresh_seconds=15))
    r.staff_card(StaffCardSpec(key="heartbeat", title=str(_("Check-in")), template="heartbeat/_staff_card.html",
                               context=panels.staff_card, module="heartbeat", order=5))
