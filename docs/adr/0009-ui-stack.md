# ADR-0009: UI stack for the staff portal

- Status: Accepted (editor framework: Lit, accepted at the start of Phase 1)
- Date: 2026-10-02

## Decision

- Server-rendered Django templates, **HTMX 2 vendored** in `static/vendor/` (no CDN: offline venues,
  strict CSP). Small behaviours are delegated `data-*` handlers in `static/js/evac.js`; no Alpine.js until a
  page needs client state that HTMX cannot express (the brief allows it; adding it is a small change).
- Styling: one hand-written stylesheet (`evac.css`, derived from DIAL's accessible dark-first design):
  tokens, dark/light, reduced motion, high contrast, 44 px touch targets, status badges with glyphs.
- Strict CSP without `unsafe-inline`; inline `<style>` only with a per-request nonce.
- **Layout and map editors (Phase 1/3)**: **Lit** (Web Components, ~6 kB, same component model as the widget
  renderers required by §5.5, so editor and player share code without a framework runtime). Accepted by the
  owner in Phase 1. Svelte remains the fallback if the editor's state handling outgrows Lit.
- **Screen player**: plain TypeScript + Vite (`player/` → `static/player/`), no framework (ADR-0013).

## Consequences

- No Node build step for the portal; the TypeScript apps (player, editors) get Vite builds in Phase 1.
