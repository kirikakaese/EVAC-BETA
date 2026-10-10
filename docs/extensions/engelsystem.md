# Engelsystem

The **Engelsystem** extension imports angel types, shifts and who signed up from an
[Engelsystem](https://engelsystem.de) into the **Crew** module (ADR-0041). Check-ins, no-shows and people added in
EVAC stay on every sync.

| Engelsystem | EVAC |
|---|---|
| angel type | team (adopted by name when a team of that name already exists) |
| shift × angel type it needs | shift of that team, with `needs` as people needed |
| location | where (linked to the venue room with the same name) |
| shift entry (an angel) | crew member and sign-up |

## Setting it up

1. Switch the **Crew** module on for the event (Settings → Modules).
2. In Engelsystem, create an API key (*Settings → API*). The account needs to see the shifts of the angel types
   you import.
3. Settings → Extensions → *Engelsystem*:
   - **Engelsystem URL**, e.g. `https://engel.example.org` (EVAC adds `/api/v0-beta`);
   - **API key** (stored encrypted, never shown again);
   - **Only these angel types** (optional): names or ids, one per line; empty imports all;
   - **Sync every (minutes)**: 15 by default, 0 only on *Sync now*;
   - tick *Enabled* and *Sync shifts*, then save.
4. **Test connection** reads `/info`, the angel types and their shifts and reports how many it found. It imports
   nothing.
5. **Sync now** (on the extension page or on the shift board) imports. The extension log shows the result, e.g.
   "12 new and 3 changed shifts, 1 removed, 40 new sign-ups, 2 new teams, 0 kept (local check-ins)".

## How conflicts are handled

- **Shifts** follow Engelsystem: title, times, location, description and the number of people needed are updated
  on every sync.
- **Sign-ups from Engelsystem** are added; when an angel leaves the shift upstream, the sign-up is removed, unless
  the angel already checked in or was marked no-show in EVAC.
- **People added in EVAC** (by a team lead, by scanning the shift's QR code, or in the staff app) are never removed
  by a sync.
- **A shift removed upstream** is deleted, unless someone checked in or was added in EVAC. Then it stays and the log
  counts it as *kept*.
- **Disconnect & purge data** deletes the imported shifts, the imported people without an EVAC account and the
  imported teams that have no shifts left.

Engelsystem accounts are not EVAC accounts: imported angels are crew members with a name only. To check in with
their own phone, an angel logs in to EVAC (e.g. through OIDC) and scans the shift's QR code; EVAC then knows them
as a walk-in on that shift.
