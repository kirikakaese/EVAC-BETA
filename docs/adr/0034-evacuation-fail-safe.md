# ADR-0034: Evacuation fail-safe — bundle, signed state, bridge issuing, watchdog, self-test

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.9 and brief §8.6 require that:
- every screen keeps an evacuation bundle and stays in alarm while offline;
- signed state can come from a secondary node or the hardware bridge (ADR-0003);
- there is a watchdog and a self-test.

ADR-0003 fixed the principles: a per-event Ed25519 key, monotonic `seq`, no stale all clear, fallback origins
polled over HTTP, and a bridge that may issue a limited set of messages but never the all clear. This ADR records
how they are built.

## Decision

- **Alarm key** (`apps/evacuation/alarmkey.py`, `EventAlarm`):
  - Created on first use; the private half is stored encrypted with `apps.core.crypto`.
  - Every payload to a screen is signed over a compact core: event, screen, `seq`, state, drill, takeover, issue
    time and content version.
  - `GET /evac/<event>/state` returns the event-wide signed state: the event and zone statuses and the blocked
    points.
  - **Rotation** keeps the previous public key valid for 24 hours. Screens get the new key with their next
    bundle, and the change is pushed at once.
  - **Export** of the private key is for bridges and secondary nodes. It is available on the *Readiness* page
    (needs `evacuation.manage` and a two-factor session) or with `manage.py evac_alarm_key <event> export`.
    Every export is audit-logged with its purpose, and the key is shown once.
- **Evacuation bundle** (`feed.bundle`). Every screen fetches its bundle with its state every minute and keeps
  it in `localStorage` (the cache-clearing command leaves it alone). The bundle holds:
  - every stage's texts, layout, sound and spoken message;
  - the screen's direction for the live situation and for each single additional blocked exit or assembly
    point (up to 30 variants);
  - the public keys and the fallback origins.

  The service worker caches the spoken messages, and the player fetches them in advance.
- **Screen rules** (`evac.ts`), the same as the server's:
  - the newest `seq` wins;
  - a stale (> 10 min) all clear or normal is never applied over an alarm;
  - nothing returns to normal on its own;
  - while offline the player polls the fallback origins every 3 s and accepts only messages signed with a
    bundled key;
  - a message that carries an issuer (`is`, set by a bridge) may raise alarms but is rejected if it carries an
    all clear.
- **Bridge as fallback** (`bridge/evac_bridge.py`, optional `[fallback]`):
  - Every heartbeat answer carries the signed event state and each input's effective policy. The bridge keeps
    them on disk and serves the state at `/evac/<event>/state` (CORS open, optionally TLS).
  - The bridge needs the exported key to sign. When an input fires while EVAC cannot be reached, it applies the
    input's policy itself: *execute* signs at once; *arm* signs after its escalation time; *arm* without
    escalation and *notify* never sign.
  - A signed message raises the input's scope over the last state with `seq + 1`, an issue time and
    `is: "bridge:<name>"`. Signing uses pure-Python Ed25519, or `cryptography` when it is installed.
  - When EVAC is reachable again, the queued change carries `issued_seq`. The server:
    - executes the alarm, because it is already public (no arming, no two-person rule);
    - moves its own counter past `issued_seq` (jumps over 10 000 are ignored);
    - writes the audit log and alerts the control room.
  - Screens that reach the server only ever saw server messages. Screens that saw the bridge's message take the
    server's next message (a newer `seq`, or the same `seq` with other content).
- **Watchdog** (`acks.watchdog`, runs with `process_due` every 5 s). During an alarm, if screens have not
  confirmed the current message 30 s after it was issued, the control room is alerted once per message with the
  names of the missing screens. Bridges without a heartbeat already raise alerts (ADR-0032).
- **Readiness** (page *Readiness*, `manage.py evac_selftest <event> --report`, which exits 1 when a screen is not
  ready, for monitoring). It checks, per screen:
  - online;
  - bundle loaded, current and refreshed in the last 10 minutes;
  - sound allowed by the browser (autoplay);
  - last self-test result and age (due every 7 days).
- **Self-test** (button or `manage.py evac_selftest <event>`). The player:
  1. renders every stage off screen, both its own layout (a failure falls back to the built-in one) and the
     built-in layout;
  2. verifies the signature of the current message against the bundled keys;
  3. probes the audio permission and every fallback origin;
  4. reports to `POST /player/api/evacuation/selftest/`.

  On request it also shows a grey *Self-test — this is a test, there is no alarm* frame for a few seconds. It
  never does so during an alarm, and the server refuses a visible test during one.

## Consequences

- A screen on an HTTPS page can only reach HTTPS fallback origins (mixed content). Bridges and secondary nodes
  need a certificate the kiosks trust, or the venue LAN serves the player over plain HTTP. The bridge example and
  the handbook say so.
- Whoever holds the private key can show alarms on screens that lost the server. The key is exported only to
  devices the operator controls. Rotation revokes a lost device after the 24-hour grace period; to cut it off at
  once, rotate twice.
- The pure-Python signer takes milliseconds on a Raspberry Pi; ESP32 bridges do not sign (no fallback role).
