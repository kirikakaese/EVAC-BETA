# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announcement channels as extensions: e-mail, ntfy, Matrix, Telegram and Mastodon (ADR-0020).

Each is configured under Settings -> Extensions (instance-wide or per event, secrets encrypted) and appears as
a channel in the announcement composer where it is switched on (docs/extensions/notify.md)."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ExtensionSpec, NotificationChannelSpec, PluginManifest, SetupCheckSpec, StaffCardSpec
from apps.core.registry import Registry

manifest = PluginManifest(key="notify", name="Announcement channels", version="1.0.0", kind="extension",
                          description="E-mail, ntfy, Matrix, Telegram and Mastodon for announcements.")

URL = {"type": "string", "format": "uri"}


def specs() -> list[tuple[ExtensionSpec, int]]:
    """(extension, max length of a per-channel text; 0 = none offered)."""
    from . import channels

    def spec(key, name, description, schema, required=(), secrets=(), icon=""):
        return ExtensionSpec(
            key=key, name=name, description=str(description), version="1.0.0", scope="both",
            settings_schema={"type": "object", "properties": schema, "required": list(required)},
            secret_fields=secrets, test_connection=channels.tester(key), docs="extensions/notify", icon=icon)

    return [
        (spec("email", "E-mail", _("Send announcements by e-mail to a list of addresses and/or the event staff, "
                                   "through the server's mail settings."), {
            "recipients": {"type": "array", "items": {"type": "string", "format": "email"}, "title": "Recipients",
                           "description": "One address per line (sent as BCC)."},
            "to_staff": {"type": "boolean", "title": "Also to the event staff", "default": False,
                         "description": "Everyone who may see announcements and has an e-mail address."},
            "subject_prefix": {"type": "string", "title": "Subject prefix", "maxLength": 60,
                               "description": "Empty: the event name in brackets."},
            "from_email": {"type": "string", "format": "email", "title": "Sender",
                           "description": "Empty: the server default."},
        }, icon="✉"), 0),
        (spec("ntfy", "ntfy", _("Push announcements to phones through an ntfy topic (ntfy.sh or your own "
                                "server); emergency announcements use the highest priority."), {
            "server": {**URL, "title": "Server", "default": "https://ntfy.sh"},
            "topic": {"type": "string", "title": "Topic", "pattern": "^[-_A-Za-z0-9]{1,64}$"},
        }, required=("topic",), secrets=(("token", str(_("Access token (optional)"))),), icon="🔔"), 1000),
        (spec("matrix", "Matrix", _("Post announcements into a Matrix room with a bot account."), {
            "homeserver": {**URL, "title": "Homeserver", "description": "e.g. https://matrix.org"},
            "room_id": {"type": "string", "title": "Room ID", "pattern": "^!.+:.+$",
                        "description": "!abc123:example.org - the bot must have joined the room."},
        }, required=("homeserver", "room_id"), secrets=(("access_token", str(_("Access token"))),), icon="[m]"),
         4000),
        (spec("telegram", "Telegram", _("Post announcements into a Telegram group or channel with a bot."), {
            "chat_id": {"type": "string", "title": "Chat ID", "description": "e.g. -1001234567890 or @channelname"},
            "api_base": {**URL, "title": "Bot API server", "default": "https://api.telegram.org"},
        }, required=("chat_id",), secrets=(("bot_token", str(_("Bot token"))),), icon="✈"), 4000),
        (spec("mastodon", "Mastodon", _("Post announcements as toots on a Mastodon (or compatible) account."), {
            "instance": {**URL, "title": "Instance", "description": "e.g. https://social.example.org"},
            "visibility": {"type": "string", "title": "Visibility", "enum": ["public", "unlisted", "private"],
                           "default": "public"},
            "hashtag": {"type": "string", "title": "Hashtag", "maxLength": 40, "description": "Without #."},
        }, required=("instance",), secrets=(("access_token", str(_("Access token"))),), icon="🐘"), 500),
    ]


def ntfy_card(request, event):
    """Staff page: subscribe to the event's ntfy topic as a backup to Web Push (brief §12)."""
    from apps.extensions import services as extensions

    cfg = extensions.effective("ntfy", event)
    topic = cfg.settings.get("topic", "") if cfg is not None else ""
    if not topic:
        return None
    server = (cfg.settings.get("server") or "https://ntfy.sh").rstrip("/")
    return {"server": server, "topic": topic, "url": f"{server}/{topic}", "protected": bool(cfg.secret("token"))}


#: channels that reach staff (Mastodon is public)
STAFF_CHANNELS = ("email", "ntfy", "matrix", "telegram")


def staff_channel_check(event, request):
    """Setup checklist (optional): a channel that reaches staff outside EVAC is set up for the event."""
    from apps.core import modules
    from apps.extensions import services as extensions

    if not modules.is_enabled("extensions", event):
        return None  # nowhere to set one up
    return "done" if any(extensions.effective(k, event) is not None for k in STAFF_CHANNELS) else "todo"


def register(r: Registry) -> None:
    from . import channels

    r.staff_card(StaffCardSpec(key="ntfy", title=str(_("Backup notifications")), template="notify/_staff_ntfy.html",
                               context=ntfy_card, module="announcements", order=95))

    r.setup_check(SetupCheckSpec(
        key="staff_channel", label=str(_("Set up a staff notification channel")), check=staff_channel_check,
        module="announcements", order=80, url_name="extensions:event_index", optional=True,
        help=str(_("E-mail, ntfy, Matrix or Telegram: reaches staff outside EVAC as a backup."))))
    for ext_spec, max_length in specs():
        r.extension(ext_spec)
        r.notification_channel(NotificationChannelSpec(
            key=ext_spec.key, name=ext_spec.name, send=channels.sender(ext_spec.key), module="announcements",
            description=ext_spec.description, available=channels.available(ext_spec.key), max_length=max_length,
            alert=channels.alerter(ext_spec.key)))
