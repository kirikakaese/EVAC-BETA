# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resources and inventory (brief §11.6, roadmap 7.2, ADR-0042)."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    DashboardPanelSpec,
    MapLayerSpec,
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
    StaffCardSpec,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="inventory", name="Inventory", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    from . import panels, services
    from . import sync as node_sync

    r.module(ModuleSpec(key="inventory", name=str(_("Inventory")), order=48, category="operations",
                        description=str(_("Radios, keys, vehicles, tools … with asset tags and QR labels; lend and "
                                          "return with signature or photo, who has what, due-back reminders, "
                                          "maintenance notes, places on the map."))))
    r.permissions_([
        PermissionSpec("inventory.view", str(_("See the inventory and who has what"))),
        PermissionSpec("inventory.lend", str(_("Lend and take back items"))),
        PermissionSpec("inventory.manage", str(_("Add and edit items, print labels, maintenance"))),
    ])
    r.nav(NavEntry(module="inventory", label=str(_("Inventory")), url_name="inventory:index",
                   permission="inventory.view", section="operations", order=70))
    r.settings_namespace(SettingsNamespace(
        key="inventory", title=str(_("Inventory")), module="inventory", order=48, permission="inventory.manage",
        levels=("instance", "event"),
        schema={"type": "object", "properties": {
            "tag_prefix": {"type": "string", "title": "Asset tag prefix", "default": "EV-", "maxLength": 10,
                           "description": "New items get the next number: EV-0001, EV-0002, …"},
            "signature_required": {"type": "boolean", "title": "Signature required when lending", "default": False},
        }},
    ))
    for key, desc in [("inventory.lent", "An item was lent."), ("inventory.returned", "An item came back."),
                      ("inventory.overdue", "A lent item is past its due time.")]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="inventory"))
    r.map_layer(MapLayerSpec(key="inventory", title=str(_("Inventory")), items=services.map_items,
                             place=services.map_place, rescale=services.map_rescale, module="inventory", order=40))
    r.dashboard_panel(DashboardPanelSpec(key="inventory.out", title=str(_("Lent out")),
                                         template="inventory/panel.html", context=panels.dashboard,
                                         module="inventory", order=65, refresh_seconds=30))
    r.staff_card(StaffCardSpec(key="inventory", title=str(_("Inventory")), template="inventory/_staff_card.html",
                               context=panels.staff_card, module="inventory", order=40))
    r.sync(node_sync.spec())
    from . import api

    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
