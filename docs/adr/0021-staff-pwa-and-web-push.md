# ADR-0021: Staff PWA basics and Web Push without extra dependencies

- Status: Accepted
- Date: 2026-10-09

## Context

Roadmap ticket 2.8 asks for the basic staff PWA: installable, alarm reception, sending and approving
announcements, an offline queue with a clear sync state. Web Push (VAPID) was moved here from 2.6 (ADR-0020)
because it needs the PWA's browser subscriptions. ADR-0010 put the PWA into the portal. The usual Python library
(`pywebpush`) pulls in `aiohttp`, `http-ece` and `py-vapid`.

## Decision

- **Web Push in the core** (`apps/core/webpush.py`): VAPID (RFC 8292, ES256 JWT) and message encryption
  (RFC 8291, `aes128gcm`, one record) implemented with `cryptography`, which EVAC already uses. Tests check the
  encryption against the RFC 8291 test vector and decrypt like a browser. The instance key pair is created on
  first use and stored encrypted (`VapidKey`); `EVAC_VAPID_SUBJECT` sets the contact.
- **Every in-app notification is also a push**: `apps.core.notify.notify` queues one outbox job per subscribed
  browser of each recipient (`PushSubscription`). Level `err` is sent with urgency *high*, a 10-minute TTL and
  `requireInteraction`. 404/410 from the push service deletes the subscription, 429/5xx/network errors are
  retried, other 4xx are recorded as refused. Announcements to staff therefore reach phones without a separate
  channel; alarms (phase 3) reuse the same path.
- **PWA shell in the portal**: `/manifest.webmanifest`, `/sw.js` (scope `/`; the screen player keeps its own
  worker below `/player/`), `/offline/`, and the staff page `/e/<slug>/staff/` (start URL `/staff/`). The worker
  caches the shell assets, keeps the last staff page for offline use, shows push notifications and focuses or
  opens the linked page on click.
- **Staff cards are contributed by modules**: `r.staff_card(StaffCardSpec(...))` (the portal must not import
  optional modules). Announcements contributes "on air", "waiting for your approval" (approve/reject) and quick
  send from templates.
- **Offline queue** (`evac.js`): forms marked `data-offline` are stored in `localStorage` while the device is
  offline and posted in order when it is back; `[data-sync]` shows "All actions sent" / "n actions waiting".
  Refusals (400/403/404) leave the queue; the server's message shows on the next page.
- **Alerts on open pages**: publishing an announcement sends `announcement.live` on the event's realtime stream;
  urgent and emergency levels raise a full-screen alert with a tone and vibration on open staff pages (the same
  alert arriving via push and the stream is shown once).

## Consequences

- No new dependency; the push code is ~150 lines with test vectors.
- Web Push needs HTTPS (or localhost) and, on iOS, the app added to the home screen.
- The offline queue covers form actions; richer offline work (counters, incidents) builds on it in phase 6.
- Without Redis, processes do not share the realtime buffer: alerts from management commands reach open pages
  only with Redis (production setups use it).
