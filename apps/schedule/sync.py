# SPDX-License-Identifier: AGPL-3.0-or-later
"""The program on venue nodes (ADR-0036): stages, tracks and speakers are configuration from central; sessions and
their live changes belong to the node during a checkout, so delays and cancellations work on site without central."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import Session, SessionChange, Speaker, Stage, Track

    return SyncSpec(module="program", order=140, models=(
        SyncModel("schedule.Stage", lambda e: Stage.objects.filter(event=e)),
        SyncModel("schedule.Track", lambda e: Track.objects.filter(event=e)),
        SyncModel("schedule.Speaker", lambda e: Speaker.objects.filter(event=e)),
        SyncModel("schedule.Session", lambda e: Session.objects.filter(event=e), live=True),
        SyncModel("schedule.SessionChange", lambda e: SessionChange.objects.filter(event=e), live=True),
    ))
