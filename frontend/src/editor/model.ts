// SPDX-License-Identifier: AGPL-3.0-or-later
// Editor state operations (pure functions, unit tested): history, element creation, snapping, alignment.
import type { Frame, LayoutData, LayoutElement } from "../renderer/types";

export const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

export class History {
  private past: LayoutData[] = [];
  private future: LayoutData[] = [];
  constructor(private limit = 200) {}

  push(state: LayoutData): void {
    this.past.push(clone(state));
    if (this.past.length > this.limit) this.past.shift();
    this.future = [];
  }

  undo(current: LayoutData): LayoutData | null {
    const prev = this.past.pop();
    if (!prev) return null;
    this.future.push(clone(current));
    return prev;
  }

  redo(current: LayoutData): LayoutData | null {
    const next = this.future.pop();
    if (!next) return null;
    this.past.push(clone(current));
    return next;
  }

  get canUndo(): boolean { return this.past.length > 0; }
  get canRedo(): boolean { return this.future.length > 0; }
}

export function newId(existing: Iterable<string>, prefix: string): string {
  const used = new Set(existing);
  for (let i = 1; ; i++) if (!used.has(`${prefix}${i}`)) return `${prefix}${i}`;
}

const DEFAULTS: Record<string, Partial<LayoutElement>> = {
  text: { frame: { x: 10, y: 10, w: 50, h: 12 }, style: { fontSize: 6 }, props: { text: "Text", autofit: true } },
  richtext: { frame: { x: 10, y: 10, w: 50, h: 30 }, style: { fontSize: 4 },
              props: { text: "A paragraph with **bold** and *italic* text." } },
  image: { frame: { x: 10, y: 10, w: 30, h: 30 }, props: { fit: "contain" } },
  slideshow: { frame: { x: 10, y: 10, w: 50, h: 50 }, props: { assets: [], interval: 8, fit: "cover" } },
  video: { frame: { x: 10, y: 10, w: 50, h: 50 }, props: { loop: true, muted: true, fit: "cover" } },
  audio: { frame: { x: 2, y: 2, w: 8, h: 8 }, props: { loop: true } },
  shape: { frame: { x: 10, y: 10, w: 30, h: 20 }, style: { background: "token:primary", radius: 1 },
           props: { shape: "rect" } },
  qr: { frame: { x: 70, y: 60, w: 20, h: 30 }, style: { background: "#ffffff", padding: 1 },
        props: { text: "https://example.org" } },
  clock: { frame: { x: 70, y: 5, w: 25, h: 12 }, style: { fontSize: 8, textAlign: "right", tabularNumbers: true },
           props: { format: "HH:mm" } },
  countdown: { frame: { x: 25, y: 40, w: 50, h: 20 }, style: { fontSize: 12, textAlign: "center",
                                                                   tabularNumbers: true },
               props: { target: "", format: "auto", finished: "Now!" } },
  date: { frame: { x: 5, y: 5, w: 40, h: 8 }, style: { fontSize: 4 }, props: { format: "long" } },
  data: { frame: { x: 10, y: 15, w: 45, h: 60 }, style: { fontSize: 4.5 }, props: { widget: "" } },
  code: { frame: { x: 10, y: 10, w: 40, h: 30 },
          props: { html: '<div class="box"><span id="t"></span></div>',
                   css: ".box { display: grid; place-items: center; height: 100%; font-size: 12vh; "
                        + "color: var(--evac-color-accent, #ffd400); }",
                   js: 'evac.onData(() => {\n  const t = document.getElementById("t");\n'
                       + '  const tick = () => { t.textContent = new Date(evac.now()).toLocaleTimeString(); };\n'
                       + '  tick();\n  setInterval(tick, 1000);\n});',
                   data: ["time"] } },
};

export function createElement(type: string, existing: LayoutElement[], name: string): LayoutElement {
  const d = clone(DEFAULTS[type] ?? DEFAULTS.text);
  const offset = (existing.length % 8) * 2;
  const frame = d.frame as Frame;
  return { id: newId(existing.map((e) => e.id), type), type, name, ...d,
           frame: { ...frame, x: frame.x + offset, y: frame.y + offset } } as LayoutElement;
}

