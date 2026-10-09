// SPDX-License-Identifier: AGPL-3.0-or-later
// Program resolution on the screen: which entry wins at a time and which slide of its playlist is on.
// Line-by-line twin of apps/playlists/engine.py; both run the vectors in test/fixtures/program-vectors.json.
// Times are integer milliseconds since the epoch, taken from the server-synchronised clock, so every screen
// computes the same slide at the same moment - also offline.
import { condition } from "../renderer/template";

export type Window = [number | null, number | null];
export type ContentRef = { layout: string } | { playlist: string } | { message: string };

export interface Entry {
  id: string; source: string; name: string; priority: number; level?: string; content: ContentRef;
  windows: Window[];
}

export interface Item {
  id: string; layout?: string; playlist?: string; duration: number | null; weight: number; tags: string[];
  when: string; from: number | null; until: number | null;
}

export interface PlaylistData { name?: string; mode: "ordered" | "shuffle" | "weighted"; default: number; items: Item[] }

export interface Program {
  version?: string;
  entries: Entry[];
  playlists: Record<string, PlaylistData>;
  layouts: Record<string, number | null>;
  messages?: Record<string, unknown>;
  horizon?: number;
}

export interface Slide {
  entry: string; layout?: string; message?: string; item?: string; index: number; count: number;
  start: number | null; end: number | null;
}

type Ctx = Record<string, unknown>;
interface Flat { layout: string; duration: number; item: string }

const MAX_DEPTH = 5;
const FALLBACK_MS = 10_000;

export function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function shuffled<T>(items: T[], seed: number): T[] {
  let x = seed >>> 0 || 1;
  const out = [...items];
  for (let i = out.length - 1; i > 0; i--) {
    x = (x ^ (x << 13)) >>> 0;
    x = (x ^ (x >>> 17)) >>> 0;
    x = (x ^ (x << 5)) >>> 0;
    const j = x % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Smooth weighted round robin: weights 3:1 give a a b a, a a b a, ... (no long runs). */
export function weighted<T>(items: T[], weights: number[]): T[] {
  const total = weights.reduce((a, b) => a + b, 0);
  const current = weights.map(() => 0);
  const out: T[] = [];
  for (let n = 0; n < total; n++) {
    weights.forEach((w, i) => { current[i] += w; });
    let best = 0;
    for (let i = 1; i < items.length; i++) if (current[i] > current[best]) best = i;
    current[best] -= total;
    out.push(items[best]);
  }
  return out;
}

function itemActive(item: Item, t: number, ctx: Ctx): boolean {
  if (item.from !== null && item.from !== undefined && t < item.from) return false;
  if (item.until !== null && item.until !== undefined && t >= item.until) return false;
  const tags = item.tags ?? [];
  const screenTags = ((ctx.screen as { tags?: string[] } | undefined)?.tags) ?? [];
  if (tags.length && !tags.some((x) => screenTags.includes(x))) return false;
  return condition(item.when ?? "", ctx);
}

export function flatten(program: Program, pid: string, ctx: Ctx, t: number, cycle: number,
                        stack: string[] = []): Flat[] {
  const pl = program.playlists[pid];
  if (!pl || stack.includes(pid) || stack.length >= MAX_DEPTH) return [];
  let units: Flat[][] = [];
  const weights: number[] = [];
  for (const item of pl.items ?? []) {
    if (!itemActive(item, t, ctx)) continue;
    let slides: Flat[] = [];
    if (item.playlist) slides = flatten(program, item.playlist, ctx, t, cycle, [...stack, pid]);
    else if (item.layout && item.layout in program.layouts) {
      const ms = item.duration || program.layouts[item.layout] || pl.default || FALLBACK_MS;
      slides = [{ layout: item.layout, duration: ms, item: item.id }];
    }
    if (slides.length) {
      units.push(slides);
      weights.push(Math.max(1, Math.trunc(item.weight || 1)));
    }
  }
  if (pl.mode === "weighted") units = weighted(units, weights);
  else if (pl.mode === "shuffle") units = shuffled(units, fnv1a(`${pid}:${cycle}`));
  return units.flat();
}

function contains(w: Window, t: number): boolean {
  return (w[0] === null || w[0] <= t) && (w[1] === null || t < w[1]);
}

/** Entries with a window containing t, best first: priority, then later start, then list order. */
export function candidates(program: Program, t: number): [Entry, Window][] {
  const found: { key: [number, number, number]; entry: Entry; w: Window }[] = [];
  program.entries.forEach((entry, n) => {
    const w = entry.windows.find((x) => contains(x, t));
    if (w) found.push({ key: [-entry.priority, -(w[0] ?? -1), n], entry, w });
  });
  found.sort((a, b) => a.key[0] - b.key[0] || a.key[1] - b.key[1] || a.key[2] - b.key[2]);
  return found.map((f) => [f.entry, f.w]);
}

function slideOf(program: Program, ctx: Ctx, t: number, entry: Entry, w: Window): Slide | null {
  const c = entry.content as Partial<Record<"layout" | "playlist" | "message", string>>;
  const base = { entry: entry.id, index: 0, count: 1, start: w[0], end: w[1] };
  if (c.message !== undefined) return c.message in (program.messages ?? {}) ? { ...base, message: c.message } : null;
  if (c.layout !== undefined) return c.layout in program.layouts ? { ...base, layout: c.layout } : null;
  const pid = c.playlist as string;
  const anchor = w[0] ?? 0;
  let slides = flatten(program, pid, ctx, t, 0);
  const total = slides.reduce((a, s) => a + s.duration, 0);
  if (!total) return null;
  const cycle = Math.floor((t - anchor) / total);
  if (cycle) slides = flatten(program, pid, ctx, t, cycle);
  let pos = t - anchor - cycle * total;
  let start = anchor + cycle * total;
  for (let i = 0; i < slides.length; i++) {
    const s = slides[i];
    if (pos < s.duration) {
      let end = start + s.duration;
      if (w[1] !== null) end = Math.min(end, w[1]);
      return { ...base, layout: s.layout, item: s.item, index: i, count: slides.length, start, end };
    }
    pos -= s.duration;
    start += s.duration;
  }
  return null;
}

/** The slide on screen at t; an entry with nothing to show here gives way to the next one. */
export function slideAt(program: Program, ctx: Ctx, t: number): Slide | null {
  for (const [entry, w] of candidates(program, t)) {
    const slide = slideOf(program, ctx, t, entry, w);
    if (slide) return slide;
  }
  return null;
}

/** The earliest time after t when the result can change (slide end or any window boundary). */
export function nextChange(program: Program, t: number, slide: Slide | null): number | null {
  const times: number[] = slide?.end != null ? [slide.end] : [];
  for (const e of program.entries) {
    for (const [s, en] of e.windows) {
      if (s !== null && s > t) times.push(s);
      if (en !== null && en > t) times.push(en);
    }
  }
  return times.length ? Math.min(...times) : null;
}
