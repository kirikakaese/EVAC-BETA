# SPDX-License-Identifier: AGPL-3.0-or-later
"""Program import from pretalx, frab/Pentabarf and iCal (brief §11.1, roadmap 5.2, ADR-0038). Each is an event
extension: Settings → Extensions → pretalx / frab / iCal; it syncs periodically and on “Sync now”, and local live
changes survive every sync."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ExtensionFeature, ExtensionSpec, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="program_import", name="Program import", version="1.0.0", kind="extension",
                          description="Import the program from pretalx, frab/Pentabarf XML or iCal.")

INTERVAL = {"type": "integer", "title": "Sync every (minutes)", "default": 15, "minimum": 0, "maximum": 1440,
            "description": "0: only when you press “Sync now”."}


def specs() -> list[ExtensionSpec]:
    from . import importer

    common = {"scope": "event", "version": "1.0.0", "icon": "▦", "docs": "extensions/program-import",
              "test_connection": importer.test_connection, "purge": importer.purge,
              "urls": "extensions.program_import.urls",
              "features": (ExtensionFeature("sync", str(_("Sync the program")), "import"),)}
    return [
        ExtensionSpec(key="pretalx", name="pretalx", description=str(_(
            "Import the schedule of a pretalx event (its public schedule export; an API token also reads "
            "schedules that are not public yet).")),
            settings_schema={"type": "object", "required": ["base_url", "event"], "properties": {
                "base_url": {"type": "string", "format": "uri", "title": "pretalx URL", "maxLength": 300,
                             "description": "e.g. https://pretalx.com"},
                "event": {"type": "string", "title": "pretalx event slug", "maxLength": 100,
                          "pattern": "^[A-Za-z0-9_-]+$"},
                "interval_minutes": INTERVAL}},
            secret_fields=(("token", str(_("API token (optional)"))),), **common),
        ExtensionSpec(key="frab", name="frab / Pentabarf", description=str(_(
            "Import a schedule.xml (frab, Pentabarf, pretalx and other conference tools) or a frab schedule.json.")),
            settings_schema={"type": "object", "required": ["url"], "properties": {
                "url": {"type": "string", "format": "uri", "title": "schedule.xml URL", "maxLength": 500},
                "interval_minutes": INTERVAL}}, **common),
        ExtensionSpec(key="ical", name="iCal", description=str(_(
            "Import the events of an iCalendar feed (.ics) as sessions; LOCATION becomes the stage.")),
            settings_schema={"type": "object", "required": ["url"], "properties": {
                "url": {"type": "string", "format": "uri", "title": "iCal URL (.ics)", "maxLength": 500},
                "interval_minutes": INTERVAL}}, **common),
    ]


def register(r: Registry) -> None:
    from . import importer

    for spec in specs():
        r.extension(spec)
    r.outbox_handler(importer.JOB, importer.handle_job)
