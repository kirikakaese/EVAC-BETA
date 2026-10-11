// SPDX-License-Identifier: AGPL-3.0-or-later
// Portal island: renders one slide with the shared renderer at a chosen time ("preview any screen at any time").
// Reads its data from <script id="preview-config" type="application/json">; time runs on from that moment.
import "./preview.css";

import { pageNonce } from "../renderer/code";
import { MemoryStore } from "../renderer/data";
import { type ProgramData, ProgramStore } from "../renderer/program";
import { renderLayout } from "../renderer/render";
import { fetchHost } from "../renderer/plugin";
import type { AssetEntry, LayoutData, PluginWidgetInfo, WidgetData } from "../renderer/types";

interface PreviewConfig {
  layout: LayoutData; at: number; timezone: string; vars: Record<string, unknown>;
  assets: Record<string, AssetEntry>; fonts: Record<string, string>; themeVariables: Record<string, string>;
  /** custom widget rows ("data" elements) */
  data?: Record<string, WidgetData>;
  /** program sessions ("program" elements) */
  program?: ProgramData | null;
  /** widgets of third-party plugins and the portal URL their data sources are read from (ADR-0045) */
  plugins?: { widgets: Record<string, PluginWidgetInfo>; sources: string };
  /** a gallery: several layouts sharing the rest of the config, each shown in ``[data-preview-layout=key]`` */
  layouts?: Record<string, LayoutData>;
  /** a print sheet: one page per entry, each rendered with these variables merged over ``vars`` (badges) */
  pages?: Record<string, unknown>[];
  /** accessible name of each page (e.g. "Badge of Ada Lovelace") */
  pageLabels?: string[];
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
    program: new ProgramStore(cfg.program ?? null),
    plugins: cfg.plugins ? fetchHost(() => cfg.plugins?.widgets ?? {}, cfg.plugins.sources) : undefined,
  });
}

/** A print sheet: the same layout once per page, each with its own variables (badges of the access module). */
export function mountPages(sheet: HTMLElement, cfg: PreviewConfig): void {
  sheet.replaceChildren();
  (cfg.pages ?? []).forEach((vars, i) => {
    const page = document.createElement("div");
    page.className = "evac-print-page";
    page.setAttribute("role", "img");
    page.setAttribute("aria-label", cfg.pageLabels?.[i] ?? "");
    sheet.appendChild(page);
    mountPreview(page, { ...cfg, vars: { ...cfg.vars, ...vars } });
  });
}

/** A gallery: one thumbnail per layout (template gallery). */
export function mountGallery(root: HTMLElement, cfg: PreviewConfig): void {
  for (const host of root.querySelectorAll<HTMLElement>("[data-preview-layout]")) {
    const layout = cfg.layouts?.[host.dataset.previewLayout ?? ""];
    if (layout) mountPreview(host, { ...cfg, layout });
  }
}

if (typeof document !== "undefined") {
  const data = document.getElementById("preview-config");
  const host = document.querySelector<HTMLElement>("[data-preview]");
  const sheet = document.querySelector<HTMLElement>("[data-preview-pages]");
  if (data && host) mountPreview(host, JSON.parse(data.textContent || "{}") as PreviewConfig);
  if (data && sheet) mountPages(sheet, JSON.parse(data.textContent || "{}") as PreviewConfig);
  const gallery = document.querySelector<HTMLElement>("[data-preview-gallery]");
  if (data && gallery) mountGallery(gallery, JSON.parse(data.textContent || "{}") as PreviewConfig);
}
