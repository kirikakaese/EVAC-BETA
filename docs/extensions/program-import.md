# Program import: pretalx, frab / Pentabarf, iCal

Three event extensions bring an existing program into the **Program** module (ADR-0038). They share one importer.
Local changes made in EVAC (delays, room changes, cancellations, edits) are kept on every sync.

| Extension | Settings | Reads |
|---|---|---|
| **pretalx** | pretalx URL (e.g. `https://pretalx.com`), event slug, optional API token (encrypted) | `<url>/<event>/schedule/export/schedule.json`; with a token also schedules that are not public yet |
| **frab / Pentabarf** | `schedule.xml` URL | frab/Pentabarf/pretalx `schedule.xml`, or a frab `schedule.json` |
| **iCal** | `.ics` URL | `VEVENT`s: `SUMMARY` title, `LOCATION` stage, `CATEGORIES` track, `DESCRIPTION`, `URL`, `STATUS:CANCELLED` |

All three have **Sync every (minutes)**: 15 by default, 0 means only on *Sync now*.

## Setting one up

1. Switch the **Program** module on for the event (Settings → Modules).
2. Settings → Extensions → *pretalx*, *frab / Pentabarf* or *iCal*: enter the URL, tick *Enabled* and
   *Sync the program*, then save.
3. **Test connection** downloads and parses the source and reports the number of sessions and stages. It imports
   nothing.
4. **Sync now** (on the extension page or on the Program page) imports. The extension log shows the result, e.g.
   "12 new, 3 updated, 40 unchanged, 1 gone from the source, 2 local changes kept".

Stages are matched by name. A new stage is linked to the venue room with the same name, so screens in that room
show it in *now and next*.

## How conflicts are handled

- **Imported fields**: title, subtitle, abstract, language, type, URL, stage, track, times, speakers and the
  cancelled status. They follow the source until they are changed in EVAC.
- **Changed in EVAC → kept.** An edit in the session form or a live change (delay, move, cancel) records the field
  as a *local change*. The next sync leaves it alone. The Program page shows "imported · 2 local changes".
- **Follow the source again** (Program page → *Change*) forgets the local changes. The next sync writes the
  source's values.
- **Back to plan** undoes the live changes (time, stage, cancellation), so the source decides again.
- **Removed upstream**: the session is deleted, unless it was changed in EVAC. Then it stays, marked *gone from the
  source*.
- **Cancelled upstream**: frab titles starting with `CANCELLED:` and iCal `STATUS:CANCELLED` become cancelled
  sessions.

## Network

EVAC only fetches public addresses. For a pretalx or calendar server on the venue network, set
`EVAC_IMPORT_ALLOW_PRIVATE=1` in the server environment. Responses are limited to 20 MB.

## Disconnect & purge

This removes the extension's settings and the sessions it created. Sessions created by hand and other sources stay.
