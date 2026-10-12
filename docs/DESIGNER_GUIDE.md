# Designer Guide

Everything about how screens look: themes, fonts, files, layouts and widgets. All of it lives under
**Design & assets** in an event (module *Screen content*, permissions `content.view`, `content.edit`,
`content.publish`).

## Themes

A theme is a set of **design tokens**: colours for dark and light mode (background, surface, text, muted text,
primary, accent, success, warning, danger), body and heading font, base text size, type scale, line height,
letter spacing, spacing, corner radius, shadow, background (colour, gradient or image), logo and a transition
style for code elements (`--evac-transition`; slide transitions are set on playlists, see *Motion*). A theme can inherit from another theme; ticked *inherited* fields come from the parent (or the EVAC
defaults). *Use for this event's screens* switches every screen at once. Layouts can pick a different theme.

In layouts, colours can refer to tokens (*Primary*, *Accent*, …): change the theme and every layout follows.

## Fonts

Upload WOFF2, WOFF, TTF or OTF files, also variable fonts. *Keep Latin characters only* makes them much smaller
(arrows and common symbols stay). EVAC serves fonts itself, so screens work without internet. Built in:
**Atkinson Hyperlegible** (made for legibility; use it for safety and wayfinding content) and **Inter**.

## Files

Images, SVG, video, audio, PDF and Lottie. EVAC makes optimised versions (WebP/AVIF, MP4/WebM with poster,
normalised audio), removes photo metadata and cleans SVGs. Give every image an *alternative text*. Files that
are used by a theme or layout cannot be deleted.

## Layouts and the editor

*Layouts → New layout* picks a screen size (Full HD landscape or portrait, 4K, 4:3, LED strips) and opens the
editor:

- **Add** elements on the left, select them on the canvas or in **Layers**; shift-click selects several.
- Drag to move, drag the handles to resize. Elements snap to the grid and to the edges and centres of other
  elements and the canvas (a pink guide shows it); hold **Alt** to move freely.
- **Properties** on the right: position and size, content, style (colour, background, font, size, weight,
  alignment, spacing, border, radius, shadow, opacity), entrance effect (see *Motion*), *Show only if*, hidden,
  locked.
  With several elements selected: align left/centre/right/top/middle/bottom.
- Keys: arrows nudge (shift: 10×), Delete, Ctrl+Z / Ctrl+Shift+Z undo/redo, Ctrl+D duplicate, Ctrl+C / Ctrl+V
  copy and paste (also between layouts), Ctrl+S save, Escape deselect.
- Positions and sizes are percentages of the screen and text sizes are percentages of its height, so the
  editor preview looks exactly like the screens (they use the same renderer).

**Save** stores a new **version** each time. Screens show the **published** version: *Publish* puts the
current draft live; on the layout page you can publish later (scheduled), publish an older version, or
*Restore* an old version as the draft. If somebody else saved in the meantime, your save is refused with a
notice; the editor also warns when someone else opened the layout in the last two minutes.

The **default layout** of the event is what screens show when no playlist, schedule or override applies.

## Playlists, schedules and overrides

Under **Playback**. A **playlist** shows layouts in turn; each layout stays for the item's *seconds*, else the
layout's *Seconds on screen (playlists)* (editor, canvas properties), else the playlist default. Order: *in
order*, *shuffled* (the same order on every screen, new each round) or *weighted* (weight 3 = three times as
often as 1, spread evenly). Items can be limited:

- *Only on screens tagged*: `stage, foyer` — the screen needs one of these tags;
- *Show only if*: the same conditions as in templates, e.g. `screen.zone == "North"`, `not screen.room`;
- *From / until*: e.g. a "doors open soon" slide only in the hour before the doors open;
- a **nested playlist** plays all its items at that position.

A playlist's *Slide transition* (and each item's) decides how the next slide comes in; see *Motion*.

A **schedule** shows a playlist or layout on chosen screens at chosen times; an **override** pushes a message,
layout or playlist at once. *Preview* shows any screen at any time with the same engine the screens use.

## Motion

Three kinds of motion, all optional and all off for existing content (ADR-0051):

- **Slide transitions** (*Playback → Playlists*): *Slide transition* of a playlist — *None (cut)*, *Fade* (the
  next slide fades in over the current one), *Slide to the left*, *Slide up*, *Zoom* — with a duration in ms (up to
  5,000; screens keep it below half of the slide). An item can pick its own transition into its slide, or *None*.
  A nested playlist uses its own items' transitions. All screens change slides at the same moment, so a
  transition runs in step across a room.
