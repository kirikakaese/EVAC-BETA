# ADR-0052: Heartbeat: health monitor, alive indicator and operator check-in

- Status: Accepted
- Date: 2026-10-12

## Context

The owner asked for a "heartbeat" module with three parts:
1. a **health monitor** that watches everything that should be alive and tells the control room when something
   goes down:
   - screens;
   - the venue node;
   - hardware bridges;
   - the DIAL link;
   - the Celery worker and beat;
   - the outbox;
2. an **alive indicator** on screens: people should see that a screen is live, and when it lost the server;
3. an optional **operator check-in**: the control room confirms "I'm here" regularly, and a missed check-in is
   escalated.

Constraints:
- **Plugins only (ADR-0001).** The core never imports optional modules, and each module knows best what "alive"
  means for its own things.
- **No external calls in a request or a check.** Deliveries go through the outbox.
- **Brief §8.** The monitor must not trigger or change any evacuation or alarm behaviour. The bridge supervision
  (ADR-0032) and the screens' offline sweep (ADR-0017) keep their own alerts.
- **Offline first.** A venue node (ADR-0036) runs the event's screens and bridges during a checkout. Central must
  not raise false alarms for things that report to the node.
- **Screens run a strict CSP.** The renderer should not change for one widget (ADR-0045).

## Decision

**Registry hook (plugin API 7).**
- `r.health_check(HealthCheckSpec(key, name, check, module=, scope=, order=, description=, while_checked_out=))`.
- `check(event | None) -> [HealthItem(key, label, status, detail, since, url)]`.
- `status` is one of:
  - `ok`;
  - `warn` (degraded, shown but never alerted);
  - `down` (alerted);
  - `unknown` (no data yet; never alerted).
- `scope` decides where a check runs: on each event, on the instance-wide view (`event=None`), or both.
- A check reads the database only. Checks of a module that is off are skipped. A check that raises shows as
  `unknown`, and the other checks still run.
- Plain dicts are accepted as items too.

**Checks.** Each owning app registers its own check in its `evac_plugin.py`:

| Check | Owner | Down when |
|---|---|---|
| `screens` | screens | a paired screen is offline (`offline_after_seconds`); stale is `warn`, never connected `unknown` |
| `nodes.event` | nodes (core) | the node holding the event has not called central for 5 min (`warn` after 1 min) |
| `nodes.instance` | nodes (core) | an enrolled node holding an event is silent for 5 min; idle nodes are `unknown`; on a node, the link to central is at worst `warn` |
| `evacuation.bridges` | evacuation | a bridge has had no heartbeat for 30 s (`OFFLINE_AFTER`); an input fault is `warn` |
| `dial` | DIAL | the last connection test failed; a failed status fetch or failed broadcasts in the last hour are `warn` |
| `extensions` | extensions | never: a failed connection test of another extension is `warn` (extensions with their own check, like DIAL, are left out) |
| `widgets.feeds` | widgets | never: a failed or old data feed is `warn` (screens keep the last data) |
| `outbox` | core | a delivery has waited 15 min without a first try (`warn` after 2 min, or with retries or dead jobs) |
| `celery` | heartbeat | the periodic task has not run for 10 min (`warn` after 90 s) |

**Status changes.**
- `HealthState` stores the confirmed status per event, check and item.
- The beat task `heartbeat-evaluate` runs every 30 s. It writes the Celery pulse, then evaluates the instance-wide
  view and every event that is not archived and has the module on.
- A change into or out of `down` is confirmed only after the observed status has stayed the same for
  `grace_seconds` (default 60). A blip that clears earlier resets the timer, so a flapping link does not alert.
- Changes between `ok`, `warn` and `unknown` are taken at once and never alert. An item seen for the first time
  while down alerts after the grace period like any other. Items that disappear are forgotten.

**Alerting.** A confirmed `down` alerts only while the event is in one of `alert_states` (default: setup and live).
It goes to:
- in-app notifications (and so Web Push) for the members of `notify_roles` (default `control-room`);
- staff alert channels in `alert_channels` through `apps.core.alerts.enqueue` (the outbox), idempotent per key;
- the audit log (`heartbeat.down`);
- the webhook event `heartbeat.down`.

The ops module's webhook sink turns the webhook event into an important line in the control room's ops log; it
only matches the event type, without an import.

