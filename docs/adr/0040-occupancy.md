# ADR-0040: Occupancy: counting, capacity rules and "room full" on screens

- Status: Accepted
- Date: 2026-10-10

## Context

Brief §11.4 asks for:
- a live headcount per zone or room from door staff (a clicker in the staff app with several devices adding up
  and an offline queue), from sensors (generic MQTT/HTTP) and later from ticket scanners;
- capacity rules, so screens show "Room full / use Hall C" automatically and staff are alerted;
- an occupancy history.

The Phase 6 gate: "Room full" appears automatically at the threshold.

Constraints:
- **Plugins only** (`apps/crowd`, module key `crowd`; the built-in roles reserve `crowd.*`).
- **Screens get content through the program.** Modules contribute with `program_source` (ADR-0016, ADR-0019),
  so the player keeps working offline with the last program it received.
- **No personal data in occupancy** (brief §13).

## Decision

**Areas, not only rooms.**
- An `Area` is a room, a zone or a free-standing counted place (a queue, a tent), with these settings:
  - a capacity; empty means the room's or zone's capacity;
  - busy %, full % and "open again below" %;
  - screen groups that should also show it;
  - an alternative area;
  - a custom text;
  - roles and channels to alert;
  - an MQTT sensor key.
- The area holds the current `value` and `state` (normal, busy, full).

**One way to change the number.**
- `services.count(delta)` and `services.set_value(value)` lock the area row and write a `CountEvent`: delta,
  value after, source, device label. They also update a per-minute `Sample` (last, highest and lowest value)
  for the charts.
- Several doors and sensors therefore add up exactly. A `client_id` makes replays harmless, so a click is never
  counted twice after a lost answer.
- The count never goes below zero.
- Clicks and sensor readings record a device label, never a person. Only manual corrections record who made them.

**The rule (pure function `state_for`).**
- The area is full from `full_percent`.
- It stays full until the count falls below `release_percent`. This hysteresis stops the screens flickering at
  the limit.
- It is busy from `busy_percent`.
- A capacity of 0 means "count only".

**When the rule changes state:**
- the audit log records it;
- `occupancy.state_changed` is emitted to webhooks, the realtime stream and the ops log;
- when the change enters or leaves "full":
  - every paired screen of the event gets `program.changed`, because a full area also changes the suggestion
    shown for other areas;
  - the roles to alert get a notification (Web Push on phones), and the channels get a staff alert (ADR-0039).

**"Full" on screens.**
- `r.program_source(services.program_source)` returns an open-ended banner overlay for each full area. Screens
  get it when they are in the area's room or zone, or in one of its screen groups.
- The text is the custom text, or "X is full. Please use Y." while the alternative has space, else "X is full.
  Please wait or come back later."
- The banner rank (25) sits above "important" announcements and below "urgent" ones. Evacuation takeovers hide
  it like every overlay.
- The player needed no change: the banner arrives with the program, and the program version changes with it.

**Door counter (staff app).**
- `/e/<slug>/crowd/count/<area>/` shows big +1/−1 buttons (plus ±5), the count, the state and a door label.
- `evac.js` shows each click at once and keeps it in localStorage with a UUID. It sends batches to
  `/e/<slug>/crowd/count/`, and the answer carries the area's state.
- While other doors count, the page polls the area's state every 4 s.
- Offline, the clicks wait. The page says how many are waiting, and they are sent when the device is back.
- The service worker keeps counter pages for offline use, like the staff page.

**Sensors.**
- HTTP: `POST /api/v1/events/<slug>/occupancy/<id>/count/` with a service token (scope `crowd`). The body is
  `{"delta"}`, `{"in", "out"}` or `{"value"}`, with an optional `"id"` for idempotency.
- MQTT: `<prefix>/crowd/<event slug>/<sensor key>` with the same JSON body, or a bare number (the occupancy).
- For this, the MQTT extension gained a generic hook: `r.mqtt_topic(MqttTopicSpec(key, pattern, handler))`. It
  subscribes to `<prefix>/<pattern>` for every registered spec and hands matching messages to the module.
  Handlers validate the payload themselves.
- Ticket scanners (phase 8) will call the same service.

**History and display.**
- The area page draws a server-side SVG step chart (2 to 48 h) with the busy and full lines, and lists the
  recent counts.
- The control room panel shows bars with glyph and word.
- The data source `crowd.areas` lets custom widgets put occupancy on screens (list, table, gauge, bars).

## Consequences

- The gate is tested end to end by `frontend/e2e/phase6.mjs`:
  - two door counters, one offline for a while;
  - the screen in the foyer shows "Foyer is full. Please use Hall B." about 0.15 s after the 10th person;
  - the control room gets an alert and an ops log line;
  - at 9 of 10 the banner stays (hysteresis); at 7 it goes.
- Counts are only as good as the doors that are counted. A correction ("set count") is audited, and "Reset all to
  0" starts a day.
- Every screen of the event refetches its program when any area enters or leaves "full". This is a few requests
  per change.
