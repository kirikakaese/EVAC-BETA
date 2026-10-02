# ADR-0010: Where the staff PWA lives

- Status: Accepted
- Date: 2026-10-02

## Decision

The staff PWA (brief §12) is **part of the portal** (`apps/portal`, service worker and manifest served
by Django like DIAL's PWA shell), not a separate `pwa/` app. Staff pages are regular server-rendered pages
with HTMX, plus small offline-queue scripts for counters and acknowledgements. The `pwa/` directory from
the brief layout is therefore not created.

## Consequences

- One login, one permission system, one set of templates; the a11y linter covers PWA pages.
- Offline write queues (counter clicks, acks) are implemented as a small shared JS module in Phase 2/6.
