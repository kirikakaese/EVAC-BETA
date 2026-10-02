# ADR-0004: Tamper-evident audit log

- Status: Accepted
- Date: 2026-10-02

## Decision

`core.AuditLog` rows are append-only and hash-chained: `hash = SHA-256(prev_hash + "\n" + canonical JSON
of the row content)`. A single `AuditChainHead` row (locked with `SELECT … FOR UPDATE` while appending)
holds the newest hash and the row count. Immutability is enforced three times: model `save()`/`delete()`,
queryset `update()`/`delete()`, and on PostgreSQL a trigger rejecting `UPDATE`, `DELETE` and `TRUNCATE`
(migration `core.0002`). `verify_chain()` (UI, `manage.py evac_audit_verify`, `GET /api/v1/audit/verify/`)
detects modified, removed, reordered and truncated rows.

Actor and event are stored as ids plus a text copy, **not foreign keys**: deleting or anonymising a user
must never rewrite audit rows. Rows carry a `drill` flag so drills are reported separately (§8.2).

## Consequences

- Appending serialises on the chain head (fine for human-paced actions; high-rate telemetry does not
  belong in the audit log).
- A database superuser can still drop the trigger and rewrite the whole chain consistently; exporting the
  head hash regularly (e.g. to the ops log or an external system) makes that detectable. A periodic
  "anchor" export is a Phase 9 hardening item.
- GDPR erasure anonymises the account but not historic audit text (documented in SECURITY.md).
