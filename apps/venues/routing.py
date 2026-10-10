# SPDX-License-Identifier: AGPL-3.0-or-later
"""Route graph and evacuation routes (ADR-0026). Pure functions without Django, so the same rules can be
tested exhaustively (property tests) and later run on screens or the venue node.

Points are nodes, edges are walkable connections (both ways unless one-way). An edge without an explicit
length is as long as the straight distance plus ``LEVEL_PENALTY`` metres per floor between its ends.
``routes`` runs one multi-source Dijkstra backwards from the targets (assembly points, else exits): every
point gets the next point to walk to, the target it leads to and the remaining distance. Blocked points are
neither passed nor reached; a step-free route avoids edges and points that are not step-free.
"""
from __future__ import annotations

import heapq
import math
from collections.abc import Iterable
from dataclasses import dataclass, field

LEVEL_PENALTY = 5.0
EXIT, ASSEMBLY = "exit", "assembly"


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    x: float = 0.0
    y: float = 0.0
    level: int = 0
    step_free: bool = True


@dataclass(frozen=True)
class Link:
    a: str
    b: str
    one_way: bool = False
    length: float | None = None
    step_free: bool = True


@dataclass(frozen=True)
class Route:
    """Where to go from a point: the next point (None at the target), the target and the distance left."""

    next: str | None
    target: str
    distance: float


@dataclass
class Graph:
    nodes: dict[str, Node] = field(default_factory=dict)
    #: id -> [(neighbour id, length, step_free)] in walking direction
    out: dict[str, list[tuple[str, float, bool]]] = field(default_factory=dict)

    @classmethod
    def build(cls, nodes: Iterable[Node], links: Iterable[Link]) -> Graph:
        g = cls(nodes={n.id: n for n in nodes})
        g.out = {n: [] for n in g.nodes}
        for link in links:
            if link.a not in g.nodes or link.b not in g.nodes or link.a == link.b:
                continue
            length = link.length if link.length is not None else g.distance(link.a, link.b)
            length = max(0.0, float(length))
            g.out[link.a].append((link.b, length, link.step_free))
            if not link.one_way:
                g.out[link.b].append((link.a, length, link.step_free))
        return g

    def distance(self, a: str, b: str) -> float:
        na, nb = self.nodes[a], self.nodes[b]
        return math.hypot(na.x - nb.x, na.y - nb.y) + LEVEL_PENALTY * abs(na.level - nb.level)

    def targets(self, kind: str, blocked: frozenset[str] = frozenset()) -> set[str]:
        return {n.id for n in self.nodes.values() if n.kind == kind and n.id not in blocked}


def _usable(node: Node, blocked: frozenset[str], step_free: bool) -> bool:
    return node.id not in blocked and (node.step_free or not step_free)


def _dijkstra(graph: Graph, targets: set[str], blocked: frozenset[str], step_free: bool) -> dict[str, Route]:
    # walk the edges backwards from every target at once
    back: dict[str, list[tuple[str, float]]] = {n: [] for n in graph.nodes}
    for a, outs in graph.out.items():
        for b, length, edge_free in outs:
            if step_free and not edge_free:
                continue
            back[b].append((a, length))
    best: dict[str, Route] = {}
    heap: list[tuple[float, str, str, str | None]] = []
    for t in sorted(targets):
        if _usable(graph.nodes[t], blocked, step_free):
            heapq.heappush(heap, (0.0, t, t, None))
    while heap:
        dist, node, target, nxt = heapq.heappop(heap)
        if node in best:
            continue
        best[node] = Route(next=nxt, target=target, distance=dist)
        for prev, length in back[node]:
            if prev not in best and _usable(graph.nodes[prev], blocked, step_free):
                heapq.heappush(heap, (dist + length, prev, target, node))
    return best


def routes(graph: Graph, *, blocked: Iterable[str] = (), step_free: bool = False) -> dict[str, Route]:
    """The way out from every point that has one: to the nearest assembly point, else to the nearest exit."""
    blocked_set = frozenset(blocked)
    out = _dijkstra(graph, graph.targets(ASSEMBLY, blocked_set), blocked_set, step_free)
    if len(out) < len(graph.nodes):
        for node, route in _dijkstra(graph, graph.targets(EXIT, blocked_set), blocked_set, step_free).items():
            out.setdefault(node, route)
    return out


def path(table: dict[str, Route], start: str) -> list[str]:
    """The points from ``start`` to its target (empty when there is no way out)."""
    out: list[str] = []
    node: str | None = start
    while node is not None and node in table and node not in out:
        out.append(node)
        node = table[node].next
    return out if out and table[out[-1]].next is None else []


def problems(graph: Graph) -> list[tuple[str, str]]:
    """Plan checks for the editor: ``(point id, problem)`` for points without a way out, and the venue-wide
    problems ``("", ...)``."""
    issues: list[tuple[str, str]] = []
    if not graph.targets(EXIT) and not graph.targets(ASSEMBLY):
        issues.append(("", "no exit or assembly point"))
    table = routes(graph)
    for node in graph.nodes.values():
        if node.id not in table:
            issues.append((node.id, "no route to an exit or assembly point"))
    step_free = routes(graph, step_free=True)
    for node in graph.nodes.values():
        if node.id in table and node.step_free and node.id not in step_free:
            issues.append((node.id, "no step-free route"))
    return issues
