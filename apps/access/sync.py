# SPDX-License-Identifier: AGPL-3.0-or-later
"""Access on venue nodes (ADR-0036): attendees, presence and scans are live during a checkout, so check-in at the
gates keeps working without central; ticket types and zones are configuration."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import AccessZone, Attendee, Presence, Scan, TicketType

    return SyncSpec(module="access", order=175, models=(
        SyncModel("access.AccessZone", lambda e: AccessZone.objects.filter(event=e)),
        SyncModel("access.TicketType", lambda e: TicketType.objects.filter(event=e)),
        SyncModel("access.Attendee", lambda e: Attendee.objects.filter(event=e), live=True),
        SyncModel("access.Presence", lambda e: Presence.objects.filter(zone__event=e), live=True),
        SyncModel("access.Scan", lambda e: Scan.objects.filter(event=e), live=True),
    ))
