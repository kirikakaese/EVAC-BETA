# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupancy on venue nodes (ADR-0036): counters are live data of the node during a checkout (ADR-0002), so door
counters and sensors keep working on site without central."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import Area, CountEvent, Sample

    return SyncSpec(module="crowd", order=160, models=(
        SyncModel("crowd.Area", lambda e: Area.objects.filter(event=e), live=True),
        SyncModel("crowd.CountEvent", lambda e: CountEvent.objects.filter(area__event=e), live=True),
        SyncModel("crowd.Sample", lambda e: Sample.objects.filter(area__event=e), live=True),
    ))
