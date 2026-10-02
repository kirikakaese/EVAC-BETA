# ADR-0006: Typed settings with inheritance

- Status: Accepted
- Date: 2026-10-02

## Decision

Settings are grouped in namespaces declared by plugins with a JSON schema (`SettingsNamespace`). Values
are stored sparsely in `core.SettingValue(namespace, level, scope_id, values)` — only keys set at that
level. Resolution merges schema defaults ← instance ← venue ← event ← screen group ← screen and reports,
per key, where the value came from; the generated form (`SchemaForm`) shows "overridden here" /
"inherited from …" and an *Inherit* checkbox per field. Validation uses `jsonschema` (Draft 2020-12, no
additional properties). Deployment-level configuration (12-factor env) stays in Django settings.

## Consequences

- One generic UI and API for every module's settings; no per-module settings models.
- Schema changes must stay backwards compatible or ship a data migration; unknown stored keys are ignored.
