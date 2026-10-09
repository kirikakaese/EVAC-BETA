# SPDX-License-Identifier: AGPL-3.0-or-later
from django.utils.translation import gettext_lazy as _

from apps.core.plugins import (
    ModuleSpec,
    NavEntry,
    NotificationChannelSpec,
    PermissionSpec,
    PluginManifest,
    SettingsNamespace,
    WebhookEventSpec,
)
from apps.core.registry import Registry

manifest = PluginManifest(key="announcements", name="Announcements", version="0.1.0", kind="module")

SCOPES = ("venue", "zone", "room", "screen_group")


def register(r: Registry) -> None:
    from . import api, services

    r.module(ModuleSpec(key="announcements", name=str(_("Announcements")), order=40, category="communication",
                        description=str(_("Write once, deliver everywhere: screens (banner, ticker, card or full "
                                          "screen), the public feed, staff notifications and webhooks, with "
                                          "levels, templates, approval, scheduling and a delivery report."))))
    r.permissions_([
        PermissionSpec("announcements.view", str(_("See announcements and their delivery report"))),
        PermissionSpec("announcements.draft", str(_("Write announcements (sent after approval)")), scopes=SCOPES),
        PermissionSpec("announcements.publish", str(_("Send announcements without approval and cancel them")),
                       scopes=SCOPES),
        PermissionSpec("announcements.approve", str(_("Approve or reject announcements of others")),
                       scopes=SCOPES),
        PermissionSpec("announcements.emergency", str(_("Send emergency announcements (full screen, no "
                                                        "approval)")), scopes=SCOPES, sensitive=True),
        PermissionSpec("announcements.manage", str(_("Edit levels and templates"))),
    ])
    r.nav(NavEntry(module="announcements", label=str(_("Announcements")), url_name="announcements:index",
                   permission="announcements.view", section="content", order=40))
    r.settings_namespace(SettingsNamespace(
        key="announcements", title=str(_("Announcements")), module="announcements", order=40,
        permission="announcements.manage", levels=("instance", "event"),
        schema={
            "type": "object",
            "properties": {
                "approval_required": {
                    "type": "boolean", "title": "Every announcement needs approval", "default": False,
                    "description": "Otherwise only those of senders without the publish permission (emergency "
                                   "announcements never wait)."},
                "public_feed": {
                    "type": "boolean", "title": "Public feed", "default": False,
                    "description": "Published announcements appear on a public page with RSS and JSON."},
                "feed_title": {
                    "type": "string", "title": "Feed title", "default": "", "maxLength": 120,
                    "description": "Empty: the event name."},
            },
        },
    ))
    for key, name, module, send, desc in [
        (services.SCREENS, _("Screens"), "screens", services.send_screens,
         _("Banner, ticker, card or full screen, depending on the level.")),
        (services.FEED, _("Public feed"), "announcements", services.send_feed,
         _("The event's public announcement page, RSS and JSON feed.")),
        (services.STAFF, _("Staff notifications"), "announcements", services.send_staff,
         _("In-app notifications to everyone who may see announcements.")),
        (services.WEBHOOK, _("Webhooks"), "announcements", services.send_webhook,
         _("The announcement.published webhook event.")),
    ]:
        r.notification_channel(NotificationChannelSpec(key=key, name=str(name), send=send, module=module,
                                                       description=str(desc)))
    r.outbox_handler("announcements.deliver", services.deliver)
    r.program_source(services.program_source)
    for key, desc in [
        ("announcement.published", "An announcement was published (once per occurrence)."),
        ("announcement.cancelled", "An announcement was cancelled."),
        ("announcement.pending", "An announcement waits for approval."),
    ]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc, module="announcements"))
    for prefix, viewset, basename in api.ROUTES:
        r.api_route(prefix, viewset, basename)
