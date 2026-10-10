# DIAL

[DIAL — DECT & IP Administration Layer](https://github.com/kirikakaese/DIAL-BETA) runs the event phone network
(DECT and SIP). The DIAL extension links one EVAC event to one DIAL event:

| Direction | What happens |
|---|---|
| DIAL → EVAC | Someone dials an emergency number → **evacuation trigger** “DIAL emergency call” (trigger policy: execute, arm or notify) |
| EVAC → DIAL | An alarm stage you choose → **DIAL handsets ring** and play the stage's spoken text (DIAL emergency broadcast) |
| DIAL → EVAC | An orga **records an announcement by phone** → EVAC imports the audio, transcribes it (optional) and creates an announcement in the approval queue |
| EVAC → DIAL | Announcements can go to **“DIAL: ring handsets”** and **“DIAL: DECT message”** |
| DIAL → screens | **Phonebook, important numbers (“call X for Y”), info pages, DECT status** as data sources and ready-made widgets |
| DIAL → EVAC | DECT alerts (base station down/up, sync degraded) → DIAL page, notifications, `dial.dect_alert` webhook |
| Both | The **same OIDC identity provider** for single sign-on; a manual DIAL role → EVAC role mapping |

Nothing outside `extensions/dial` imports it; switch it off (or don't configure it) and EVAC works as before.

## Set up

1. **DIAL: a service token.** In DIAL, *Orga → Tokens* (`/e/<slug>/orga/tokens/`) or on the DIAL server:

   ```sh
   manage.py dial_token --user <orga e-mail> --name evac --event <dial-event> \
       --scopes events:read pages:read phonebook:read dect:read ivr:read emergency:read emergency:write messaging:write
   ```

   The token's owner needs the **orga** (or event admin) role in the DIAL event: broadcasts and the member list are
   orga features. Leave out scopes you do not use (`messaging:write` without DECT messages, `events:read` without
   the role mapping).

   | Scope | Used for |
   |---|---|
   | `events:read` | number plan (emergency and service numbers), members (role mapping) |
   | `pages:read` | info pages data source |
   | `phonebook:read` | phonebook data source |
   | `dect:read` | DECT status |
   | `ivr:read` | downloading the audio of a phone recording |
   | `emergency:read` | where emergency numbers ring (labels in “call X for Y”) |
   | `emergency:write` | ringing handsets (emergency broadcast) |
   | `messaging:write` | DECT text messages |

2. **EVAC: the link.** *Settings → Extensions → DIAL* of the event: DIAL URL, DIAL event slug, the token. Choose what
   the link does (see the settings below) and press **Test connection** (`GET /api/v1/health/?event=` and
   `GET /api/v1/me/`; it names scopes the token lacks and a token bound to another DIAL event).
3. **DIAL: the webhook.** EVAC shows the inbound webhook URL and a secret on the link settings page. In DIAL,
   *Orga → Webhooks* (`/e/<slug>/orga/webhooks/`): paste the URL and the secret; leave the event types empty to
   receive all.
4. **EVAC: check.** The event's DIAL page (`/e/<slug>/dial/`, also *Settings → Extensions → DIAL → Open*) shows the
   link, the DECT network, broadcasts and phone recordings. *Send test* sends a DECT message or rings the handsets.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| Alarm stage for an emergency call | staff alert | What the trigger asks for. When the event's model lacks the stage, the next more severe enabled stage is used (the simple model: evacuate). |
| Only these emergency numbers | all | Comma-separated; other emergency numbers are only logged. |
| Ring DIAL handsets for these stages | attention, shelter in place, evacuate | Raising or escalating into one of them rings the handsets. |
| Also announce the all clear | on | Only after an alarm that rang the handsets. |
| Ring DIAL handsets for drills too | off | Drills carry the drill marker (“DRILL: …”). |
| DIAL group to ring | all handsets | A DIAL group slug, e.g. `orga`. |
| Important numbers | – | `number = what for`, one per line; shown first in “call X for Y”. |
| Publish phone recordings at once from these extensions | – | Other recordings wait in the approval queue. |
| Announcement level for phone recordings | info | Emergency levels are never published without a person. |
| Transcribe phone recordings | on | Needs Whisper (below). |

Every contribution can be switched off on its own under *Features*: emergency calls → trigger, alarms ring handsets,
announcement channels, announcements by phone, data sources.

## Emergency calls → evacuation trigger

DIAL posts `emergency.triggered` when someone dials an emergency number (DIAL's `incident-log` hook). EVAC passes it
to the evacuation trigger **“DIAL emergency call”** with the configured stage. The **trigger policy** decides
(*Evacuation → Triggers & drills*): the default for extension sources is **arm** (the control room confirms; with
auto-escalation it executes when nobody answers). Set it to *notify* if a call should only inform the control
room, or *execute* where a call to that number always means an alarm.

- The evacuation module must be on and its safety statement accepted, or EVAC answers `409` and logs it.
- DIAL's own broadcasts (also the ones EVAC asked for) arrive as `emergency.triggered` with `kind: "broadcast"`;
  they are ignored, so there is no loop.
- DIAL retries a webhook with the same `X-DIAL-Delivery` id (older DIAL versions: a new `sent_at` and no id; EVAC
  then recognises the repeat by its content); it is handled once.

## Alarms ring handsets

When the event or a zone is raised or escalated into a chosen stage, EVAC queues a DIAL emergency broadcast
(`POST /api/v1/emergency/broadcast/ {event, announcement, group?}`). The text is the stage's **spoken text** from
*Evacuation → Screen content*, else its first screen text, else the stage name; zones are named, drills marked.
DIAL rings every active handset (or the group) and, when its messaging feature is on, also sends the text as a
DECT message, so EVAC never sends both. Deliveries go through the outbox and are retried until DIAL accepts them;
the DIAL page lists each broadcast with its result.

## Announcements by phone

1. In DIAL, an orga dials the announcement record number plus the announcement's code and speaks.
2. DIAL posts `announcement.recorded` with the announcement's id. EVAC downloads the file from DIAL's
   `ivr/announcements/<id>/audio/` **at the configured DIAL URL** (the token never goes to another host), stores it as
   the announcement's spoken audio (normalised to AAC with ffmpeg when available) and, with Whisper, transcribes it.
3. EVAC creates an announcement with the transcript (or a note) at the configured level: in the **approval queue**,
   or published at once when the calling extension is on the allow-list. Screens play the recording itself, never a
   synthetic voice.

DIAL versions before the audio endpoint (they send no announcement id) only give the media name: then EVAC needs DIAL
to serve `/media/ivr/` (`DEBUG=1` or a reverse proxy). Without audio the announcement is still created, and the DIAL
page says why.

**Whisper** (optional, offline, English): install [whisper.cpp](https://github.com/ggml-org/whisper.cpp)'s
`whisper-cli` on the worker (or set `EVAC_WHISPER_BINARY`) and an English model at `EVAC_WHISPER_MODEL` (default
`<MEDIA_ROOT>/whisper/ggml-base.en.bin`, e.g. from the whisper.cpp model download script). ffmpeg prepares the
audio. Transcription runs in the outbox worker.

## Data sources and widgets

| Data source | Content |
|---|---|
| `dial.phonebook` | public phonebook entries: number, label, name, type, description, location, category |
| `dial.numbers` | “call X for Y”: your important numbers, the emergency numbers (labelled with where they ring) and DIAL's service numbers; each item has `call` (“Call 112”) and `label` |
| `dial.pages` | published info pages: title, text (from DIAL's rendered Markdown; screens never render HTML from DIAL), Markdown |
| `dial.dect` | base stations (status, location, calls), cluster health, counts and recent DECT alerts |

Use them under *Widgets → Data feeds → Data source*, or press **Add DIAL widgets** on the DIAL page: five ready-made
widgets (call X for Y, important numbers, phonebook, info pages, DECT status) appear under *Widgets → Custom
widgets*. Like every feed, the last good data stays on screens when DIAL is unreachable. `page.updated` and DECT
alerts refresh the matching feeds at once.

## DECT alerts

`dect.rfp.down`, `dect.rfp.up`, `dect.sync.degraded`, `dect.omm.unreachable` and `dect.omm.reachable` are kept on the
DIAL page and in the extension log, sent to EVAC integrations as `dial.dect_alert`, and problems are notified to the
people with the permission **“See the DIAL link”** (`dial.status`). The operations log (roadmap 6.1) will list them
too.

## Single sign-on and roles

EVAC and DIAL can use the **same OIDC identity provider**: register two clients (or one client with both redirect
URIs) and set `EVAC_OIDC_*` and `DIAL_OIDC_*` (see the operator handbooks). Both link accounts by the IdP subject and
then by verified e-mail address, so a person has one login for both. Neither maps IdP groups to roles: roles stay in
each system.

*DIAL page → Roles* (needs “Create and edit roles”) maps DIAL event roles (user, helpdesk, orga, event admin) to EVAC
roles. **Nothing is assigned automatically.** EVAC fetches the DIAL members and proposes, for each member with a
mapped role, the EVAC member with the same e-mail address (“same e-mail”); with older DIAL versions, which send no
addresses, the member whose e-mail name or display name equals the DIAL username (“check: matched by name”). A
person with the permission to manage members checks each row, corrects the member if needed, and assigns. Only people who already are
members of the EVAC event can get a role.

## Troubleshooting

| Symptom | Check |
|---|---|
| Test connection: “refused the service token” | token expired or revoked; mint a new one |
| Broadcasts fail with `HTTP 403: orga role required` | the token's owner is not orga in the DIAL event |
| Broadcasts fail with `HTTP 404: emergency disabled` / `messaging disabled` | the DIAL feature is off (`DIAL_FEATURES`) or disabled for the event |
| Webhooks rejected (`401`) in the DIAL webhook status | secret differs; regenerate it in EVAC and paste it into DIAL |
| Emergency call answered `409` | evacuation module off or safety statement not accepted |
| Recording without audio | DIAL kept the file on the PBX (it could not read the recording directory), or an older DIAL does not serve `/media/` |
