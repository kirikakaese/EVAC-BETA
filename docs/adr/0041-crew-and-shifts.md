# ADR-0041: Crew and shifts, QR check-in and the Engelsystem import

- Status: Accepted
- Date: 2026-10-10

## Context

Brief §11.2 asks for:
- teams with leads, skills, a shift plan with sign-up rules, check-in and check-out (also by QR), no-show
  handling;
- a "needed now" board for the crew room and for screens;
- an Engelsystem import, because many events plan their angels there.

The Phase 7 gate: the shift board on screens.

Constraints:
- **Plugins only** (`apps/crew`, module key `crew`; the built-in roles reserve `crew.*`, the *Crew* role has
  `crew.view` and `crew.self`).
- **Scope kind `team`**, so team leads can be given permissions for their team only (ADR-0005).
- **Screens get data through custom widgets** (ADR-0023); a module does not render screen content itself.
- Volunteers are often not account holders: crew members may exist without an EVAC account.

## Decision

**Model.**
- `Team` (colour, leads, meeting point), `Skill`, `Member` (name, contact, teams, skills; optionally an account,
  one member per account and event), `ShiftType`, `Shift` (team, title, room or free place, start, end, people
  needed, skills, open for self sign-up, a random `checkin_token`), `Assignment` (signed up, checked in, done,
  no-show; who added it and from where: lead, self, `qr`, Engelsystem).
- Teams, members, shifts and assignments implement `evac_scope_chain()` → `[("team", id)]`. `crew.view`,
  `crew.checkin` and `crew.manage` can be granted per team; team leads (the team's `leads`) may manage their team
  without a role.

**Rules in one place** (`services.problems`, settings namespace `crew`): full, started more than
`late_signup_minutes` ago, missing skills, overlap, less than `min_rest_minutes` rest, more than
`max_hours_per_day`. A lead can sign someone up anyway (`force`); the audit log records `crew.signed_up_forced`
with the reasons. Sign-up locks the shift row, so two phones cannot overfill it.

**QR check-in.** Every shift has a QR code (shift page, printable sheet) for
`/e/<slug>/crew/scan/<token>/`. A logged-in crew member (`crew.self`) who scans it gets one big button: check in,
or check out when already in. Someone not on the shift joins it as a walk-in if the rules allow. The scan page and
the staff app's buttons work with the offline queue; replays are harmless because the actions only move forward.

**No-shows.** The beat task `crew-mark-no-shows` (every minute) marks sign-ups that are not checked in
`no_show_minutes` after the start. Team leads get a notification, `crew.no_show` goes to webhooks and the ops
log, and the shift shows up as needed again. A no-show who turns up checks in normally.

**"Needed now" on screens.** Data sources `crew.needed_now` (shifts now and in the next `needed_now_hours` that
miss people) and `crew.board` (the next 24 hours, a rolling window so night shifts stay after midnight). The
shift board's *Add shift board widgets for screens* creates the feeds and two custom widgets (*Crew: needed now*,
*Crew: shift board*) that an editor puts on a layout with a data element. Every change (sign-up, check-in,
no-show, sync) refetches the crew feeds after the commit; the widgets module then pushes the new data to the
screens (`notify_screens`), so a screen follows within a second or two.

**Elsewhere.** A control room panel (*Crew needed now*), a staff app card (my shifts with check-in/out and cancel,
"help needed" with one-tap sign-up), an announcement audience *Team*, `crew.shift_changed` webhooks, read-only
API (`shifts`, `crew-teams`). Venue nodes get the plan as configuration and assignments as live data
(ADR-0036), so check-in works on site without central.

**Engelsystem** (`extensions/engelsystem`, feature `shifts`): API v0-beta with an API key; angel types become
teams, each shift becomes one EVAC shift per angel type it needs (`external_id = "<shift>:<angel type>"`), entries
become members and sign-ups. Local data wins: check-ins, no-shows and people added in EVAC stay; a shift removed
upstream stays while it has local activity. The sync runs through the outbox (`engelsystem.sync`), periodically
or on *Sync now*. The feature key is `shifts` (not `sync`), so the program page does not list it as a program
source.

## Consequences

- The gate is tested by `frontend/e2e/phase7.mjs`: a layout with *Crew: needed now* on a paired screen shows
  "Wristbands: 2 needed"; a crew member scans the shift's QR code on the phone (walk-in, checked in) and the
  screen shows "1 needed" about a second later.
- Rules are deliberately few and per event; anything finer (minimum age, certificates with expiry) is a later
  extension of `problems`.
- Engelsystem stays the place where angels sign up when an event uses it; EVAC adds check-in, no-shows and the
  screens. Two-way sync is out of scope.