export function duplicate(el: LayoutElement, existing: LayoutElement[]): LayoutElement {
  const copy = clone(el);
  copy.id = newId(existing.map((e) => e.id), `${el.type}`);
  copy.name = `${el.name ?? el.type} copy`;
  copy.frame = { ...copy.frame, x: copy.frame.x + 2, y: copy.frame.y + 2 };
  return copy;
}

const round = (v: number, step: number) => Math.round(v / step) * step;

/** Snap a value to the grid and to nearby guides (other edges, centres, canvas edges). Returns the snapped
 *  value and the guide it snapped to (for drawing guide lines). */
export function snap(value: number, guides: number[], { grid = 0.5, threshold = 0.8 } = {}): [number, number | null] {
  let best: number | null = null;
  for (const g of guides) if (Math.abs(g - value) <= threshold && (best === null || Math.abs(g - value) <
                                                                       Math.abs(best - value))) best = g;
  return best !== null ? [best, best] : [round(value, grid), null];
}

export function guidesFor(elements: LayoutElement[], exclude: Set<string>, axis: "x" | "y"): number[] {
  const out = [0, 50, 100];
  for (const e of elements) {
    if (exclude.has(e.id)) continue;
    const pos = axis === "x" ? e.frame.x : e.frame.y, size = axis === "x" ? e.frame.w : e.frame.h;
    out.push(pos, pos + size / 2, pos + size);
  }
  return out;
}

/** Move a frame so that its left/centre/right (top/middle/bottom) edge snaps; returns the new position. */
export function snapMove(pos: number, size: number, guides: number[], opts?: { grid?: number; threshold?: number })
  : [number, number | null] {
  const candidates: [number, number | null, number][] = [0, size / 2, size].map((off) => {
    const [v, g] = snap(pos + off, guides, opts);
    return [v - off, g, g === null ? Infinity : Math.abs(v - (pos + off))];
  });
  const hit = candidates.filter((c) => c[1] !== null).sort((a, b) => a[2] - b[2])[0];
  return hit ? [hit[0], hit[1]] : [round(pos, opts?.grid ?? 0.5), null];
}

export type AlignMode = "left" | "center" | "right" | "top" | "middle" | "bottom";

export function align(elements: LayoutElement[], ids: Set<string>, mode: AlignMode): LayoutElement[] {
  const sel = elements.filter((e) => ids.has(e.id));
  if (!sel.length) return elements;
  const single = sel.length === 1;
  const minX = single ? 0 : Math.min(...sel.map((e) => e.frame.x));
  const maxX = single ? 100 : Math.max(...sel.map((e) => e.frame.x + e.frame.w));
  const minY = single ? 0 : Math.min(...sel.map((e) => e.frame.y));
  const maxY = single ? 100 : Math.max(...sel.map((e) => e.frame.y + e.frame.h));
  return elements.map((e) => {
    if (!ids.has(e.id)) return e;
    const f = { ...e.frame };
    if (mode === "left") f.x = minX;
    if (mode === "right") f.x = maxX - f.w;
    if (mode === "center") f.x = (minX + maxX) / 2 - f.w / 2;
    if (mode === "top") f.y = minY;
    if (mode === "bottom") f.y = maxY - f.h;
    if (mode === "middle") f.y = (minY + maxY) / 2 - f.h / 2;
    return { ...e, frame: f };
  });
}

export function reorder(elements: LayoutElement[], id: string, delta: number): LayoutElement[] {
  const i = elements.findIndex((e) => e.id === id);
  const j = Math.min(elements.length - 1, Math.max(0, i + delta));
  if (i < 0 || i === j) return elements;
  const out = [...elements];
  const [item] = out.splice(i, 1);
  out.splice(j, 0, item);
  return out;
}

export function resize(frame: Frame, handle: string, dx: number, dy: number, min = 1): Frame {
  const f = { ...frame };
  if (handle.includes("w")) { f.x = Math.min(frame.x + dx, frame.x + frame.w - min); f.w = frame.w - (f.x - frame.x); }
  if (handle.includes("e")) f.w = Math.max(min, frame.w + dx);
  if (handle.includes("n")) { f.y = Math.min(frame.y + dy, frame.y + frame.h - min); f.h = frame.h - (f.y - frame.y); }
  if (handle.includes("s")) f.h = Math.max(min, frame.h + dy);
  return f;
}

export const r2 = (v: number) => Math.round(v * 100) / 100;
