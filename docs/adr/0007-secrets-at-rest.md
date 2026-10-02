# ADR-0007: Secrets at rest

- Status: Accepted
- Date: 2026-10-02

## Decision

Extension credentials, webhook secrets and TOTP seeds are encrypted with Fernet (`cryptography`,
AES-128-CBC + HMAC-SHA256) through `MultiFernet` with keys from `EVAC_SECRETS_KEYS` (first key encrypts,
all decrypt; `evac_rotate_secrets` re-encrypts). Production refuses to start with the insecure default
`SECRET_KEY`; without explicit keys, development derives one from `SECRET_KEY`. Secrets are write-only in
the UI ("stored ✓", blank keeps, explicit "remove"), shown once when EVAC generates them (webhook
secrets, tokens, recovery codes) and never written to the audit log (only "changed: name").

## Alternatives considered

libsodium secretbox (no extra benefit, extra dependency); a KMS/Vault (a runtime service, unsuitable
for offline venue nodes).
