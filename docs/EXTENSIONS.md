# Extensions

An **extension** connects EVAC to an external system (DIAL, pretalx, pretix, Matrix, …). Extensions are
plugins (see [PLUGIN_SDK.md](PLUGIN_SDK.md)) that register an `ExtensionSpec`. They are configured under
**Settings → Extensions**:

- **Instance level** (`/settings/extensions/`, instance admins): one connection used by many events.
- **Event level** (`/e/<slug>/settings/extensions/`, permission `extensions.manage`): each event links its
  own external instance, or opts into the instance-wide connection ("Use the instance-wide connection").

The module **Extensions** can be switched off per event; then the event pages and inbound webhooks of
event-level configurations are unavailable.

## The settings page

Generated from the extension's spec:

| Section | What it does |
|---|---|
| Connection | Enabled switch, settings form generated from the JSON schema, secret fields (encrypted with `EVAC_SECRETS_KEYS`, write-only: blank keeps, "remove" deletes) |
| Features | One switch per contribution (data source, widget, trigger, channel, import, webhook) |
| Status | State, health, last check, last sync, last error; **Test connection** (HTMX, logs the result) |
| Inbound webhook | URL to paste into the other system, secret (generated, shown once, regenerable) |
| More | Custom views of the extension (e.g. webhook endpoints) |
| Disconnect | Deletes the configuration and secrets and calls the extension's purge function |
| Log | Recent log entries (tests, rejected signatures, deliveries) |

Card status: *not configured*, *enabled*, *uses instance connection*, *disabled*, *error* (last test
failed).

## Inbound webhooks

`POST /api/v1/extensions/<key>/<config-id>/webhook/` with a JSON body.

- Signature header (default `X-EVAC-Signature`, extensions may use their own, e.g. `X-DIAL-Signature`):
  `sha256=<hex HMAC-SHA256 of the raw body with the webhook secret>`, compared in constant time.
- Optional delivery id header (`X-EVAC-Delivery`): the same id is processed once; repeats return the stored
  answer with `"duplicate": true`. Senders without one can be deduplicated by the extension
  (`ExtensionSpec.delivery_id`, e.g. DIAL: event type + hash of `data`).
- Custom views of an extension are mounted at `…/extensions/<key>/x/`; the settings page links there ("More").
- Optional event header (`X-EVAC-Event`).
- Answers: `401` bad signature, `403` disabled, `400` invalid JSON, `404` unknown, otherwise what the
  extension returns.

## First-party extensions

| Extension | Phase | Page |
|---|---|---|
| Webhooks (generic, in/out) | 0 | [webhooks](extensions/webhooks.md) |
| DIAL — DECT & IP Administration Layer | 4 | [dial](extensions/dial.md) |
| pretalx / frab / iCal | 5 | – |
| pretix | 8 | – |
| Engelsystem | 7 | – |
| Matrix, Telegram, ntfy, Mastodon, SMTP | 2 | – |
| MQTT broker, Open-Meteo, info-beamer hosted, OIDC IdP | later | – |
