// SPDX-License-Identifier: AGPL-3.0-or-later
// Map editor model (ADR-0027): data from /e/<event>/venues/<venue>/map/data/ and pure geometry helpers.
// Positions are metres on the floor plan; the SVG viewBox is in metres too.

export interface MapPoint {
  id: string; kind: string; name: string; x: number; y: number; stepFree: boolean; zone: string | null;
  next: string | null; noWayOut: boolean;
}
export interface MapEdge { id: string; a: string; b: string; oneWay: boolean; stepFree: boolean; elsewhere: string | null }
export interface MapZone { id: string; name: string; color: string; area: [number, number][] | null }
export interface LayerItem {
  id: string; label: string; placed: boolean; floor: string | null; x: number | null; y: number | null;
  facing: number | null; state?: string;
}
export interface MapLayer { key: string; title: string; editable: boolean; items: LayerItem[] }
export interface MapPlan { url: string; width: number; height: number; metresPerPx: number; scaled: boolean }
export interface MapData {
  floor: string | null;
  floors: { id: string; label: string; level: number; hasPlan: boolean }[];
  plan: MapPlan | null;
  points: MapPoint[];
  elsewhere: Record<string, { name: string; floor: string }>;
  edges: MapEdge[];
  zones: MapZone[];
  layers: MapLayer[];
  kinds: [string, string][];
  canEdit: boolean;
}
export interface Box { x: number; y: number; w: number; h: number }

/** One letter per kind, so kinds are never told apart by colour alone. */
export const GLYPHS: Record<string, string> = {
  waypoint: "W", door: "D", stairs: "S", lift: "L", exit: "E", assembly: "A",
};

export const r3 = (n: number): number => Math.round(n * 1000) / 1000;

/** The area to show: the plan, else everything drawn, else 100 × 60 m; with a margin. */
export function extent(data: MapData): Box {
  if (data.plan) {
    const w = data.plan.width * data.plan.metresPerPx, h = data.plan.height * data.plan.metresPerPx;
    return pad({ x: 0, y: 0, w, h });
  }
  const xs: number[] = [], ys: number[] = [];
  for (const p of data.points) { xs.push(p.x); ys.push(p.y); }
  for (const z of data.zones) for (const [x, y] of z.area ?? []) { xs.push(x); ys.push(y); }
  for (const l of data.layers) for (const i of l.items) if (i.placed && i.x !== null && i.y !== null) {
    xs.push(i.x); ys.push(i.y);
  }
  if (!xs.length) return pad({ x: 0, y: 0, w: 100, h: 60 });
  const minX = Math.min(...xs), minY = Math.min(...ys);
  return pad({ x: minX, y: minY, w: Math.max(Math.max(...xs) - minX, 20), h: Math.max(Math.max(...ys) - minY, 12) });
}

function pad(b: Box, f = 0.05): Box {
  return { x: b.x - b.w * f, y: b.y - b.h * f, w: b.w * (1 + 2 * f), h: b.h * (1 + 2 * f) };
}

/** Zoom the view by ``factor`` (> 1: in) keeping the point ``(px, py)`` where it is. */
export function zoom(view: Box, factor: number, px: number, py: number): Box {
  const w = Math.min(Math.max(view.w / factor, 1), 100000), h = view.h * (w / view.w);
  return { x: px - (px - view.x) * (w / view.w), y: py - (py - view.y) * (h / view.h), w, h };
}

export function distance(a: [number, number], b: [number, number]): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

/** A short arrow from ``a`` towards ``b`` (route hint): start, end and the two barb ends. */
export function arrow(a: { x: number; y: number }, b: { x: number; y: number }, length: number, barb: number):
    { x1: number; y1: number; x2: number; y2: number; barbs: [number, number][] } | null {
  const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy);
  if (d < 1e-6) return null;
  const ux = dx / d, uy = dy / d, l = Math.min(length, d * 0.6);
  const x2 = a.x + ux * l, y2 = a.y + uy * l;
  const back = (angle: number): [number, number] => {
    const c = Math.cos(angle), s = Math.sin(angle);
    return [r3(x2 - barb * (ux * c - uy * s)), r3(y2 - barb * (ux * s + uy * c))];
  };
  return { x1: r3(a.x), y1: r3(a.y), x2: r3(x2), y2: r3(y2), barbs: [back(0.5), back(-0.5)] };
}

/** The triangle of a screen facing ``deg`` (clockwise from up) at ``(x, y)`` with size ``s``. */
export function facingTriangle(x: number, y: number, deg: number, s: number): string {
  const rad = (deg * Math.PI) / 180;
  const fx = Math.sin(rad), fy = -Math.cos(rad);
  const tip: [number, number] = [x + fx * s * 3, y + fy * s * 3];
  const left: [number, number] = [x + fy * s * 1.1, y - fx * s * 1.1];
  const right: [number, number] = [x - fy * s * 1.1, y + fx * s * 1.1];
  return [tip, left, right].map(([a, b]) => `${r3(a)},${r3(b)}`).join(" ");
}

/** Facing (degrees, clockwise from up) from a screen at ``a`` towards ``b``. */
export function bearing(a: [number, number], b: [number, number]): number {
  const deg = (Math.atan2(b[0] - a[0], -(b[1] - a[1])) * 180) / Math.PI;
  return Math.round((deg + 360) % 360);
}

/** Plan pixels that ``metres`` correspond to now (for the "Measure" tool). */
export function pixelsFor(metres: number, plan: MapPlan): number {
  return metres / plan.metresPerPx;
}
