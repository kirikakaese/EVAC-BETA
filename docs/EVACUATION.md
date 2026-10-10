# Evacuation and alarm information

> **Status:** phase 3 in progress. The state machine, the control page (3.3), the evacuation models with
> blocked exits and screen directions (3.4) and triggers with policies (3.5) exist; triggers and
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

## Evacuation models (roadmap 3.4, [ADR-0030](adr/0030-evacuation-models-and-screen-directions.md))

| Model | What can be raised | Screens |
|---|---|---|
| Simple takeover | only *evacuate*, whole event | evacuation layout until the all clear |
| Staged, global (default) | every enabled stage, whole event | the stage's layout; optional fixed direction per screen |
| Zones and routes | every enabled stage, per event and per zone | arrow and text to the nearest open assembly point or exit |

- The model limits what can be raised or changed, never what can be ended: an alarm that is active when the model
  changes stays visible and can be cleared.
- **Blocked exits** (zones model): *Block* an exit, assembly point, door or stair on the control page (hold to
  confirm). Routes avoid it at once; *Open again* restores it. Both are audit-logged and sent as
  `evacuation.routes_changed`.
- **Directions**: each screen starts at the nearest point of the route graph on its floor. Place a waypoint near
  every screen; the plan knows no walls. The arrow is drawn for the people reading the screen. Without a route,
  a place on the map or a connection to an exit, a screen says **"Follow staff instructions"**.
- **Fixed direction**: an arrow and a text per screen (e.g. ← "Exit B") override the computed route in every
  model.

## Triggers and policies (roadmap 3.5, [ADR-0031](adr/0031-evacuation-triggers-and-policies.md))

| Source | Default | Notes |
|---|---|---|
| Control room page | execute | hold-to-confirm |
| Panic page (staff app) | execute | hold-to-confirm, big buttons, zone choice |
| API / external systems | arm | service token with `evacuation:write`, created with two factors; idempotency `key` |
| Hardware bridge | arm | ADR-0003, ADR-0032 |
| Scheduled drills | execute | always drills; not during a real alarm; not more than 15 minutes late |

- **Execute** switches at once. **Arm** shows the alarm on the control page ("Waiting for a decision") and alerts
  everyone who may confirm (bell and push). If nobody confirms or rejects it within **120 s** it executes by itself
  (auto-escalation; per rule, can be switched off). **Notify** only alerts the control room.
- Rules per source, stage and zone (*Triggers & drills*); the most specific wins.
- **Two-person rule** (Settings → Evacuation, per stage): a person's change into that stage waits until someone
  else with the permission confirms. After the set time (default 60 s) it expires, nothing changes and the
  control room is alerted.
- Policies never end alarms. Only people end alarms, from the control or panic page, with the all clear.

## Hardware bridge (roadmap 3.6, [ADR-0032](adr/0032-hardware-bridge.md))

- A *Hardware bridge* (page *Triggers & drills → Hardware bridges*) has its own token (`evacb_…`) and a list of
  inputs: `key; label; stage; zone`. It reports over HTTPS (`/bridge/v1/heartbeat`, `/bridge/v1/input`) or MQTT
  (optional extension, [docs](extensions/mqtt.md)).
- An input becoming active raises its stage through the *Hardware bridge* source (arm by default). A contact
  returning to rest only tells the control room; wiring faults and a bridge silent for 30 s raise alerts,
  never public alarms.
- Reference software: `bridge/` (Raspberry Pi with a persistent retry queue; ESP32 sketch).

## Screen content (roadmap 3.7, [ADR-0033](adr/0033-evacuation-content.md))

- *Screen content*: per stage a layout or the built-in one, rotating texts, signs-only frame, sound, spoken
  message. Layouts used for evacuation must pass the guardrails (signs, text, direction, contrast, letter
  height for the viewing distance in Settings → Evacuation).
- Shelter, evacuate and all clear take over participating screens; attention is a banner. Per screen the
  display setting *Evacuation role* chooses participant, info (banner only) or excluded.

## Screens reached and staff answers (roadmap 3.8, [ADR-0035](adr/0035-evacuation-acknowledgements.md))

- Every screen confirms each message it renders. The control page shows **"X of Y screens confirmed"**, offline
  and waiting screens per zone, and the time from trigger to screen (p95; target ≤ 2 s on the venue LAN).
  Offline screens keep showing the last state they had and their cached evacuation bundle (3.9).
- During an alarm staff answer from the staff app or the panic page: *I'm on it*, *Zone clear*, *Need help*.
  The answers appear on the control page; *Need help* also alerts the control room.

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
