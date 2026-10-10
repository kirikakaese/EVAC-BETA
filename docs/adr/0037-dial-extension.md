# ADR-0037: DIAL extension

- Status: Accepted
- Date: 2026-10-10

## Context

Phase 4 (brief §9) links EVAC to DIAL, the sibling phone network manager. The link has to be "small but deep":
- emergency calls in DIAL must reach the evacuation triggers;
- alarms must ring the handsets;
- orga must be able to record announcements by phone;
- DIAL's data must show on screens.

Constraints:
- **Plugins only.** Nothing outside `extensions/dial` may import it.
- **Outbox.** Every outgoing delivery goes through the durable outbox.
- **Alarm rules (brief §8).** Alarm behaviour stays under the trigger policy and the safety statement.
- **DIAL is not changed by this phase.**

Reading DIAL's code (not only its API document) showed details that shape the design:
- Webhooks carry no delivery id, and a retry re-renders `sent_at`, so the body (and its signature) differs on every
  attempt.
- `emergency.triggered` has two variants: an incident (someone dialled an emergency number) and a broadcast (DIAL
  rang the handsets). The broadcast variant includes the ones EVAC itself asked for.
- DIAL's emergency broadcast already sends a DECT text message when DIAL's messaging feature is on.
- There is no authenticated download for IVR audio. The API gives an absolute `/media/` URL that DIAL serves only
  with `DEBUG` or behind a proxy.
- The member list has usernames, not e-mail addresses.
- DECT list endpoints filter with `event__slug`, not `event`.
- `me/` does not show the token's scopes.

## Decision

- **One link per EVAC event** (`ExtensionSpec(scope="event")`):
  - DIAL URL, DIAL event slug, a `dial_…` service token (encrypted) and a webhook secret.
  - Five features that can each be switched off.
  - Test connection calls `health/?event=` (a `503` with JSON still counts as reachable, with the PBX/DECT state
    shown) and `me/`.
  - The needed scopes are documented and shown on the page, because DIAL cannot report them.
- **Inbound webhook idempotency.**
  - The framework gains `ExtensionSpec.delivery_id(headers, body, payload)`, used when the sender sends no delivery
    header.
  - DIAL's key is the event type plus a hash of `data`, so a retry with a new `sent_at` is processed once.
  - Handlers are idempotent on their own as well: the trigger key holds the incident id, and refresh jobs are keyed.
- **Emergency calls are a trigger source** (`EvacTriggerSpec("dial")`), not a direct state change:
  - They go through `triggers.trigger` and therefore the source's policy. The default is arm: the control room
    confirms, and auto-escalation fails towards alarm.
  - The stage is configurable (default staff alert). If the event's model lacks it, the next more severe enabled
    stage is used.
  - The evacuation module must be on and the statement accepted; otherwise the answer is `409`, and it is logged.
  - Broadcast variants are ignored. This breaks the EVAC → DIAL → EVAC loop.
- **Alarms ring handsets.**
  - A webhook sink on `evacuation.state_changed` queues a `Broadcast` and an outbox job on these changes: a raise,
    an escalation or a drill replacement into the chosen stages; and the all clear after an alarm that rang.
  - The text is the stage's spoken text (the same text the screens speak).
  - Drills ring only when allowed, and carry the drill marker.
  - EVAC does not send a separate DECT message for alarms, because DIAL's broadcast already does.
  - The sink catches its own errors: an integration never breaks an evacuation change.
- **Announcement channels.**
  - `dial_call` (emergency broadcast) and `dial_sms` (messaging broadcast, at most 480 characters).
  - They run inside the announcement's own delivery job, so the existing delivery report and retries apply. The
    `Broadcast` row (keyed by delivery) gives one place to see everything sent to DIAL.
- **Announcements by phone.**
  - The webhook only stores a `Recording` and queues a job.
  - The job finds the file through `ivr/announcements/` and downloads the path **from the configured DIAL URL**, so
    the token never follows a host DIAL put into a URL.
  - It accepts only WAV, stores it as announcement speech (AAC with ffmpeg) and transcribes it with optional
    whisper.cpp.
  - Announcements gain `speech_recorded`, so approval does not replace the recording with Piper speech, and a new
    service `submit_external`. With it the announcement goes into the approval queue, or is published at once for
    allow-listed extensions. Emergency levels always wait for a person.
  - Without downloadable audio the announcement is still created, and the reason is recorded.
- **Data sources, not widget code.**
  - `dial.phonebook`, `dial.numbers` ("call X for Y": own list, emergency numbers labelled with their targets,
    service numbers), `dial.pages` and `dial.dect` feed the existing widgets module. It handles polling, last good
    snapshot offline and screen rendering with the built-in visuals.
  - One button installs five preset widgets.
  - Info pages become plain text from DIAL's escaped HTML: screens never render another system's HTML.
- **No external calls inside requests.**
  - The DIAL page and the role page read `Snapshot` rows (DECT status, members).
  - Snapshots are refreshed by outbox jobs: when stale (over 5 minutes) on page view, and after DECT webhooks.
  - The only synchronous call is the framework's own "Test connection".
- **DECT alerts until the ops log exists (6.1).**
  - Each alert becomes a `DectAlert` row and an extension-log entry, and is emitted as the webhook event
    `dial.dect_alert`.
  - Problems are notified to holders of the new `dial.status` permission.
- **Roles stay manual.**
  - A mapping table maps each DIAL role to an EVAC role.
  - Proposals match DIAL usernames to EVAC members by e-mail local part or display name, and are only suggestions.
  - A person with `events.members` ticks and corrects each row. Only existing members can get a role.
  - Editing the mapping needs `events.roles` (sensitive, two-factor).
  - Nothing is assigned automatically. SSO uses the same OIDC IdP in both systems, documented; no IdP group mapping.
- **Framework fix found on the way.** Extension custom views were mounted at `<slug:key>/x/`, which sent every
  extension's views to the first one registered. They are now mounted per literal key, and the "More" button opens
  `x/`.

## Consequences

- An emergency call in DIAL can at most arm an alarm unless an orga explicitly sets the DIAL source to execute. A
  call never ends an alarm (policies never apply to the all clear).
- Ringing every handset for each chosen stage is loud by design. Drills stay quiet unless allowed, and a group can
  limit who is rung.
- Recordings need DIAL to serve `/media/ivr/` for the audio part. A small authenticated download endpoint in DIAL
  (like its voicemail audio) would remove that requirement. It belongs to DIAL and is not part of this phase.
- Role proposals are weaker than e-mail matching while DIAL's member list lacks addresses. That is acceptable only
  because a person confirms every row.
- On a venue node the DIAL link stays on central (`secrets_on_site` is off). Emergency calls arrive at central and
  are forwarded to the node like every trigger.

## Alternatives considered

- **Dedupe on the raw body.** Does not work: DIAL's retries change `sent_at`.
- **Map emergency calls straight to a state change.** Bypasses the policy and the two-person rule, against brief
  §8.3.
- **Send DECT messages for alarms from EVAC too.** Duplicates DIAL's own text broadcast.
- **Render DIAL's info page HTML on screens.** Would let another system inject markup into every screen.
- **Live DIAL calls when a page loads.** Violates the outbox rule, and makes the page as slow as DIAL.
- **Change DIAL now** (e-mail in members, an audio endpoint, a delivery id). Out of scope for EVAC's phase. Noted
  for DIAL.
