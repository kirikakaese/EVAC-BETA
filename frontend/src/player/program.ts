// SPDX-License-Identifier: AGPL-3.0-or-later
// The screen's program (overrides, schedules, default playlist for the next days), kept on the device so the
// screen keeps changing slides without network.
import { request, Unauthorized } from "./api";
import type { Program } from "../program/engine";

const KEY = "evac.player.program";

export async function fetchProgram(api: string, token: string): Promise<Program | null> {
  try {
    const res = await request<{ program: Program | null }>(api, "playlists/program/", { token, timeout: 15000 });
    try {
      if (res.program) localStorage.setItem(KEY, JSON.stringify(res.program));
      else localStorage.removeItem(KEY);
    } catch { /* quota: keep in memory */ }
    return res.program;
  } catch (err) {
    if (err instanceof Unauthorized) throw err;
    return cachedProgram();
  }
}

export function cachedProgram(): Program | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Program) : null;
  } catch {
    return null;
  }
}

export function clearProgram(): void {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}
