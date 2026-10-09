// SPDX-License-Identifier: AGPL-3.0-or-later
// Content bundle of the screen's event (theme, fonts, published layouts, asset URLs). Kept on the device so the
// screen restarts without network; asset files are prefetched so the service worker has them cached.
import { request, Unauthorized } from "./api";
import type { ThemePayload } from "./theme";
import type { AssetEntry, LayoutData } from "../renderer/types";

export interface BundleLayout { id: string; key: string; name: string; default: boolean; version: number;
                                data: LayoutData; variables?: Record<string, string> }

export interface Bundle {
  version: string;
  theme: ThemePayload & { tokens: Record<string, unknown> };
  layouts: BundleLayout[];
  assets: Record<string, AssetEntry>;
  fonts_css: string;
  fonts: Record<string, string>;
}

const KEY = "evac.player.bundle";

export async function fetchBundle(api: string, token: string): Promise<Bundle | null> {
  try {
    const res = await request<{ bundle: Bundle | null }>(api, "content/bundle/", { token, timeout: 20000 });
    if (res.bundle) {
      try { localStorage.setItem(KEY, JSON.stringify(res.bundle)); } catch { /* quota: keep in memory */ }
    }
    return res.bundle;
  } catch (err) {
    if (err instanceof Unauthorized) throw err;
    return cachedBundle();
  }
}

export function cachedBundle(): Bundle | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Bundle) : null;
  } catch {
    return null;
  }
}

export function clearBundle(): void {
  try { localStorage.removeItem(KEY); } catch { /* ignore */ }
}

export function defaultLayout(bundle: Bundle | null): BundleLayout | null {
  if (!bundle?.layouts.length) return null;
  return bundle.layouts.find((l) => l.default) ?? bundle.layouts[0];
}

/** Fetch every file the layouts use once, so the service worker caches them for offline playback. */
export async function prefetch(bundle: Bundle): Promise<number> {
  const urls = new Set<string>();
  for (const a of Object.values(bundle.assets)) Object.values(a.urls).forEach((u) => urls.add(u));
  let ok = 0;
  await Promise.all([...urls].map(async (u) => {
    try {
      const res = await fetch(u, { credentials: "omit" });
      if (res.ok) ok += 1;
      await res.body?.cancel();
    } catch {
      /* offline: the next sync retries */
    }
  }));
  return ok;
}
