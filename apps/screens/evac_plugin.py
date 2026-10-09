# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    ModuleSpec,
    NavEntry,
    PermissionSpec,
    PluginManifest,
    ScopeKind,
    SettingsNamespace,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="screens", name="Screens", version="0.1.0", kind="module")

SCOPES = ("venue", "zone", "room", "screen_group")


def _group_choices(event):
    return [(str(g.pk), g.name) for g in event.screen_groups.all()]


def register(r: Registry) -> None:
    from . import api, consumers

    r.module(ModuleSpec(key="screens", name=str(_("Screens")), order=30, category="screens",
                        description=str(_("Digital signage: pair screens, group them and watch their health. "
                                          "Content, playlists and overrides build on this module."))))
    r.permissions_([
        PermissionSpec("screens.view", str(_("See screens and their status")), scopes=SCOPES),
        PermissionSpec("screens.manage", str(_("Edit, move, revoke and delete screens and screen groups")),
                       scopes=SCOPES),
        PermissionSpec("screens.pair", str(_("Pair new screens"))),
    ])
    r.scope_kind(ScopeKind(key="screen_group", label=str(_("Screen group")), choices=_group_choices,
                           module="screens"))
    r.nav(NavEntry(module="screens", label=str(_("Screens")), url_name="screens:index", permission="screens.view",
                   section="content", order=10))
    r.settings_namespace(SettingsNamespace(
        key="screens", title=str(_("Screens")), module="screens", levels=("instance", "event"), order=30,
        schema={
            "type": "object",
            "properties": {
                "offline_after_seconds": {
                    "type": "integer", "title": "Offline after (seconds)", "minimum": 15, "maximum": 3600,
                    "default": 60, "description": "A screen without heartbeat for this long counts as offline."},
                "alert_offline": {
                    "type": "boolean", "title": "Notify when a screen goes offline", "default": True,
                    "description": "Sends a notification to everyone who manages the screen."},
            },
        },
    ))
    for key, desc in [
        ("screen.paired", "A screen was paired (or re-paired) with a device."),
        ("screen.revoked", "The device token of a screen was revoked."),
        ("screen.offline", "A screen stopped sending heartbeats."),
        ("screen.online", "An offline screen is back."),
    ]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="screens"))
    r.api_route(r"events/(?P<event_slug>[^/.]+)/screens", api.ScreenViewSet, "event-screen")
    r.api_route(r"events/(?P<event_slug>[^/.]+)/screen-groups", api.ScreenGroupViewSet, "event-screen-group")
    r.websocket_route(path("ws/screen/", consumers.ScreenConsumer.as_asgi()))
