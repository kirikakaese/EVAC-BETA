# ADR-0042: Inventory with QR labels, lend and return

- Status: Accepted
- Date: 2026-10-10

## Context

Brief §11.6 asks for resources and inventory: radios, keys, vehicles, tools, laptops; asset tags and QR labels;
lend and return with a signature or photo; who has what; due-back reminders; maintenance notes; places on the
venue map. The Phase 7 gate: lend/return with QR.

Constraints: plugin (`apps/inventory`, module `inventory`), offline first (the counter at the radio desk may
lose network), no JS framework on staff pages (strict CSP, `evac.js` only).

## Decision

**Model.** `Category` (with a usual loan time), `Item` (asset tag unique per event, serial, status available /
lent / maintenance / missing / retired, room and place, photo, map position), `Loan` (borrower name and
optionally an account, contact, lent/due/returned times, who lent and took back, signature, photos out and back,
condition), `Note` (note, maintenance, damage, status change).

**Asset tags.** Empty tags get the next number with the event's prefix (`EV-0001`); *How many* creates identical
items with consecutive tags in one go and opens their label sheet.

**QR labels.** The label holds `/e/<slug>/inventory/t/<asset tag>/`, the item's page. The phone camera is the
scanner: no app and no scanning library. The label sheet is a print page (3 columns on A4, tag, name, event).

**Lend and return.** One form on the item page: who (a name or an account), contact, due back (pre-filled from
the category), an optional photo (`capture=environment` opens the camera) and a signature. The signature pad is a
`<canvas data-signature>` handled by `evac.js` (pointer events, works with a finger); it writes a PNG data URL
into a hidden field. The server accepts only a real PNG up to 300 KB. A setting can make the signature required.
Lending locks the item row, so two desks cannot lend the same radio. Taking back records the condition; damaged
or incomplete items go to maintenance with a note. A replayed "take back" from the offline queue does nothing.

**Reminders.** The beat task `inventory-remind-overdue` (every 5 minutes) reminds the borrower (with an account)
and the lender once per loan, emits `inventory.overdue` to webhooks and the ops log.

**Elsewhere.** "Who has what" at the top of the inventory page, a control room panel (lent out, overdue), a staff
app card (what I have), a map layer (items placed on floor plans, ADR-0027), webhooks `inventory.lent`,
`inventory.returned`, read-only API (`inventory-items`, `loans`). Venue nodes keep items and loans as live data
(ADR-0036), with their photos and signatures.

## Consequences

- The gate is tested by `frontend/e2e/phase7.mjs`: the radio's QR URL opens its page on a phone, a signature is
  drawn on the pad, the radio is lent and taken back.
- Signatures are images, not cryptographic signatures; they document a hand-over, nothing more.
- Barcode scanners that type the tag work too: the search box finds items by tag.
