# ADR-0035: Propagation and acknowledgements

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.8 and brief §8.5 require three things:
- an alarm reaches 95 % of the online screens on the venue LAN within 2 s, and this is measured, not assumed;
- the control room sees "X of Y screens confirmed / Z offline", per zone;
- staff can answer an alarm from the staff app.

## Decision

- **Screen acknowledgements.** After every evacuation message it renders, the player posts
  `POST /player/api/evacuation/ack/` with:
  - the message `seq` and content version;
  - the state it shows and the drill flag;
  - the path the message took: `websocket`, `poll`, `bundle` or `fallback`;
  - `rendered_at` and the server's `issued` time, both on the player's server-synchronised clock.

  The ack is also sent with every heartbeat. `ScreenAck` keeps one row per screen with the latest ack.
- **Latency.** Each ack gives a trigger-to-render time: `rendered_at - issued`. One `LatencySample` is stored
  per screen and message. Values over 10 minutes are clock jumps and are dropped.

  The control page shows the p95 of two sets:
  - the current message;
  - the last 24 hours.

  Above the 2 s target it shows a warning badge. The load test (roadmap 3.12) runs the same measurement with
  500 players.
- **Coverage** (`acks.coverage`):
  - It counts every paired screen that is not *excluded*.
  - A screen is **confirmed** when its latest ack has a `seq` at or above the event's current `seq`.
  - A screen is **offline** when its health is offline or stale and it has not confirmed.
  - Every other screen is **waiting**.
  - Zones come from the screen's zone and the zones of its room.
  - Screens that rendered from the signed fallback are counted separately.

  The *Screens reached* card on the control page refreshes every 3 s during an alarm and every 15 s otherwise
  (htmx polling of a fragment, no extra JS). The same data is at `GET /api/v1/events/<slug>/evacuation/coverage/`.
- **Staff answers.** The staff app card and the panic page offer three answers during an alarm: *I'm on it*,
  *Zone clear* and *Need help*. Each answer can carry a zone and a note.

  An answer:
  - is stored as a `StaffAck` with the message `seq` and the drill flag;
  - is written to the audit log (`evacuation.staff_<kind>`);
  - is emitted as the webhook and realtime event `evacuation.staff_ack`.

  *Need help* also alerts the control room through the bell and push. The control page lists the answers since
  the alarm started. The start is the last change into an alarm state for each scope; stepping between alarm
  stages keeps it.
- Answers are not permissions to change anything. They only need `evacuation.view`.

## Consequences

- An ack proves that the player rendered the message. It does not prove that the panel is physically on or
  readable. Screens report their display state with the heartbeat (phase 1), and the self-test (3.9) checks
  them visually.
- Latency depends on the player's clock synchronisation (offset from the heartbeat). Small skews can make a
  single sample slightly wrong but do not move the p95 materially.
