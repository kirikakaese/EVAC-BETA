# ADR-0036: Venue node sync, as built

- Status: Accepted
- Date: 2026-10-10

## Context

[ADR-0002](0002-central-node-sync.md) decided the design for venue nodes:
- the configuration has one writer, central, and the live state has one writer, the node, while an event is
  checked out;
- snapshots with ETags go from central to the node;
- an op-log with idempotency keys goes from the node to central;
- media files are synced resumably;
- central forwards live actions to the node;
- a lost node can be taken back with a forced check-in.

Roadmap 3.10 builds it. This ADR records the choices made while building it.

## Decision

- **One generic mechanism, declared per module.** Plugins declare what syncs with
  `r.sync(SyncSpec(module, models=(SyncModel(...), ...), order))`. No module writes its own sync code.
  - `SyncModel(label, queryset(event), ...)` names a model and the rows that belong to the event.
  - `live=True` marks node-owned state:
    - evacuation state, history, blocked points, requests and acknowledgements;
    - announcements and their deliveries;
    - overrides.
  - `local_fields` belong to the node, such as screen pairing and health, bridge status and the alarm counter.
    Central's values seed a new row; after that, snapshots never overwrite them.
  - `secret_fields` are encrypted with `apps.core.crypto`; they are sealed for the node and re-encrypted there.
  - `natural_key` makes rows with integer keys upsert by those fields (module switches, settings).
  - `files` lists the media files the node must have.

  Rows travel in Django's serialisation format and are applied in one transaction, in module order. On the node,
  rows the snapshot no longer has are deleted. A node-side reference to a person missing on the node becomes
  empty.
- **Plugin API 2.** The new hooks are `r.sync` and `r.node_action`, plus `r.layout_check` from 3.7, and
  `ExtensionSpec` gains `secrets_on_site`. They are additive: plugins written for API 1 still load.
- **Identity and transport.**
  - An instance admin adds a node on *Venue nodes* and gets a one-time enrolment code (24 hours).
  - `manage.py evac_node enrol --central URL --code …` generates an Ed25519 signing key and an X25519 key on the
    node and presents their public halves. The node receives its token (`evacn_…`, stored hashed on central).
  - Every request carries `Authorization: Node …` and an Ed25519 signature over method, path with query,
    timestamp and body hash. Requests outside a five-minute window are refused.
  - The node only makes outbound HTTPS requests to `/api/v1/node/`.
- **Secrets.** Central decrypts a secret and seals it for the node: ephemeral X25519, HKDF-SHA256, AES-256-GCM.
  The node re-encrypts it with its own keys. This covers:
  - TOTP secrets, so people can sign in on site with their second factor;
  - the alarm key, so the node signs screen messages;
  - feed auth headers;
  - the settings of extensions marked `secrets_on_site` (the MQTT extension).

  Every other extension stays on central.
- **People.** The event's members and the instance admins travel, with password hashes, TOTP devices
  (sealed), security keys and recovery codes, so they can sign in on site without the uplink.
- **Snapshots.**
  - The `version` (the ETag) hashes the configuration without the node's local fields and without sealed
    values, so it changes exactly when the configuration changes.
  - The first snapshot of a checkout is the *seed*: it includes the live models.
  - The node asks every 30 s with `If-None-Match`. After applying a snapshot it re-pushes the evacuation
    payloads to its screens.
- **Op-log.**
  - On the node, signals record every save and delete of a live model, and every audit row, for events it
    holds. Each entry gets a `seq` and the key `<checkout>:<seq>` in the change's own transaction. Changes made
    while a snapshot is applied are not recorded.
  - Central applies entries in order, skips keys it already has, and stops at a gap. It answers with the highest
    contiguous `seq`.
  - Central only accepts rows of live models that belong to the checked-out event.
  - Central appends audit entries to its own chain as imported rows. Each keeps the original actor and target,
    plus `scope.node`, `scope.node_hash` and `scope.node_at`, so both chains stay verifiable.
  - Central stores what it applied as `ReceivedOp`. The node keeps `OpLogEntry` rows until central confirms
    them.
- **Single writer.** Central forwards evacuation triggers, request decisions, blocked points and staff answers
  for a checked-out event.
  - Central checks the person's permissions with their two-factor session, then queues a `ProxiedAction`. The
    node fetches it every round and runs the registered `r.node_action` as that person. The result returns
    with the op-log.
  - Direct writes are refused on central (`services.change`). Escalations, scheduled drills, the watchdog and the
    bridge sweep skip checked-out events, because the node runs them.
  - After a check-in the node keeps a read-only copy.
- **Check-in.** Central requests it. The node pushes the whole op-log and hands back its alarm counter, and
  central moves its own counter past that value, so screens accept central's next message.
  - A forced check-in (sensitive permission `nodes.checkout`, hold-to-confirm, reason, audit) takes the event
    back at the last applied position, expires pending forwarded actions and jumps the alarm counter by 1000.
- **Files.** Asset variants, font files, floor plans and spoken messages are fetched from
  `/api/v1/node/events/<id>/files/<path>`. Downloads resume with `Range` into a `.part` file, are checked
  against SHA-256 where known, and are limited to 64 MB per round. Offline map tiles stay online-only.
- **Runtime.** `manage.py evac_node run` runs every 2 s: op-log and actions every round, snapshots every 30 s.
  It is available as the entrypoint role `node-sync`, the systemd unit `evac-node-sync` and the compose profile
  `node`.

## Consequences

- A new module gets venue nodes by declaring a `SyncSpec`. If it has live state, it also registers node actions
  for what central's UI may still trigger.
- Rows with integer keys created on the node itself (rare: a person enrolling a second factor on site) could be
  overwritten by central's rows with the same key; they are reconciled at the next snapshot.
- `scripts/node_sync_e2e.py` (`make node-e2e`, CI job *venue node sync*) runs two real instances. It covers
  enrolment, the seed, an alarm on site reaching central, the all clear from central running on the node, a
  partition and the check-in. Load limits for 200 screens per node follow from the 3.12 load tests.
