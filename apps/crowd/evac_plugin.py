# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crowd and occupancy (brief §11.4, roadmap 6.3, ADR-0040): areas with live counts from door counters and
sensors, capacity rules that put "full" on screens and alert staff, and the occupancy history."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    DashboardPanelSpec,
    DataSourceSpec,
    ModuleSpec,
    MqttTopicSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    StaffCardSpec,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="crowd", name="Occupancy", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    from . import panels, sensors, services, staff
    from . import sync as node_sync

    r.module(ModuleSpec(key="crowd", name=str(_("Occupancy")), order=46, category="operations",
                        description=str(_("Live headcount per room, zone or area from door counters (staff app, "
                                          "works offline) and sensors; capacity rules show “full” on screens and "
                                          "alert staff; occupancy history."))))
    r.permissions_([
        PermissionSpec("crowd.view", str(_("See occupancy and its history"))),
        PermissionSpec("crowd.count", str(_("Count people at a door (counter in the staff app)"))),
        PermissionSpec("crowd.manage", str(_("Set up areas and capacity rules; correct counts"))),
    ])
    r.nav(NavEntry(module="crowd", label=str(_("Occupancy")), url_name="crowd:index", permission="crowd.view",
                   section="operations", order=50))
    r.webhook_event(WebhookEventSpec(key="occupancy.state_changed", module="crowd",
                                     description="An area became busy or full, or has space again."))
    r.program_source(services.program_source)
    r.mqtt_topic(MqttTopicSpec(key="crowd", pattern="crowd/+/+", handler=sensors.mqtt_handler, module="crowd"))
    r.data_source(DataSourceSpec(key="crowd.areas", name=str(_("Occupancy")), module="crowd", ttl_seconds=30,
                                 fetch=panels.data_source,
                                 description=str(_("Areas with their count, capacity, percentage and state."))))
    r.dashboard_panel(DashboardPanelSpec(key="crowd.occupancy", title=str(_("Occupancy")),
                                         template="crowd/panel.html", context=panels.dashboard, module="crowd",
                                         order=30, refresh_seconds=5))
    r.staff_card(StaffCardSpec(key="crowd", title=str(_("Door counter")), template="crowd/_staff_card.html",
                               context=staff.card, module="crowd", order=25))
    r.sync(node_sync.spec())
    from . import api

    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
