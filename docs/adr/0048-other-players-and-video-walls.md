# ADR-0048: Native and info-beamer players, video walls

- Status: Accepted
- Date: 2026-10-11

## Context

Roadmap 9.4 asks for a Tauri player wrapper and an info-beamer hosted package; 9.5 lists video walls as a stretch
goal. The web player (any browser, the Raspberry Pi kiosk recipe) stays the reference player.

## Decision

- **EVAC Player** (`deploy/tauri/`, Tauri 2): a native window around the unchanged web player. It only stores the
  server address (command line, `EVAC_SERVER` or a local setup page) and opens `<server>/player/` full screen.
  The setup page is the only local content and the only page with IPC; EVAC's pages run as a remote site without
  access to the app. CI builds it and runs its unit tests.
- **info-beamer package** (`deploy/info-beamer/`): info-beamer draws with Lua/OpenGL, so the package is a
  text-only player. A Python service (standard library only) pairs the device with the normal pairing flow,
  polls the player API with the screen token (evacuation state every 3 s, program every 30 s, configuration,
  heartbeat) and writes `data.json`; `node.lua` draws the evacuation state (full screen or a band), announcements
  and the time. The last state is kept while EVAC is unreachable. Tests run the service against the real player
  API.
- **Video walls**: display settings `wall_columns`, `wall_rows`, `wall_column`, `wall_row` and `wall_bezel`
  (screen or screen group level). The player makes its stage as large as the wall and moves it so each display
  shows its tile; the bezel setting keeps lines straight across frames. Screens of one wall change slides together
  already (shared server clock, ADR-0016). The evacuation layer is never split: an alarm shows complete on every
  display of a wall.

## Consequences

- The info-beamer player has no layouts, media or speech and gets alarms up to ~3 s later than pushed players;
  it does not verify the alarm signature (no crypto library on the device) and relies on HTTPS. Documented in its
  README.
- Walls need displays of the same resolution; mixed walls are not supported.

## Alternatives considered

- **Electron**: ~100 MB per install and a Chromium to keep updated; Tauri uses the system webview.
- **Rendering layouts to images for info-beamer**: a server-side browser per screen; too heavy for 1,000 screens.
- **One player spanning several outputs** for walls: depends on the GPU and operating system; tiles work with
  any player.
