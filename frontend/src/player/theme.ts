// SPDX-License-Identifier: AGPL-3.0-or-later
// Event theme on the screen: CSS custom properties from the server plus fonts loaded with the FontFace API.
// Fonts and background images are fetched with the device token and kept in the Cache API, so a screen that
// restarts without network still looks right.

import { request } from "./api";

export interface ThemePayload {
  key: string;
  version: number;
  variables: Record<string, string>;
  fonts_css: string;
}

const CACHE = "evac-player-content-v1";
const THEME_URL = "content/theme/";
const URL_IN_CSS = /url\("([^"]+)"\)/g;

async function cached(url: string, token: string): Promise<Response | null> {
  // fonts and theme images are content-addressed (the URL changes with the file): the cache is always right,
  // and a hanging network must never hold up the screen
  const cache = await caches.open(CACHE).catch(() => null);
  const hit = await cache?.match(url).catch(() => undefined);
  if (hit) return hit;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 10_000);
  try {
    const res = await fetch(url, { headers: { Authorization: `Screen ${token}` }, credentials: "omit",
                                   signal: ctrl.signal });
    if (res.ok) {
      await cache?.put(url, res.clone());
      return res;
    }
  } catch {
    /* offline or timed out */
  } finally {
    clearTimeout(timer);
  }
  return null;
}

export async function fetchTheme(api: string, token: string): Promise<ThemePayload | null> {
  try {
    const res = await request<{ theme: ThemePayload | null }>(api, THEME_URL, { token });
    if (res.theme) localStorage.setItem("evac.player.theme", JSON.stringify(res.theme));
    return res.theme;
  } catch {
    try {
      const raw = localStorage.getItem("evac.player.theme");
      return raw ? (JSON.parse(raw) as ThemePayload) : null;
    } catch {
      return null;
    }
  }
}

/** Parse the @font-face rules the server sends (family, weight, style, url). */
export function parseFontFaces(css: string): { family: string; url: string; weight: string; style: string;
                                               unicodeRange?: string }[] {
  const out = [];
  for (const block of css.match(/@font-face\{[^}]*\}/g) ?? []) {
    const family = /font-family:"([^"]+)"/.exec(block)?.[1];
    const url = /src:url\("([^"]+)"\)/.exec(block)?.[1];
    if (!family || !url) continue;
    out.push({ family, url, weight: /font-weight:([^;]+);/.exec(block)?.[1] ?? "400",
               style: /font-style:([^;]+);/.exec(block)?.[1] ?? "normal",
               unicodeRange: /unicode-range:([^;]+);/.exec(block)?.[1] });
  }
  return out;
}

const objectUrls: string[] = [];

export async function applyTheme(theme: ThemePayload, token: string, root: HTMLElement = document.documentElement)
  : Promise<void> {
  const fonts = document.fonts;
  await Promise.all(parseFontFaces(theme.fonts_css).map(async (f) => {
    // built-in fonts are static files (no token needed, same cache path)
    const res = await cached(f.url, token);
    if (!res) return;
    try {
      const face = new FontFace(f.family, await res.arrayBuffer(), { weight: f.weight, style: f.style,
                                                                     unicodeRange: f.unicodeRange });
      fonts.add(await face.load());
    } catch {
      /* a broken font must not stop the screen */
    }
  }));
  objectUrls.splice(0).forEach((u) => URL.revokeObjectURL(u));
  for (const [name, value] of Object.entries(theme.variables)) {
    let v = value;
    for (const m of value.matchAll(URL_IN_CSS)) {
      const res = await cached(m[1], token);
      if (res) {
        const blobUrl = URL.createObjectURL(await res.blob());
        objectUrls.push(blobUrl);
        v = v.replace(m[1], blobUrl);
      }
    }
    root.style.setProperty(name, v);
  }
  root.dataset.theme = theme.key || "default";
}
