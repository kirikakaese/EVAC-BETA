# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crew on venue nodes (ADR-0036): teams, skills, members and shifts are configuration from central; assignments
(sign-ups, check-ins, no-shows) are live on the node during a checkout, so check-in by QR works on site."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import Assignment, Member, Shift, ShiftType, Skill, Team

    return SyncSpec(module="crew", order=170, models=(
        SyncModel("crew.Skill", lambda e: Skill.objects.filter(event=e)),
        SyncModel("crew.Team", lambda e: Team.objects.filter(event=e)),
        SyncModel("crew.ShiftType", lambda e: ShiftType.objects.filter(event=e)),
        SyncModel("crew.Member", lambda e: Member.objects.filter(event=e)),
        SyncModel("crew.Shift", lambda e: Shift.objects.filter(event=e)),
        SyncModel("crew.Assignment", lambda e: Assignment.objects.filter(shift__event=e), live=True),
    ))
