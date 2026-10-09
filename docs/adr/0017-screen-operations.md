# ADR-0017: Screen operations — display settings, remote management, resilience, kiosk

- Status: Accepted
- Date: 2026-10-09

## Context

Roadmap 1.2.2, 1.2.3, 1.1.7, 1.1.9 and 1.5.4: screens hang in places nobody can reach during an event. Staff
need to set rotation, overscan, dimming and audio per screen or group, see what a screen really shows, read its
logs, and trust that a screen recovers by itself. Raspberry Pis are the reference hardware.

## Decision

- **Display settings** are a normal settings namespace (`display`, levels instance → event → screen group →
  screen). A screen in several groups applies its groups in name order (a later group wins); the settings
  framework's `chain()` takes the list. The player applies everything itself: rotation, scale and keystone as
  one CSS transform on the player root, overscan as an inset of the content (not of the test pattern), dim and
  sleep as an overlay above everything, audio through the render context, the daily reload through the
  reload guard. Saving any `screens`/`display` value notifies the affected screens (`config.changed`).
- **Remote management uploads only on request**: staff commands `screenshot` and `logs` set a two-minute
  marker; `/player/api/upload/<kind>/` refuses anything not asked for (a stolen device token cannot fill the
  disk). The marker is cleared *after* the result is stored, so a page rendered in between keeps polling.
  Screenshots are decoded and re-encoded as JPEG (≤ 1920 px) before they are stored; nothing uploaded is
  served as sent, and the image is only readable with `screens.view` (`Cache-Control: private, no-store`).
- **Real screenshots** use the screen-capture API on the player's own tab (`getDisplayMedia` with
  `preferCurrentTab`), which Chromium allows without a prompt when started with `--auto-accept-this-tab-capture`
  (set by the kiosk recipe). Other browsers report why they cannot, and the screen page says so. Capture has a
  10 s timeout. DOM-to-image libraries were rejected: large, and wrong for video, fonts and cross-origin media.
- **Resilience** in the player: per-widget error boundaries (ADR-0015); a failed render falls back to the idle
  slide; every reload goes through a guard (at most 3 in 10 minutes unless staff force it); 50 errors within a
  minute, heap pressure (> 85 %) and the daily reload time trigger a guarded reload at the next slide change;
  an unclean stop is detected on the next boot and reported in the heartbeat; stalled timers (a frozen tab)
  resynchronise. The kiosk adds a process/DevTools watchdog and the hardware watchdog.
- **Kiosk recipe** (`deploy/kiosk/`): Raspberry Pi OS Lite + cage (Wayland kiosk compositor) + Chromium as a
  systemd service of an unprivileged `kiosk` user; a one-minute watchdog timer; optional read-only overlay;
  a pi-gen stage for images. No agent with its own credentials runs on the device.
- **First screen in the wizard**: the wizard links to the screens module's pairing page (the core does not
  import the module); the content module listens to `screen.paired` and, for an event without layouts,
  creates and publishes a welcome layout, so the first screen shows something right away.

## Consequences

- Rotation in the browser costs a little GPU time; displays or the OS should rotate where they can.
- Screenshots need a capture-capable browser; plain TV browsers only report the error.
- The DevTools port listens on 127.0.0.1 of the kiosk only; physical access to the device remains the
  boundary, as it is for any kiosk.
