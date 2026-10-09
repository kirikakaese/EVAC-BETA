# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ModuleSpec, NavEntry, PackSectionSpec, PermissionSpec, PluginManifest, WebhookEventSpec
from apps.core.registry import Registry

manifest = PluginManifest(key="playlists", name="Playlists, schedules and overrides", version="0.1.0",
                          kind="module")

SCOPES = ("venue", "zone", "room", "screen_group")


def register(r: Registry) -> None:
    from . import api, packs

    r.module(ModuleSpec(key="playlists", name=str(_("Playlists")), order=32, category="screens",
                        depends_on=("content",),
                        description=str(_("Slides in turn: ordered, shuffled or weighted playlists with "
                                          "durations, conditions and nesting; the event's default playlist."))))
    r.module(ModuleSpec(key="schedules", name=str(_("Schedules")), order=33, category="screens",
                        depends_on=("playlists",),
                        description=str(_("Time rules such as 'stage screens 18:00-20:00 show the concert "
                                          "playlist', with a calendar and a preview of any screen at any time."))))
    r.module(ModuleSpec(key="overrides", name=str(_("Live overrides")), order=34, category="screens",
                        depends_on=("playlists",),
                        description=str(_("Push a layout, playlist or message to screens at once, with "
                                          "priority levels and an expiry."))))
    r.permissions_([
        PermissionSpec("playlists.view", str(_("See playlists, schedules, overrides and what screens show"))),
        PermissionSpec("playlists.edit", str(_("Edit playlists and schedules"))),
        PermissionSpec("playlists.override", str(_("Push and cancel live overrides")), scopes=SCOPES),
        PermissionSpec("playlists.emergency", str(_("Push emergency-level overrides (above everything except "
                                                    "evacuation)")), scopes=SCOPES, sensitive=True),
    ])
    r.nav(NavEntry(module="playlists", label=str(_("Playback")), url_name="playlists:index",
                   permission="playlists.view", section="content", order=30))
    for key, desc in [
        ("override.started", "A live override was pushed to screens."),
        ("override.cancelled", "A live override was cancelled."),
    ]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="overrides"))
    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
    r.pack_section(PackSectionSpec(key="playlists", title=str(_("Playlists")), module="playlists", order=70,
                                   choices=packs.choices, requires=packs.requires, dump=packs.dump, load=packs.load))
