# ADR-0025: Announcement audiences and time anchors

- Status: Accepted
- Date: 2026-10-10

## Context

Brief §6 asks for announcements "relative to program items" ("10 min before {{talk}}", ticket 2.3) and for
per-channel audiences such as crew teams, roles and attendee groups (ticket 2.4). Program items arrive with the
program module (phase 5), crew teams and attendee groups with the crew and ticketing modules. The announcements
module must not import them (CLAUDE.md: never import an optional module).

## Decision

- **Two core hooks** (`apps/core/plugins.py`):
  - `TimeAnchorSpec(key, title, choices(event), resolve(event, id) -> Anchor(start, end, label) | None)`:
    `r.anchor_source(...)`. Modules send `apps.core.signals.anchor_moved` (sender = spec key, `event`,
    `anchor_id`) when an anchor moves.
  - `AudienceSpec(key, title, choices(event), members(event, ids))`: `r.audience(...)`.
- **Announcements** store `anchor` (`"<source>:<id>"`), `anchor_edge` (start/end), `anchor_offset` (minutes,
  negative = before; at most a week either way) and the anchor's label, and `audiences` (`["roles:<id>", …]`).
- **Timing follows the anchor until the announcement is sent**: saving and submitting compute `starts_at` from
  the anchor (an end time moves with it, so the duration stays); `anchor_moved` reschedules drafts, pending and
  scheduled announcements (audit `announcement.rescheduled`, screens refetch their program); the scheduler
  looks once more before sending, so a move without a signal is caught too. A vanished anchor keeps the last
  time (audit `announcement.anchor_lost`). Anchored announcements cannot repeat. `{{anchor}}` in the texts
  becomes the anchor's name.
- **Audiences limit channels that reach people**, not screens or public channels: today the staff channel (in-app
  notifications and Web Push); empty means everybody the channel reaches. Other channels can call
  `services.audience_members(announcement)`.
- **Built in now**: the audience *roles* (members holding one of the chosen event roles, any scope). No anchor
  source exists yet; the compose page shows the anchor fields only when one is registered. The program module
  (phase 5) registers program items; crew teams and attendee groups come with their modules.

## Consequences

- Ticket 2.3 is complete only when phase 5 registers program items; the mechanism is tested with a fake source.
- The API accepts `anchor`, `anchor_edge`, `anchor_offset` and `audiences`; `anchor_label` is read-only.
- Screens still receive announcements in advance; a moved anchor reaches them through `program.changed`.
