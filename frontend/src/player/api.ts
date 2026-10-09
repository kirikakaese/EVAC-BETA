// SPDX-License-Identifier: AGPL-3.0-or-later
// HTTP calls to /player/api/ with a timeout and the device token.

import type { DisplaySettings } from "./screen-settings";

export class Unauthorized extends Error {}

export interface ScreenConfig {
  screen: { id: string; name: string; tags: string[]; venue: string | null; zone: string | null; room: string | null;
            groups: { id: string; name: string }[] };
  event: { slug: string; name: string; timezone: string };
  settings: { heartbeat_seconds: number; [key: string]: unknown };
  display?: DisplaySettings;
  server_time: number;
  seq: number;
}

export interface PairStart { id: string; code: string; secret: string; expires_in: number; pair_url: string }
export type PairStatus =
  | { status: "pending"; code: string; expires_in: number }
  | { status: "expired" | "delivered" }
  | { status: "paired"; token: string; screen: { id: string; name: string }; event: { slug: string; name: string } };

export async function request<T>(base: string, path: string, init: RequestInit & { token?: string | null;
                                 timeout?: number } = {}): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), init.timeout ?? 10000);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.token) headers.set("Authorization", `Screen ${init.token}`);
  try {
    const res = await fetch(base + path, { ...init, headers, signal: ctrl.signal, cache: "no-store",
                                           credentials: "omit" });
    if (res.status === 401) throw new Unauthorized("token rejected");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export const startPairing = (base: string, info: object) =>
  request<PairStart>(base, "pair/", { method: "POST", body: JSON.stringify({ info }) });

export const pairingStatus = (base: string, start: PairStart) =>
  request<PairStatus>(base, `pair/${start.id}/`, { method: "POST", headers: { "X-Pairing-Secret": start.secret } });

export const fetchConfig = (base: string, token: string) => request<ScreenConfig>(base, "config/", { token });
