// SPDX-License-Identifier: AGPL-3.0-or-later
// Rows of the event's custom widgets (ADR-0023), kept on the device so "data" elements keep showing the last
// data offline. Refreshed at start, on "data.changed" and every few minutes.
import { request, Unauthorized } from "./api";
import { MemoryStore } from "../renderer/data";
import type { WidgetData } from "../renderer/types";

const KEY = "evac.player.widgets";

export function cachedWidgetData(): Record<string, WidgetData> {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Record<string, WidgetData>) : {};
  } catch {
    return {};
  }
}

/** Fetch and store; returns false when the server could not be reached (the cached data stays). */
export async function refreshWidgetData(api: string, token: string, store: MemoryStore): Promise<boolean> {
  try {
    const res = await request<{ widgets: Record<string, WidgetData> }>(api, "widgets/data/", { token, timeout: 15000 });
    store.set(res.widgets ?? {});
    try { localStorage.setItem(KEY, JSON.stringify(res.widgets ?? {})); } catch { /* quota */ }
    return true;
  } catch (err) {
    if (err instanceof Unauthorized) throw err;
    return false;
  }
}

export function clearWidgetData(): void {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
