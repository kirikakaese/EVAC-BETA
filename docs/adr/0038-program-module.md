# ADR-0038: Program module and program imports

- Status: Accepted
- Date: 2026-10-10

## Context

Phase 5 (brief §11.1) adds the event program: stages, sessions, speakers and tracks; live changes (delays,
cancellations, room changes) that reach screens at once; a public page with exports; imports from the tools
conferences already use (pretalx, frab/Pentabarf, iCal). The gate: an imported schedule shows now/next on screens
and a live change reaches them in under 5 s.

Constraints:
- **Plugins only.** The program is an optional module (`apps/schedule`, module key `program`). The importers are
  extensions (`extensions/program_import`). Nothing in the core imports either.
- **Offline first.** A screen must keep showing the right session when the server is unreachable, so it must be able
  to move on to the next session by itself.
- **Local changes win.** Orga delays or moves a session on site. The next sync from pretalx must not undo that.
- **Venue node.** Live changes on site must work while the event is checked out to a venue node (ADR-0036).

## Decision

**Data model.** `Stage` (optionally linked to a venue `Room`), `Track` (name, colour), `Speaker`, `Session` and
`SessionChange` (one row per live change, the text screens show). A session keeps its plan in `planned_start`,
`planned_end` and `planned_stage` the first time it is changed live. `delay_minutes`, `moved` and `changed` are
derived from them, and *Back to plan* restores them. The module key is `program` because `schedules` already names
the playlist schedule rules (ADR-0016). The app label stays `schedule`.

**Live changes** go through `services.delay/cancel/move/reschedule/restore`. Each one writes a `SessionChange`, an
audit entry `program.<kind>` and, after the commit:
- sends `schedule.changed` to every paired screen of the event (they refetch `/player/api/schedule/`);
- emits the webhook and realtime event `program.session_changed`;
- sends `anchor_moved`, so announcements timed relative to the session follow it (ADR-0025, roadmap 2.3).

They refuse while the event is checked out (`apps.nodes.guard`). On the node, sessions and changes are live models
of the sync spec.

**Screens compute now/next themselves.** `/player/api/schedule/` returns the public sessions from 12 h ago to 48 h
ahead, the stages with their rooms, recent changes and the screen's room. The player keeps the answer in
`localStorage`. The `program` layout element (views *now and next*, *the day*, *live changes*) works out "now" from
the synchronised screen clock every 15 s. The server is only needed for changes. With no stage chosen, an element
shows the stage in the screen's room, else all stages. The editor gets the same data inline (`editor_choices`), so
the preview shows the real program. So does the playlist preview.

**Imports keep local changes.** An importer produces `Imported` items. `services.merge(event, source, items)`:
- matches sessions by `(source, external_id)`. The source is `<extension>:<config id>`, so two pretalx instances
  never collide;
- for every imported field, keeps the local value when the field is listed in `Session.overrides`. Edit-form
  changes and live changes record their fields there. A pending live time or stage change is kept too;
- deletes a session that disappeared upstream, unless it was changed locally. That session stays, flagged *gone
  from the source*;
- reuses stages by name and links new stages to the venue room with the same name.

*Follow the source again* clears the overrides. *Back to plan* drops the time, stage and status overrides, so the
next sync may move or cancel the session again.

**Three extensions, one importer.** `pretalx` (instance URL + event slug, optional API token; it reads the
frab-compatible `schedule.json`), `frab` (`schedule.xml` from frab, Pentabarf or pretalx, or `schedule.json`) and
`ical` (an `.ics` feed: `LOCATION` is the stage; all-day events and recurring masters are skipped, overridden
occurrences are kept). Each one:
- has *Test connection* (fetch and parse, import nothing);
- has *Sync now* (an outbox job, deduplicated per 30 s);
- has a periodic interval checked by the beat task `program-import-sync-due` (0 = manual only);
- has a feature switch "Sync the program";
- with *Disconnect & purge*, removes only the sessions it created.

Fetching uses `safefetch`: public addresses only, unless `EVAC_IMPORT_ALLOW_PRIVATE` is set (an on-site pretalx).

**Public page and exports.** `/public/<slug>/program/` is off by default (setting *Public program page*). It
offers `program.ics` (cancelled sessions as `STATUS:CANCELLED`), `program.json` and a frab `schedule.xml` (days run
06:00–06:00 local time). Non-public sessions never leave the portal.

**API.** `GET /api/v1/events/<slug>/sessions/` (`?day=`) and `POST …/<id>/live/` (`delay`, `cancel`, `move`,
`restore`), permissions `program.view` and `program.live`, token scope `program`.

## Consequences

- A screen keeps showing the right session offline for 48 h. A change made while it is offline appears when it
  reconnects (on the next `schedule.changed` or the 5-minute refresh).
- Speakers are matched by external id, then by name. Two different people with the same name in one event become
  one speaker. This is acceptable for display.
- Room changes made in pretalx after a local move are kept local until *Back to plan* or *Follow the source again*.
- The gate is checked by `frontend/e2e/phase5.mjs` (part of `make e2e`): import from a frab server, now/next on a
  screen in the stage's room, delay → screen in about 0.2–0.3 s.
