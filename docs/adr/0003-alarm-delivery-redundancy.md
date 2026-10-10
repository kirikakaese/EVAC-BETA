# ADR-0003: Alarm delivery redundancy

- Status: Accepted (2026-10-10, open questions resolved below)
- Date: 2026-10-02

## Context

During a live event the venue node is the authority for evacuation state. If the node (or the
web/channels process) dies during an alarm, screens must not fall back to normal content, and it must
still be possible to raise or change an alarm. Screens must not accept forged state from anyone on the
LAN. EVAC is a supplementary system (brief §2); this design limits, but cannot eliminate, single points of
failure.

## Decision

1. **Alarm key per event.** When the evacuation module is enabled, EVAC generates an Ed25519 *alarm
   signing key pair* per event. Public key: part of every screen's evacuation bundle. Private key: held
   by the primary node, an optional secondary node and the hardware bridge(s) (provisioned once, stored
   encrypted; rotation re-distributes the public key via the bundle and keeps the previous key valid for
   a grace period).
2. **Signed state messages.** Every evacuation state change is published as a compact signed message:
   `{event, scope (event|zone ids), state, drill, seq, issued_at, issuer, bundle_version}` + signature.
   Screens verify the signature and accept a message only if `seq` is greater than the last accepted one
   for that scope (monotonic per event, persisted in IndexedDB) — replay protection without trusting
   clocks. `issued_at` older than a window is ignored *only for escalations to normal*: a stale "all
   clear" is never applied, a stale alarm is (fail-safe direction).
3. **Delivery paths, in order**: (a) WebSocket from the node, (b) SSE/long-poll from the node,
   (c) **LAN fallback**: secondary node or hardware bridge serves the same signed message via a tiny HTTP
   endpoint the player polls (`/evac/state`) when (a)/(b) fail; screens are configured with up to three
   fallback origins at pairing. UDP multicast of the same message is an optional optimisation, **off by
   default**.
4. **Fail-safe rules on the screen** (unchanged by any path): offline in alarm → stay in alarm; offline in
   normal → keep normal content + staff-only offline marker; no state returns to `normal` except via a
   signed `all_clear` (then `normal` after the configured time); missing/broken custom layout → built-in
   fallback layout.
5. **Secondary node** (optional): follows the primary's op-log in near real time (same mechanism as
   ADR-0002 between node and central, but on the LAN), takes over issuing signed messages when the
   primary's heartbeat is missing for N seconds *and* an operator confirms (or immediately for messages
   coming from a hardware trigger). Split-brain is harmless for screens because `seq` is monotonic and
   both issuers derive `seq` from the shared op-log; a fenced primary stops issuing when it sees a higher
   `seq`.
6. **Hardware bridge** can issue a limited set of messages (e.g. `evacuate` for its configured zones,
   `staff_alert`) directly when it detects a dry-contact trigger and cannot reach any node; it never
   issues `all_clear`. Its **default trigger policy is `arm`**: a person confirms with hold-to-confirm, with
   auto-escalation after a configurable timeout; an admin can set a source to `execute` explicitly
   (audit-logged). When no node is reachable the bridge applies the configured policy itself.

## Consequences

- Players need Ed25519 verification (WebCrypto supports Ed25519 in current Chromium/Firefox/WebKit; a
  ~10 kB fallback implementation is acceptable within the bundle budget).
- Chaos tests (§8.7) cover: kill channels/web during an alarm, kill the node, partition screen ↔ node,
  replayed and forged messages.
- Key provisioning for bridges and secondary nodes needs a documented, audited ceremony.

## Alternatives considered

- HMAC with a shared secret: every screen would hold the secret → a stolen screen could forge alarms.
- Trust TLS to the node only: does not cover node failure.
- MQTT broker as fallback bus: one more service at the venue; can be added as an *additional* transport
  for bridges later.

## Resolved questions (review 2026-10-10)

1. UDP multicast: HTTP polling of fallback origins is the baseline; multicast is optional and off by default.
2. Hardware bridge default: policy `arm` (human confirmation, auto-escalation timeout); `execute` only when an
   admin sets it for a source.
