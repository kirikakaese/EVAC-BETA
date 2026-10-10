# Evacuation drill runbook

How to prepare and run an evacuation drill with EVAC, and how to check afterwards that everything worked.
EVAC is a supplementary information system: run the drill with the venue's own alarm and evacuation procedures,
and use this runbook for EVAC's part ([EVACUATION.md](EVACUATION.md)).

Roles used below: the **drill lead** runs the drill, the **control room** operates EVAC, **stewards** are staff in
the zones with the staff app.

## 1. A week before

1. **Statement**: *Settings → Evacuation*. The safety statement must be accepted for the event, once. Check the
   evacuation model, the states in use, their names and the drill marker (default "DRILL").
2. **People**: everyone who may raise or end alarms has a role with the alarm permissions and a second factor set
   up (*Account → Two-factor*). Stewards have the staff app installed and notifications allowed.
3. **Map and routes** (zones and routes model): exits and assembly points are on the venue map, every screen is
   placed with its facing, and *Evacuation → Screens* shows an arrow for each screen. A screen that says "Follow
   staff instructions" needs a waypoint near it, or a fixed direction.
4. **Screen content**: *Evacuation → Screen content*. Every stage passes the guardrails; texts are short; the
   spoken message has been rendered.
5. **Triggers**: *Evacuation → Triggers & drills*. Check what each source does (execute, arm, notify), and test
   every hardware bridge input with the panel's test function. Bridges show *online*.
6. **Fail-safe**: *Evacuation → Readiness → Run self-test*. Fix every screen marked *problem*: offline, bundle not
   current, sound blocked (kiosk set up with `deploy/kiosk`), self-test failures. If bridges or a secondary node
   are fallback origins, their row says *ok* in the self-test.
7. **Venue node** (if used): the event is checked out to it and `manage.py evac_node status` shows nothing left to
   send and no files missing.

## 2. On the day, before the drill

1. Brief the stewards: the drill is announced as a drill on every screen, they answer in the staff app with
   *I'm on it*, *Zone clear* or *Need help*.
2. *Readiness*: run the self-test again (with *visible test frame* if you want to see every screen once). All
   screens *ready*.
3. Open the control page on the control room's screen. *Screens reached* shows every screen.

## 3. Run the drill

1. **Raise** (control page, or the panic page on a phone): choose the stage and the zone, tick **Drill**, write a
   short note, and **hold** the button until it confirms. Or let the planned drill start at its time (*Triggers &
   drills → Scheduled drills*).
2. **Watch *Screens reached***: "X of Y screens confirmed" should reach all screens within seconds (target: 95 %
   within 2 s on the venue LAN). Screens still waiting after 30 s are reported by the watchdog with their names.
   Note them for the debrief.
3. **Steps**: step up (attention → evacuate) or block an exit (*Exits and passages → Block*, hold) to exercise
   the routes; screens change their arrows at once.
4. **Stewards answer** in the staff app; the answers appear on the control page. *Need help* also alerts the
   control room.
5. **End**: give the **All clear** (hold). Screens show it for the configured time and then return to normal
   content. *Back to normal now* ends it early.

A real alarm during a drill ends the drill at once; screens then show the real alarm without the drill marker.

## 4. After the drill

1. *Evacuation → History* (filter *drills only*): every change with time, person and note.
2. *Audit log* (filter *drills*): the full record, exportable as CSV or JSON.
3. *Screens reached*: the trigger-to-screen time (p95) for the drill's messages. Over 2 s means checking the
   network or the server.
4. Readiness: fix the screens that did not confirm. Run the self-test again.
5. Write down what the stewards reported and what changed (texts, routes, screen placement).

## Rehearsing without people: automated checks

The same flow runs automatically in CI and can be run on a test instance:

- `make e2e`: the browser test `frontend/e2e/evacuation.mjs` accepts the statement, pairs a screen, raises a
  drill with hold-to-confirm, checks the screen takes over within 2 s, that the control page shows "1 of 1 screens
  confirmed", that a staff answer arrives, the all clear and the return to normal.
- `make chaos`: kills the server during an alarm. The screen must stay in alarm, take a bridge-signed alarm from a
  fallback origin, refuse forged, stale and bridge-issued all-clear messages, survive a reload without the server,
  and follow the control room again when the server is back.
- `make load`: 500 screens on WebSockets receive an alarm (p95 within 2 s).
- `make node-e2e`: a venue node holding the event, with the central server going away and coming back.
