# SPDX-License-Identifier: AGPL-3.0-or-later
"""The event itself, its roles and memberships for venue nodes (ADR-0036)."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import Event, Membership, Role, RoleAssignment

    return SyncSpec(module="events", order=20, models=(
        SyncModel("events.Event", lambda e: Event.objects.filter(pk=e.pk), delete_missing=False),
        SyncModel("events.Role", lambda e: Role.objects.filter(event=e)),
        SyncModel("events.Membership", lambda e: Membership.objects.filter(event=e)),
        SyncModel("events.RoleAssignment", lambda e: RoleAssignment.objects.filter(membership__event=e)),
    ))
