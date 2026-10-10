# ADR-0029: Evacuation state machine

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.3 and brief §8.2: an explicit, persisted state machine per event and per zone (zone states override
the event state for screens in that zone, highest severity wins), drills in any state, and **never auto-clear**.
Four questions were open in the brief and were decided by the project owner on 2026-10-10:

1. Stepping an alarm down (evacuate → shelter in place) — **directly**, by an authorised person with
   hold-to-confirm, audit-logged; only `normal` requires the all clear.
2. An event-wide all clear while zones have their own alarm — the all-clear form **lists those zones, all
   ticked**; unticked zones keep their alarm.
3. A real alarm while a drill runs — **a real alarm replaces the drill**; a drill cannot start while a real
   alarm is active and can never mask one.
4. Configurability — **the six states of the brief with a fixed severity order**; per event, three of them can
   be switched off and all of them renamed. Custom states are not part of 3.3.

## Decision

- **Pure core** `apps/evacuation/machine.py` (no Django, mypy strict, every transition tested): `State`,
  `SEVERITY` (`normal` 0 < `all_clear` 1 < `staff_alert` 2 < `attention` 3 < `shelter_in_place` 4 <
  `evacuate` 5), `Status(state, drill, since, clear_until)`, `transition()` (returns the new status and its
  kind — raise, escalate, step down, replace drill, clear, end — or raises `Refused` with a code),
  `current()`, `end_drill()` and `effective()`.
- **Rules**
  - `normal` is reached only from `all_clear`. `all_clear` is only possible from an alarm and keeps its drill
    flag; it shows for the configured time (default 5 minutes, 0 allowed), then counts as `normal`. That
    expiry is computed when the state is read, from the stored `clear_until`, so restarts, reconnects and
    missed timers cannot end an alarm and cannot change when an all clear ends. There is no other timed
    transition.
  - `evacuate`, `all_clear` and `normal` cannot be switched off.
  - A drill may change between alarm states and end with its own all clear. It is refused while a real alarm
    is active anywhere in the event.
  - A real alarm anywhere in the event ends every drill in it (history kind `drill_ended`), so a drill can
    never be mistaken for, or shown instead of, a real alarm.
  - `effective(statuses)`: what a screen shows is the event status and the statuses of its zones, highest
    severity first and real before drill. While any real alarm applies, drills are ignored entirely.
- **Persistence**: `EvacState` holds one row per event (`zone` empty) and per zone, with state, drill flag,
  `since`, `clear_until`, who, source, note and a `version` counter. `StateChange` is an append-only history
  (the model refuses updates and deletes). Every change also goes to the hash-chained audit log
  (`evacuation.<kind>`, with the audit log's drill flag) and emits `evacuation.state_changed` after commit,
  for webhooks and the realtime stream.
- **Service** `apps.evacuation.services.change()` is the only writer. It locks the event's rows
  (`select_for_update`), checks permissions on the scope, applies the machine and records the result.
  Permissions are `evacuation.view`, `evacuation.trigger` (raise, change and step down real alarms),
  `evacuation.clear` (the all clear for real alarms), `evacuation.drill` (start, change and end drills) and
  `evacuation.manage` (settings). The first three are sensitive (two-factor session for everyone) and can be
  scoped to a venue or a zone. Ending something needs the permission for what ends, so the built-in
  *security* role may raise alarms but not clear them. An event-wide all clear skips zones the person may not
  clear.
- **Module**: `evacuation` is off by default and depends on `venues`. The control page (`/e/<event>/evacuation/`)
  shows the event state, each zone's own state and what its screens show, a change form with hold-to-confirm,
  and the history (filter: real alarms or drills). Settings → Evacuation holds the states in use, their
  names, the all-clear time and the drill marker text.

## Consequences

- Trigger sources and policies (arm / execute / notify, two-person rule, panic page, API, MQTT; 3.5),
  screens rendering the states (3.7, 3.8) and the per-event safety acknowledgement when enabling the module
  (3.11) build on `services.change()` and `effective()`. Until then, changes are made on the control page and
  by code (`source=` names the caller; callers without a person check permissions themselves).
- Fail-safe paths (signed state from a secondary node or the bridge, ADR-0003) reuse the same pure rules, so
  a screen deciding offline reaches the same result as the server.
- Custom states would need a severity rank and display rules; the fixed order keeps "highest severity wins"
  unambiguous.
