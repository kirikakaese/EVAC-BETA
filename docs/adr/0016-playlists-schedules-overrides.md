# ADR-0016: Playlists, schedules, overrides and client-side program resolution

- Status: Accepted
- Date: 2026-10-09

## Context

The brief (§5.6) asks for playlists (ordered, weighted, shuffled, durations, conditions, nesting), schedule
rules with a calendar and a "preview any screen at any time" tool, and live overrides with priority levels and
expiry, all switchable. Priority order: evacuation > emergency announcement > live override > urgent
announcement > schedule > default playlist. Slide changes must be synchronised across screens (±50 ms on the
LAN, 1.1.5) and screens must keep playing without the server (1.1.4).

## Decision

- **One app, three modules**: `apps/playlists` registers the modules `playlists`, `schedules` and `overrides`
  (the latter two depend on `playlists`, which depends on `content`). Permissions `playlists.view`,
  `playlists.edit`, `playlists.override` (scopable to venue/zone/room/screen group) and `playlists.emergency`
  (sensitive: two-factor verified sessions only). Override targets are checked against the user's scopes.
- **Priority bands** (integers): default 0, schedules 100–199 (100 + rule priority 0–99), override levels
  `urgent` 200, `override` 300, `emergency` 400; evacuation (phase 3) is fixed at 1000 and cannot be chosen.
  Announcements (phase 2) slot into the same bands.
- **Program per screen**: the server does not tell screens what to show. `GET /player/api/playlists/program/`
  returns every *entry* that can apply to the screen (overrides, schedule rules expanded into time windows
  for the next 7 days in the event time zone — recurrences, date ranges, slots past midnight and DST are
  handled on the server — and the default playlist or layout), plus the playlists they use and the published
  layout durations. The player keeps it on the device and resolves it locally.
- **Deterministic resolution** (`apps/playlists/engine.py` and its twin `frontend/src/program/engine.ts`):
  the winning entry is the highest priority window containing *t*; an entry with nothing to show on this
  screen (unpublished layout, all items filtered by tag/condition/validity) gives way to the next. A playlist
  is flattened (nesting up to depth 5 with a cycle guard; weighted = smooth weighted round robin; shuffled =
  xorshift32 seeded with FNV-1a of `playlist:cycle`, so every screen shuffles alike and the order changes per
  round) and the slide is `(t - window start) mod total`. With the server-synchronised clock, all screens
  compute the same slide at the same instant, also offline. The player wakes at the next slide end or window
  boundary (at most every 60 s) and refetches the program on `program.changed` and hourly.
- **One algorithm, two implementations, shared vectors**: `frontend/test/fixtures/program-vectors.json`
  (generated from the Python engine, checked by pytest and vitest) keeps the portal's calendar and preview
  identical to what screens play.
- **Message overrides** need no layout: the server builds a layout (title, text, clock; danger background
  for emergencies) from the theme tokens and ships it in the program.

## Consequences

- An override reaches screens as fast as the realtime channel (measured ~0.35 s) and a schedule change
  needs no server action at the boundary; a screen offline for more than 7 days falls back to its default.
- Item validity (`from`/`until`) changes the round length; screens stay in sync but the position jumps.
- Conditions use the template subset (`==`, `!=`, `not`, truthiness, filters `upper/lower/default/join`);
  data-source conditions arrive with data widgets.

## Alternatives considered

- Server pushes "show slide X now" to every screen: simple, but fails offline and synchronisation depends
  on delivery latency per screen.
- Shipping rule definitions (RRULE-like) to the player: smaller payload, but time zone/DST logic would have
  to be duplicated in the browser; precomputed windows keep the client trivial.
