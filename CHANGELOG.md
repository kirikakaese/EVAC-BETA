# Changelog

All notable changes to EVAC are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning once 1.0 is
released.

## [Unreleased]

### Added — Phase 0 (foundation)

- Project scaffold mirroring PET: `evac/` settings (base/dev/prod/test), ASGI with Channels, Celery + beat.
- Plugin registry API (`apps/core/plugins.py`, `apps/core/registry.py`): modules, permissions, nav
  entries, settings namespaces, scope kinds, data sources, widgets, notification channels, evacuation
  triggers, webhook event types, CLI commands, extensions, event hooks, outbox handlers; discovery via
  `evac_plugin.py` and the `evac.plugins` entry point group.
- Module toggles (instance and per event, dependencies, required modules) with Settings → Modules.
- Typed settings framework (JSON schema, generated forms, instance → venue → event → screen group → screen
  inheritance with provenance markers).
- Tamper-evident audit log (SHA-256 hash chain, immutable in ORM and via PostgreSQL trigger, verify,
  CSV/JSON export, drill flag).
- Accounts: e-mail login with lockout, invitations, OpenID Connect SSO (PKCE, account linking, SSO-only
  mode, optional IdP-MFA trust), TOTP + WebAuthn + recovery codes, per-role and per-permission
  two-factor enforcement, service tokens (`evac_…`, scopes, event binding, expiry), GDPR export and
  erasure.
- Events with lifecycle (draft/setup/live/teardown/archived), scheduled transitions, branding, clone
  (with/without content), JSON export/import.
- Venues reusable across events: buildings, floors, rooms (capacity, accessibility), zones.
- RBAC: built-in roles, custom roles with glob patterns, scoped role assignments (venue/zone/room).
- Extension framework and Settings → Extensions (instance and event level): generated settings pages,
  encrypted secrets, test connection, health and log, feature toggles, inbound webhook URL + secret,
  disconnect & purge; signed inbound webhooks with idempotency.
- Generic webhooks extension: signed outbound deliveries for every registered event type via the durable
  outbox, endpoint management, inbound webhook store + signal.
- Durable outbox with retries/backoff/dead-letter; realtime stream (WebSocket, SSE, long-poll).
- UI shell (event switcher, search, notifications, sidebar from enabled modules, dark/light mode), first-run
  wizard, dashboards, members/roles/modules/settings/audit/token/user pages; strict CSP; a11y linter in tests.
- REST API v1 with OpenAPI (Swagger/ReDoc), `evac` CLI, health/readiness/Prometheus metrics, JSON logs.
- In-portal documentation, demo seed, Dockerfile, docker-compose, Ansible role, systemd units, CI
  (lint, types, tests + coverage, PostgreSQL checks, a11y, OpenAPI drift, dependency audit, Docker build,
  attribution check).
- Planning: roadmap, ADR-0001…0011 (ADR-0002 central/node sync and ADR-0003 alarm delivery redundancy are
  proposals awaiting review).
