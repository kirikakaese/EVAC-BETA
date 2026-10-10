# ADR-0002: Central/node sync

- Status: Accepted (2026-10-10, open questions resolved below)
- Date: 2026-10-02

## Context

One permanent central service hosts many events. A venue may run an **EVAC venue node** (same codebase,
`EVAC_MODE=node`) so screens, announcements, evacuation and ops keep working without an uplink. Screens
at the venue talk to the node. Only outbound HTTPS from the node is allowed (no inbound ports at the
venue). DIAL solved a similar problem with a venue agent pulling versioned snapshots with ETags.

## Decision

**Authority split per event**

| Data | Authority while checked out | Direction |
|---|---|---|
| Configuration: event settings, roles, users/memberships, venues, layouts, themes, fonts, assets, playlists, schedules, extension configs (minus secrets the node does not need) | central | central → node |
| Live operational state: screen state/acks, overrides, announcements (incl. drafts created on site), evacuation state + history, incidents, counters, audit entries created on the node | node | node → central |

**Checkout / check-in**

1. An admin checks an event out to a registered node (node identity = Ed25519 key pair generated on the
   node, public key registered at central with a one-time enrolment code; requests are signed and carry a
   node token).
2. Checkout makes the node the only writer of live state. Central shows "checked out to node X since …"
   and **proxies live actions** (announcements, overrides, alarms) to the node over the node's outbound
   connection while it is up; the node applies them like local actions (same permissions, audit) and the
   result comes back through the op-log. With the link down, central shows the last known state read-only
   and points to the node. Config stays editable on central.
3. Check-in: the node pushes everything pending, central confirms the op-log position, the node becomes
   a read-only replica of that event until the next checkout.
4. Emergency: if central is unreachable the node keeps working indefinitely; if the node is lost, an
   admin can *force check-in* on central (audit-logged, sensitive permission, two-person rule optional)
   accepting the last synced op-log position.

**Config sync (central → node)**: `GET /api/v1/node/<event>/snapshot/` returns a versioned JSON snapshot
of all configuration (content hash `version`, `ETag`); the node polls (default 30 s, immediate on a
"changed" hint pushed over a long-poll/WS when the uplink is up) with `If-None-Match` and applies the
snapshot transactionally. Large binary assets are not in the snapshot: it lists content hashes; the node
fetches missing assets with HTTP range requests (resumable, verified by SHA-256).

**Operational sync (node → central)**: every live-state change on the node is appended to an **op-log**
(`OpLogEntry(event, seq, idempotency_key, type, payload, created_at)`), the same records also drive the
node's own state. The node pushes batches `POST /api/v1/node/<event>/oplog/` (`since`, entries);
central applies them idempotently by `idempotency_key` and answers with the highest contiguous `seq`.
Audit rows written on the node are shipped as op-log entries and appended to central's audit chain as
*imported* rows referencing the node's chain hash (both chains stay verifiable).

**Screens**: pairing stores the node's local base URL (DNS name or mDNS `_evac._tcp`), with central as
secondary. Screens never talk to central while the event is checked out.

**Conflicts**: config is single-writer (central) and live state is single-writer (node) during a
checkout, so there are no write-write conflicts by construction. Clock skew: op-log ordering uses `seq`,
not timestamps.

## Consequences

- Needs: node registration UI, snapshot builder per plugin (`EventHook.snapshot`, `apply_snapshot`),
  op-log model + applier per plugin, asset sync, "checked out" guards in live-state services.
- Every module with live state must route state changes through op-log-aware services (contract for
  Phase 1+: keep live state changes in services, not views).
- Plugin API grows (`EventHook` gains `snapshot/apply_snapshot/oplog_apply`), which bumps
  `API_VERSION`.

## Alternatives considered

- PostgreSQL logical replication / multi-master: needs inbound connectivity, complex conflict handling,
  hard on a Raspberry Pi, and ties the node to schema internals.
- CRDTs for all state: overkill; single-writer per data class avoids conflicts.
- Node as pure cache of central: fails the "venue keeps working without uplink" requirement.

## Resolved questions (review 2026-10-10)

1. Remote control rooms during a checkout: **proxy live actions through central to the node** while the
   link is up (decision above); read-only on central when it is down.
2. Extension secrets on nodes: **opt-in per extension** ("needed on site", e.g. DIAL broadcast); those
   secrets are re-encrypted with the node's public key, all others stay on central.
3. Polling intervals and limits for 200 screens per Pi 5-class node: settled by the load tests of 3.12; the
   defaults above (30 s snapshot poll, change hints) stay until measured.