The recovery is reported the same way (`heartbeat.recovered`), but only for outages that were alerted. More than
three changes of one check in one run (a power cut takes 40 screens down) become one message ("Down: 40 ×
Screens"), with one webhook event per item.

Instance-wide changes notify instance admins.

On central, while an event is checked out to a venue node, only checks marked `while_checked_out` run: the node's
sync, the outbox and Celery. The node runs the heartbeat for the event itself.

**Celery.** The task that evaluates the checks also writes the pulse, so it cannot alert about its own absence.
The page and the dashboard panel compute checks live on every request, so a dead worker shows there as `down`.
This is stated in the handbook; `/metrics` and the outbox depth stay the external signal.

**Dashboard and pages.**
- The control room gets the panel `heartbeat.health`: counts, problems and the check-in.
- `/e/<slug>/heartbeat/` shows every check with its status, details, since when, and the last contact.
- `/settings/heartbeat/` is the instance-wide view for instance admins.
- Permissions: `heartbeat.view` and `heartbeat.manage`. The built-in control-room role gets `heartbeat.*` and
  security gets `heartbeat.view` (new events only; existing roles are edited by people, as for other modules).

**Alive indicator.**
- It is a plugin widget (ADR-0045), so the renderer does not change. `WidgetSpec("heartbeat.alive",
  element="evac-heartbeat-alive", script="heartbeat/alive.js")` uses the data source `heartbeat.alive`
  (`{server_time, timezone, ttl}`, TTL 10 s).
- While the server is unreachable, the renderer hands the last payload to the element again. The element sees that
  `server_time` has not changed. It turns grey with "Offline since HH:MM" after three refresh periods without a new
  one (35 s), or at once when the browser reports offline.
- A payload restored from storage after an offline restart is dated back to its own server time.
- The clock uses the device's time in the event's time zone. With `prefers-reduced-motion` the dot does not
  pulse. The element is built once, so the pulse runs smoothly; offline is told by text, not by colour alone.

**Operator check-in.** It is off by default. Settings in the `heartbeat` namespace (instance and event):
- enabled, and only while live (default) or also during setup and teardown;
- the interval, and the grace between escalation steps;
- the roles that check in, and the escalation chain (role short names, in order);
- channels for escalations.

The steps:
- `CheckInWatch.armed_at` starts the clock when check-ins become active, so switching them on or going live never
  escalates at once.
- At the due time, the check-in roles get a reminder (step 0, in the app only).
- After each further grace period, the next role of the chain is notified (steps 1…n, in the app and on the
  configured channels).
- `CheckInEscalation(event, due_at, step)` is unique, so every step runs once even if the task runs twice.

Members of a check-in role, and people with `heartbeat.manage`, check in from the page, the dashboard panel or the
staff app card.

A check-in is a plain POST, not queued offline: it counts only when the server receives it. It ends the escalation
and tells the roles that were alerted. Every check-in, reminder and escalation is audited (`heartbeat.checkin`,
`heartbeat.checkin_reminder`, `heartbeat.checkin_escalated`). Webhook events: `heartbeat.checked_in` and
`heartbeat.checkin_missed`.

On central, check-ins for a checked-out event are refused ("check in on the venue node") and not escalated there.

## Consequences

- A module adds monitoring with one registration, and the heartbeat page, the panel and the alerts follow.
- `HealthState`, `Pulse` and the check-in rows are kept on each installation and never synced. A node watches what
  it runs.
- Duplicates are possible on purpose. The bridge supervision and the screens' sweep still write their own ops log
  lines and alerts. The heartbeat adds the role notifications, the channels and the webhook events. Staff channels
  stay empty unless configured.
- Role keys in settings are free text. The heartbeat page shows the role names it resolved, and the event's alert
  channel keys.
- Nothing here touches evacuation states, triggers or policies. The bridge check only reads what the supervision
  recorded.

## Alternatives considered

- **A heartbeat field on every spec (screens, bridges) read by a core loop:** couples the core to module models
  and breaks ADR-0001.
- **Alive indicator inside the renderer, using the player's transport state:** more precise, but it changes the
  shared renderer and both bundles for one optional widget. The data-source freshness gives the same answer within
  a few seconds.
- **Per-person check-ins:** every control-room member would be escalated separately. The brief's need is "is
  somebody at the desk", so one check-in per event per interval is enough.
- **Alerting from the web process when the page sees Celery down:** a GET with side effects, and no alert at all
  when nobody looks. External monitoring (`/metrics`, the outbox depth) is the right place.
