# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engelsystem import (roadmap 7.1, ADR-0041): angel types, shifts and their sign-ups into the crew module."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ExtensionFeature, ExtensionSpec, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="engelsystem", name="Engelsystem", version="1.0.0", kind="extension",
                          description="Import angel types, shifts and sign-ups from an Engelsystem.")


def register(r: Registry) -> None:
    from . import importer

    r.extension(ExtensionSpec(
        key=importer.KEY, name="Engelsystem", scope="event", version="1.0.0", icon="👼", docs="extensions/engelsystem",
        description=str(_("Import angel types as teams, shifts and who signed up from an Engelsystem (API v0-beta). "
                          "Check-ins and people added in EVAC stay on every sync.")),
        settings_schema={"type": "object", "required": ["base_url"], "properties": {
            "base_url": {"type": "string", "format": "uri", "title": "Engelsystem URL", "maxLength": 300,
                         "description": "e.g. https://engel.example.org"},
            "angeltypes": {"type": "array", "title": "Only these angel types", "items": {"type": "string"},
                           "maxItems": 50, "description": "Names or ids, one per line. Empty: all."},
            "interval_minutes": {"type": "integer", "title": "Sync every (minutes)", "default": 15, "minimum": 0,
                                 "maximum": 1440, "description": "0: only when you press “Sync now”."},
        }},
        secret_fields=(("api_key", str(_("API key (Engelsystem → Settings → API)"))),),
        features=(ExtensionFeature("shifts", str(_("Sync shifts")), "import"),),
        test_connection=importer.test_connection, purge=importer.purge, urls="extensions.engelsystem.urls"))
    r.outbox_handler(importer.JOB, importer.handle_job)
