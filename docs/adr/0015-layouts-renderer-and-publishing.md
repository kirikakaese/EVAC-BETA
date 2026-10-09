# ADR-0015: Layout format, shared renderer and publishing

- Status: Accepted
- Date: 2026-10-09

## Context

The brief (§5.1, §5.4) asks for a visual editor whose preview is pixel-identical to the screens, versioning with
draft/published and scheduled publishing, template variables, offline playback and a widget contract usable by
extensions. Screens must keep playing without the server.

## Decision

- **Stored format v1** (`apps/content/layout_format.py`, JSON schema, validated on every save): canvas size,
  optional background, a flat ordered list of elements (z-order = order) with `frame` in percent of the
  canvas, `style` (sizes in percent of the canvas height, colours as `#rrggbb` or theme tokens, fonts as
  tokens or font-family ids), type-specific `props`, `visible_if`, entrance `animation`, `hidden`, `locked`.
  Unknown properties are rejected; referenced files and fonts must belong to the event or the shared library.
- **One renderer** (`frontend/src/renderer/`) for editor and player: a stage with the layout's aspect ratio
  (letterboxed into its host), `container-type: size`, elements positioned in percent and sized in container
  query units. Built-in widgets are custom elements (`evac-text`, `evac-image`, …) with an error boundary
  each; `WidgetSpec` registrations name them, so extensions plug in the same way.
- **Templates** (`{{ var|filter }}`, `{% if %}`) are evaluated client-side and inserted as text only.
- **Versions**: the draft lives on the layout; every save writes a `LayoutVersion`; the screens show the
  published version. Publishing can be scheduled (beat task every 30 s), any version can be published or
  restored. Optimistic locking (`version`) plus a soft "someone is editing" marker; no collaborative editing.
- **Offline bundle**: `/player/api/content/bundle/` returns theme, fonts, published layouts and asset entries.
  The player keeps the bundle on the device and prefetches every file. File URLs for screens carry a
  per-screen HMAC signature (`?s=<screen>.<sig>`), so `<img>`/`<video>` load them natively and the service
  worker caches them (Cache API, content-addressed, cache-first); signatures stop working when the screen is
  revoked. The brief's "IndexedDB content bundle" is realised with localStorage (JSON) + Cache API (files),
  which the browser manages the same way and which serves media to native elements directly.
- **Editor**: a Lit island (ADR-0009) in light DOM, so the renderer, theme variables and fonts apply;
  ~27 kB gzipped. UI strings come from the server.

## Consequences

- Percent-based frames stretch when a layout is shown on a different aspect ratio than designed; responsive
  anchors are a later ticket (the format has room for them).
- Signed URLs are bearer secrets for one file and one screen; they live as long as the screen is paired.

## Alternatives considered

- Absolute pixels with CSS transform scaling: simple, but blurry text on some players and no adaptation.
- Shadow DOM widgets: stronger isolation, but themes and fonts would need to be piped into every shadow root.
- Blob URLs from IndexedDB for media: works for images, but video seeking and memory use are poor on kiosks.
