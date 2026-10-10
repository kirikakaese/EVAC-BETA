# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crew and shifts (brief §11.2, roadmap 7.1, ADR-0041)."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    AudienceSpec,
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

manifest = PluginManifest(key="crew", name="Crew", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    from . import panels, staff
    from . import sync as node_sync

    r.module(ModuleSpec(key="crew", name=str(_("Crew & shifts")), order=47, category="operations",
                        description=str(_("Teams, crew members with skills, shifts with sign-up rules, check-in "
                                          "by QR in the staff app, no-shows and a “needed now” board for screens. "
                                          "Import from Engelsystem."))))
    r.permissions_([
        PermissionSpec("crew.view", str(_("See teams, shifts and the shift board")), scopes=("team",)),
        PermissionSpec("crew.self", str(_("Sign up for shifts and check in (own shifts)"))),
        PermissionSpec("crew.checkin", str(_("Check crew in and out, mark no-shows")), scopes=("team",)),
        PermissionSpec("crew.manage", str(_("Manage teams, members and shifts")), scopes=("team",)),
    ])
    r.scope_kind(ScopeKind(key="team", label=str(_("Team")), choices=panels.team_choices, module="crew"))
    r.audience(AudienceSpec(key="teams", title=str(_("Team")), choices=panels.team_choices,
                            members=panels.team_members, module="crew", order=20))
    for label, url, order, active in [
            (_("Shift board"), "crew:index", 60, ("crew:index", "crew:shift*", "crew:scan", "crew:install_widgets")),
            (_("Teams"), "crew:teams", 61, ("crew:teams", "crew:member*"))]:
        r.nav(NavEntry(module="crew", label=str(label), url_name=url, permission="crew.view", section="operations",
                       order=order, active=active))
    r.settings_namespace(SettingsNamespace(
        key="crew", title=str(_("Crew & shifts")), module="crew", order=47, permission="crew.manage",
        levels=("instance", "event"),
        schema={"type": "object", "properties": {
            "max_hours_per_day": {"type": "number", "title": "Most hours per day", "default": 10, "minimum": 1,
                                  "maximum": 24},
            "min_rest_minutes": {"type": "integer", "title": "Rest between shifts (minutes)", "default": 30,
                                 "minimum": 0, "maximum": 720},
            "late_signup_minutes": {"type": "integer", "title": "Sign-up after the start (minutes)", "default": 30,
                                    "minimum": 0, "maximum": 240},
            "cancel_until_minutes": {"type": "integer", "title": "Crew may cancel until (minutes before)",
                                     "default": 60, "minimum": 0, "maximum": 2880},
            "no_show_minutes": {"type": "integer", "title": "No-show after (minutes)", "default": 15,
                                "minimum": 5, "maximum": 240,
                                "description": "A sign-up not checked in this long after the start is a no-show; "
                                               "team leads are told and the shift needs people again."},
            "needed_now_hours": {"type": "number", "title": "“Needed now” looks ahead (hours)", "default": 3,
                                 "minimum": 0.5, "maximum": 24},
        }},
    ))
    for key, desc in [("crew.shift_changed", "A shift was created, edited or someone signed up or checked in."),
                      ("crew.no_show", "A crew member did not check in for a shift.")]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="crew"))
    r.data_source(DataSourceSpec(key="crew.needed_now", name=str(_("Crew: needed now")), module="crew",
                                 ttl_seconds=60, fetch=panels.needed_now_source,
                                 description=str(_("Shifts now and soon that still need people."))))
    r.data_source(DataSourceSpec(key="crew.board", name=str(_("Crew: shift board")), module="crew",
                                 ttl_seconds=60, fetch=panels.board_source,
                                 description=str(_("Shifts of the next 24 hours with how many are filled."))))
    r.dashboard_panel(DashboardPanelSpec(key="crew.needed", title=str(_("Crew needed now")),
                                         template="crew/panel.html", context=panels.dashboard, module="crew",
                                         order=35, refresh_seconds=15))
    r.staff_card(StaffCardSpec(key="crew", title=str(_("My shifts")), template="crew/_staff_card.html",
                               context=staff.card, module="crew", order=15))
    r.sync(node_sync.spec())
    from . import api

    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
