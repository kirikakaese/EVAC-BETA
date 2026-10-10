# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program (brief §11.1, roadmap 5.1, ADR-0038): stages, sessions, speakers, tracks, live changes, a public page with
iCal/JSON/frab exports, program elements on screens and sessions as announcement anchors."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
    TimeAnchorSpec,
    WebhookEventSpec,
    WidgetSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="program", name="Program", version="1.0.0", kind="module")


def register(r: Registry) -> None:
    from . import services
    from . import sync as node_sync

    r.module(ModuleSpec(key="program", name=str(_("Program")), order=38, category="communication",
                        description=str(_("Sessions on stages and rooms with speakers and tracks; live changes "
                                          "(delays, cancellations, room changes) reach screens and the public "
                                          "program at once. Import from pretalx, frab or iCal."))))
    r.permissions_([
        PermissionSpec("program.view", str(_("See the program"))),
        PermissionSpec("program.live", str(_("Make live changes: delay, cancel, move a session"))),
        PermissionSpec("program.edit", str(_("Edit sessions, stages, tracks and speakers"))),
    ])
    r.nav(NavEntry(module="program", label=str(_("Program")), url_name="schedule:index",
                   permission="program.view", section="content", order=35))
    r.settings_namespace(SettingsNamespace(
        key="program", title=str(_("Program")), module="program", order=38, permission="program.edit",
        levels=("instance", "event"),
        schema={"type": "object", "properties": {
            "public_page": {"type": "boolean", "title": "Public program page", "default": False,
                            "description": "Public sessions on a page without login, with iCal, JSON and frab "
                                           "XML exports."},
            "changes_hours": {"type": "integer", "title": "Show live changes for (hours)", "default": 6,
                              "minimum": 1, "maximum": 48,
                              "description": "How long a delay or cancellation stays in the changes list on "
                                             "screens."},
        }},
    ))
    r.widget(WidgetSpec(key="program", name=str(_("Program")), module="program", element="evac-program",
                        script="player/player.js",
                        description=str(_("Now and next on a stage, the day's sessions, or live changes"))))
    r.anchor_source(TimeAnchorSpec(key=services.ANCHOR_KEY, title=str(_("Program session")), module="program",
                                   choices=services.anchor_choices, resolve=services.anchor_resolve))
    r.webhook_event(WebhookEventSpec(key=services.WEBHOOK, module="program",
                                     description="A session changed (edited, delayed, cancelled, moved, imported)."))
    r.sync(node_sync.spec())
    from . import api

    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
    r.editor_choices("programStages", _stage_choices, module="program")
    r.editor_choices("programData", services.screen_payload, module="program")


def _stage_choices(event):  # type: ignore[no-untyped-def]
    from .models import Stage

    return [{"value": str(s.pk), "label": s.name} for s in Stage.objects.filter(event=event)]
