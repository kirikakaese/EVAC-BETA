# ADR-0039: Incidents, ops log, escalation and the control room dashboard

- Status: Accepted
- Date: 2026-10-10

## Context

Phase 6 (brief §11.3) adds the control room's working tools:
- an incident log (category, severity, place, assignment, status, timeline, attachments, links);
- a radio-style ops log;
- tasks;
- escalation of incidents to notification channels;
- a report after the event;
- one large-screen page that shows alarms, open incidents, screen health, occupancy, DIAL/DECT status and recent
  announcements.

Constraints:
- **Plugins only.** Operations is an optional module (`apps/ops`, module key `ops`). The dashboard shows what
  other modules contribute, and the core never imports `ops`.
- **On site and offline.** Incidents and the ops log must work during a venue node checkout (ADR-0002 lists
  incidents as node data). Staff report from the staff app, also without network.
- **No external calls in requests.** Escalation messages go through the outbox.
- The built-in roles already reserve `ops.*` for the control room and security.

## Decision

**Incidents.**
- Each event numbers its incidents (#1, #2, …) on its own. On a numbering collision, the next number is retried.
- Everything that happens to an incident is an `IncidentUpdate` row in its timeline: created, note, status,
  assigned, severity, edited, escalated, link, attachment.
- Attachments are photos, PDF, text or audio, up to 10 MB. They are served only to `ops.view`, with `nosniff`
  and a restrictive CSP. They travel to a venue node with the incident (`SyncModel.files`).
- Status follows a small transition table: new → acknowledged → in progress → resolved → closed. A resolved or
  closed incident can be reopened.
- Whoever may report may also acknowledge ("I'm on it"). Everything else needs `ops.manage`.
- Incidents carry a scope chain (zone, room), so roles scoped to a zone handle that zone's incidents.
- Links to other modules are plain `{kind, id, label, url}` entries. This keeps `ops` free of imports from other
  modules.

**Ops log.**
- `LogEntry` is either a person's message ("Security 2 → Control: …") or a system line.
- System lines come from a webhook sink: `r.webhook_sink(services.sink)` turns the events other modules already
  emit into one line each:
  - alarms and staff answers;
  - offline screens;
  - DECT alerts;
  - announcements and overrides;
  - occupancy changes;
  - program cancellations and moves.
- A setting switches system lines off.
- Entries from the staff app carry a client id: a replay from the offline queue is ignored. They keep the time
  they were written, up to a day back and never in the future.

**Offline queue ids.** The staff app's offline queue (ADR-0021) had no idempotency. Forms that need it now carry
`<input data-client-id>` and `<input data-written-at>`. `evac.js` fills both on every submission, and the server
ignores a second submission with the same id. Incident reports and ops log entries use this.

**Escalation.**
- `EscalationRule` has these settings:
  - a minimum severity and optional categories;
  - `after_minutes`: 0 means at once;
  - `until`: "not acknowledged" or "not resolved";
  - roles to notify;
  - channels to send to.
- Each rule fires once per incident. A unique `Escalation(incident, rule)` row guards this. Rules are checked
  after an incident is created, when its severity changes, and every minute by the beat task `ops-escalate-due`.
- Role members get an in-app notification, which becomes a Web Push on their phones.

**Staff alerts through channels (plugin API 3).**
- `NotificationChannelSpec` gains an optional `alert(event, Alert)`: a plain staff message (title, body, level,
  URL, key), next to the announcement `send(delivery)`.
- These channels implement it:
  - ntfy, Matrix, Telegram and e-mail (fixed recipients only);
  - DIAL's DECT message.
- Mastodon and the public feed do not, because they are public.
- `apps.core.alerts` lists an event's alert-capable channels and queues alerts in the outbox (`core.alert`),
  idempotent per key. Matrix uses the key for its transaction id, and DIAL as the broadcast reference.
- Occupancy (ADR-0040) uses the same path.

**Control room dashboard.**
- A new contribution type, `r.dashboard_panel(DashboardPanelSpec(key, title, template, context, module, order,
  size, refresh_seconds))`. `context(request, event)` returns None to hide a panel for the user, and panels of
  modules that are switched off are left out.
- The page `/e/<slug>/ops/control/` renders the panels in a dense grid. Each panel refreshes itself through htmx
  (`hx-get` every few seconds), with no inline script and a strict CSP. A "full screen" button puts the grid on
  the wall.
- Panels:
  - **evacuation:** state and zones in alarm, every 3 s;
  - **ops:** open incidents, a zone map, the ops log, tasks;
  - **crowd:** occupancy;
  - **screens:** health;
  - **announcements:** on air and pending;
  - **DIAL:** DECT base stations and alerts.
- The map is a server-side SVG of the zone outlines (ADR-0026). Zones with open incidents are coloured, and every
  state also carries a glyph and a text.

**Report.** `/e/<slug>/ops/report/` gives a CSV with one row per incident: times to acknowledge and resolve. It
escapes cells that would start a spreadsheet formula. The JSON version includes the ops log. Every export is
audited.

**API.**
- `…/incidents/` supports list, create and patch, plus `status` and `note` actions.
- `…/ops-log/` supports list and create (with `client_id`).
- Token scope is `ops`. Webhook events are `incident.created`, `incident.updated` and `incident.escalated`.

## Consequences

- A module adds itself to the control room with one registration. Phase 7 (crew) and phase 8 (access) will add
  their panels the same way.
- An escalation needs at least one rule. Without one, incidents notify nobody automatically, and the rules page
  says so.
- A rule is not re-armed when an incident is reopened. Each rule fires once per incident by design.
- Map pins inside a zone and incident layers in the map editor are left for later. The zone colouring covers the
  control room's need to see where things happen.
