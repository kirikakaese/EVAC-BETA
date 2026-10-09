# Announcement channels: e-mail, ntfy, Matrix, Telegram, Mastodon

Five extensions that deliver [announcements](../OPERATOR_HANDBOOK.md#5d-announcements) beyond screens. Each is
configured under *Settings → Extensions*, either once for the whole instance (events then choose "use the
instance configuration") or per event. Secrets (tokens) are encrypted at rest and never shown again. *Test
connection* checks the setup without sending an announcement (ntfy sends a lowest-priority test message).

Once an extension is on for an event, its channel appears in the announcement composer and in *Announcements →
Levels → default channels*. Each delivery is a row in the announcement's delivery report:

- **Delivered**: the service accepted the message.
- **Failed**: the service refused it (wrong token, unknown room, 4xx). It is not retried; the extension log
  shows the reason.
- **Failed, retrying**: network trouble, rate limits (429) or server errors (5xx). The outbox retries with
  backoff; the row turns *Delivered* once a retry succeeds.
- **Skipped**: the extension was switched off after the announcement was sent, or there was no recipient.

Errors never include request URLs (the Telegram bot token is part of its URL).

## Own text per channel

Under *Own text per channel* in the composer you can write a different text for ntfy (1000 characters), Matrix
and Telegram (4000) and Mastodon (500). Empty: the title and text; texts longer than the channel allows are
cut with "…".

## E-mail

Uses the server's mail settings (`EMAIL_URL`, `DEFAULT_FROM_EMAIL`).

| Setting | |
|---|---|
| Recipients | fixed addresses, sent as BCC |
| Also to the event staff | everyone who may see announcements and has an e-mail address |
| Subject prefix | default `[Event name]`; the subject is `prefix Level: Title` |
| Sender | default `DEFAULT_FROM_EMAIL` |

Urgent and emergency announcements are marked as high importance.

## ntfy

Publishes to a topic on [ntfy.sh](https://ntfy.sh) or your own server. Settings: server, topic; optional access
token for protected topics. Priority follows the level (info 2, important 3, urgent 4, emergency 5; emergency
gets the 🚨 tag). With `EVAC_PUBLIC_URL` set, tapping the notification opens the announcement.

## Matrix

Posts an `m.text` message with HTML (level in its colour) into a room. Create a bot account, invite it into the
room and let it join, then enter the homeserver URL, the room ID (`!abc:example.org`) and the bot's access token.
The delivery ID is the Matrix transaction ID, so a retry after a lost answer does not post twice.

## Telegram

Create a bot with @BotFather, add it to your group or make it an admin of your channel, and enter the bot token
and the chat ID (`-100…` for groups/channels or `@channelname`). Messages are HTML formatted; info announcements
arrive silently. *Bot API server* lets you use a self-hosted Bot API.

## Mastodon

Create an application under *Preferences → Development* on your instance with the `write:statuses` scope (and
`read:accounts` for the connection test), then enter the instance URL and the access token. Settings: visibility
(public, unlisted, followers only) and an optional hashtag added to the toot. Toots are limited to 500
characters; the delivery ID is sent as `Idempotency-Key`.

## Web Push

Push notifications to staff phones arrive with the staff PWA (roadmap 2.8).
