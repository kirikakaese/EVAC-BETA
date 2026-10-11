# SPDX-License-Identifier: AGPL-3.0-or-later
"""pretix: ticket types, attendees and check-ins with the access module (roadmap 8.2, ADR-0044)."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ExtensionFeature, ExtensionSpec, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="pretix", name="pretix", version="1.0.0", kind="extension",
                          description="Import tickets from pretix and keep check-ins in step.")


def register(r: Registry) -> None:
    from . import importer

    r.extension(ExtensionSpec(
        key=importer.KEY, name="pretix", scope="event", version="1.0.0", icon="🎟", docs="extensions/pretix",
        description=str(_("Import admission products as ticket types and order positions as attendees (their QR "
                          "codes work at EVAC's scanners); take over pretix check-ins and send EVAC's back.")),
        settings_schema={"type": "object", "required": ["base_url", "organizer", "event"], "properties": {
            "base_url": {"type": "string", "format": "uri", "title": "pretix URL", "maxLength": 300,
                         "description": "e.g. https://pretix.eu"},
            "organizer": {"type": "string", "title": "Organizer short name", "maxLength": 100},
            "event": {"type": "string", "title": "Event short name", "maxLength": 100},
            "checkin_list": {"type": "integer", "title": "Check-in list id (for check-ins sent to pretix)",
                             "minimum": 1, "description": "Test connection lists them."},
            "pending_valid": {"type": "boolean", "title": "Pending (unpaid) orders are valid", "default": False},
            "interval_minutes": {"type": "integer", "title": "Sync every (minutes)", "default": 10, "minimum": 0,
                                 "maximum": 1440, "description": "0: only when you press “Sync now”."},
        }},
        secret_fields=(("api_token", str(_("API token (pretix → Organizer → API access)"))),),
        features=(ExtensionFeature("attendees", str(_("Sync attendees")), "import"),
                  ExtensionFeature("push_checkins", str(_("Send check-ins to pretix")), "other")),
        test_connection=importer.test_connection, purge=importer.purge, urls="extensions.pretix.urls"))
    r.outbox_handler(importer.JOB, importer.handle_job)
    r.outbox_handler(importer.CHECKIN_JOB, importer.handle_checkin)
    r.webhook_sink(importer.on_event)
