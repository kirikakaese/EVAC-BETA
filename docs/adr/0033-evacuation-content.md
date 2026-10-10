# ADR-0033: Evacuation content on screens

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.7 and brief §8.4:
- evacuation layouts built with the normal editor, with guardrails (contrast, text size for the viewing distance,
  required elements; warnings in the editor, publishing blocked for hard failures);
- a built-in, non-deletable fallback layout (ISO 7010 pictograms, English text), always cached on every screen;
- text rotation with a signs-only option;
- arrows computed per screen with a manual override (ADR-0030);
- an alarm sound and pre-rendered messages in a loop.

## Decision

- **Safety signs** are a renderer element `pictogram` (`E001`/`E002` emergency exit, `E003` first aid, `E007`
  assembly point, `W001` general warning, `arrow`). The ISO 7010 signs are the published artwork, imported
  from the npm package `@iso-safety-signs/core` (MIT, pinned dev dependency) by
  `frontend/scripts/import-iso7010.mjs` into `src/renderer/iso7010.generated.ts`. The import only turns inline
  `style` declarations into SVG attributes, because the strict CSP blocks inline styles, and it refuses any
  other active content. The build checks that the generated file is current, and the bundles carry the licence
  notice. The direction arrow and the all-clear check mark are not ISO 7010 signs and are drawn by EVAC. The
  `arrow` sign with direction `auto` shows the
  screen's computed way out and hides itself without one. Templates get `{{ evac.text }}`,
  `{{ evac.direction }}`, `{{ evac.stage }}`, `{{ evac.target }}` and `{{ evac.drill }}`.
- **Guardrails** (`apps/evacuation/lint.py`, pure, mypy strict) check every layout used by a stage:
  - required elements: a sign and a text, and in the zones model also a direction;
  - WCAG contrast of each text against what is behind it: error below 4.5:1, warning below 7:1;
  - letter height for the viewing distance: at least 1/250 of it, using *viewing distance* and *screen height*
    from Settings → Evacuation; error below half, warning below.
  
  They run through a new plugin hook `r.layout_check(fn)`. The editor lists findings on load and save, and
  publishing (now or scheduled) is refused while an error remains. A stage cannot be given a failing layout.
- **Stage content** (`StageContent` per event and stage, page *Screen content*): layout or built-in, texts shown
  in turn (with an optional signs-only frame), rotation time, sound (siren, gong, alert tone, none), repeat time,
  and a spoken message pre-rendered with Piper when the announcements module and a voice are installed.
- **Built-in layout**: lives in the player's code (cannot be deleted, is always cached with the app). It shows
  the stage's sign, the computed arrow, the stage name, the current text and the direction. It is also used
  when an own layout fails to render; the acknowledgement then says *fallback*.
- **Per-screen payload** (`feed.py`): state shown (event and zones, highest severity), drill marker, role
  (`evacuation_role` display setting: participant, info, excluded), guidance, texts, sound, speech URL (signed
  per screen), layout, the event's message `seq` and a content version, signed with the alarm key (ADR-0034).
- **Player** (`evac.ts`):
  - The evacuation layer sits above everything, including the dim/sleep overlay, and turns with the screen's
    rotation.
  - Shelter, evacuate and all clear take over participating screens.
  - Attention, and every stage on *info* screens, is a banner over the normal content; staff alert is silent.
  - Overlays and announcement speech pause during a takeover. The siren loops at the set interval, followed
    by the spoken message.
- **Pushes**: every state change, blocked point, stage content save and relevant settings change bumps `seq` in
  the same transaction and, after commit, sends each screen its payload (`evac.state`). Changes in one
  transaction send once. Screens also fetch their payload on start, on reconnect and every minute.

## Consequences

- Screens show the official sign artwork. A new sign means adding its code to the import script and running
  `npm run iso7010`.
- Audio needs the kiosk's autoplay permission (ADR-0017); a refused autoplay is skipped silently.
