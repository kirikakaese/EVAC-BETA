// SPDX-License-Identifier: AGPL-3.0-or-later
// Custom widgets on screens (ADR-0023): the "data" element draws one widget of the widgets module - text, list,
// table, cards, counter, gauge, ticker or bar chart - from rows the server already mapped. The rows come from a
// DataStore (player: /player/api/widgets/data/, kept offline; editor and preview: inline). A widget without data
// shows nothing on a public screen; staff (editing) see a placeholder or a "stale" badge.
import { render as renderTemplate } from "./template";
import type { DataStore, WidgetData } from "./types";
import { EvacWidget, WIDGETS } from "./widgets";

export type { DataStore, Row, WidgetData } from "./types";

export class MemoryStore implements DataStore {
  private listeners = new Set<() => void>();
  constructor(private data: Record<string, WidgetData> = {}) {}
  get(id: string): WidgetData | undefined { return this.data[id]; }
  set(data: Record<string, WidgetData>): void {
    this.data = data;
    this.listeners.forEach((fn) => fn());
  }
  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text?: unknown): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined && text !== null && text !== "") node.textContent = String(text);
  return node;
}

export function num(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function formatTime(value: unknown, timezone?: string): string {
  if (typeof value !== "string" || !value) return "";
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const d = new Date(dateOnly ? `${value}T12:00:00Z` : value);
  if (Number.isNaN(d.getTime())) return value;
  const opts: Intl.DateTimeFormatOptions = dateOnly ? { weekday: "short", day: "numeric", month: "short" }
    : { hour: "2-digit", minute: "2-digit", hour12: false };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: dateOnly ? "UTC" : timezone }).format(d);
  } catch {
    return new Intl.DateTimeFormat("en-GB", opts).format(d);
  }
}

const COLUMNS = ["time", "title", "subtitle", "label", "value"] as const;

export class DataWidget extends EvacWidget {
  private unsubscribe: (() => void) | null = null;

  draw(): void {
    if (!this.unsubscribe && this.ctx.data) this.unsubscribe = this.ctx.data.subscribe(() => this.safely(() => this.paint()));
    this.paint();
  }

  private paint(): void {
    const id = String(this.props.widget ?? "");
    const data = id ? this.ctx.data?.get(id) : undefined;
    if (!data) {
      this.replaceChildren();
      this.placeholder(id ? "Data widget (no data yet)" : "Data widget: choose a widget");
      return;
    }
    this.classList.remove("evac-placeholder");
    const box = el("div", `evac-data evac-data-${data.visual}`);
    const heading = String(this.props.title || data.options.heading || "");
    if (heading) box.appendChild(el("div", "evac-data-heading", heading));
    const body = el("div", "evac-data-body");
    box.appendChild(body);
    (VISUALS[data.visual] ?? VISUALS.list)(body, data, this);
    if (this.ctx.editing && data.stale) box.appendChild(el("span", "evac-data-stale", "stale"));
    this.replaceChildren(box);
  }

  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(text: string, data: WidgetData): string {
    return renderTemplate(text, { ...this.ctx.vars, data: { first: data.rows[0] ?? {}, rows: data.rows,
                                                            count: data.rows.length } },
                          { now: this.ctx.now, timezone: this.ctx.timezone });
  }

  get tz(): string | undefined { return this.ctx.timezone; }

  disconnectedCallback(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    super.disconnectedCallback();
  }
}

type Visual = (body: HTMLElement, data: WidgetData, w: DataWidget) => void;

function empty(body: HTMLElement, data: WidgetData): boolean {
  if (data.rows.length) return false;
  body.appendChild(el("div", "evac-data-empty", "–"));
  return true;
}

