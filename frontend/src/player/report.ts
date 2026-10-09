// SPDX-License-Identifier: AGPL-3.0-or-later
// What the player reports in every heartbeat (the server keeps a whitelisted subset).

const errors: string[] = [];
const started = Date.now();

export function recordError(message: string): void {
  errors.push(`${new Date().toISOString()} ${message}`.slice(0, 300));
  if (errors.length > 10) errors.shift();
}

export function installErrorHandlers(win: Window = window): void {
  win.addEventListener("error", (e) => recordError(e.message || "error"));
  win.addEventListener("unhandledrejection", (e) => recordError(String((e as PromiseRejectionEvent).reason)));
}

export interface ReportState { version: string; slide: string; lastSync: number | null; online: boolean;
                               contentVersion?: string }

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
  };
}
