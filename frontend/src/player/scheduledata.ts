// SPDX-License-Identifier: AGPL-3.0-or-later
// The event's program for "program" elements (ADR-0038), kept on the device so now/next keeps working offline.
// Refreshed at start, on "schedule.changed" (a live change: delay, cancellation, room change) and every few minutes.
import { request, Unauthorized } from "./api";
import { ProgramStore, type ProgramData } from "../renderer/program";

const KEY = "evac.player.schedule";

export function cachedSchedule(): ProgramData | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as ProgramData) : null;
  } catch {
    return null;
  }
}

/** Fetch and store; returns false when the server could not be reached (the cached program stays). */
export async function refreshSchedule(api: string, token: string, store: ProgramStore): Promise<boolean> {
  try {
    const res = await request<ProgramData>(api, "schedule/", { token, timeout: 15000 });
    store.set(res.sessions ? res : null);
    try { localStorage.setItem(KEY, JSON.stringify(res)); } catch { /* quota */ }
    return true;
  } catch (err) {
    if (err instanceof Unauthorized) throw err;
    return false;
  }
}

export function clearSchedule(): void {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
