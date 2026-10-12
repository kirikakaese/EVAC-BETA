// SPDX-License-Identifier: AGPL-3.0-or-later
// Display settings of this screen (namespace "display", set per event, screen group or screen): rotation,
// overscan, scale and keystone are applied to the player root; dim and sleep times put an overlay above it.

export interface DisplaySettings {
  rotation?: string; overscan?: number; scale?: number; keystone_x?: number; keystone_y?: number;
  dim_from?: string; dim_until?: string; dim_level?: number; sleep_from?: string; sleep_until?: string;
  audio?: boolean; volume?: number; daily_reload?: string; expected_resolution?: string; evacuation_role?: string;
  wall_columns?: number; wall_rows?: number; wall_column?: number; wall_row?: number; wall_bezel?: number;
  /** no slide transitions or entrance effects (ADR-0051) */
  reduce_motion?: boolean;
}

/** Video wall: this screen's tile of a ``columns`` × ``rows`` wall (1-based), or null when it is a single screen. */
export function wallTile(s: DisplaySettings): { cols: number; rows: number; col: number; row: number;
                                                 bezel: number } | null {
  const cols = Math.max(1, Math.min(8, Math.round(s.wall_columns ?? 1)));
  const rows = Math.max(1, Math.min(8, Math.round(s.wall_rows ?? 1)));
  if (cols === 1 && rows === 1) return null;
  return { cols, rows, col: Math.max(1, Math.min(cols, Math.round(s.wall_column ?? 1))),
           row: Math.max(1, Math.min(rows, Math.round(s.wall_row ?? 1))),
           bezel: Math.max(0, Math.min(10, s.wall_bezel ?? 0)) };
}

/** "HH:MM" of ``now`` in ``timezone`` (falls back to the device's zone). */
export function localHHMM(now: number, timezone?: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23",
                                              timeZone: timezone || undefined }).format(new Date(now));
  } catch {
    return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
      .format(new Date(now));
  }
}

/** Is ``hhmm`` inside [from, until)? A range whose end is before its start runs past midnight. */
export function inRange(hhmm: string, from?: string, until?: string): boolean {
  if (!from || !until || from === until) return false;
  return from < until ? hhmm >= from && hhmm < until : hhmm >= from || hhmm < until;
}

export type DisplayState = "on" | "dimmed" | "sleeping";

export function displayState(s: DisplaySettings, hhmm: string): DisplayState {
  if (inRange(hhmm, s.sleep_from, s.sleep_until)) return "sleeping";
  if (inRange(hhmm, s.dim_from, s.dim_until)) return "dimmed";
  return "on";
}

/** CSS for the player root: rotation (swapping width/height for portrait), overscan (insets the content, not the test pattern), scale, keystone. */
export function rootTransform(s: DisplaySettings, wall = true): { width: string; height: string; transform: string;
                                                                  overscan: string } {
  const rot = Number(s.rotation ?? 0) || 0;
  const portrait = rot === 90 || rot === 270;
  const tile = wall ? wallTile(s) : null;
  if (tile) {
    // the stage spans the whole wall (bezel: the gap between two displays, in % of one display) and is moved so
    // that this display's tile sits in the viewport; rotation and keystone do not apply to wall tiles
    const unitW = 100 + tile.bezel;
    const unitH = 100 + tile.bezel;
    const width = tile.cols * 100 + (tile.cols - 1) * tile.bezel;
    const height = tile.rows * 100 + (tile.rows - 1) * tile.bezel;
    const cx = ((tile.col - 1) * unitW + 50) / width * 100;
    const cy = ((tile.row - 1) * unitH + 50) / height * 100;
    return { width: `${width}vw`, height: `${height}vh`, overscan: "0%",
             transform: `translate(${-cx.toFixed(4)}%, ${-cy.toFixed(4)}%)` };
  }
  const parts = ["translate(-50%, -50%)"];
  if (rot) parts.push(`rotate(${rot}deg)`);
  if (s.keystone_x || s.keystone_y) {
    parts.push("perspective(1200px)");
    if (s.keystone_y) parts.push(`rotateX(${s.keystone_y}deg)`);
    if (s.keystone_x) parts.push(`rotateY(${s.keystone_x}deg)`);
  }
  const scale = (s.scale ?? 100) / 100;
  if (scale !== 1) parts.push(`scale(${scale})`);
  const over = Math.max(0, Math.min(15, s.overscan ?? 0));
  return { width: portrait ? "100vh" : "100vw", height: portrait ? "100vw" : "100vh", transform: parts.join(" "),
           overscan: `${over}%` };
}

/** ``wall: false`` for the evacuation layer: an alarm shows complete on every display of a wall. */
export function applyRoot(root: HTMLElement, s: DisplaySettings, wall = true): void {
  const css = rootTransform(s, wall);
  root.classList.add("evac-root");
  root.style.width = css.width;
  root.style.height = css.height;
  root.style.transform = css.transform;
  root.style.setProperty("--evac-overscan", css.overscan);
}

/** The dim/sleep overlay (one element above everything, never catching clicks). */
export function applyState(state: DisplayState, s: DisplaySettings, doc: Document = document): void {
  let ov = doc.getElementById("evac-dim");
  if (state === "on") {
    ov?.remove();
    return;
  }
  if (!ov) {
    ov = doc.createElement("div");
    ov.id = "evac-dim";
    ov.setAttribute("aria-hidden", "true");
    doc.body.appendChild(ov);
  }
  const level = state === "sleeping" ? 0 : Math.max(10, Math.min(90, s.dim_level ?? 40));
  ov.style.opacity = String(1 - level / 100);
  ov.dataset.state = state;
}
