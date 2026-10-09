# SPDX-License-Identifier: AGPL-3.0-or-later
"""Core plugin: the always-on platform (audit, settings, modules)."""
from django.utils.translation import gettext_lazy as _

from .plugins import ModuleSpec, PermissionSpec, PluginManifest, SettingsNamespace, WebhookEventSpec
from .registry import Registry

manifest = PluginManifest(key="core", name="EVAC core", version="0.1.0", kind="core")


def register(r: Registry) -> None:
    from . import webpush

    r.outbox_handler(webpush.JOB_KIND, webpush.handle_job)
    r.module(ModuleSpec(key="core", name=str(_("Core")), required=True, order=0,
                        description=str(_("Accounts, events, roles, audit log, settings and the plugin framework."))))
    r.permissions_([
        PermissionSpec("audit.view", str(_("View the audit log"))),
        PermissionSpec("audit.export", str(_("Export the audit log"))),
        PermissionSpec("settings.manage", str(_("Change event settings"))),
        PermissionSpec("modules.manage", str(_("Switch modules on or off for the event"))),
    ])
    r.settings_namespace(SettingsNamespace(
        key="general", title=str(_("General")), levels=("instance", "event"), order=10,
        schema={
            "type": "object",
            "properties": {
                "support_contact": {"type": "string", "title": "Support contact", "maxLength": 200, "default": "",
                                    "description": "Shown in the footer and on error pages."},
                "retention_days": {"type": "integer", "title": "Data retention after the event (days)",
                                   "minimum": 0, "maximum": 3650, "default": 90,
                                   "description": "Personal data of modules is purged this long after archiving. "
                                                  "0 = keep."},
                "heartbeat_seconds": {"type": "integer", "title": "Screen heartbeat interval (seconds)",
                                      "minimum": 2, "maximum": 300, "default": 10},
                "public_pages": {"type": "boolean", "title": "Public event pages", "default": False,
                                 "description": "Show the public event page to visitors without an account."},
            },
        },
    ))
    for key, desc in [
        ("event.created", "An event was created."),
        ("event.updated", "Event settings changed."),
        ("event.state_changed", "An event moved to another lifecycle state."),
        ("member.added", "A user joined an event."),
        ("member.removed", "A user was removed from an event."),
        ("module.toggled", "A module was switched on or off."),
        ("webhook.ping", "Connectivity test sent by 'Test connection'."),
    ]:
        r.webhook_event(WebhookEventSpec(key=key, description=desc))
