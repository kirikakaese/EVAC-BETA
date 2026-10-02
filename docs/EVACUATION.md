# Evacuation and alarm information

> **Status:** the evacuation module ships in **phase 3**. This page states the safety position and the
> design that phase 0 prepares; it is extended with operating instructions, drill runbooks and limitations
> when the module exists.

## Safety statement

EVAC is a **supplementary information system**. It is **not** a certified fire alarm system, voice alarm
system or evacuation system; DIN 14675, DIN VDE 0833, EN 54 and similar standards do not apply and EVAC
does not claim compliance. It complements — and never replaces — the legally required systems and
procedures of the venue. Operators must acknowledge this once per event when enabling the module.

## What phase 0 already provides

- **Permissions with two-factor gates**: alarm permissions will be registered as *sensitive*; they only work
  in a two-factor verified session, for every user. Built-in alarm roles (admin, orga, control-room,
  security) require two-factor authentication by default.
- **Scoped permissions**: e.g. "may trigger pre-alarm in Zone North only" via a role assignment scoped to a
  zone.
- **Tamper-evident audit log** with a drill flag, so real alarms and drills are reported separately.
- **Hold-to-confirm** buttons (`data-hold`) for safety actions in the UI.
- **Realtime fan-out** with WebSocket → SSE → long-poll fallbacks.
- **Evacuation trigger registry** (`EvacTriggerSpec`) so extensions (DIAL, hardware bridge) can contribute
  trigger sources.

## Design (phase 3)

- Models: simple takeover, staged global, zones and routes (per event).
- States: normal, staff alert (pre-alarm), attention, shelter in place, evacuate, all clear; persisted
  state machine per event and zone, highest severity wins, drills, **never auto-clear**.
- Triggers: control room and mobile panic page (hold-to-confirm, optional two-person rule), hardware
  bridge, DIAL, API/MQTT, scheduled drills; policies execute / arm / notify per source, stage and zone.
- Content: guardrail linter, non-deletable built-in fallback layout (ISO 7010 + English), text rotation,
  per-screen arrows from the route graph, audio.
- Propagation: ≤ 2 s on 95 % of online LAN screens, acknowledgements per screen and zone.
- Fail-safe: evacuation bundle cached on every screen, stays in alarm when offline, signed state messages
  from a secondary node or the hardware bridge ([ADR-0003](adr/0003-alarm-delivery-redundancy.md)).
