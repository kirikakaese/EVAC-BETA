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
| Malicious content (XSS) via layouts or code mode | Strict CSP without `unsafe-inline`; template output is text only. Code mode needs `content.code` and is audit-logged; it runs in `sandbox="allow-scripts"` frames (opaque origin: no page, storage, cookies or device token), with no network (`connect-src 'none'`), no navigation of the screen and only declared data via postMessage ([ADR-0018](adr/0018-code-mode.md)); `make e2e` tries the escapes |
| A forged screen / rogue player | Per-screen device tokens, revocable (phase 1); uploads (screenshots, logs) only accepted within two minutes of a staff request, size-limited, images re-encoded before storing and never served as uploaded |
| A malicious `.evacpack` | Structure, sizes, hashes and Ed25519 signature checked before anything is shown; unsigned packs and unknown keys need an explicit confirmation or are refused (*only trusted packs*); import goes through the normal services (code needs `content.code`, feed URLs the SSRF check), creates copies only and is audit-logged with signer and fingerprint ([ADR-0024](adr/0024-evacpack.md)) |
| Privilege escalation via role editing | Editing roles and handing out roles with sensitive permissions requires `events.roles` (sensitive); orga cannot grant admin; last-admin guard |
| A compromised plugin | Plugins are code with full access: install only trusted plugins; `EVAC_DISABLED_PLUGINS` removes one |

### False (or suppressed) evacuation alarms — phase 3

- Alarm permissions are *sensitive* (2FA verified session, every user) and scopable to zones.
- Hold-to-confirm for every alarm action (UI primitive available now), optional two-person rule, trigger
  policies execute / arm / notify, drills clearly marked and separated in the audit log.
- Signed state messages; screens accept only monotonic sequence numbers; a stale "all clear" is never
  applied; no auto-clear ([ADR-0003](adr/0003-alarm-delivery-redundancy.md)).
- Inbound trigger webhooks (DIAL, bridges) need HMAC signatures and are idempotent. A DIAL emergency call goes
  through the trigger policy of source “DIAL” (default: arm, the control room confirms); it can never end an alarm,
  and DIAL's broadcast echo is ignored ([ADR-0037](adr/0037-dial-extension.md)).
- The DIAL service token is encrypted, sent only to the configured DIAL URL (recordings are fetched by path from
  that URL, never from a host DIAL names), and needs only the scopes listed in
  [extensions/dial.md](extensions/dial.md). Screens never render HTML from DIAL; DIAL roles are never applied without
  a person confirming each assignment.
- The per-event alarm key's private half is stored encrypted and leaves the server only through an audit-logged
  export (two-factor session) for bridges and secondary nodes; rotation keeps the old public key for 24 hours.
  A message a bridge signed itself may raise alarms but never clear them; players enforce this
  ([ADR-0034](adr/0034-evacuation-fail-safe.md)).
- Hardware bridges have their own tokens (`evacb_…`, hashed); their inputs arm by default and never end alarms
  ([ADR-0032](adr/0032-hardware-bridge.md)).

### Other threats

| Threat | Control |
|---|---|
| Credential stuffing / brute force | argon2, per-account and per-IP lockout, rate limits on login, 2FA, setup and webhooks |
| First-run takeover (someone else finishes the wizard) | Early-access gate (`EVAC_EARLY_ACCESS_PASSWORD`) in front of everything, optional `EVAC_SETUP_TOKEN`; the wizard creates the first account only while none exists (row lock) |
| Premature public exposure | Early-access gate: signed, password-bound cookie, constant-time check, rate limit, WebSockets gated too |
| CSRF / clickjacking | Django CSRF on all forms, HTMX sends the token header, `X-Frame-Options: DENY`, `frame-ancestors 'none'` |
| Webhook forgery / replay | HMAC-SHA256 with constant-time comparison, per-config secrets shown once, delivery-id idempotency |
| Map tile fetching | Tiles are fetched by a background task, never inside a request, from the one tile server an instance admin configured; size limit, image type check, login required to view; bulk download refused for the public OpenStreetMap servers ([ADR-0028](adr/0028-georeference-and-map-tiles.md)) |
| SSRF via outbound webhooks | Only admins/orgas with `extensions.manage` add endpoints; deliveries do not follow redirects. Venue LANs are private networks by design, so private addresses are allowed — restrict egress at the firewall if needed |
| Secret disclosure | Fernet at rest, write-only forms, never in audit/logs, key rotation |
| Audit tampering | Hash chain + immutable rows + PostgreSQL trigger; verify on demand |
| Dependency vulnerabilities | `pip-audit` in CI (nightly too) |
| OIDC token substitution | PKCE, state, nonce, `iss`/`aud`/`azp`/`exp` validation, linking only by verified e-mail |

### Venue nodes ([ADR-0036](adr/0036-venue-node-sync.md))

- Enrolment needs a one-time code (24 h, hashed, rate-limited). The node creates its own keys; every request is
  signed with Ed25519 over method, path, timestamp and body hash (5-minute window) and carries a hashed token.
- Secrets reach the node sealed for its X25519 key (TOTP secrets, alarm key, feed headers, extensions marked
  `secrets_on_site`) and are re-encrypted there; other extension secrets never leave central.
- Central accepts from a node only changes of live state of the event checked out to it; audit entries join
  central's chain as imported rows that keep the node's hash. A lost node is revoked after a forced check-in.

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
