# ADR-0018: Code mode — sandboxed HTML/CSS/JS in layouts

- Status: Accepted
- Date: 2026-10-09

## Context

Roadmap 1.3.6 and brief §5.3: designers may need what the visual widgets cannot do (an animated infographic, a
custom ticker, a sponsor wall). The brief demands a sandboxed iframe, a strict per-frame CSP and a
permission-gated postMessage data API. Screens must work offline, and §13 singles out "who can make every screen
say anything" as the main threat.

## Decision

- A layout element of type `code` holds `html`, `css`, `js` (size-limited), `data` (which kinds of data it may
  receive: `event`, `screen`, `time`, `assets`) and `assets` (up to 20 files of the library).
- **Frame**: `<iframe sandbox="allow-scripts">` with a `srcdoc` document built by the renderer. No
  `allow-same-origin` (opaque origin: no access to the page, its storage, cookies or the device token), no
  `allow-top-navigation`, `allow-popups` or `allow-forms`. A served frame page was rejected: the service worker
  does not serve sandboxed frames, so code would not work offline (tested in Chromium).
- **CSP**: a `srcdoc` document inherits the page's policy. Pages that render layouts (player, editor, playback
  preview) add their per-request nonce to `script-src`; the frame's scripts and styles carry that nonce. The frame
  adds its own policy in a `<meta>` element (both apply): `default-src 'none'`, scripts and styles by nonce only,
  `connect-src 'none'` (no fetch, XHR, WebSocket — no exfiltration), images, media and fonts only from EVAC
  itself or `data:`/`blob:`, no forms, frames, workers or `<base>`. Inline `style=""` attributes and `<script>`
  tags inside the HTML do not run; use the CSS and JavaScript fields. `</style>`/`</script>` sequences in the
  code are neutralised so code cannot leave its element.
- **Data API**: the frame gets `window.evac` with `data`, `onData(fn)`, `now()` (server-synchronised) and
  `log()`. The page sends only the declared kinds via `postMessage` (on `evac:ready`, and every 10 s when `time`
  is declared); messages from the frame are accepted only from that frame's window and only as `evac:error` /
  `evac:log` (into the player log). Data sources (phase 2+) join as further declared kinds.
- **Permission**: adding or changing code (any of `html`, `css`, `js`, `data`, `assets` of a code element) needs
  `content.code`, checked in the layout service for saves, creation, restores and the API; moving or deleting a
  code element does not. Every code change is audit-logged with a hash and size per element (not the code).
  The editor shows code elements read-only and hides the "Code" button without the permission.

## Consequences

- Code cannot load anything from the internet, by design; content comes through files and the data API.
- The page nonce is visible to code in the frame. That gives it nothing: the frame is a separate, opaque-origin
  document and cannot write into the page.
- Theme colours reach the frame as CSS variables (`--evac-…`); uploaded fonts do not yet (use files via the data
  API or system fonts).
