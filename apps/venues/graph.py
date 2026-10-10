# SPDX-License-Identifier: AGPL-3.0-or-later
"""The route graph of a venue from the database (ADR-0026); the rules live in ``routing.py``."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from . import routing
from .models import Edge, Point


def build(venue) -> routing.Graph:
    points = list(Point.objects.filter(venue=venue).select_related("floor"))
    nodes = [routing.Node(id=str(p.pk), kind=p.kind, x=p.x, y=p.y, level=p.level, step_free=p.step_free)
             for p in points]
    links = [routing.Link(a=str(e.a_id), b=str(e.b_id), one_way=e.one_way, length=e.length_m,
                          step_free=e.step_free) for e in Edge.objects.filter(venue=venue)]
    return routing.Graph.build(nodes, links)


def table(venue, *, blocked: Iterable[str] = (), step_free: bool = False) -> dict[str, routing.Route]:
    return routing.routes(build(venue), blocked=blocked, step_free=step_free)


def report(venue) -> dict[str, Any]:
    """Every point with its way out (any route and step-free), plus plan problems, for the venue page."""
    g = build(venue)
    points = {str(p.pk): p for p in Point.objects.filter(venue=venue).select_related("floor__building", "zone")}
    normal, free = routing.routes(g), routing.routes(g, step_free=True)
    rows = []
    for pid, p in points.items():
        r, f = normal.get(pid), free.get(pid)
        rows.append({"point": p, "next": points.get(r.next) if r and r.next else None,
                     "target": points.get(r.target) if r else None, "distance": r.distance if r else None,
                     "free_target": points.get(f.target) if f else None, "free_distance": f.distance if f else None})
    rows.sort(key=lambda row: (row["target"] is not None, row["point"].kind, row["point"].name))
    issues = [(points.get(pid), text) for pid, text in routing.problems(g)]
    return {"rows": rows, "problems": issues}


def api_table(venue, *, blocked: Iterable[str] = (), step_free: bool = False) -> dict[str, Any]:
    t = table(venue, blocked=blocked, step_free=step_free)
    return {pid: {"next": r.next, "target": r.target, "distance": round(r.distance, 1),
                  "path": routing.path(t, pid)} for pid, r in t.items()}
