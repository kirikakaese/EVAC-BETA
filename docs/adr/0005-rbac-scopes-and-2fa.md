# ADR-0005: RBAC with scoped grants and two-factor gates

- Status: Accepted
- Date: 2026-10-02

## Decision

- Permissions are registered `module.action` strings (`PermissionSpec`). Roles are per event and hold
  **glob patterns** (`screens.*`, `*.view`, `!events.delete`), so a role keeps working when a module is
  installed later. Built-in roles (admin, orga, control-room, security, helpdesk, crew, viewer) are
  created for every event, editable but not deletable.
- A member gets roles through `RoleAssignment`s; each may be **scoped** to one object of a registered
  `ScopeKind` (venue, zone, room; screen group and team arrive with their modules). An object declares
  the scopes it lives in with `evac_scope_chain()`; a scoped grant applies when its `(kind, id)` is in the
  chain. Event-wide actions require an unscoped grant.
- Evaluation is a pure function (`apps/events/permissions.py`, mypy strict, property-tested); the
  database side (`rbac.py`) builds grants and caches them per request.
- **Two-factor gates**: a role with `require_2fa` grants nothing in a session that did not pass a
  second factor; independently, every `sensitive` permission (role management, deleting events, and in
  Phase 3 every alarm trigger) needs a 2FA-verified session for everyone, including instance admins.
  Tokens inherit "2FA" only if minted in a verified session (`created_with_2fa`). Built-in admin, orga,
  control-room and security roles require 2FA by default (§4).
- Handing out a role that grants sensitive permissions needs `events.roles` (itself sensitive), so an
  orga cannot escalate to admin.

## Consequences

- Users without 2FA see a banner listing roles that are inactive for them, instead of silent 403s.
- Lists (e.g. venues) filter by `scopes_for(perm)`.
