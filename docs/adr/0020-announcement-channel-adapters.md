# ADR-0020: Announcement channel adapters as extensions

- Status: Accepted
- Date: 2026-10-09

## Context

Roadmap ticket 2.6 asks for channel adapters (e-mail, ntfy, Matrix, Telegram, Mastodon, Web Push) with
per-channel text and the outbox delivery report of ADR-0019. Each needs connection settings and secrets, should
be switchable per instance or event, and must not slow down or break publishing when a service is down.

## Decision

- **One extension per service**, all in the plugin `extensions/notify`: e-mail, ntfy, Matrix, Telegram and
  Mastodon register an `ExtensionSpec` each (settings schema, encrypted secrets, *Test connection*, scope "both")
  and a `NotificationChannelSpec` with the same key. They reuse the extension pages, logs and instance/event
  inheritance (`apps.extensions.services.effective`).
- **`NotificationChannelSpec` gains `available(event)` and `max_length`**: the composer and the level settings
  only offer channels that are set up for the event; channels with a `max_length` get an optional own text
  (`Announcement.channel_texts`, validated against the limit). `services.text_for(ann, channel, limit)` gives
  every adapter the same fallback (title and text, cut with "…").
- **Failure classes**: 4xx means the service refused the message (bad token, unknown room); the delivery is
  marked failed at once, logged on the extension, and not retried. Network errors, 429 and 5xx raise, so the
  outbox retries with backoff and the delivery report follows the latest attempt. Error texts never contain
  request URLs.
- **Idempotency** where the service supports it: the delivery ID is Matrix's transaction ID and Mastodon's
  `Idempotency-Key`. E-mail and ntfy may duplicate a message when an answer is lost after sending.
- **Plain HTTP with `requests`** (already a dependency); no SDKs. E-mail uses Django's mail backend.
- **Web Push moves to the staff PWA** (2.8): it needs browser subscriptions and VAPID keys, which come with the
  PWA, and a new dependency (`pywebpush`) that is decided there.

## Consequences

- New services are small plugins: an `ExtensionSpec` plus a `send(delivery)` function.
- Every adapter call happens in a Celery worker through the outbox, never in the request that publishes.
- An extension switched off after publishing turns pending deliveries into *skipped*.
