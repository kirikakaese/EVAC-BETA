# ADR-0043: Helpdesk: lost & found, requests and FAQ

- Status: Accepted
- Date: 2026-10-10

## Context

Brief §11.7 asks for lost & found (with matching), requests from visitors and crew, and an FAQ for the public and
for screens. Visitors have no accounts; their contact details are personal data (brief §13).

## Decision

**Plugin** `apps/helpdesk`, module `helpdesk`, permissions `helpdesk.view`, `helpdesk.manage`, `helpdesk.faq`
(the built-in *Helpdesk* role has `helpdesk.*`).

**Lost & found in one model.** `LostFound.kind` is lost or found, so matching is one query. Each has a reference
(`L-0001`, `F-0001`), what, category, colour, details, where and when, a photo, where it is kept, the owner's or
finder's name and contact, status (open, matched, returned, closed) and a link to its match.

**Matching suggestions** (`services.score`): same category (+3), shared colour word (+2), shared words of what,
details and colour (+1 each, at most 4), same room (+1), found long before it was lost (−3). Open items of the
other kind with a score of 3 or more are suggested on the item page; one click matches, *Hand over* records to
whom (ID checked) and closes both.

**Requests** (`Ticket`, `R-0001`): category (question, problem, accessibility, feedback, other), subject, message,
name and contact, status (new, in progress, waiting, done), assignee, notes. A note can be a *reply*: the
requester sees it on their status page. New requests notify the helpdesk; accessibility requests also go to the
ops log.

**Public page without accounts.** `/public/<slug>/help/`: the FAQ, found items (what, category, colour, day;
never details, photos or contacts) and two forms (ask the helpdesk, report a lost item). Each submission gets a
status link with a random token instead of an account (`/public/<slug>/help/status/<token>/`, `no-store`,
`no-referrer`). Spam guard: a honeypot field and a per-IP limit (`EVAC_RATE_LIMITS["public_form"]`, 10 per
minute). Settings switch the page, the forms and the found list off.

**Screens.** Data sources `helpdesk.faq` (entries marked *on screens*), `helpdesk.found` (as on the public page)
and `helpdesk.queue` (open and new requests) for custom widgets.

**Elsewhere.** Control room panel, staff app card (new requests, mine, log a found item), webhooks
(`helpdesk.request`, `helpdesk.lost`, `helpdesk.found`, `helpdesk.matched`, `helpdesk.returned`), read-only API
(`helpdesk-requests`, `lost-found`, `faq`), live data on venue nodes.

## Consequences

- Contacts of visitors live only in the helpdesk's rows; they are covered by the event's data export and
  deletion (purging the event deletes them). Retention after the event is an operator decision documented in the
  handbook.
- Matching is a suggestion, never automatic: a person checks the item and the owner's ID.
