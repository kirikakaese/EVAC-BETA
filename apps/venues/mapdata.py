# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data and edit operations of the map editor (ADR-0027). One floor at a time (``None``: outdoors); positions in
metres on that floor's plan. Other modules add placeable things through ``r.map_layer`` (screens)."""
from __future__ import annotations

import math
from typing import Any

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import modules
from apps.core.audit import log
from apps.core.registry import registry

from . import geo, graph, plans
from .models import Edge, Floor, Point, Zone

LIMIT = 100_000.0  # metres; anything beyond is a typo


def floors(venue) -> list[Floor]:
    return list(Floor.objects.filter(building__venue=venue).select_related("building").order_by(
        "building__order", "building__name", "level", "name"))


def floor_of(venue, value: str | None) -> Floor | None:
    """``value`` is a floor id, or "" / "outdoors" for ground level outdoors."""
    if not value or value == "outdoors":
        return None
    try:
        return Floor.objects.get(building__venue=venue, pk=value)
    except (Floor.DoesNotExist, ValidationError, ValueError):
        raise ValidationError(_("Unknown floor.")) from None


def layers(event) -> list:
    return sorted((s for s in registry.ensure_loaded().map_layers.values()
                   if s.module == "core" or modules.is_enabled(s.module, event)), key=lambda s: (s.order, s.key))


def _plan(event, venue, floor: Floor | None) -> dict[str, Any] | None:
    if floor is None or not floor.plan_file:
        return None
    return {"url": reverse("venues:plan", args=[event.slug, venue.slug, floor.pk]) + f"?v={floor.plan_file[:12]}",
            "width": floor.plan_width, "height": floor.plan_height, "metresPerPx": floor.metres_per_px,
            "scaled": floor.plan_scaled}


def data(event, venue, floor: Floor | None, *, can_edit: bool) -> dict[str, Any]:
    fid = str(floor.pk) if floor else None
    pts = {str(p.pk): p for p in Point.objects.filter(venue=venue).select_related("floor")}
    here = {pid: p for pid, p in pts.items() if (str(p.floor_id) if p.floor_id else None) == fid}
    edges = []
    for e in Edge.objects.filter(venue=venue):
        a, b = str(e.a_id), str(e.b_id)
        if a in here or b in here:
            other = pts[b] if a in here else pts[a]
            edges.append({"id": str(e.pk), "a": a, "b": b, "oneWay": e.one_way, "stepFree": e.step_free,
                          "elsewhere": None if (a in here and b in here) else str(other.floor or _("outdoors"))})
    table = graph.table(venue)
    zones = []
    for z in Zone.objects.filter(venue=venue):
        area = next((a.get("points") for a in z.areas or [] if a.get("floor") == fid), None)
        zones.append({"id": str(z.pk), "name": z.name, "color": z.color, "area": area})
    layer_data = []
    for spec in layers(event):
        items = [i for i in spec.items(event, venue) if not i.get("placed") or i.get("floor") == fid]
        layer_data.append({"key": spec.key, "title": spec.title, "editable": spec.place is not None and can_edit,
                           "items": items})
    return {
        "floor": fid,
        "floors": [{"id": str(f.pk), "label": str(f), "level": f.level, "hasPlan": bool(f.plan_file)}
                   for f in floors(venue)],
        "plan": _plan(event, venue, floor),
        "points": [{"id": pid, "kind": p.kind, "name": p.name, "x": p.x, "y": p.y, "stepFree": p.step_free,
                    "zone": str(p.zone_id) if p.zone_id else None,
                    "next": table[pid].next if pid in table else None,
                    "noWayOut": pid not in table} for pid, p in here.items()],
        "elsewhere": {pid: {"name": p.name, "floor": str(p.floor or _("outdoors"))} for pid, p in pts.items()
                      if pid not in here},
        "edges": edges, "zones": zones, "layers": layer_data,
        "kinds": [[k, str(v)] for k, v in Point.Kind.choices],
        "map": _map(venue, floor),
        "canEdit": can_edit, "pdf": plans.has_pdf_renderer(),
    }


def _map(venue, floor: Floor | None) -> dict[str, Any] | None:
    cfg = geo.config()
    if not cfg.get("tiles_enabled") or not geo.tile_url():
        return None
    frame = geo.frame_of(venue, floor)
    return {"tileUrl": reverse("maptiles:tile", args=[0, 0, 0]).replace("/0/0/0.png", "/{z}/{x}/{y}.png"),
            "attribution": str(cfg.get("attribution") or ""), "maxZoom": int(cfg.get("max_zoom") or 19),
            "frame": {"lat": frame.lat, "lon": frame.lon, "rotation": frame.rotation} if frame else None,
            "rotatable": floor is not None, "areaDownload": geo.area_download_allowed()}


