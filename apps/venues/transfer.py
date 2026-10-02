# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venue structure in event exports. Venues are shared: import reuses a venue with the same slug."""
from __future__ import annotations

from typing import Any

from django.utils.text import slugify

from .models import Building, Floor, Room, Venue, Zone


def export_venues(event) -> list[dict[str, Any]]:
    out = []
    for v in event.venues.prefetch_related("buildings__floors", "zones", "rooms__zones"):
        out.append({
            "slug": v.slug, "name": v.name, "description": v.description, "address": v.address,
            "timezone": v.timezone, "is_permanent": v.is_permanent,
            "latitude": str(v.latitude) if v.latitude is not None else None,
            "longitude": str(v.longitude) if v.longitude is not None else None,
            "buildings": [{"name": b.name, "outdoor": b.outdoor, "order": b.order,
                           "floors": [{"name": f.name, "level": f.level} for f in b.floors.all()]}
                          for b in v.buildings.all()],
            "zones": [{"name": z.name, "outdoor": z.outdoor, "capacity": z.capacity, "color": z.color}
                      for z in v.zones.all()],
            "rooms": [{"name": r.name, "capacity": r.capacity, "step_free": r.step_free, "has_lift": r.has_lift,
                       "wheelchair_spaces": r.wheelchair_spaces,
                       "floor": [r.floor.building.name, r.floor.name] if r.floor_id else None,
                       "zones": [z.name for z in r.zones.all()]} for r in v.rooms.all()],
        })
    return out


def import_venues(event, data: list[dict[str, Any]], user) -> None:
    for item in data or []:
        venue = Venue.objects.filter(slug=item.get("slug")).first()
        if venue is None:
            venue = Venue.objects.create(
                slug=item.get("slug") or slugify(item.get("name", "venue"))[:50], name=item.get("name", "Venue"),
                description=item.get("description", ""), address=item.get("address", ""),
                timezone=item.get("timezone", "UTC"), is_permanent=bool(item.get("is_permanent")),
                latitude=item.get("latitude"), longitude=item.get("longitude"))
            floors = {}
            for b in item.get("buildings", []):
                building = Building.objects.create(venue=venue, name=b["name"], outdoor=bool(b.get("outdoor")),
                                                   order=int(b.get("order", 0)))
                for f in b.get("floors", []):
                    floors[(b["name"], f["name"])] = Floor.objects.create(building=building, name=f["name"],
                                                                          level=int(f.get("level", 0)))
            zones = {z["name"]: Zone.objects.create(venue=venue, name=z["name"], outdoor=bool(z.get("outdoor")),
                                                    capacity=z.get("capacity"), color=z.get("color", "#22c55e"))
                     for z in item.get("zones", [])}
            for r in item.get("rooms", []):
                room = Room.objects.create(venue=venue, name=r["name"], capacity=r.get("capacity"),
                                           step_free=bool(r.get("step_free", True)), has_lift=bool(r.get("has_lift")),
                                           wheelchair_spaces=int(r.get("wheelchair_spaces", 0)),
                                           floor=floors.get(tuple(r["floor"])) if r.get("floor") else None)
                room.zones.set([zones[z] for z in r.get("zones", []) if z in zones])
        event.venues.add(venue)
