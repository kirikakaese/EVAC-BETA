# ADR-0049: Evacuation alarms to staff channels, pinned outbound fetches

- Status: Accepted
- Date: 2026-10-11

## Context

Staff learn about an evacuation from the screens, the staff app and Web Push (ADR-0021). Crews already
subscribe to the event's ntfy topic, Matrix room or Telegram group for announcements and staff alerts
(ADR-0039), and asked for alarms there too, as a second path to their phones. Changing how alarms go out is
safety behaviour (brief §8), so the rules are set here.

The Phase 9 security review left DNS rebinding open: `safefetch` resolved a host to check it, and `requests`
resolved it again to connect.

## Decision

- **Opt-in per event**: the evacuation setting `staff_alarm_channels` (ntfy, Matrix, Telegram, e-mail; empty by
  default). Screens, Web Push and the staff app never depend on it.
- **After the screens**: `services._record` queues the alert with `transaction.on_commit` after the screen
  update and webhooks, through the outbox (`core.alert` jobs). A slow or broken service never holds up the
  alarm, and failed sends are retried. Each change is one job per channel, idempotent per history entry.
- **Every state change** except going back to normal: alarms and shelter in place as errors (ntfy priority 5,
  🚨), attention and staff alert as warnings, all clear as info. **Drills** carry the drill text in the title and
  body and are sent as warnings, so a drill never wakes a phone at maximum priority.
- **Forgery**: `Alert.critical` (plugin API 5) marks alarms. A channel where strangers can post into what staff
  read must refuse critical alerts. ntfy refuses them when no access token is set, since an open topic lets
  anyone who knows its name publish a fake "Evacuate". Matrix rooms, Telegram groups and e-mail recipients are
  closed by their own membership.
- **Pinned fetches**: `safefetch` resolves once, refuses the host if any answer is private, and connects to the
  first checked address through a thread-local pin in urllib3's `create_connection`. The URL keeps the
  hostname, so the Host header, SNI and certificate checks are unchanged. `safefetch.post` does the same for
  POSTs; the pretix check-in uses it. Behind an egress proxy the proxy resolves the name.

## Consequences

- Organisers can reach staff phones through the apps crews already use. A wrong or unprotected setup fails
  visibly (in the extension log) instead of sending alarms over an open topic.
- The pin patches a urllib3 function at import time; a urllib3 upgrade that stops calling
  `urllib3.util.connection.create_connection` breaks the pinning test (`apps/core/tests/test_safefetch_pinning.py`),
  not production silently.