# ------------------------------------------------------------------ operations
def _num(value: Any, what: str) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValidationError(_("%(w)s must be a number.") % {"w": what}) from None
    if not math.isfinite(n) or abs(n) > LIMIT:
        raise ValidationError(_("%(w)s is out of range.") % {"w": what})
    return round(n, 3)


def _get(model, venue, pk: Any, message: str):
    try:
        return model.objects.get(venue=venue, pk=pk)
    except (model.DoesNotExist, ValidationError, ValueError):
        raise ValidationError(message) from None


def _point(venue, pid: Any) -> Point:
    return _get(Point, venue, pid, _("Unknown point."))


def apply(event, venue, floor: Floor | None, op: dict[str, Any], *, actor, request=None) -> dict[str, Any]:
    """Run one editor operation; returns ``{"id": ...}`` for created objects."""
    kind = op.get("op")
    audit = {"actor": actor, "event": event, "request": request}
    if kind == "point.add":
        k = op.get("kind") if op.get("kind") in Point.Kind.values else Point.Kind.WAYPOINT
        name = str(op.get("name") or "").strip()[:200] or str(Point.Kind(k).label)
        p = Point.objects.create(venue=venue, floor=floor, kind=k, name=name, x=_num(op.get("x"), "x"),
                                 y=_num(op.get("y"), "y"), step_free=k != Point.Kind.STAIRS)
        log(action="venue.part_created", target=p, message=f"{p} placed on the map", **audit)
        return {"id": str(p.pk)}
    if kind == "point.update":
        p = _point(venue, op.get("id"))
        fields = []
        for f in ("x", "y"):
            if f in op:
                setattr(p, f, _num(op[f], f))
                fields.append(f)
        if "name" in op:
            p.name = str(op["name"]).strip()[:200] or p.name
            fields.append("name")
        if op.get("kind") in Point.Kind.values:
            p.kind = op["kind"]
            fields.append("kind")
        if "stepFree" in op:
            p.step_free = bool(op["stepFree"])
            fields.append("step_free")
        if "zone" in op:
            p.zone = _get(Zone, venue, op["zone"], _("Unknown zone.")) if op["zone"] else None
            fields.append("zone")
        if fields:
            p.save(update_fields=fields)
            log(action="venue.map_edited", target=p, message=f"{p} changed on the map",
                changes={f: getattr(p, f if f != "zone" else "zone_id") for f in fields}, **audit)
        return {}
    if kind == "point.delete":
        p = _point(venue, op.get("id"))
        log(action="venue.part_deleted", target=p, message=f"{p} removed from the map", **audit)
        p.delete()
        return {}
    if kind == "edge.add":
        a, b = _point(venue, op.get("a")), _point(venue, op.get("b"))
        if a == b:
            raise ValidationError(_("A connection needs two different points."))
        if Edge.objects.filter(a=a, b=b).exists() or Edge.objects.filter(a=b, b=a).exists():
            raise ValidationError(_("These points are already connected."))
        e = Edge.objects.create(venue=venue, a=a, b=b, one_way=bool(op.get("oneWay")),
                                step_free=bool(op.get("stepFree", a.step_free and b.step_free)))
        log(action="venue.part_created", target=e, message=f"Connection {e} drawn", **audit)
        return {"id": str(e.pk)}
    if kind == "edge.update":
        e = _get(Edge, venue, op.get("id"), _("Unknown connection."))
        e.one_way, e.step_free = bool(op.get("oneWay", e.one_way)), bool(op.get("stepFree", e.step_free))
        e.save(update_fields=["one_way", "step_free"])
        log(action="venue.map_edited", target=e, message=f"Connection {e} changed",
            changes={"one_way": e.one_way, "step_free": e.step_free}, **audit)
        return {}
    if kind == "edge.delete":
        e = _get(Edge, venue, op.get("id"), _("Unknown connection."))
        log(action="venue.part_deleted", target=e, message=f"Connection {e} removed", **audit)
        e.delete()
        return {}
    if kind == "zone.area":
        zone = _get(Zone, venue, op.get("zone"), _("Unknown zone."))
        raw = op.get("points") or []
        if not isinstance(raw, list) or len(raw) > 500 or (raw and len(raw) < 3):
            raise ValidationError(_("An outline needs at least three corners."))
        points = [[_num(p[0], "x"), _num(p[1], "y")] for p in raw if isinstance(p, list | tuple) and len(p) == 2]
        fid = str(floor.pk) if floor else None
        zone.areas = [a for a in zone.areas or [] if a.get("floor") != fid] + (
            [{"floor": fid, "points": points}] if points else [])
        zone.save(update_fields=["areas"])
        log(action="venue.map_edited", target=zone, message=f"Outline of zone {zone} drawn",
            changes={"floor": fid, "corners": len(points)}, **audit)
        return {}
    if kind == "layer.place":
        spec = next((s for s in layers(event) if s.key == op.get("layer")), None)
        if spec is None or spec.place is None:
            raise ValidationError(_("Unknown map layer."))
        x = None if op.get("x") is None else _num(op.get("x"), "x")
        y = None if x is None else _num(op.get("y"), "y")
        facing = None if op.get("facing") is None else _num(op.get("facing"), "facing") % 360
        spec.place(event, str(op.get("id")), floor=floor, x=x, y=y, facing=facing, actor=actor, request=request)
        return {}
    if kind in ("georef", "georef.move"):
        return _georef(venue, floor, op, kind, audit)
    if kind == "map.download":
        return _download(venue, floor, audit)
    if kind == "scale":
        if floor is None or not floor.plan_file:
            raise ValidationError(_("Upload a floor plan first."))
        plans.set_scale(floor, px=_num(op.get("px"), "px"), metres=_num(op.get("metres"), "metres"), **audit)
        return {}
    raise ValidationError(_("Unknown operation."))


