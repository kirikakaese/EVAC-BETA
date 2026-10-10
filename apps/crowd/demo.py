# SPDX-License-Identifier: AGPL-3.0-or-later
"""Demo occupancy for ``evac_seed_demo``: the halls and the beer garden with capacities and a few hours of counts."""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

from django.utils import timezone

from . import services
from .models import Area, CountEvent, Sample


def seed(event: Any, actor: Any) -> int:
    if Area.objects.filter(event=event).exists():
        return 0
    from apps.venues.models import Room

    rooms = {r.name: r for r in Room.objects.filter(venue__in=event.venues.all())}
    control = event.roles.filter(key="control-room").first()
    specs = [("Hall A", 800, "Hall B", 0.62), ("Hall B", 600, "Hall A", 0.35), ("Beer garden", 500, "", 0.81),
             ("Workshop 1", 40, "Workshop 2", 0.5)]
    areas: dict[str, Area] = {}
    for i, (name, cap, _alt, _level) in enumerate(specs):
        a = Area(event=event, name=name, room=rooms.get(name), capacity=cap, order=i,
                 sensor_key=name.lower().replace(" ", "-"))
        services.save_area(a, actor=actor, m2m={"notify_roles": [control] if control else []})
        areas[name] = a
    for name, _cap, alt, _level in specs:
        if alt in areas:
            Area.objects.filter(pk=areas[name].pk).update(alternative=areas[alt])
    # a believable afternoon: history samples, then the current counts through the service
    now = timezone.now().replace(second=0, microsecond=0)
    for name, cap, _alt, level in specs:
        a = areas[name]
        rows = []
        for m in range(240, 0, -5):
            t = now - dt.timedelta(minutes=m)
            v = int(cap * level * (0.35 + 0.65 * (1 - m / 240)) * (1 + 0.08 * math.sin(m / 17)))
            rows.append(Sample(area=a, minute=t, value=v, peak=v + cap // 40, low=max(0, v - cap // 40)))
        Sample.objects.bulk_create(rows)
        services.set_value(a, int(cap * level), source=CountEvent.Source.SENSOR, device="demo")
    return len(specs)
