# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venues, their floors, zones, rooms and route graph for venue nodes (ADR-0036). Venues are shared between
events: a node keeps a venue another of its events still uses."""
from __future__ import annotations

from typing import Any

from django.conf import settings

from apps.core.plugins import SyncModel, SyncSpec


def _plan(floor: Any) -> list[tuple[str, str]]:
    if not floor.plan_file:
        return []
    sha = floor.plan_file.split(".")[0]
    return [(f"{settings.MEDIA_ROOT}/venues/plans/{floor.plan_file}", sha if len(sha) == 64 else "")]


def spec() -> SyncSpec:
    from .models import Building, Edge, Floor, Point, Room, Venue, Zone

    return SyncSpec(module="venues", order=10, models=(
        SyncModel("venues.Venue", lambda e: Venue.objects.filter(events=e), delete_missing=False),
        SyncModel("venues.Building", lambda e: Building.objects.filter(venue__events=e)),
        SyncModel("venues.Floor", lambda e: Floor.objects.filter(building__venue__events=e), files=_plan),
        SyncModel("venues.Zone", lambda e: Zone.objects.filter(venue__events=e)),
        SyncModel("venues.Room", lambda e: Room.objects.filter(venue__events=e)),
        SyncModel("venues.Point", lambda e: Point.objects.filter(venue__events=e)),
        SyncModel("venues.Edge", lambda e: Edge.objects.filter(venue__events=e)),
    ))
