# ADR-0027: Map editor

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.2 and brief §10: upload a floor plan (PDF/SVG/PNG, scaled and georeferenced) or use OpenStreetMap tiles
cached offline for open-air sites; draw zones, place exits, waypoints and screens (position and facing), draw
route edges. Evacuation arrows (3.7) need every screen's position and the direction it faces. The route graph
(ADR-0026) stores positions in metres per floor.

## Decision

- **Floor plans** belong to `venues.Floor`: PNG, JPEG, WebP, SVG or the first page of a PDF. Raster plans are
  re-encoded as PNG (at most 8000 px), SVG plans are sanitised (`apps.core.svg`, moved from the content module),
  PDFs are rendered with `pdftoppm` (poppler-utils, added to the Docker image; an instance without it refuses
  PDFs with a clear message). Files are stored by hash under `MEDIA_ROOT/venues/plans/` and served to venue
  viewers with a locked-down CSP.
- **Scale**: until someone measures a known distance a plan is taken as 100 m wide. *Measure* sets metres per
  pixel; everything already placed on that floor (points, zone outlines, screens) is rescaled with it, so it stays
  where it was drawn.
- **Editor island** (`frontend/src/mapeditor`, Lit + SVG, no map library, 14 kB gzipped): the SVG viewBox is in
  metres; tools select/drag, add point, connect, zone outline, place, measure; pan and wheel zoom; a side panel
  with properties, numeric x/y fields and lists for keyboard use. Every change is one operation
  (`POST …/map/op/`), sent in order, audit-logged and followed by a reload, so routes ("next step" arrows) and
  plan checks always come from the server (`routing.py`).
- **Zone outlines**: `Zone.areas = [{"floor", "points"}]`, one polygon per floor.
- **Map layers** (`r.map_layer(MapLayerSpec(key, title, items, place, rescale))`): modules put their things on
  the map without the venues app knowing them. Screens are the first layer: `Screen.floor`, `position_x/y`
  (metres; the old unused 0..1 meaning is dropped) and `facing` (degrees clockwise from the plan's up). Placing a
  screen needs `screens.manage` for it in addition to `venues.manage`.

## Consequences

- Georeferencing floor plans and OpenStreetMap tiles cached offline for open-air sites follow in 3.2b (the
  outdoor "floor" is a metre grid until then).
- Event export/import carries points, edges and zone outlines but not plan files (they stay with the venue).
- Live layers (blocked exits, occupancy, incidents, screen status) can use the same layer hook later.
