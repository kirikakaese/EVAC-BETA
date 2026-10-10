# ADR-0030: Evacuation models, blocked points and screen directions

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.4 and brief §8.1: three selectable evacuation models per event (simple takeover, staged global, zones
and routes), a fixed exit hint per screen in the staged model, and in the zones model a direction arrow and text
per screen to the nearest open exit or assembly point, live blocking of exits with instant recomputation, and
partial evacuation of zones. The state machine is ADR-0029; the route graph is ADR-0026.

## Decision

- **Model** (Settings → Evacuation, per event, default **staged**):
  - *simple*: only `evacuate` can be raised; the whole event.
  - *staged*: every enabled stage, for the whole event.
  - *zones*: stages per event and per zone (partial evacuation), computed routes and live blocking.
  The model limits what can be **raised or changed**, never what can be **ended**. Switching it while an alarm
  is active leaves that alarm in place and visible, and it can still be cleared. The rule lives in the pure state
  machine (`transition(..., model=, zone=)`) and is tested for every state, model and scope.
- **Blocked points**: `BlockedPoint(event, point)` marks an exit, assembly point, door, stair or passage as unusable
  for this event, with who, when and why. Blocking needs `evacuation.trigger` for the point's scope (venue,
  zone, assembly point), uses hold-to-confirm, is audit-logged (`evacuation.point_blocked` /
  `evacuation.point_reopened`) and emits `evacuation.routes_changed`. Routes are computed from the current
  blocked set on every read, so they change immediately.
- **Screen directions** (`apps/evacuation/guidance.py`, pure, mypy strict):
  - A screen's way out starts at the **nearest** point on its floor that still has a route; ties go to the
    shorter route. A plan has no walls, so the nearest point is the only straight line EVAC can trust; the
    operator places a waypoint near every screen.
  - The arrow points to that point, or to the next one when the screen is within 3 m of it. It is relative to
    the people reading the screen, who look opposite to the screen's facing, and is rounded to eight directions.
  - Without a route, a screen place or a facing (arrow only), the screen shows **"Follow staff instructions"**.
    It never guesses.
- **Fixed direction per screen** (namespace `evacuation_screen`, screen level): arrow and text (e.g. "Exit B").
  It overrides the computed route in every model and is the brief's manual per-screen override.
- **Screen zones**: a screen is in its own zone and in the zones of its room; it shows the most severe of the
  event state and those zone states (ADR-0029).
- The control page shows the model, the exits and passages with block / open again (zones model) and every
  screen with the state it shows and its direction, with an inline fixed-direction form.

## Consequences

- 3.7 renders these directions on screens (arrow, text, ISO 7010 pictograms) and 3.9 caches them in the
  evacuation bundle. Screens can recompute offline with the same pure functions and the blocked set.
- Step-free routes exist in the graph but are not shown on screens yet; a second arrow is a content decision for
  3.7.
- The evacuation module reads screens only when the screens app is installed; without it the screen list is
  empty.
