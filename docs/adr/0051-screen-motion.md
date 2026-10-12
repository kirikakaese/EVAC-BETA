# ADR-0051: Screen motion — slide transitions, entrance effects, slide timer

- Status: Accepted
- Date: 2026-10-12

## Context

The brief (§5.4) asks for entrance animations, slide transitions and timing, with respect for
`prefers-reduced-motion` and a global "no animation" switch. The layout format already had an entrance
`animation` per element (ADR-0015), but slides always cut, the theme's transition token was not used by the player,
and previews never showed effects. Viewers also asked how long a slide stays: a timer bar is a common pattern.

Forces:
- **Safety (brief §8)**: the evacuation takeover, full-screen announcements and emergency overrides must never be
  delayed or softened by motion. The ≤ 2 s target from trigger to rendered alarm includes nothing for animations.
- Screens change slides together from the synchronised clock (ADR-0016); motion must not break that and must work
  offline.
- Strict CSP on the player (no inline scripts or style attributes in markup; CSSOM from script is allowed); small
  players (Raspberry Pi); bundle budgets.
- Existing content must look exactly as before.

## Decision

- **Slide transitions belong to playlists**: `Playlist.transition` (`none`, `fade`, `slide-left`, `slide-up`,
  `zoom`; default `none`) and `transition_ms` (≤ 5,000, default 600) are the playlist's default;
  `PlaylistItem.transition` (empty = the playlist's) and `transition_ms` (empty = the playlist's) override it for the
  transition *into* that item's slide. A nested playlist's slides use its own items. The program sends a resolved
  `transition: {effect, ms}` on layout items that have one and nothing otherwise, so a playlist without transitions
  produces the same program as before. Forms, API, packs (`transition`, `transition_ms` in the playlists section;
  older packs import as *none*) and venue-node sync (whole rows) carry the fields. The theme's `transition` token
  stays a CSS variable for code elements and is relabelled as such.
- **The player draws the transition**: the slide resolution itself (engine and shared vectors) is unchanged. When
  the slide (entry, item, start) changes and the new slide has a transition, `Display` renders the new slide into a
  second view above the old one and runs CSS keyframes (classes `evac-tr-in/out` + effect, duration in a custom
  property set through the CSSOM); the old view is destroyed after the duration. The duration is capped at half the
  slide. Transitions are skipped for a forced redraw of the same slide (configuration or program refresh).
- **Entrance effects** stay in the format as they were (`enter`: fade, slide-up, slide-left, zoom; `duration`
  ≤ 10 s; `delay` ≤ 60 s — existing bounds, so stored layouts stay valid) and are applied by the shared renderer when
  `motionOn(ctx)`: not with reduced motion, not with `ctx.motion === false`, and in the editor only on *Play
  animations*. Previews (playback preview, pack review, widget preview) now play them; gallery thumbnails and print
  sheets do not.
- **Slide timer**: element type `progress` (*Slide timer*) with `orientation`, `mode` (shrink/grow), `reverse` and
  `untimed` (`full`/`hide`). The player passes `ctx.slide = {start, end}` for playlist slides that change
  (`count > 1`) and `null` otherwise — a lone slide, a schedule or override showing one layout, or the default
  layout have no meaningful end, so the timer shows full (default) or hides. The bar is one CSS animation with a
  negative delay from the synchronised start (cheap, in step across screens); with reduced motion it is set once a
  second. Without `ctx.slide` (editor, previews) it loops over the layout's duration (10 s by default).
- **Reduced motion**: the device's `prefers-reduced-motion` or the new display setting `reduce_motion` (namespace
  `display`, screen/group/event/instance) turns off transitions and entrance effects; the player sets
  `html.reduce-motion` so CSS makes sure. Tickers keep moving (they carry text).
- **Safety**: the evacuation controller renders with `motion: false, reducedMotion: true, slide: null` whatever the
  content context says, the evacuation layer's CSS forbids animations and transitions on it, and a takeover calls
  `Display.settle()`, which ends a running transition at once. Program entries that are announcements, evacuation
  or emergency overrides (`isUrgent`) get no transition and no entrance effects. Announcement banners and cards lost
  their slide-in/pop-in animations and appear at once. Tested in vitest (alarm offered in the middle of a transition:
  layer visible synchronously, no effect classes, transition ended, acknowledgement without waiting) and in the
  browser (`frontend/e2e/motion.mjs`: drill raised during a 4.5 s fade, takeover with no running animations in the
  layer, the transition cut short).

## Consequences

- Existing playlists, layouts and screens behave exactly as before until someone picks a transition.
- During a transition two slides are in the DOM for up to 5 s (video and code elements of the old slide keep
  running until it is removed); on very small players a *Fade* is the cheapest effect, and *Reduce motion* is the
  switch for hardware that stutters.
- A transition starts when the new slide is due, so the new slide's time on screen includes the transition.
- Message overrides and single layouts cut; transitions are a playlist feature only.

## Alternatives considered

- **Transitions as a layout property**: one layout appears in many playlists and as a single slide; the playlist is
  where "what comes next" is known.
- **Theme-wide transition token**: the existing token defaulted to *fade*, wiring it up would have changed every
  screen at once; and it cannot express per-item choices.
- **Web Animations API** instead of CSS classes: equivalent under the CSP, but CSS classes are inspectable,
  overridable by the reduced-motion rules and testable in jsdom.
- **Timer driven by `requestAnimationFrame`**: smooth everywhere, but a continuous main-thread loop on small players;
  a compositor CSS animation costs nothing between slide changes.
