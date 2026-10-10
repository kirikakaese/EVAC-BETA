# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    DashboardPanelSpec,
    EvacTriggerSpec,
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
    StaffCardSpec,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="evacuation", name="Evacuation", version="0.1.0", kind="module")

SCOPES = ("venue", "zone")


def _label(default: str) -> dict[str, Any]:
    return {"type": "string", "title": f"Name of “{default}”", "default": "", "maxLength": 60,
            "description": "Empty: the built-in name."}


SAFETY_STATEMENT = _(
    "EVAC is a supplementary information system. It is not a certified fire alarm system, voice alarm system or "
    "evacuation system: DIN 14675, DIN VDE 0833, EN 54 and similar standards do not apply to it, and it does not "
    "comply with them.\n\n"
    "It complements, and never replaces, the fire alarm and voice alarm systems, the signage and the evacuation "
    "procedures the venue and the authorities require. Screens, networks and power can fail: plan the evacuation "
    "so that it works without EVAC, and keep the venue's own alarms as the alarm that counts.\n\n"
    "Test the evacuation content, the self-test and a drill before the event.")


def register(r: Registry) -> None:
    from . import sync as node_sync

    r.sync(node_sync.spec())
    from .node_actions import ACTIONS

    for kind, fn in ACTIONS.items():
        r.node_action(kind, fn)
    r.module(ModuleSpec(
        key="evacuation", name=str(_("Evacuation")), order=15, category="venue", default_enabled=False,
        depends_on=("venues",),
        description=str(_("Supplementary evacuation information: alarm states per event and zone, drills. "
                          "Not a certified fire alarm, voice alarm or evacuation system; it complements them.")),
        acknowledgement=str(SAFETY_STATEMENT)))
    r.permissions_([
        PermissionSpec("evacuation.view", str(_("See the evacuation state and its history")), scopes=SCOPES),
        PermissionSpec("evacuation.trigger", str(_("Raise, change and step down real alarms")), scopes=SCOPES,
                       sensitive=True),
        PermissionSpec("evacuation.clear", str(_("Give the all clear for real alarms")), scopes=SCOPES,
                       sensitive=True),
        PermissionSpec("evacuation.drill", str(_("Run drills (start, change and end them)")), scopes=SCOPES,
                       sensitive=True),
        PermissionSpec("evacuation.manage", str(_("Configure evacuation states"))),
    ])
    r.nav(NavEntry(module="evacuation", label=str(_("Evacuation")), url_name="evacuation:index",
                   permission="evacuation.view", section="event", order=5))
    props: dict[str, Any] = {
        "model": {"type": "string", "title": "Evacuation model", "default": "staged",
                  "enum": ["simple", "staged", "zones"],
                  "x-enum-labels": ["Simple takeover: one button, evacuate everywhere",
                                "Staged, global: all stages, the whole event at once",
                                "Zones and routes: stages per zone, arrows to the nearest open exit"],
                  "description": "Switching never ends an alarm that is active; it limits what can be raised."},
        "staff_alert_enabled": {"type": "boolean", "title": "Use “Staff alert” (silent pre-alarm)", "default": True},
        "attention_enabled": {"type": "boolean", "title": "Use “Attention”", "default": True},
        "shelter_in_place_enabled": {"type": "boolean", "title": "Use “Shelter in place”", "default": True},
        "all_clear_minutes": {"type": "integer", "title": "Show “All clear” for (minutes)", "default": 5,
                              "minimum": 0, "maximum": 240,
                              "description": "Then screens return to normal content. Nothing else ever returns "
                                             "to normal on its own."},
        "two_person_states": {"type": "array", "title": "Two-person rule for", "default": [],
                              "items": {"type": "string", "enum": ["staff_alert", "attention", "shelter_in_place",
                                                                   "evacuate", "all_clear"],
                                        "x-enum-labels": ["Staff alert", "Attention", "Shelter in place",
                                                          "Evacuate", "All clear"]},
                              "description": "A person's change into these states waits until a second "
                                             "authorised person confirms it."},
        "two_person_seconds": {"type": "integer", "title": "Second person must confirm within (seconds)",
                               "default": 60, "minimum": 10, "maximum": 600,
                               "description": "Otherwise the request expires, nothing changes and the control "
                                              "room is alerted."},
        "fallback_origins": {"type": "array", "title": "Fallback origins for screens", "default": [],
                             "items": {"type": "string", "format": "uri", "maxLength": 200}, "maxItems": 3,
                             "description": "Up to three base URLs (secondary node, hardware bridge) that serve the "
                                            "signed alarm state when the main server is unreachable, e.g. "
                                            "http://10.0.0.5:8088. One per line."},
        "viewing_distance_m": {"type": "number", "title": "Viewing distance for evacuation text (m)", "default": 8,
                               "minimum": 1, "maximum": 100,
                               "description": "Used by the layout checks: letters at least 1/250 of this high."},
        "screen_height_m": {"type": "number", "title": "Typical screen height (m)", "default": 0.6, "minimum": 0.1,
                            "maximum": 10},
        "drill_text": {"type": "string", "title": "Drill marker", "default": "DRILL", "maxLength": 40,
                       "description": "Shown on screens and prefixed to notifications during drills."},
    }
    for key, default in [("staff_alert", "Staff alert"), ("attention", "Attention"),
                         ("shelter_in_place", "Shelter in place"), ("evacuate", "Evacuate"),
                         ("all_clear", "All clear")]:
        props[f"{key}_label"] = _label(default)
    r.settings_namespace(SettingsNamespace(
        key="evacuation", title=str(_("Evacuation")), module="evacuation", order=15,
        permission="evacuation.manage", levels=("instance", "event"),
        schema={"type": "object", "properties": props}))
    r.settings_namespace(SettingsNamespace(
        key="evacuation_screen", title=str(_("Evacuation direction")), module="evacuation", order=16,
        permission="evacuation.manage", levels=("screen",),
        schema={"type": "object", "properties": {
            "hint_text": {"type": "string", "title": "Direction text", "default": "", "maxLength": 80,
                          "description": "e.g. “Exit B”. Overrides the computed route on this screen."},
            "hint_arrow": {"type": "string", "title": "Arrow", "default": "",
                           "enum": ["", "ahead", "ahead_right", "right", "back_right", "back", "back_left", "left",
                                    "ahead_left"],
                           "x-enum-labels": ["None", "Ahead", "Ahead right", "Right", "Back right", "Back",
                                         "Back left", "Left", "Ahead left"]},
        }}))
    r.webhook_event(WebhookEventSpec(key="evacuation.routes_changed", module="evacuation",
                                     description="An exit, assembly point or passage was blocked or opened again; "
                                                 "routes changed."))
    r.webhook_event(WebhookEventSpec(key="evacuation.state_changed", module="evacuation",
                                     description="The evacuation state of the event or a zone changed "
                                                 "(includes the drill flag)."))
    from . import api, staff

    r.staff_card(StaffCardSpec(key="evacuation", title=str(_("Evacuation")), module="evacuation",
                               template="evacuation/_staff_card.html", context=staff.card, order=5))
    for key, name, desc in [
        ("api", _("API / external systems"), _("Authenticated HTTPS trigger (service token, idempotency key).")),
        ("bridge", _("Hardware bridge"), _("Dry contacts, buttons and key switches via the bridge (3.6).")),
    ]:
        r.evac_trigger(EvacTriggerSpec(key=key, name=str(name), description=str(desc), module="evacuation"))
    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
    from . import content

    r.layout_check(content.layout_check)
    r.outbox_handler(content.SPEECH_JOB, content.render_speech)
    r.webhook_event(WebhookEventSpec(key="evacuation.staff_ack", module="evacuation",
                                     description="A staff member answered an alarm in the staff app (on it, zone "
                                                 "clear, need help)."))
    from . import panels

    r.dashboard_panel(DashboardPanelSpec(key="evacuation.state", title=str(_("Alarms")),
                                         template="evacuation/panel.html", context=panels.dashboard,
                                         module="evacuation", order=10, refresh_seconds=3))
