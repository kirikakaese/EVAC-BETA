// SPDX-License-Identifier: AGPL-3.0-or-later
// Portal island: renders one slide with the shared renderer at a chosen time ("preview any screen at any time").
// Reads its data from <script id="preview-config" type="application/json">; time runs on from that moment.
import "./preview.css";

import { pageNonce } from "../renderer/code";
import { MemoryStore } from "../renderer/data";
import { renderLayout } from "../renderer/render";
import type { AssetEntry, LayoutData, WidgetData } from "../renderer/types";

interface PreviewConfig {
  layout: LayoutData; at: number; timezone: string; vars: Record<string, unknown>;
  assets: Record<string, AssetEntry>; fonts: Record<string, string>; themeVariables: Record<string, string>;
  /** custom widget rows ("data" elements) */
  data?: Record<string, WidgetData>;
}

export function mountPreview(host: HTMLElement, cfg: PreviewConfig): void {
  const started = Date.now();
  host.replaceChildren();
  host.style.aspectRatio = `${cfg.layout.width} / ${cfg.layout.height}`;
  for (const [k, v] of Object.entries(cfg.themeVariables ?? {})) host.style.setProperty(k, v);
  host.classList.add("evac-preview-host");
  renderLayout(host, cfg.layout, {
    vars: cfg.vars, now: () => cfg.at + (Date.now() - started), timezone: cfg.timezone, assets: cfg.assets,
    fonts: cfg.fonts, reducedMotion: true, nonce: pageNonce(), data: new MemoryStore(cfg.data ?? {}),
  });
}

if (typeof document !== "undefined") {
  const data = document.getElementById("preview-config");
  const host = document.querySelector<HTMLElement>("[data-preview]");
  if (data && host) mountPreview(host, JSON.parse(data.textContent || "{}") as PreviewConfig);
}
