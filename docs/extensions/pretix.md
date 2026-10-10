# pretix

The **pretix** extension brings tickets from [pretix](https://pretix.eu) into the **Access** module (ADR-0044):
ticket types, attendees and check-ins. The QR code on a pretix ticket works at EVAC's scanners, because the
ticket's secret becomes the attendee's code.

| pretix | EVAC |
|---|---|
| product with *admission* | ticket type (adopted by name when one of that name exists) |
| order position of such a product | attendee (name, e-mail, organisation, code = the ticket secret) |
| paid order | valid ticket |
| cancelled / expired order, cancelled position | cancelled ticket |
| pending order | cancelled, or valid when *Pending (unpaid) orders are valid* is on |
| check-in with pretix's scanners | checked in |

## Setting it up

1. Switch the **Access** module on for the event (Settings → Modules).
2. In pretix, create an API token: *Organizer → Teams → a team with access to the event → API tokens*. The team
   needs *Can view orders* and, to send check-ins back, *Can change orders* / *Can perform check-ins*.
3. Settings → Extensions → *pretix*:
   - **pretix URL**, e.g. `https://pretix.eu`;
   - **organizer** and **event** short names (as in the pretix URL `/control/event/<organizer>/<event>/`);
   - **API token** (stored encrypted, never shown again);
   - **Check-in list id**: where EVAC's check-ins are sent (*Test connection* lists the check-in lists);
   - **Sync every (minutes)**: 10 by default, 0 only on *Sync now*;
   - tick *Enabled*, *Sync attendees* and, if wanted, *Send check-ins to pretix*; save.
4. **Test connection** reads the event, its products and check-in lists. It imports nothing.
5. **Sync now** (on the extension page or on the attendee page) imports. The extension log shows the result, e.g.
   "120 new and 3 changed attendees, 1 cancelled, 12 check-ins from pretix, 2 new ticket types".

## How conflicts are handled

- Ticket types keep the zones, colours and badge layouts set in EVAC.
- Attendees follow pretix (name, e-mail, ticket type, status). An attendee gone from pretix is **cancelled, not
  deleted**, so their scans stay.
- A check-in at EVAC's gates of a pretix attendee is sent to pretix (once; retried by the outbox while pretix is
  unreachable). Check-ins taken over from pretix are not sent back.
- **Disconnect & purge data** deletes the imported attendees and the imported ticket types nobody uses.
