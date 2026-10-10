# Evacuation and alarm information

> **Status:** phase 3 in progress. The state machine and the control page exist (3.3); triggers and
> policies, screen content, propagation, fail-safe and the drill runbook follow (see the roadmap).

## Safety statement

EVAC is a **supplementary information system**. It is **not** a certified fire alarm system, voice alarm
system or evacuation system; DIN 14675, DIN VDE 0833, EN 54 and similar standards do not apply and EVAC
does not claim compliance. It complements — and never replaces — the legally required systems and
procedures of the venue. Operators must acknowledge this once per event when enabling the module.

## States and rules (roadmap 3.3, [ADR-0029](adr/0029-evacuation-state-machine.md))

| State | Severity | Meaning |
|---|---|---|
| Normal | 0 | regular content |
| All clear | 1 | "all clear" for the configured time (default 5 minutes), then normal |
| Staff alert | 2 | silent pre-alarm: staff channels only |
| Attention | 3 | public "please pay attention to announcements" |
| Shelter in place | 4 | stay inside / severe weather |
| Evacuate | 5 | full evacuation with routes |

- The event has a state and every zone can have its own. A screen in a zone shows the **more severe** of the
  two (real before drill).
- **Never auto-clear**: nothing returns to normal by timeout, reconnect or restart. Only the **all clear**, given
  by someone with `evacuation.clear` (or `evacuation.drill` for a drill), ends an alarm. The all-clear time is
  stored, so a restart neither shortens nor extends it. *Back to normal now* ends it early.
- Alarms can be raised, escalated and **stepped down directly** (evacuate → shelter in place), always with
  hold-to-confirm and recorded.
- An all clear for the whole event also clears the zones that have their own alarm; the form lists them, all
  ticked, and an unticked zone keeps its alarm.
- **Drills** run in any alarm state with a marker (Settings → Evacuation → *Drill marker*, default "DRILL"). A
  real alarm anywhere in the event ends every drill at once; a drill cannot start while a real alarm is
  active; drills are never shown instead of a real alarm. History and audit log keep drills apart.
- Staff alert, attention and shelter in place can be switched off per event; every state can be renamed.
  Evacuate, all clear and normal cannot be switched off.
- Permissions: `evacuation.view`, `evacuation.trigger`, `evacuation.clear`, `evacuation.drill` (all three
  sensitive: two-factor session; scope them to a venue or zone), `evacuation.manage`. The built-in
  *security* role raises alarms but cannot clear them.

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
