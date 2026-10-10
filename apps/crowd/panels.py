# SPDX-License-Identifier: AGPL-3.0-or-later
"""Occupancy for the control room panel and as a data source for screen widgets."""
from __future__ import annotations

from typing import Any

from apps.events import rbac

from .models import Area


def rows(event: Any) -> list[dict[str, Any]]:
    return [{"id": str(a.pk), "name": a.name, "value": a.value, "capacity": a.capacity, "percent": a.percent,
             "free": a.free, "state": a.state, "place": a.room.name if a.room_id else (a.zone.name if a.zone_id
                                                                                         else "")}
            for a in Area.objects.filter(event=event).select_related("room", "zone")]


def data_source(event: Any, **_kw: Any) -> dict[str, Any]:
    """``crowd.areas``: one item per area (custom widgets: list, table, gauge, bars)."""
    items = rows(event)
    return {"items": items, "total": sum(i["value"] for i in items),
            "full": [i["name"] for i in items if i["state"] == Area.State.FULL]}


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "crowd.view", request=request):
        return None
    areas = list(Area.objects.filter(event=event).select_related("room", "zone"))
    for a in areas:
        a.bar = min(100, round((a.percent or 0) / 5) * 5)
    return {"areas": areas, "total": sum(a.value for a in areas)}
