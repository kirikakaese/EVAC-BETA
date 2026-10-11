# EVAC screen for info-beamer hosted

A package for [info-beamer hosted](https://info-beamer.com/hosted) devices (Raspberry Pi). info-beamer draws with
Lua/OpenGL and cannot run EVAC's HTML player, so this package is a **text-only player**: it shows

1. the **evacuation state** of the screen (full screen with its direction arrow and texts, or a band at the top for
   states without takeover; an alarm stays up while EVAC is unreachable),
2. **announcements** (takeovers full screen, banners/tickers/cards as bands at the bottom),
3. otherwise the **event name and the time** (the event's time zone).

Layouts, widgets, media and speech need the browser player (kiosk, Tauri wrapper or any browser).

## Install

1. In the info-beamer dashboard: *Packages → Add package → Git repository* with
   `https://github.com/kirikakaese/EVAC-BETA` and the path `deploy/info-beamer` (or upload this directory as a zip).
2. *Setups → Create setup* from the package; set **EVAC server** (the address staff open EVAC with).
3. Assign the setup to a device. The screen shows a **pairing code**: enter it in EVAC under *Screens → Pair*.

The service keeps the screen token in the device's scratch directory; revoking the screen in EVAC makes it show a
new pairing code.

## How it works

- `service` (Python 3, standard library only) pairs the device, then polls EVAC with the screen token:
  evacuation state every 3 s, configuration every 5 min, program (announcements) every 30 s, heartbeat every 30 s.
  It writes `data.json`.
- `node.lua` draws `data.json`.

Polling instead of EVAC's WebSocket means up to ~3 s from an alarm to the screen (the browser player gets it
pushed). The evacuation payload's Ed25519 signature is not verified on the device (no crypto library there), so give an
`https://` server address: TLS is then what keeps the state authentic.

Fonts: Atkinson Hyperlegible (SIL Open Font License, `OFL-font.txt`).
