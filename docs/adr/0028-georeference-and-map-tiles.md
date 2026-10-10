# ADR-0028: Georeferencing and offline map tiles

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.2 and brief §10 ask for georeferenced floor plans and OpenStreetMap tiles cached offline for open-air
sites. ADR-0027 left both for 3.2b. The venue may have no internet during the event, so tiles must come from the
EVAC server, never from the operator's browser. The public OpenStreetMap tile servers allow viewing but forbid
bulk downloading ("prefetching") in their tile usage policy.

## Decision

- **Frame**: a floor stores `geo_lat`, `geo_lon` (the plan's top-left corner) and `geo_rotation` (bearing of the
  plan's "up", degrees clockwise from north). Plan coordinates stay metres; geographic positions come from a local
  tangent plane (`apps/venues/geo.py`, mirrored in `frontend/src/mapeditor/model.ts`), exact to centimetres over
  a venue. The outdoor "floor" uses the venue's own latitude/longitude with bearing 0, so open-air sites are
  drawn directly on the map.
- **Aligning**: *Align with map* in the editor shows tiles under the plan (adjustable plan opacity). Operators
  type the corner position and rotation, or drag the map until it matches the plan (`georef.move`). Changes are
  ordinary map operations: `venues.manage`, audit-logged (`venue.georeferenced`).
- **Tile proxy and cache**: the editor loads `/maptiles/{z}/{x}/{y}.png` (login required). A cached tile is
  served from `MEDIA_ROOT/venues/tiles/<hash of the tile URL>/`. A missing tile is never fetched inside the
  request: a Celery task fetches it (SSRF-safe fetch, 2 MB limit, image magic bytes checked, identifying
  User-Agent, deduplicated for a minute), and the request answers `503 Retry-After: 2`, after which the editor
  retries a few times. Changing the tile server starts a fresh cache.
- **Settings → Maps** (instance level): tiles on/off, tile server URL (default `tile.openstreetmap.org`),
  attribution (always shown on the map), maximum zoom, and *allow area download*.
- **Offline area download** (`map.download`) queues every tile covering the plan and its points plus 100 m, zoom
  14 up to the maximum, at most 5000 tiles (the top zoom levels are dropped until it fits). It is refused for the
  public OpenStreetMap servers whatever the setting says; it needs a tile server you run yourself (or one whose
  terms allow it). With the public servers, tiles viewed before the event stay cached and work offline.

## Consequences

- Without a frame the editor works as before (plan only); tiles are optional decoration and alignment aid.
- The tile cache is plain files; backups may skip `venues/tiles/` (it refills).
- The tile server URL is set by an instance admin and may point into the venue LAN, so private addresses are
  allowed for it.
- Screen positions, exits and assembly points now have geographic coordinates available for later features
  (staff PWA map, external dispatch exports).
