# Security & privacy

Threat model and controls. Updated with every phase; evacuation-specific controls are added in phase 3.

## Assets

1. **What every screen shows** (phase 1+) — misuse means misinformation or panic.
2. **Alarm state** (phase 3) — false alarms and suppressed alarms are both dangerous.
3. **Accounts, roles and tokens** — the keys to 1 and 2.
4. **Extension secrets** — credentials of other systems (DIAL, pretix, Matrix, …).
5. **Personal data** — names, e-mail addresses, later crew data, lost & found reports.
6. **The audit trail** — needed to reconstruct incidents.

## Threats and controls

### "Who can make every screen say anything?"

| Path | Control |
|---|---|
| A user with a broad role | Fine-grained permissions with scopes (venue/zone/room, later screen group); content and override permissions are separate (phase 1); every publish/override is audit-logged with before/after |
| A stolen session | Two-factor authentication required for orga/control-room/security/admin; sensitive actions only in 2FA-verified sessions; session cookies HttpOnly/SameSite, Secure in production |
| A leaked API token | Tokens hashed, scoped (`module:read|write`), event-bound, expiring, revocable, `last_used_at`; tokens minted without 2FA cannot use sensitive permissions; tokens cannot mint tokens |
| Malicious content (XSS) via layouts or code mode | Strict CSP without `unsafe-inline`; code mode runs in a sandboxed iframe with its own CSP and only a postMessage data API (phase 1) |
| A forged screen / rogue player | Per-screen device tokens, revocable (phase 1) |
| A malicious `.evacpack` | Signed packs, manifest hashes verified (phase 2) |
| Privilege escalation via role editing | Editing roles and handing out roles with sensitive permissions requires `events.roles` (sensitive); orga cannot grant admin; last-admin guard |
| A compromised plugin | Plugins are code with full access: install only trusted plugins; `EVAC_DISABLED_PLUGINS` removes one |

### False (or suppressed) evacuation alarms — phase 3

- Alarm permissions are *sensitive* (2FA verified session, every user) and scopable to zones.
- Hold-to-confirm for every alarm action (UI primitive available now), optional two-person rule, trigger
  policies execute / arm / notify, drills clearly marked and separated in the audit log.
- Signed state messages; screens accept only monotonic sequence numbers; a stale "all clear" is never
  applied; no auto-clear ([ADR-0003](adr/0003-alarm-delivery-redundancy.md)).
- Inbound trigger webhooks (DIAL, bridges) need HMAC signatures and are idempotent.

### Other threats

| Threat | Control |
|---|---|
| Credential stuffing / brute force | argon2, per-account and per-IP lockout, rate limits on login, 2FA, setup and webhooks |
| First-run takeover (someone else finishes the wizard) | Early-access gate (`EVAC_EARLY_ACCESS_PASSWORD`) in front of everything, optional `EVAC_SETUP_TOKEN`; the wizard creates the first account only while none exists (row lock) |
| Premature public exposure | Early-access gate: signed, password-bound cookie, constant-time check, rate limit, WebSockets gated too |
| CSRF / clickjacking | Django CSRF on all forms, HTMX sends the token header, `X-Frame-Options: DENY`, `frame-ancestors 'none'` |
| Webhook forgery / replay | HMAC-SHA256 with constant-time comparison, per-config secrets shown once, delivery-id idempotency |
| SSRF via outbound webhooks | Only admins/orgas with `extensions.manage` add endpoints; deliveries do not follow redirects. Venue LANs are private networks by design, so private addresses are allowed — restrict egress at the firewall if needed |
| Secret disclosure | Fernet at rest, write-only forms, never in audit/logs, key rotation |
| Audit tampering | Hash chain + immutable rows + PostgreSQL trigger; verify on demand |
| Dependency vulnerabilities | `pip-audit` in CI (nightly too) |
| OIDC token substitution | PKCE, state, nonce, `iss`/`aud`/`azp`/`exp` validation, linking only by verified e-mail |

## Privacy (GDPR)

- **Minimisation**: accounts hold e-mail, display name, optional SSO subject and second-factor metadata.
- **Export** (Art. 15/20): *Profile → Download my data*.
- **Erasure** (Art. 17): *Profile → Delete my account* anonymises the account and deletes memberships,
  tokens, second factors and notifications. Audit log entries are immutable by design and keep the actor
  description they were written with (legitimate interest: safety and accountability records); they fall
  under the audit retention policy.
- **Retention**: setting `general.retention_days` (instance/event) — modules purge personal data that long
  after an event is archived (implemented per module as they ship).
- **Occupancy counters and sensors** (phase 6) store counts only, never personal data.

## Reporting vulnerabilities

Please report security issues privately to the maintainer via a GitHub security advisory on the repository
rather than a public issue.