const VISUALS: Record<string, Visual> = {
  text(body, data, w) {
    body.appendChild(el("div", "evac-data-text", w.tmpl(String(data.options.template || "{{ data.first.title }}"),
                                                        data)));
  },
  list(body, data, w) {
    if (empty(body, data)) return;
    const ul = el("ul", "evac-data-list");
    for (const r of data.rows) {
      const li = el("li");
      if (r.time) li.appendChild(el("span", "evac-data-time", formatTime(r.time, w.tz)));
      const main = el("span", "evac-data-main");
      main.appendChild(el("span", "evac-data-title", r.title ?? r.label ?? r.value));
      if (r.subtitle) main.appendChild(el("span", "evac-data-sub", r.subtitle));
      li.appendChild(main);
      if (r.value !== undefined && r.value !== null && r.title) li.appendChild(el("span", "evac-data-value", r.value));
      ul.appendChild(li);
    }
    body.appendChild(ul);
  },
  table(body, data, w) {
    if (empty(body, data)) return;
    const cols = COLUMNS.filter((c) => data.rows.some((r) => r[c] !== undefined && r[c] !== null && r[c] !== ""));
    const table = el("table", "evac-data-table");
    const tbody = el("tbody");
    for (const r of data.rows) {
      const tr = el("tr");
      for (const c of cols) tr.appendChild(el("td", `evac-data-${c}`, c === "time" ? formatTime(r[c], w.tz) : r[c]));
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    body.appendChild(table);
  },
  cards(body, data, w) {
    if (empty(body, data)) return;
    const grid = el("div", "evac-data-cards");
    for (const r of data.rows) {
      const card = el("div", "evac-data-card");
      if (typeof r.image === "string" && r.image.startsWith("/")) {
        const img = el("img");
        img.src = r.image;
        img.alt = "";
        card.appendChild(img);
      }
      if (r.time) card.appendChild(el("div", "evac-data-time", formatTime(r.time, w.tz)));
      card.appendChild(el("div", "evac-data-title", r.title ?? r.label));
      if (r.subtitle) card.appendChild(el("div", "evac-data-sub", r.subtitle));
      if (r.value !== undefined && r.value !== null) card.appendChild(el("div", "evac-data-value", r.value));
      grid.appendChild(card);
    }
    body.appendChild(grid);
  },
  counter(body, data) {
    const first = data.rows[0] ?? {};
    // the first item's value, else the number of items
    const value = first.value !== undefined && first.value !== null ? first.value : data.rows.length;
    const n = num(value);
    const big = el("div", "evac-data-number", n === null ? value : n.toLocaleString("en-GB"));
    if (data.options.unit) big.appendChild(el("span", "evac-data-unit", ` ${data.options.unit}`));
    body.appendChild(big);
    if (first.label || first.title) body.appendChild(el("div", "evac-data-sub", first.label ?? first.title));
  },
  gauge(body, data) {
    const first = data.rows[0] ?? {};
    const value = num(first.value) ?? 0;
    const min = num(data.options.minimum) ?? 0;
    const max = num(data.options.maximum) ?? 100;
    const share = Math.max(0, Math.min(1, (value - min) / ((max - min) || 1)));
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "0 0 200 110");
    svg.setAttribute("class", "evac-data-gauge");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `${value}${data.options.unit ? ` ${data.options.unit}` : ""}`);
    const arc = (to: number, cls: string): void => {
      const a = Math.PI * (1 - to);
      const p = document.createElementNS(svgNS, "path");
      p.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(a)} ${100 - 80 * Math.sin(a)}`);
      p.setAttribute("class", cls);
      svg.appendChild(p);
    };
    arc(1, "evac-gauge-track");
    if (share > 0) arc(share, "evac-gauge-fill");
    body.appendChild(svg);
    const label = el("div", "evac-data-number", value.toLocaleString("en-GB"));
    if (data.options.unit) label.appendChild(el("span", "evac-data-unit", ` ${data.options.unit}`));
    body.appendChild(label);
    if (first.label || first.title) body.appendChild(el("div", "evac-data-sub", first.label ?? first.title));
  },
  ticker(body, data, w) {
    if (empty(body, data)) return;
    const text = data.rows.map((r) => [r.time ? formatTime(r.time, w.tz) : "", r.title ?? r.label ?? ""]
      .filter(Boolean).join(" ")).join("   ◆   ");
    const box = el("div", "evac-marquee-box");
    const run = el("span", "evac-marquee", text);
    run.style.animationDuration = `${Math.max(10, text.length / 5)}s`;
    box.appendChild(run);
    body.appendChild(box);
  },
  bars(body, data) {
    if (empty(body, data)) return;
    const values = data.rows.map((r) => num(r.value) ?? 0);
    const max = num(data.options.maximum) || Math.max(...values, 1);
    const list = el("div", "evac-data-bars");
    data.rows.forEach((r, i) => {
      const row = el("div", "evac-bar");
      row.appendChild(el("span", "evac-bar-label", r.label ?? r.title));
      const track = el("span", "evac-bar-track");
      const fill = el("span", "evac-bar-fill");
      fill.style.width = `${Math.max(0, Math.min(100, (values[i] / max) * 100))}%`;
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("span", "evac-bar-value", `${values[i].toLocaleString("en-GB")}${data.options.unit ? ` ${data.options.unit}` : ""}`));
      list.appendChild(row);
    });
    body.appendChild(list);
  },
};

WIDGETS.data = DataWidget;
