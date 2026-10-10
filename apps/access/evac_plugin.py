# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ticketing and access: attendees, ticket types, badges, the check-in app and access zones (brief §11.5,
roadmap 8.1, ADR-0044)."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    DashboardPanelSpec,
    DataSourceSpec,
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    ScopeKind,
    SettingsNamespace,
    StaffCardSpec,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="access", name="Access", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    from . import panels
    from . import sync as node_sync

    r.module(ModuleSpec(key="access", name=str(_("Access")), order=46, category="operations",
                        description=str(_("Attendee lists, ticket types, badges and wristbands from the layout "
                                          "editor, a check-in app that works offline, access zones with scanner "
                                          "rules that feed occupancy."))))
    r.permissions_([
        PermissionSpec("access.view", str(_("See attendees, zones and scans"))),
        PermissionSpec("access.scan", str(_("Scan tickets (check-in app)")), scopes=("access_zone",)),
        PermissionSpec("access.manage", str(_("Manage attendees, ticket types, zones and badges"))),
    ])
    r.scope_kind(ScopeKind(key="access_zone", label=str(_("Access zone")), choices=panels.zone_choices,
                           module="access"))
    r.nav(NavEntry(module="access", label=str(_("Attendees")), url_name="access:index", permission="access.view",
                   section="operations", order=55,
                   active=("access:index", "access:attendee*", "access:types", "access:type*", "access:zone*",
                           "access:badges", "access:import")))
    r.nav(NavEntry(module="access", label=str(_("Check-in")), url_name="access:stations",
                   permission="access.scan", section="operations", order=56,
                   active=("access:stations", "access:scanner")))
    r.settings_namespace(SettingsNamespace(
        key="access", title=str(_("Access")), module="access", order=46, permission="access.manage",
        levels=("instance", "event"),
        schema={"type": "object", "properties": {
            "list_refresh_seconds": {"type": "integer", "title": "Scanners refresh their ticket list every (seconds)",
                                     "default": 60, "minimum": 10, "maximum": 3600},
        }},
    ))
    for key, desc in [("access.checked_in", "An attendee was checked in (first scan into a check-in zone)."),
                      ("access.refused", "A scan was refused (unknown, invalid, not allowed or already inside).")]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="access"))
    r.data_source(DataSourceSpec(key="access.zones", name=str(_("Access: people per zone")), module="access",
                                 ttl_seconds=30, fetch=panels.zones_source,
                                 description=str(_("How many ticket holders are inside each access zone, and how "
                                                   "many are checked in."))))
    r.dashboard_panel(DashboardPanelSpec(key="access.checkin", title=str(_("Check-in")),
                                         template="access/panel.html", context=panels.dashboard, module="access",
                                         order=45, refresh_seconds=15))
    r.staff_card(StaffCardSpec(key="access", title=str(_("Check-in")), template="access/_staff_card.html",
                               context=panels.staff_card, module="access", order=20))
    r.sync(node_sync.spec())
    from . import api

    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
