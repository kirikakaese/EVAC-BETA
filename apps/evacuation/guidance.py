# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which way a screen sends people (brief §8.1 zones and routes, ADR-0030). Pure Python, mypy strict.

A screen has a place on a floor plan (metres) and a facing (degrees clockwise from the plan's up). Its way out
starts at the *nearest* point of the route graph on the same floor that still has a route (ties: the shorter
route). The plan knows no walls, so the nearest point is the only safe straight line: place a waypoint near every
screen. The arrow points to that point, or to the point after it when the screen is right next to it, relative to
where the screen faces. Without a usable
route the screen says "follow staff instructions"; it never guesses.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from apps.venues import routing

#: closer than this (metres) to the entry point, the arrow already shows the step after it
NEAR = 3.0


class Arrow(StrEnum):
    AHEAD = "ahead"
    AHEAD_RIGHT = "ahead_right"
    RIGHT = "right"
    BACK_RIGHT = "back_right"
    BACK = "back"
    BACK_LEFT = "back_left"
    LEFT = "left"
    AHEAD_LEFT = "ahead_left"


ARROWS = list(Arrow)  # clockwise from ahead, 45° apart


class Kind(StrEnum):
    ROUTE = "route"  # computed from the route graph
    HINT = "hint"  # fixed text/arrow configured for the screen (manual override)
    FOLLOW_STAFF = "follow_staff"  # no route known: follow staff instructions
    NONE = "none"  # no direction (simple model, or no hint configured)


@dataclass(frozen=True)
class Place:
    x: float
    y: float
    facing: float | None = None


@dataclass(frozen=True)
class Guidance:
    kind: Kind
    arrow: Arrow | None = None
    toward: str | None = None  # point id the arrow points to
    target: str | None = None  # assembly point or exit id
    distance: float | None = None  # metres to the target
    text: str = ""


def bearing(x0: float, y0: float, x1: float, y1: float) -> float:
    """Degrees clockwise from the plan's up (negative y) from (x0, y0) to (x1, y1)."""
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360.0


def relative(bearing_deg: float, facing: float) -> Arrow:
    """The arrow for a direction seen by someone looking at the screen.

    The screen's facing is the direction its display looks; people reading it look the opposite way, so
    "ahead" is ``facing + 180``. Rounded to the nearest of eight directions.
    """
    viewer = (facing + 180.0) % 360.0
    rel = (bearing_deg - viewer) % 360.0
    return ARROWS[int((rel + 22.5) // 45.0) % 8]


def route(graph: routing.Graph, table: dict[str, routing.Route], place: Place,
          candidates: Iterable[str]) -> Guidance:
    """``candidates``: the points on the screen's floor (the way out must start where the screen is)."""
    best: tuple[float, float, str] | None = None
    for pid in candidates:
        r = table.get(pid)
        node = graph.nodes.get(pid)
        if r is None or node is None:
            continue
        key = (round(math.hypot(node.x - place.x, node.y - place.y), 3), r.distance, node.id)
        if best is None or key < best:
            best = key
    if best is None:
        return Guidance(Kind.FOLLOW_STAFF)
    near, _rest, entry = best
    cost = near + table[entry].distance
    toward = entry
    node = graph.nodes[entry]
    nxt = table[entry].next
    if math.hypot(node.x - place.x, node.y - place.y) < NEAR and nxt is not None:
        toward = nxt
    aim = graph.nodes[toward]
    arrow = None
    if place.facing is not None and (aim.x, aim.y) != (place.x, place.y):
        arrow = relative(bearing(place.x, place.y, aim.x, aim.y), place.facing)
    return Guidance(Kind.ROUTE, arrow, toward, table[entry].target, round(cost, 1))
