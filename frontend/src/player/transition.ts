// SPDX-License-Identifier: AGPL-3.0-or-later
// Slide transitions (ADR-0051): which transition brings the next slide in. A playlist item carries its resolved
// transition in the program (``item.transition``, left out for a cut). Nothing animates for content that must
// appear at once: evacuation, full-screen announcements and emergency overrides, nor with reduced motion.
import type { Entry, Program, Slide } from "../program/engine";

export type TransitionEffect = "fade" | "slide-left" | "slide-up" | "zoom";
export interface Transition { effect: TransitionEffect; ms: number }

export const EFFECTS: readonly TransitionEffect[] = ["fade", "slide-left", "slide-up", "zoom"];
export const MAX_TRANSITION_MS = 5000;
/** shorter transitions are not worth drawing */
const MIN_TRANSITION_MS = 50;

/** Content that is never delayed or animated in (brief §8, ADR-0051). */
export function isUrgent(entry: Pick<Entry, "id" | "source" | "level"> | undefined | null): boolean {
  if (!entry) return false;
  return entry.source === "announcement" || entry.source === "evacuation" || entry.id.startsWith("evacuation")
    || entry.id.startsWith("announcement:") || entry.level === "emergency";
}

/** The transition into ``slide`` (null: a cut). It is kept below half of the slide's time on screen. */
export function transitionFor(program: Program | null, slide: Slide | null,
                              opts: { reduced?: boolean; urgent?: boolean } = {}): Transition | null {
  if (!program || !slide?.item || opts.reduced || opts.urgent) return null;
  let found: { effect?: string; ms?: number } | undefined;
  for (const pl of Object.values(program.playlists ?? {})) {
    const item = pl.items?.find((i) => i.id === slide.item);
    if (item) {
      found = item.transition;
      break;
    }
  }
  if (!found || !EFFECTS.includes(found.effect as TransitionEffect)) return null;
  let ms = Math.min(Number(found.ms) || 0, MAX_TRANSITION_MS);
  if (slide.start !== null && slide.end !== null) ms = Math.min(ms, (slide.end - slide.start) / 2);
  if (!(ms >= MIN_TRANSITION_MS)) return null;
  return { effect: found.effect as TransitionEffect, ms: Math.round(ms) };
}
