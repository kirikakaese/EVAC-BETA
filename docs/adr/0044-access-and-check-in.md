# ADR-0044: Access: attendees, badges, offline check-in, access zones and pretix

- Status: Accepted
- Date: 2026-10-11

## Context

Brief §11.5 asks for:
- a pretix extension (attendee and check-in sync), or EVAC's own lightweight attendee lists;
- ticket types and wristbands or badges, with print templates made in the layout editor;
- a check-in app (QR, offline);
- access zones (backstage, crew-only) with scanner rules and an occupancy feed.

The Phase 8 gate: offline check-in syncs; access zone counts feed occupancy.

Constraints:
- Plugins only (`apps/access`, module `access`; `extensions/pretix`).
- Offline first: the gates of a festival lose the network.
- No heavy dependency: no JS QR-decoding library, no app store app.
- Attendee data is personal data (brief §13).

## Decision

**Model.**
- `TicketType`: colour, the zones it grants, a badge layout.
- `AccessZone`:
  - *every valid ticket*, or only the granting ticket types;
  - *checks in*: the first scan in is the check-in;
  - *re-entry allowed*;
  - a room, and an optional occupancy area.
- `Attendee`: name, e-mail, organisation, ticket type, code unique per event, status valid / cancelled / blocked, check-in time.
- `Presence`: inside a zone or not.
- `Scan`: zone, direction, result, the device's time, offline flag, device label, client id.
- Pretix tickets use pretix's own secret as the code, so the QR code on the pretix ticket works at EVAC's gates.

**One rule** (`services.decide`), in this order:
1. unknown code → *unknown*;
2. cancelled or blocked → *invalid*;
3. a zone the ticket type does not grant → *denied*;
4. into a zone without re-entry while already inside → *duplicate*;
5. otherwise *OK*.

An accepted scan updates the presence. A scan into a check-in zone checks the attendee in (webhook `access.checked_in`); refusals emit `access.refused`.

**Offline check-in app.** The scanner page `/e/<event>/access/scan/<zone>/[?dir=out]` is plain JS (`static/js/scanner.js`), cached by the staff service worker.

- **Ticket list.** The page fetches the zone's list:
  - per ticket only the first 20 hex digits of the code's SHA-256, the name, the ticket type, valid or not, and inside or not;
  - which ticket types the zone admits, and whether it allows re-entry.

  The list is kept in localStorage and refreshed every `list_refresh_seconds`.
- **Scanning.** A scan is decided on the device at once with the same rule, using the device's own idea of who is inside. It is queued with a UUID and the device time, and sent in batches to `/e/<event>/access/scan/sync/`.
- **The server's answer wins.**
  - It applies the rule again in arrival order and returns each result.
  - A replayed id returns the stored scan; nothing happens twice.
  - Where the server disagrees (a ticket let in at another gate while this one was offline), the device's log shows "Server: … Already inside".
- **Input.**
  - A hardware scanner typing into the field.
  - The keyboard.
  - The camera where the browser has `BarcodeDetector` (Chrome on Android). No JS decoding library is needed.

**Occupancy feed.**
- When a zone names an occupancy area, every accepted scan that changes the presence counts ±1 there (`crowd.services.count`, source *scanner*, client id `scan:<id>`).
- A re-entry while inside, a duplicate or a refusal counts nothing.
- This is the hook ADR-0040 left for phase 8.
- The access module calls the occupancy service only when that module is installed and on.

**Badges with the layout editor.**
- *Create a badge layout* makes an ordinary layout with an A6 canvas, a white page, a colour band, `{{ attendee.name }}`, `{{ attendee.company }}`, a QR element with `{{ attendee.code }}` and `{{ ticket.name }}`. It is never the event's default screen layout.
- The badge print page feeds the layout and one set of variables per attendee to the preview island. The new `[data-preview-pages]` mode renders a print sheet with the shared renderer, so badges look exactly like the editor shows them.
- Without a layout, a built-in HTML badge is printed. *Mark as printed* records `badge_printed_at`, so *Print new badges* prints only the rest.

**Permissions and scope.**
- `access.view`, `access.scan` and `access.manage`.
- `access.scan` can be scoped to a zone (scope kind `access_zone`): gate staff for the backstage door scan only there.
- The built-in *Control room*, *Security* and *Helpdesk* roles get `access.view` and `access.scan`.

**pretix** (`extensions/pretix`, API token):
- **What it imports.**
  - Admission products → ticket types (adopted by name).
  - Order positions → attendees: paid → valid; cancelled or expired → cancelled; pending → valid only when set.
  - A position gone from pretix is cancelled, never deleted.
- **Check-ins both ways.**
  - Check-ins from pretix's own scanners are taken over.
  - EVAC's check-ins go back to a pretix check-in list through the outbox (`pretix.checkin`, `checkinrpc/redeem`).
  - Taken-over check-ins are not sent back.
- **When it runs.** The sync runs periodically or on *Sync now* (also on the attendee page).

**Elsewhere.**
- Attendee CSV import and formula-safe export.
- A control room panel (checked in, inside per zone, refusals) and a staff app card (gates I may scan).
- A data source `access.zones`.
- A REST API: `attendees` (create, edit), `ticket-types`, `access-zones` with `POST …/scan/` for hardware scanners and turnstiles.
- Venue nodes keep attendees, presence and scans as live data (ADR-0036), so the gates work on site without central.

## Consequences

- The gate is tested by `frontend/e2e/phase8.mjs`:
  - two gate phones, one offline;
  - valid, cancelled and unknown tickets are decided offline;
  - the 5 queued scans arrive with their offline flag and device time;
  - the ticket used at both gates is flagged as a duplicate after the sync;
  - "Festival site" counts each guest exactly once (+4), and an exit counts down.
- An offline gate can let a ticket in twice; the server records the second as a duplicate and the gate learns it after the sync. Strict single entry across gates needs the gates online (or one gate per ticket type).
- The offline list holds names of attendees on staff devices. It is limited to devices of people with `access.scan`, holds no e-mail addresses and no codes, and is replaced on every refresh.
