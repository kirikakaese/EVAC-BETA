# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venue structure in event exports. Venues are shared: import reuses a venue with the same slug."""
from __future__ import annotations

from typing import Any

from django.utils.text import slugify

from .models import Building, Edge, Floor, Point, Room, Venue, Zone


def export_venues(event) -> list[dict[str, Any]]:
    out = []
    for v in event.venues.prefetch_related("buildings__floors", "zones", "rooms__zones", "points__floor__building",
                                           "points__zone", "points__room", "edges"):
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
            # route graph (ADR-0026): points by their id, edges refer to those ids
            "points": [{"id": str(p.pk), "kind": p.kind, "name": p.name, "x": p.x, "y": p.y,
                        "capacity": p.capacity, "step_free": p.step_free, "note": p.note,
                        "floor": [p.floor.building.name, p.floor.name] if p.floor_id else None,
                        "zone": p.zone.name if p.zone_id else None, "room": p.room.name if p.room_id else None}
                       for p in v.points.all()],
            "edges": [{"a": str(e.a_id), "b": str(e.b_id), "one_way": e.one_way, "length_m": e.length_m,
                       "step_free": e.step_free} for e in v.edges.all()],
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
            _import_graph(venue, item, floors, zones)
        event.venues.add(venue)


def _import_graph(venue, item: dict[str, Any], floors: dict, zones: dict) -> None:
    rooms = {r.name: r for r in venue.rooms.all()}
    points = {}
    for p in item.get("points", []):
        kind = p.get("kind") if p.get("kind") in Point.Kind.values else Point.Kind.WAYPOINT
        points[str(p.get("id"))] = Point.objects.create(
            venue=venue, kind=kind, name=str(p.get("name", ""))[:200], x=float(p.get("x") or 0),
            y=float(p.get("y") or 0), capacity=p.get("capacity"), step_free=bool(p.get("step_free", True)),
            note=str(p.get("note", ""))[:300], floor=floors.get(tuple(p["floor"])) if p.get("floor") else None,
            zone=zones.get(p.get("zone")), room=rooms.get(p.get("room")))
    for e in item.get("edges", []):
        a, b = points.get(str(e.get("a"))), points.get(str(e.get("b")))
        if a and b and a != b and not Edge.objects.filter(a=a, b=b).exists():
            Edge.objects.create(venue=venue, a=a, b=b, one_way=bool(e.get("one_way")),
                                length_m=e.get("length_m"), step_free=bool(e.get("step_free", True)))
