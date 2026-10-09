// SPDX-License-Identifier: AGPL-3.0-or-later
// Display settings of this screen (namespace "display", set per event, screen group or screen): rotation,
// overscan, scale and keystone are applied to the player root; dim and sleep times put an overlay above it.

export interface DisplaySettings {
  rotation?: string; overscan?: number; scale?: number; keystone_x?: number; keystone_y?: number;
  dim_from?: string; dim_until?: string; dim_level?: number; sleep_from?: string; sleep_until?: string;
  audio?: boolean; volume?: number; daily_reload?: string; expected_resolution?: string; evacuation_role?: string;
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
export function rootTransform(s: DisplaySettings): { width: string; height: string; transform: string;
                                                      overscan: string } {
  const rot = Number(s.rotation ?? 0) || 0;
  const portrait = rot === 90 || rot === 270;
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

export function applyRoot(root: HTMLElement, s: DisplaySettings): void {
  const css = rootTransform(s);
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
