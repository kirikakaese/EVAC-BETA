# ADR-0026: Venue route graph

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.1 and brief §10: exits, assembly points, doors and waypoints with capacities and accessibility, and
a route graph that drives evacuation arrows, wayfinding and the "you are here" map (§8.1 model 3: arrow to the
nearest open exit or assembly point, routes recompute when an exit is blocked). Venues are shared by events;
blocking an exit is live state of one event (phase 3.4).

## Decision

- **One table for all nodes**: `venues.Point` with `kind` (waypoint, door, stairs, lift, exit, assembly point),
  `floor` (empty: outdoors at ground level), zone and room, position `x`/`y` in **metres on that floor's plan**,
  capacity and `step_free`. The map editor (3.2) places points by clicking and georeferences floor plans;
  nothing else depends on the coordinate source.
- **Edges** (`venues.Edge`) connect two points of the venue, both ways unless one-way, with an explicit length or
  the straight distance plus 5 m per floor between the ends, and `step_free`.
- **Routing is pure Python** (`apps/venues/routing.py`, mypy strict, no Django): one multi-source Dijkstra
  backwards from the targets gives every point the next point, its target and the remaining distance. Targets
  are assembly points; points that cannot reach one fall back to the nearest exit. Blocked points are neither
  passed nor reached; step-free routing skips stairs and non-step-free edges. Property tests (hypothesis)
  compare it with a brute-force shortest path and check that every step is a real edge.
- **Plan checks**: points without a way out, missing exits and points without a step-free route are shown on the
  venue page.
- **API**: `/api/v1/points/`, `/api/v1/edges/` (venue-scoped like rooms) and
  `GET /api/v1/venues/<slug>/routes/?blocked=<ids>&step_free=1`. Event export/import carries the graph.
- **Scope kind** `assembly`: roles can be limited to an assembly point (marshals, roll calls).

## Consequences

- The evacuation module (3.3–3.9) computes routes with the event's blocked points and ships them in the screen's
  evacuation bundle, so screens keep correct arrows offline. The same function can run on the venue node.
- Positions in metres keep distances meaningful before any georeferencing; outdoor sites use one ground-level
  frame per site.
- Capacities are informational until occupancy (phase 7) can weigh routes by load.
