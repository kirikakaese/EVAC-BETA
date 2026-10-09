# ADR-0023: Custom widgets from external feeds

- Status: Accepted
- Date: 2026-10-09

## Context

Roadmap ticket 2.9 and brief §6: a no-code widget builder for screens — sources HTTP JSON, RSS, iCal, MQTT and
CSV; JSONPath mapping; visuals. Screens are offline first and must keep showing the last known data. Feed URLs
are entered by event staff, so fetching them must not let anyone reach the server's internal network.

## Decision

- **Server-side fetching** (`apps.widgets`): a *feed* is a URL (JSON, RSS/Atom, iCal or CSV) or a registered data
  source (`DataSourceSpec` with `fetch(event)`; `announcements.on_air`, `event.info`). Celery beat fetches due feeds
  (interval at least 60 s, default 5 min) with ETag support. Screens never contact the source.
- **SSRF protection**: only http(s), no credentials in the URL, every resolved address must be public (private,
  loopback, link-local, multicast, reserved and IPv4-mapped forms are refused), redirects are followed by hand
  and checked again (at most 3), 10 s timeout, 2 MB limit. An instance setting *Allow feeds from private
  networks* (`widgets.allow_private_networks`) opens the venue LAN for sensors. An optional authorization header
  is encrypted (`apps.core.crypto`) and never shown or audited.
- **Snapshots**: the parsed data is stored on the feed; a failed fetch keeps the last good snapshot and shows the
  error. XML is parsed with defusedxml.
- **Mapping on the server**: a widget picks the item list with a JSONPath subset (`$`, `.key`, `["key"]`, `[n]`,
  `[*]`) and maps up to eight fields (title, subtitle, value, label, time, end, image, link). Filters and
  recursive descent are left out because JSONPath dialects disagree there. The builder shows the snapshot as a
  clickable tree and a live preview.
- **Screens**: the layout element `data` references a widget. The player loads all mapped rows of its event from
  `/player/api/widgets/data/` (screen token), keeps them in local storage for offline use and reloads when the
  server sends `data.changed` (only when a used feed's data changed) or every 5 minutes. Visuals: text (template
  with `{{ data.first.title }}`), list, table, cards, counter, gauge, ticker and bars.
- **Editor choices hook**: `r.editor_choices(key, fn, module=)` lets modules hand option lists to the layout
  editor without the content module importing them.

## Consequences

- MQTT is deferred to phase 6: it needs a persistent subscriber and a broker client library, i.e. a runtime
  service, which needs a separate decision.
- Repeating iCal events show their first date only (no RRULE expansion).
- Data is as fresh as the poll interval; push sources come with MQTT.
