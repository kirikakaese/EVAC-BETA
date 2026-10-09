// SPDX-License-Identifier: AGPL-3.0-or-later
// Keeping a kiosk alive without a person nearby: a guarded reload (never more than 3 in 10 minutes, so a
// broken page cannot reload itself in a loop), crash detection across restarts, a memory watchdog and the
// daily reload from the display settings.
import { log, recordError } from "./report";

const RELOADS = "evac.player.reloads";
const ALIVE = "evac.player.alive";
const MAX_RELOADS = 3;
const WINDOW_MS = 10 * 60_000;

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* storage unavailable: no guard history, still safe */ }
}

export function recentReloads(now = Date.now()): number[] {
  try {
    return (JSON.parse(read(RELOADS) ?? "[]") as number[]).filter((t) => now - t < WINDOW_MS);
  } catch {
    return [];
  }
}

/** Reload unless that would be the 4th reload in 10 minutes. ``force`` (staff command) skips the guard. */
export function safeReload(reason: string, opts: { force?: boolean; win?: { reload(): void } } = {}): boolean {
  const now = Date.now();
  const recent = recentReloads(now);
  if (!opts.force && recent.length >= MAX_RELOADS) {
    recordError(`reload (${reason}) skipped: ${recent.length} reloads in the last 10 minutes`);
    return false;
  }
  write(RELOADS, JSON.stringify([...recent, now]));
  log("info", `reload: ${reason}`);
  markClean();
  (opts.win ?? location).reload();
  return true;
}

/** ``"crashed"``-style note when the previous run ended without saying goodbye (browser crash, power cut). */
export function bootCheck(now = Date.now()): string {
  const prev = read(ALIVE);
  write(ALIVE, String(now));
  if (!prev || prev === "clean") return "";
  const at = Number(prev);
  return Number.isFinite(at) ? `restarted after an unclean stop (last sign of life ${new Date(at).toISOString()})` : "";
}

export function markAlive(now = Date.now()): void {
  write(ALIVE, String(now));
}

export function markClean(): void {
  write(ALIVE, "clean");
}

export function installLifecycle(win: Window = window): void {
  win.addEventListener("pagehide", () => markClean());
}

/** True when the JS heap is above 85 % of its limit (Chromium only; elsewhere never). */
export function memoryPressure(): boolean {
  const mem = (performance as unknown as { memory?: { usedJSHeapSize: number; jsHeapSizeLimit: number } }).memory;
  return !!mem && mem.jsHeapSizeLimit > 0 && mem.usedJSHeapSize / mem.jsHeapSizeLimit > 0.85;
}
