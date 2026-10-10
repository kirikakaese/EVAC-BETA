# ADR-0019: Announcements: levels, approval, screen overlays and delivery through the outbox

- Status: Accepted
- Date: 2026-10-09

## Context

The brief (§6) asks for announcements written once and delivered to screens and other channels, with
configurable priority levels (display style, sound, minimum display time, repetition, default channels),
templates with variables, scheduling, scoped targeting, an approval workflow with an emergency bypass, and a
delivery report. The phase 2 gate: one announcement reaches screens and three channels with a delivery
report, and the approval flow is tested. Screens must show announcements on time without network (1.1.4), and
the priority order of ADR-0016 must hold (evacuation > emergency announcement > live override > urgent
announcement > schedules > default).

## Decision

- **A module of its own** (`apps/announcements`, module `announcements`, no dependency): channels other than
  screens work without the screen modules. Permissions `announcements.view`, `.draft`, `.publish`, `.approve`
  (the last three scopable to venue/zone/room/screen group), `.emergency` (scopable, **sensitive**: two-factor
  sessions only) and `.manage` (levels and templates). Targets are checked against the sender's scopes for
  every venue, zone, room, screen group or screen addressed; "everywhere" needs an unscoped grant.
- **Levels are data**, created per event from built-in defaults (info → ticker, important → banner + chime,
  urgent → card + gong every 10 minutes, emergency → full screen + alert tone) and editable. A level marked
  *emergency* needs `announcements.emergency`, skips approval and takes over screens.
- **Workflow**: draft → submit → (pending → approve/reject by *someone else* with `announcements.approve`) →
  scheduled → live (per occurrence) → ended, or cancelled at any time by its author or a publisher. Approval is
  needed when the sender lacks `announcements.publish` for the targets, when the level always requires it, or
  when the event setting *every announcement needs approval* is on. Every step is audit-logged; approvers and
  authors get in-app notifications; `announcement.pending/published/cancelled` webhook events.
- **Screens through the program, not through pushes**: a new core hook `r.program_source(fn)` lets modules add
  entries, messages and **overlays** to every screen's program (`apps/playlists/services.build_program`).
  Full-screen levels become program entries (priority 500 for emergency, 250 for takeover levels, so above
  urgent overrides and below live overrides) with a layout built from the level colour or the template's
  layout (`{{ announcement.title }}`, `{{ announcement.text }}` filled in). Banners, tickers and cards are
  overlays with time windows (repetitions expanded on the server); the player draws them above whatever plays,
  hides them during a takeover, and plays the level's sound once per appearance (synthesised with WebAudio, no
  audio files; muted when the screen's display settings switch sound off). Screens therefore show and hide
  announcements on time offline, like schedules; `program.changed` makes them refetch at once.
- **Every other channel is a `NotificationChannelSpec`** with a `send(delivery)` function. Publishing an
  occurrence creates one `Delivery` row per channel and an outbox job each (`announcements.deliver`), so
  retries, backoff and the delivery report come from the outbox (ADR-0001). Built in: screens, public feed
  (page, RSS 2.0, JSON Feed 1.1; off by default), staff notifications, webhooks. E-mail, ntfy, Matrix,
  Telegram, Mastodon and Web Push register the same way (phase 2, part 2).
- **Scheduling**: a start time, an optional end, daily or weekly repetition until a day; a beat task
  (`announcements-publish-due`, 15 s) sends due occurrences and ends finished announcements. Screens do not
  depend on it (they have the windows).

## Consequences

- Plugins can add screen content (evacuation in phase 3) without the playlists app knowing them.
- The program grows with the number of announcements a screen can see in seven days; repetitions are capped
  at 500 windows per announcement.
- Text substitution is plain (no markup, no logic); unknown variables stay visible as `{{name}}` so a missing
  value is noticed instead of silently dropped.
- Announcements "relative to program items" (ticket 2.3) and audiences other than places are not part of
  this step; see [ADR-0025](0025-audiences-and-time-anchors.md).

## Alternatives considered

- Announcements as playlists overrides: no overlays (banner, ticker) and no delivery to other channels.
- Pushing banners to screens over the realtime channel only: lost on a screen that is offline at that moment,
  and repetitions would need the server at every boundary.
- One channel adapter call per announcement inside the request: violates the outbox rule and gives no
  per-channel report or retry.
