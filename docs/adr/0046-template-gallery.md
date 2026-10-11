# ADR-0046: Template gallery

- Status: Accepted
- Date: 2026-10-11

## Context

Roadmap 9.3 asks for a template gallery: organisers should start a screen from something that already looks right
instead of an empty canvas. Packs (ADR-0024) already exchange whole designs between instances, but they are files
to import, need review and bring their own themes and assets; a gallery is about one layout, now, in the event's
own look.

## Decision

- A registry contribution `r.layout_template(LayoutTemplateSpec(key, name, data, description, category, module,
  order))`; `data()` returns layout data (format 1). Plugin API version 4.
- Templates use only theme tokens (`token:accent`, `token:surface`, …), template variables (`{{ event.name }}`,
  `{{ screen.room }}`) and no assets, so they fit every event and need no import step.
- The content module registers the general templates (welcome, information board, portrait information,
  countdown, sponsor slideshow, picture with ticker, wayfinding); the program module registers its stage screen
  and day program (`module="program"`, hidden while the module is off).
- *Layouts → Start from a template* (`/e/<event>/content/templates/`, `content.view`) shows every template rendered
  live by the preview island (new gallery mode: one thumbnail per `[data-preview-layout]`, rendered when scrolled
  into view) in the event's theme. *Use template* (`content.edit`) copies the data into a new layout through
  `create_layout` (validation, audit log) and opens the editor.
- A CI test validates every registered template and creates a layout from it.

## Consequences

- Plugins can ship templates for their widgets without core changes.
- A template is copied, not linked: later changes to the template do not reach layouts made from it.

## Alternatives considered

- **Templates as bundled `.evacpack` files**: heavier (signing, review, assets) for what is a single JSON
  document; packs stay the way to move complete designs.
- **Static thumbnails (PNG)**: would not show the event's theme and would need regenerating for every change.
