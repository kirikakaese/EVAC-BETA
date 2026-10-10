// SPDX-License-Identifier: AGPL-3.0-or-later
// What the player reports in every heartbeat (the server keeps a whitelisted subset).

const errors: string[] = [];
const lines: string[] = [];
const started = Date.now();
const MAX_LINES = 300;
let errorTimes: number[] = [];
let onStorm: (() => void) | null = null;

/** Keep a line for the remote log view (newest last). */
export function log(level: string, message: string): void {
  lines.push(`${new Date().toISOString()} ${level.toUpperCase()} ${message}`.slice(0, 500));
  if (lines.length > MAX_LINES) lines.shift();
}

export function logLines(): string[] {
  return [...lines];
}

export function recordError(message: string): void {
  errors.push(`${new Date().toISOString()} ${message}`.slice(0, 300));
  if (errors.length > 10) errors.shift();
  log("error", message);
  const now = Date.now();
  errorTimes = errorTimes.filter((t) => now - t < 60_000);
  errorTimes.push(now);
  if (errorTimes.length >= 50 && onStorm) {
    errorTimes = [];
    onStorm();
  }
}

/** Called when 50 errors happen within a minute (the player reloads itself, guarded). */
export function onErrorStorm(fn: () => void): void {
  onStorm = fn;
}

export function installErrorHandlers(win: Window = window): void {
  win.addEventListener("error", (e) => recordError(e.message || "error"));
  win.addEventListener("unhandledrejection", (e) => recordError(String((e as PromiseRejectionEvent).reason)));
  for (const level of ["warn", "info"] as const) {
    const original = console[level].bind(console);
    console[level] = (...args: unknown[]) => {
      log(level, args.map(String).join(" "));
      original(...args);
    };
  }
}

export interface ReportState { version: string; slide: string; lastSync: number | null; online: boolean;
                               contentVersion?: string; displayState?: string; capture?: boolean;
                               recovered?: string; evacAck?: string; evacBundle?: string; evacAudio?: string }

export function report(state: ReportState): Record<string, unknown> {
  const w = window.innerWidth, h = window.innerHeight;
  const mem = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
  return {
    version: state.version,
    resolution: `${Math.round(w * devicePixelRatio)}x${Math.round(h * devicePixelRatio)}`,
    orientation: w >= h ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - started) / 1000),
    slide: state.slide,
    errors: [...errors],
    memory: mem ? Math.round(mem.usedJSHeapSize / 1048576) : null,
    last_sync: state.lastSync ? new Date(state.lastSync).toISOString() : null,
    online: state.online,
    user_agent: navigator.userAgent,
    ...(state.contentVersion ? { content_version: state.contentVersion } : {}),
    ...(state.displayState ? { display_state: state.displayState } : {}),
    ...(state.capture !== undefined ? { capture: state.capture } : {}),
    ...(state.recovered ? { recovered: state.recovered } : {}),
    ...(state.evacAck ? { evac_ack: state.evacAck } : {}),
    ...(state.evacBundle ? { evac_bundle: state.evacBundle } : {}),
    ...(state.evacAudio ? { evac_audio: state.evacAudio } : {}),
  };
}
