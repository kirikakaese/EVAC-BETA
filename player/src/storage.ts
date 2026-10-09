// SPDX-License-Identifier: AGPL-3.0-or-later
// Device token and last known configuration. localStorage is enough for these small values; the content
// bundle (layouts, assets) goes to IndexedDB with the renderer.

const TOKEN = "evac.player.token";
const CONFIG = "evac.player.config";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN, token);
    else {
      localStorage.removeItem(TOKEN);
      localStorage.removeItem(CONFIG);
    }
  } catch {
    /* private mode: the screen re-pairs after a reload */
  }
}

export function getConfig<T>(): T | null {
  try {
    const raw = localStorage.getItem(CONFIG);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function setConfig(value: unknown): void {
  try {
    localStorage.setItem(CONFIG, JSON.stringify(value));
  } catch {
    /* quota: keep running with the in-memory copy */
  }
}
