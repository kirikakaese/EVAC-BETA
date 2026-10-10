# ADR-0031: Evacuation triggers, policies and the two-person rule

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.5 and brief §8.3: triggers from the web control room, a mobile panic page, the hardware bridge, DIAL,
an API (and MQTT), and scheduled drills, each with a policy *execute*, *arm* (the control room confirms, optional
auto-escalation) or *notify only*, per source, stage and zone, plus an optional two-person rule per stage.
ADR-0003 already set the hardware bridge default to *arm* with auto-escalation. The project owner decided the open
points on 2026-10-10:

1. Two-person rule: when nobody confirms in time, the request **expires**, nothing changes and the control room
   is alerted. The second person is never the requester. Default 60 s.
2. Auto-escalation of armed alarms is **on by default after 120 s** (fail towards alarm: an unattended control
   room must not swallow a real alarm); configurable per rule, can be switched off.
3. Defaults: control room page and panic page **execute** (a person already held to confirm); API **arm**;
   hardware bridge **arm**; scheduled drills **execute** (always as drills); extension sources **arm**.
4. MQTT is **not** part of 3.5: the HTTPS API ships now; MQTT follows as an optional transport with the
   hardware bridge (3.6), connecting to a broker the operator runs. No broker is bundled.

## Decision

- **Pure policy core** `apps/evacuation/policy.py` (mypy strict): `resolve(rules, source, stage, zone)`
  chooses the most specific rule (source + stage + zone > source + stage > source + zone > source > default).
  Equally specific rules resolve deterministically to the firmer action (execute > arm > notify) and, for arm,
  the shorter escalation. `due()` and `deadline()` give the timing of requests. A second-person request
  never executes by itself.
- **`triggers.trigger()`** is the single entry for every source. It runs these steps in order:
  1. Idempotency key (a repeated delivery returns the first result).
  2. Only person sources (`web`, `panic`) may end alarms.
  3. Permissions.
  4. A read-only check of the state machine (`services.check`), so an impossible change is refused for every
     source and never armed.
  5. The two-person rule, for person sources and the configured stages.
  6. The policy: execute (`services.change`), arm (an `EvacRequest` with a deadline, the control room alerted)
     or notify (an `EvacRequest` recorded as notified, the control room alerted).
- **Requests** (`EvacRequest`, kinds `arm` and `second`): confirm (hold-to-confirm, permission for the stage and
  scope; for `second` not the requester), reject (or withdraw your own), escalate, expire. A request that can no
  longer apply when decided (e.g. the state was set meanwhile) becomes *superseded*. Everything is audit-logged
  (`evacuation.armed`, `.notified`, `.second_requested`, `.request_confirmed`, `.request_rejected`,
  `.request_escalated`, `.request_expired`).
- **Timing**: Celery beat runs `process_due` every 5 s; the control and panic pages also run it on load. Deadlines
  are stored, so a restart neither loses nor shortens them.
- **Notifications**: in-app plus Web Push to everyone who could confirm (`evacuation.trigger` in the request's
  scope, with two factors where their role needs them).
- **Scheduled drills** (`ScheduledDrill`): start by themselves through the `schedule` source, always as drills.
  They are not started while a real alarm is active, nor more than 15 minutes late (server down). Like every
  drill they end with the all clear given by a person.
- **Panic page** `/e/<event>/evacuation/panic/`: a mobile page linked from the staff app card. It has one large
  hold-to-confirm button per enabled stage, a zone choice in the zones model, a drill box and the requests waiting
  for a decision.
- **API**: `GET /api/v1/events/<slug>/evacuation/` (state, zones, pending requests, blocked points) and
  `POST .../evacuation/trigger/` (`state`, `zone`, `drill`, `reason`, `key`, `source` = `api` | `bridge` |
  extension). Tokens need the `evacuation:write` scope, must be created in a two-factor session (the alarm
  permissions are sensitive) and act with their owner's permissions. The API cannot end alarms.
- **Triggers & drills page** (`evacuation.manage`): built-in defaults, rules, scheduled drills. The two-person
  states and time live in Settings → Evacuation.

## Consequences

- DIAL (phase 4) and the hardware bridge (3.6) register trigger sources and call `triggers.trigger()`; MQTT
  becomes a transport for the same call.
- Policies never apply to ending alarms, so "never auto-clear" (ADR-0029) holds for every source.
- The control page does not refresh by itself yet; live updates arrive with propagation (3.8). Notifications
  (bell and Web Push) carry the alert meanwhile.