def _georef(venue, floor: Floor | None, op: dict[str, Any], kind: str, audit: dict[str, Any]) -> dict[str, Any]:
    """Align the plan with the map: set the frame, or move it by a drag of (dx, dy) metres."""
    if kind == "georef":
        lat, lon = _num(op.get("lat"), "lat"), _num(op.get("lon"), "lon")
        if not (-85 <= lat <= 85 and -180 <= lon <= 180):
            raise ValidationError(_("This is not a position on the map."))
        rotation = _num(op.get("rotation", 0), "rotation") % 360 if floor is not None else 0.0
    else:
        frame = geo.frame_of(venue, floor)
        if frame is None:
            raise ValidationError(_("Set a position first."))
        # dragging the map by (dx, dy) moves the plan's origin the other way
        lat, lon = geo.to_geo(frame, -_num(op.get("dx"), "dx"), -_num(op.get("dy"), "dy"))
        rotation = frame.rotation
    if floor is None:
        venue.latitude, venue.longitude = round(lat, 6), round(lon, 6)
        venue.save(update_fields=["latitude", "longitude", "updated_at"])
        target = venue
    else:
        floor.geo_lat, floor.geo_lon, floor.geo_rotation = round(lat, 7), round(lon, 7), round(rotation, 2)
        floor.save(update_fields=["geo_lat", "geo_lon", "geo_rotation"])
        target = floor
    log(action="venue.georeferenced", target=target, message=f"{target} aligned with the map",
        changes={"lat": round(lat, 7), "lon": round(lon, 7), "rotation": round(rotation, 2)}, **audit)
    return {}


def _download(venue, floor: Floor | None, audit: dict[str, Any]) -> dict[str, Any]:
    """Queue the tiles around this floor (or the outdoor area) for offline use."""
    from .tasks import download_area

    if not geo.area_download_allowed():
        raise ValidationError(_("Area downloads are only allowed for a tile server you run yourself "
                                "(Settings → Maps)."))
    frame = geo.frame_of(venue, floor)
    if frame is None:
        raise ValidationError(_("Align the plan with the map first."))
    xs, ys = [0.0], [0.0]
    if floor is not None and floor.plan_file:
        xs.append(floor.plan_width * floor.metres_per_px)
        ys.append(floor.plan_height * floor.metres_per_px)
    for p in Point.objects.filter(venue=venue, floor=floor):
        xs.append(p.x)
        ys.append(p.y)
    margin = 100.0
    corners = [geo.to_geo(frame, x, y) for x in (min(xs) - margin, max(xs) + margin)
               for y in (min(ys) - margin, max(ys) + margin)]
    top = int(geo.config().get("max_zoom") or 19)
    tiles = geo.tiles_for_area(corners, range(14, top + 1))
    while len(tiles) > geo.MAX_AREA_TILES and top > 14:
        top -= 1
        tiles = geo.tiles_for_area(corners, range(14, top + 1))
    tiles = tiles[:geo.MAX_AREA_TILES]
    download_area.delay([list(t) for t in tiles])
    log(action="venue.map_downloaded", target=floor or venue, message=f"{len(tiles)} map tiles queued",
        changes={"tiles": len(tiles), "max_zoom": top}, **audit)
    return {"tiles": len(tiles)}
