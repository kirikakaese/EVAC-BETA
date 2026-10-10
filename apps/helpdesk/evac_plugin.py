# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpdesk: lost & found, requests, FAQ (brief §11.7, roadmap 7.3, ADR-0043)."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    DashboardPanelSpec,
    DataSourceSpec,
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
    StaffCardSpec,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="helpdesk", name="Helpdesk", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    from . import panels
    from . import sync as node_sync

    r.module(ModuleSpec(key="helpdesk", name=str(_("Helpdesk")), order=49, category="operations",
                        description=str(_("Lost & found with matching suggestions, requests from visitors and crew, "
                                          "an FAQ for the public page and screens."))))
    r.permissions_([
        PermissionSpec("helpdesk.view", str(_("See requests and lost & found"))),
        PermissionSpec("helpdesk.manage", str(_("Handle requests, log and hand over lost & found"))),
        PermissionSpec("helpdesk.faq", str(_("Edit the FAQ"))),
    ])
    r.nav(NavEntry(module="helpdesk", label=str(_("Helpdesk")), url_name="helpdesk:index",
                   permission="helpdesk.view", section="operations", order=75,
                   active=("helpdesk:index", "helpdesk:ticket*", "helpdesk:faq*")))
    r.nav(NavEntry(module="helpdesk", label=str(_("Lost & found")), url_name="helpdesk:lost_found",
                   permission="helpdesk.view", section="operations", order=76,
                   active=("helpdesk:lost_found", "helpdesk:lf*")))
    r.settings_namespace(SettingsNamespace(
        key="helpdesk", title=str(_("Helpdesk")), module="helpdesk", order=49, permission="helpdesk.manage",
        levels=("instance", "event"),
        schema={"type": "object", "properties": {
            "public_page": {"type": "boolean", "title": "Public help page", "default": True,
                            "description": "/public/<event>/help/: FAQ, found items and the forms, no login."},
            "public_requests": {"type": "boolean", "title": "Visitors can send requests", "default": True},
            "public_lost": {"type": "boolean", "title": "Visitors can report lost items", "default": True},
            "public_found": {"type": "boolean", "title": "List found items publicly", "default": True,
                             "description": "What, category, colour and day only; never details or contacts."},
        }},
    ))
    for key, desc in [("helpdesk.request", "A request came in."), ("helpdesk.lost", "A lost item was reported."),
                      ("helpdesk.found", "A found item was logged."),
                      ("helpdesk.matched", "A lost report was matched with a found item."),
                      ("helpdesk.returned", "A found item went back to its owner.")]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="helpdesk"))
    r.data_source(DataSourceSpec(key="helpdesk.faq", name=str(_("Helpdesk: FAQ")), module="helpdesk",
                                 ttl_seconds=300, fetch=panels.faq_source,
                                 description=str(_("FAQ entries marked “on screens”."))))
    r.data_source(DataSourceSpec(key="helpdesk.found", name=str(_("Helpdesk: found items")), module="helpdesk",
                                 ttl_seconds=120, fetch=panels.found_source,
                                 description=str(_("Found items waiting for their owner (no details)."))))
    r.data_source(DataSourceSpec(key="helpdesk.queue", name=str(_("Helpdesk: open requests")), module="helpdesk",
                                 ttl_seconds=60, fetch=panels.queue_source,
                                 description=str(_("How many requests are open."))))
    r.dashboard_panel(DashboardPanelSpec(key="helpdesk.queue", title=str(_("Helpdesk")),
                                         template="helpdesk/panel.html", context=panels.dashboard,
                                         module="helpdesk", order=70, refresh_seconds=30))
    r.staff_card(StaffCardSpec(key="helpdesk", title=str(_("Helpdesk")), template="helpdesk/_staff_card.html",
                               context=panels.staff_card, module="helpdesk", order=45))
    r.sync(node_sync.spec())
    from . import api

    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