- **Entrance effects** (editor, *Animation* in the properties): *Fade*, *Slide up*, *Slide in* (from the right),
  *Zoom in*, with a duration (up to 10 s) and a delay (up to 60 s) after the slide appears. They play on screens
  and in previews, not while editing: *Play animations* in the editor toolbar plays them once. Stagger the delays
  (0, 200, 400 ms) to bring a list in line by line.
- **Slide timer** (element *Slide timer*): a bar that counts down the time the slide stays on screen. Its colour is
  the element's *Colour* (default: accent), the track behind it the *Background*; its thickness is the element's
  height (or width when *Vertical*). Options: *Horizontal* / *Vertical*, the bar *Shrinks* or *Grows*, *Start from
  the other end* (right instead of left, top instead of bottom), and *Without an end time*: *Show a full bar* or
  *Hide*. The timer counts only playlist slides that change; a playlist with one slide, a schedule or override that
  shows a single layout, or the default layout have no end, so the timer shows full (or hides). In the editor and
  previews it loops over the layout's *Seconds on screen (playlists)* (10 s when empty).

Screens with *Reduce motion* (display setting) or whose device asks for reduced motion show no transitions or
entrance effects; slide timers still count down, in one-second steps. **Evacuation and emergency content is never
animated**: an alarm takeover, a full-screen announcement or an emergency override appears at once, cuts a running
transition short and plays no entrance effects (also when its layout has some); announcement banners and cards
appear at once as well.

## Widgets

| Widget | What it shows |
|---|---|
| Text | text with template variables, *shrink to fit*, maximum lines, ticker |
| Rich text | paragraphs with `**bold**` and `*italic*` |
| Image, Slideshow | images from the library (slideshows change at the same moment on every screen) |
| Video, Audio | from the library, muted and looping by default |
| Shape | rectangle, ellipse, line |
| QR code | for any text or link (template variables allowed) |
| Clock, Date | in the event time zone (or another one), synchronised with the server |
| Countdown | to a date and time, with a text when it is over |
| Slide timer | a bar that shrinks or grows over the time the slide stays on screen (see *Motion*) |
| Program | *now and next* on a stage (automatic: the stage in the screen's room), *the day's sessions* or *live changes*; delays, cancellations and room changes show as badges (Program module) |

A widget that fails (missing file, wrong input) shows nothing on a public screen; the editor outlines it.

## Code mode

The **Code** element (permission *Write code elements*, `content.code`) runs your own HTML, CSS and JavaScript
in a sandbox: it cannot reach the network, the page or the screen's storage, and cannot navigate the screen. Use
the three fields (a `<script>` tag or `style=""` attribute inside the HTML does not run). Tick what the code
may read:

| Data | In the code |
|---|---|
| Event | `evac.data.event.name`, `evac.data.event.slug` |
| Screen | `evac.data.screen.name`, `.zone`, `.room`, `.venue`, `.tags`, `.groups` |
| Time | `evac.now()` — the server-synchronised time (ms), and `evac.data.timezone` |
| Files | `evac.data.assets[id].urls.webp` (and `original`, `mp4`, …) for the files you pick |

```js
evac.onData((d) => {                       // called when the data arrives (and when it changes)
  document.getElementById("t").textContent = `${d.event.name} · ${new Date(evac.now()).toLocaleTimeString()}`;
});
evac.log("started");                       // shows up in the screen's log (Screens → Fetch logs)
```

Theme colours are available as CSS variables (`var(--evac-color-accent)`). Errors in the code are reported to
the screen's log; the rest of the slide keeps working. People without the permission can move or delete code
elements but not change their code.

## Template variables

Text, rich text and QR content may contain variables:

| Variable | Example |
|---|---|
| `{{ event.name }}`, `{{ event.slug }}` | Demo Camp |
| `{{ screen.name }}`, `{{ screen.zone }}`, `{{ screen.room }}`, `{{ screen.venue }}` | Foyer left · North |
| `{{ now\|time }}`, `{{ now\|date }}`, `{{ now\|date:"short" }}` | 18:30 · Wednesday 1 July 2026 · 1 Jul |

Filters: `upper`, `lower`, `title`, `truncate:20`, `default:"text"`, `date:"long|short|weekday|iso"`,
`time:"HH:mm|HH:mm:ss|h:mm a"`, `join:", "`. Conditions:
`{% if screen.zone %}Zone {{ screen.zone }}{% else %}Welcome{% endif %}` (also `not x`, `x == "y"`,
`x != "y"`). *Show only if* on an element takes the same conditions (e.g. `screen.zone == "North"`).
Variables are inserted as plain text, so they can never inject markup.

## Still to come in phase 1

Responsive constraints (anchors) for one layout on very different
aspect ratios; the no-code widget builder and data widgets; ISO 7010 pictograms (with the evacuation phase);
`.evacpack` import/export.
