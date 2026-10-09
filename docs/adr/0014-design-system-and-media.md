# ADR-0014: Design system, fonts and media storage

- Status: Accepted
- Date: 2026-10-09

## Context

Screens need event branding (brief §5.3): themes with design tokens that compile to CSS custom properties,
self-hosted fonts (no Google Fonts at runtime, venues are offline), and an asset library with optimised
derivatives. Uploads are untrusted input (SVG can carry scripts, images carry GPS metadata, fonts and media
are complex parsers), and files must work on screens without internet.

## Decision

- **Themes** store only the tokens set at their level (`tokens` JSON) and inherit from a parent theme and the
  EVAC defaults. The token schema is flat, so the settings form framework renders it with "inherited"
  checkboxes. Tokens compile to `--evac-*` custom properties; the same variables drive the portal preview and
  the player. Saving uses optimistic locking (`version`); a stale save is refused with a clear notice
  (collaborative editing is out of scope, brief §5.4). An event picks its theme by key
  (`Event.default_theme`); paired screens are told to reload their configuration.
- **Fonts** are read with fontTools (family, weight, style, variable axes), optionally subset to Latin plus
  arrows and symbols, and always stored as WOFF2. Each family gets a unique CSS name (`evac-<uuid>`) so
  uploads in different events never clash. Atkinson Hyperlegible and Inter (both SIL OFL 1.1) ship in
  `static/fonts/` as built-in families.
- **Assets** are content addressed: `MEDIA_ROOT/content/<sha[:2]>/<sha>/<variant>`, identical uploads are
  stored once per owner. Uploads are accepted by extension and verified by content (Pillow, defusedxml,
  ffprobe, JSON); SVGs are sanitised (no scripts, event handlers, foreign objects, external references);
  images get EXIF rotation applied and metadata stripped. A Celery task makes the derivatives: WebP + AVIF +
  thumbnail, H.264/MP4 + VP9/WebM + poster, loudness-normalised AAC. **ffmpeg is part of the Docker image**;
  without it media stays as uploaded and the asset says so.
- **No public media URLs.** Files are served by Django only to members with `content.view` in an owning event
  (`/content/files/<sha>/<name>`) or to paired screens of such an event (`/player/api/content/files/…`, device
  token). Responses are immutable-cacheable; SVGs get a sandboxing CSP. The player fetches with its token and
  keeps fonts and images in the Cache API for offline use.
- **Shared library**: objects without event are usable by every event and managed by instance admins.

## Consequences

- Media is not served by the reverse proxy; the Django workers stream files (content-hashed, cached by
  browsers and the player). If this becomes a bottleneck, `X-Accel-Redirect`/`X-Sendfile` can be added
  without changing URLs.
- The Docker image grows by about 80 MB for ffmpeg (approved by the owner).
- Asset usage tracking covers themes now; layouts, playlists and widgets register their references when they
  arrive.

## Alternatives considered

- Public `/media/` via the reverse proxy: simpler, but uploaded drafts and staff-only material would be
  world-readable by URL.
- Transcoding in the browser or on demand: slow on kiosk hardware and not available offline.
