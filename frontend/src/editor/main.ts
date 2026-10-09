// SPDX-License-Identifier: AGPL-3.0-or-later
// Layout editor island (Lit, ADR-0009): canvas with drag, resize and snapping, layers, properties, undo/redo,
// save (every save is a version) and publish. The canvas uses the same renderer as the screens, so what you
// see is what the screens show. Rendered in light DOM so the renderer, theme variables and fonts apply.
import "./editor.css";

import { html, LitElement, nothing, type TemplateResult } from "lit";
import { directive, Directive, type ElementPart, type PartInfo, PartType } from "lit/directive.js";

import { pageNonce } from "../renderer/code";
import { frameStyle, renderLayout, type RenderedLayout } from "../renderer/render";
import type { AssetEntry, ElementStyle, LayoutData, LayoutElement, RenderContext } from "../renderer/types";
import {
  align, type AlignMode, clone, createElement, duplicate, guidesFor, History, r2, reorder, resize, snapMove,
} from "./model";

interface EditorConfig {
  layout: { id: string; name: string; data: LayoutData; version: number };
  assets: Record<string, AssetEntry>;
  fonts: Record<string, string>;
  fontChoices: { value: string; label: string }[];
  themeVariables: Record<string, string>;
  vars: Record<string, unknown>;
  timezone: string;
  urls: { save: string; publish: string; back: string; assets: string };
  canPublish: boolean;
  canCode: boolean;
  types: string[];
}

const TYPE_LABELS: Record<string, string> = {
  text: "Text", richtext: "Rich text", image: "Image", slideshow: "Slideshow", video: "Video", audio: "Audio",
  shape: "Shape", qr: "QR code", clock: "Clock", countdown: "Countdown", date: "Date", code: "Code",
};
const TOKENS = ["primary", "accent", "text", "muted", "surface", "background", "success", "warning", "danger"];
const TOKEN_LABELS: Record<string, string> = {
  primary: "Primary", accent: "Accent", text: "Text", muted: "Muted text", surface: "Surface",
  background: "Background", success: "Success", warning: "Warning", danger: "Danger",
};
const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

/** Tiny ref directive replacement: call ``fn`` with the element after render (keeps the bundle small). */
class RefDirective extends Directive {
  constructor(part: PartInfo) {
    super(part);
    if (part.type !== PartType.ELEMENT) throw new Error("ref() only on elements");
  }
  update(part: ElementPart, [fn]: [(el: Element) => void]) {
    fn(part.element);
    return this.render(fn);
  }
  render(_fn: (el: Element) => void) { return nothing; }
}
const ref = directive(RefDirective);


function readJson<T>(id: string, fallback: T): T {
  const el = document.getElementById(id);
  try {
    return el?.textContent ? (JSON.parse(el.textContent) as T) : fallback;
  } catch {
    return fallback;
  }
}

function csrf(): string {
  return document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

type Drag = { mode: "move" | "resize"; handle?: string; x0: number; y0: number; start: Record<string, LayoutElement["frame"]>;
              moved: boolean };

export class LayoutEditor extends LitElement {
  static properties = {
    data: { state: true }, selected: { state: true }, status: { state: true }, zoom: { state: true },
    guides: { state: true }, error: { state: true },
  };

  data!: LayoutData;
  selected = new Set<string>();
  status: "saved" | "dirty" | "saving" | "error" = "saved";
  zoom = 0; // 0 = fit
  guides: { x: number | null; y: number | null } = { x: null, y: null };
  error = "";

  private cfg = readJson<EditorConfig>("editor-config", {} as EditorConfig);
  private strings = readJson<Record<string, string>>("editor-strings", {});
  private history = new History();
  private version = 0;
  private rendered: RenderedLayout | null = null;
  private drag: Drag | null = null;
  private clipboardKey = "evac.editor.clipboard";

  createRenderRoot() { return this; }

  t(s: string): string { return this.strings[s] ?? s; }

  connectedCallback(): void {
    this.replaceChildren(); // drop the server-rendered "Loading…" fallback before Lit renders into light DOM
    super.connectedCallback();
    this.data = clone(this.cfg.layout.data);
    this.version = this.cfg.layout.version;
    this.tabIndex = 0;
    this.addEventListener("keydown", (e) => this.onKey(e));
    window.addEventListener("beforeunload", (e) => { if (this.status === "dirty") e.preventDefault(); });
  }

  // ---------------------------------------------------------------- state changes
  private get elements(): LayoutElement[] { return this.data.elements; }

  private get selection(): LayoutElement[] { return this.elements.filter((e) => this.selected.has(e.id)); }

  private commit(next: LayoutData, record = true): void {
    if (record) this.history.push(this.data);
    this.data = next;
    this.status = "dirty";
  }

  private updateElements(fn: (els: LayoutElement[]) => LayoutElement[]): void {
    this.commit({ ...this.data, elements: fn(clone(this.elements)) });
  }

  private patchSelected(fn: (el: LayoutElement) => void): void {
    this.updateElements((els) => els.map((e) => { if (this.selected.has(e.id)) fn(e); return e; }));
  }

  private select(id: string | null, additive = false): void {
    const next = new Set(additive ? this.selected : []);
    if (id) {
      if (additive && next.has(id)) next.delete(id);
      else next.add(id);
    }
    this.selected = next;
  }

  private add(type: string): void {
    const el = createElement(type, this.elements, this.t(TYPE_LABELS[type] ?? type));
    this.updateElements((els) => [...els, el]);
    this.selected = new Set([el.id]);
  }

  private removeSelected(): void {
    if (!this.selected.size) return;
    this.updateElements((els) => els.filter((e) => !this.selected.has(e.id) || e.locked));
    this.selected = new Set();
  }

  private duplicateSelected(): void {
    const copies: LayoutElement[] = [];
    for (const el of this.selection) copies.push(duplicate(el, [...this.elements, ...copies]));
    this.updateElements((els) => [...els, ...copies]);
    this.selected = new Set(copies.map((c) => c.id));
  }

  private undo(): void {
    const prev = this.history.undo(this.data);
    if (prev) { this.data = prev; this.status = "dirty"; }
  }

  private redo(): void {
    const next = this.history.redo(this.data);
    if (next) { this.data = next; this.status = "dirty"; }
  }

  // ---------------------------------------------------------------- save and publish
  async save(): Promise<boolean> {
    this.status = "saving";
    this.error = "";
    try {
      const res = await fetch(this.cfg.urls.save, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
        body: JSON.stringify({ data: this.data, version: this.version }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok && body.ok) {
        this.version = body.version;
        this.status = "saved";
        return true;
      }
      this.status = "error";
      this.error = body.conflict ? this.t("Someone else saved this layout in the meantime.")
        : [this.t("The layout could not be saved."), ...(body.errors ?? [])].join(" ");
    } catch {
      this.status = "error";
      this.error = this.t("The layout could not be saved.");
    }
    return false;
  }

  async publish(): Promise<void> {
    if (this.status !== "saved" && !(await this.save())) return;
    const res = await fetch(this.cfg.urls.publish, {
      method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf() },
    });
    const body = await res.json().catch(() => ({}));
    this.error = res.ok ? `${this.t("Published")}: v${body.published}` : this.t("The layout could not be saved.");
  }

  // ---------------------------------------------------------------- keyboard
  private onKey(e: KeyboardEvent): void {
    const target = e.target as HTMLElement;
    if (target.closest("input, textarea, select")) return;
    const mod = e.ctrlKey || e.metaKey;
    const step = e.shiftKey ? 5 : 0.5;
    const nudge = (dx: number, dy: number) => this.patchSelected((el) => {
      if (!el.locked) el.frame = { ...el.frame, x: r2(el.frame.x + dx), y: r2(el.frame.y + dy) };
    });
    const keys: Record<string, () => void> = {
      ArrowLeft: () => nudge(-step, 0), ArrowRight: () => nudge(step, 0), ArrowUp: () => nudge(0, -step),
      ArrowDown: () => nudge(0, step), Delete: () => this.removeSelected(), Backspace: () => this.removeSelected(),
      Escape: () => this.select(null),
    };
    if (mod && e.key.toLowerCase() === "z") (e.shiftKey ? this.redo() : this.undo());
    else if (mod && e.key.toLowerCase() === "y") this.redo();
    else if (mod && e.key.toLowerCase() === "d") this.duplicateSelected();
    else if (mod && e.key.toLowerCase() === "s") void this.save();
    else if (mod && e.key.toLowerCase() === "c") {
      try { localStorage.setItem(this.clipboardKey, JSON.stringify(this.selection)); } catch { /* ignore */ }
    } else if (mod && e.key.toLowerCase() === "v") {
      let items: LayoutElement[] = [];
      try { items = JSON.parse(localStorage.getItem(this.clipboardKey) ?? "[]"); } catch { /* ignore */ }
      const copies: LayoutElement[] = [];
      for (const el of items) copies.push(duplicate(el, [...this.elements, ...copies]));
      if (copies.length) {
        this.updateElements((els) => [...els, ...copies]);
        this.selected = new Set(copies.map((c) => c.id));
      }
    } else if (keys[e.key]) keys[e.key]();
    else return;
    e.preventDefault();
  }

  // ---------------------------------------------------------------- canvas
  private get ctx(): RenderContext {
    return { vars: this.cfg.vars, now: () => Date.now(), timezone: this.cfg.timezone, assets: this.cfg.assets,
             fonts: this.cfg.fonts, editing: true, nonce: pageNonce() };
  }

  updated(): void {
    const host = this.querySelector<HTMLElement>(".ed-host");
    if (!host) return;
    if (!this.drag) {
      this.rendered?.destroy();
      for (const [k, v] of Object.entries(this.cfg.themeVariables ?? {})) host.style.setProperty(k, v);
      this.rendered = renderLayout(host, this.data, this.ctx);
      if (this.zoom) {
        this.rendered.stage.style.width = `${this.data.width * this.zoom}px`;
        this.rendered.stage.style.height = `${this.data.height * this.zoom}px`;
      }
    }
    this.placeOverlay();
  }

  private placeOverlay(): void {
    const overlay = this.querySelector<HTMLElement>(".ed-overlay");
    const stage = this.rendered?.stage;
    if (!overlay || !stage) return;
    overlay.style.left = `${stage.offsetLeft}px`;
    overlay.style.top = `${stage.offsetTop}px`;
    overlay.style.width = `${stage.offsetWidth}px`;
    overlay.style.height = `${stage.offsetHeight}px`;
  }

  private percent(e: PointerEvent): [number, number] {
    const stage = this.rendered?.stage;
    if (!stage) return [0, 0];
    return [(e.clientX / stage.offsetWidth) * 100, (e.clientY / stage.offsetHeight) * 100];
  }

  private startDrag(e: PointerEvent, id: string, handle?: string): void {
    e.stopPropagation();
    if (!this.selected.has(id) || e.shiftKey) this.select(id, e.shiftKey);
    const targets = this.selection.filter((el) => !el.locked);
    if (!targets.length) return;
    const [x0, y0] = this.percent(e);
    this.drag = { mode: handle ? "resize" : "move", handle, x0, y0, moved: false,
                  start: Object.fromEntries(targets.map((t) => [t.id, { ...t.frame }])) };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }

  private onMove(e: PointerEvent): void {
    const d = this.drag;
    if (!d) return;
    const [x, y] = this.percent(e);
    let dx = x - d.x0, dy = y - d.y0;
    if (!d.moved && Math.abs(dx) < 0.2 && Math.abs(dy) < 0.2) return;
    if (!d.moved) { this.history.push(this.data); d.moved = true; }
    const ids = new Set(Object.keys(d.start));
    const free = e.altKey;
    const guidesX = guidesFor(this.elements, ids, "x"), guidesY = guidesFor(this.elements, ids, "y");
    const els = this.elements.map((el) => {
      const start = d.start[el.id];
      if (!start) return el;
      let frame;
      if (d.mode === "move") {
        const [nx, gx] = free ? [start.x + dx, null] : snapMove(start.x + dx, start.w, guidesX);
        const [ny, gy] = free ? [start.y + dy, null] : snapMove(start.y + dy, start.h, guidesY);
        this.guides = { x: gx, y: gy };
        dx = nx - start.x;
        dy = ny - start.y;
        frame = { ...start, x: r2(nx), y: r2(ny) };
      } else {
        frame = resize(start, d.handle ?? "se", dx, dy);
        frame = { ...frame, x: r2(frame.x), y: r2(frame.y), w: r2(frame.w), h: r2(frame.h) };
      }
      const next = { ...el, frame };
      const node = this.rendered?.elements.get(el.id);
      if (node) frameStyle(node, next);
      return next;
    });
    this.data = { ...this.data, elements: els };
    this.status = "dirty";
  }

  private endDrag(): void {
    if (!this.drag) return;
    const moved = this.drag.moved;
    this.drag = null;
    this.guides = { x: null, y: null };
    if (moved) this.requestUpdate();
  }

  // ---------------------------------------------------------------- rendering
  render(): TemplateResult {
    const statusText = { saved: this.t("Saved"), dirty: this.t("Unsaved changes"), saving: this.t("Saving…"),
                         error: this.error }[this.status];
    return html`
      <div class="ed-toolbar" role="toolbar" aria-label=${this.t("Layout")}>
        <strong class="ed-title">${this.cfg.layout?.name}</strong>
        <button class="btn btn-sm" ?disabled=${!this.history.canUndo} @click=${() => this.undo()}>${this.t("Undo")}</button>
        <button class="btn btn-sm" ?disabled=${!this.history.canRedo} @click=${() => this.redo()}>${this.t("Redo")}</button>
        <label class="ed-inline">${this.t("Zoom")}
          <select @change=${(e: Event) => { this.zoom = Number((e.target as HTMLSelectElement).value); }}>
            <option value="0">${this.t("Fit")}</option>${[0.25, 0.5, 0.75, 1].map((z) => html`
            <option value=${z}>${z * 100}%</option>`)}</select></label>
        <span class="ed-status" role="status" data-status=${this.status}>${statusText}</span>
        ${this.error && this.status !== "error" ? html`<span class="ed-status" role="status">${this.error}</span>` : nothing}
        <button class="btn btn-sm btn-primary" @click=${() => void this.save()}>${this.t("Save")}</button>
        ${this.cfg.canPublish ? html`<button class="btn btn-sm" @click=${() => void this.publish()}>${this.t("Publish")}</button>` : nothing}
        <a class="btn btn-sm btn-ghost" href=${this.cfg.urls?.back}>${this.t("Back")}</a>
      </div>
      <div class="ed-body">
        <aside class="ed-side ed-left" aria-label=${this.t("Layers")}>
          <h2 class="ed-h">${this.t("Add")}</h2>
          <div class="ed-add">${(this.cfg.types ?? []).filter((type) => type !== "code" || this.cfg.canCode).map((type) => html`
            <button class="btn btn-sm" @click=${() => this.add(type)}>${this.t(TYPE_LABELS[type] ?? type)}</button>`)}</div>
          <h2 class="ed-h">${this.t("Layers")}</h2>
          <ol class="ed-layers">${[...this.elements].reverse().map((el) => html`
            <li class=${this.selected.has(el.id) ? "selected" : ""}>
              <button class="ed-layer" aria-pressed=${this.selected.has(el.id)}
                      @click=${(e: MouseEvent) => this.select(el.id, e.shiftKey)}>
                ${el.hidden ? "◌ " : ""}${el.locked ? "🔒 " : ""}${el.name || el.id}
                <span class="muted small">${this.t(TYPE_LABELS[el.type] ?? el.type)}</span></button></li>`)}</ol>
        </aside>
        <div class="ed-canvas" @pointerdown=${() => this.select(null)}>
          <div class="ed-host"></div>
          <div class="ed-overlay" @pointermove=${(e: PointerEvent) => this.onMove(e)}
               @pointerup=${() => this.endDrag()} @pointercancel=${() => this.endDrag()}>
            ${this.guides.x !== null ? html`<div class="ed-guide ed-guide-x" ${ref((n) => {
              (n as HTMLElement).style.left = `${this.guides.x}%`; })}></div>` : nothing}
            ${this.guides.y !== null ? html`<div class="ed-guide ed-guide-y" ${ref((n) => {
              (n as HTMLElement).style.top = `${this.guides.y}%`; })}></div>` : nothing}
            ${this.elements.map((el) => this.box(el))}
          </div>
        </div>
        <aside class="ed-side ed-right" aria-label=${this.t("Properties")}>${this.panel()}</aside>
      </div>`;
  }

  private box(el: LayoutElement): TemplateResult {
    const sel = this.selected.has(el.id);
    return html`<div class="ed-box ${sel ? "selected" : ""} ${el.locked ? "locked" : ""}" data-id=${el.id}
        ${ref((n) => { if (n) frameStyle(n as HTMLElement, el); })}
        @pointerdown=${(e: PointerEvent) => this.startDrag(e, el.id)}>
        ${sel && this.selected.size === 1 && !el.locked ? HANDLES.map((h) => html`<span class="ed-handle ed-${h}"
          @pointerdown=${(e: PointerEvent) => this.startDrag(e, el.id, h)}></span>`) : nothing}
      </div>`;
  }

  // ---------------------------------------------------------------- property panel
  private field(label: string, control: TemplateResult): TemplateResult {
    return html`<label class="ed-field"><span>${this.t(label)}</span>${control}</label>`;
  }

  private num(label: string, value: number | undefined, set: (v: number | undefined) => void,
              opts: { min?: number; max?: number; step?: number } = {}): TemplateResult {
    return this.field(label, html`<input type="number" .value=${value === undefined ? "" : String(value)}
      min=${opts.min ?? ""} max=${opts.max ?? ""} step=${opts.step ?? "any"}
      @change=${(e: Event) => { const v = (e.target as HTMLInputElement).value; set(v === "" ? undefined : Number(v)); }}>`);
  }

  private check(label: string, value: boolean | undefined, set: (v: boolean) => void): TemplateResult {
    return html`<label class="ed-check"><input type="checkbox" .checked=${Boolean(value)}
      @change=${(e: Event) => set((e.target as HTMLInputElement).checked)}> ${this.t(label)}</label>`;
  }

  private choice(label: string, value: string | undefined, options: [string, string][],
                 set: (v: string) => void): TemplateResult {
    return this.field(label, html`<select @change=${(e: Event) => set((e.target as HTMLSelectElement).value)}>
      ${options.map(([v, l]) => html`<option value=${v} ?selected=${(value ?? "") === v}>${this.t(l)}</option>`)}</select>`);
  }

  private colour(label: string, value: string | undefined, set: (v: string | undefined) => void): TemplateResult {
    const isToken = !value || value.startsWith("token:") || value === "transparent";
    const options: [string, string][] = [["", "None"], ...TOKENS.map((t): [string, string] => [`token:${t}`,
                                          TOKEN_LABELS[t]]), ["custom", "Custom"]];
    return html`<div class="ed-colour">${this.choice(label, isToken ? value ?? "" : "custom", options, (v) =>
        set(v === "custom" ? "#ffffff" : v || undefined))}
      ${!isToken ? html`<input type="color" aria-label=${this.t(label)} .value=${value ?? "#ffffff"}
        @change=${(e: Event) => set((e.target as HTMLInputElement).value)}>` : nothing}</div>`;
  }

  private assetSelect(label: string, value: unknown, kinds: string[], set: (v: string) => void): TemplateResult {
    const assets = Object.values(this.cfg.assets).filter((a) => kinds.includes(a.kind));
    return this.choice(label, String(value ?? ""), [["", "None"], ...assets.map((a): [string, string] => [a.id, a.name])],
                       set);
  }

  private setProp(key: string, value: unknown): void {
    this.patchSelected((el) => {
      el.props = { ...(el.props ?? {}), [key]: value };
      if (value === undefined || value === "") delete el.props[key];
    });
  }

  private setStyle<K extends keyof ElementStyle>(key: K, value: ElementStyle[K] | undefined): void {
    this.patchSelected((el) => {
      el.style = { ...(el.style ?? {}) };
      if (value === undefined || (value as unknown) === "") delete el.style[key];
      else el.style[key] = value;
    });
  }

  private panel(): TemplateResult {
    const sel = this.selection;
    if (!sel.length) return this.layoutPanel();
    if (sel.length > 1) {
      const a = (mode: AlignMode, label: string) => html`<button class="btn btn-sm" @click=${() =>
        this.commit({ ...this.data, elements: align(this.elements, this.selected, mode) })}>${this.t(label)}</button>`;
      return html`<h2 class="ed-h">${this.t("Several elements selected")}</h2>
        <div class="ed-add">${a("left", "Align left")}${a("center", "Align centre")}${a("right", "Align right")}
          ${a("top", "Align top")}${a("middle", "Align middle")}${a("bottom", "Align bottom")}</div>
        <div class="ed-add"><button class="btn btn-sm" @click=${() => this.duplicateSelected()}>${this.t("Duplicate")}</button>
          <button class="btn btn-sm btn-danger" @click=${() => this.removeSelected()}>${this.t("Delete")}</button></div>`;
    }
    const el = sel[0];
    const p = el.props ?? {};
    const s = el.style ?? {};
    const f = el.frame;
    const setFrame = (k: keyof typeof f) => (v: number | undefined) =>
      this.patchSelected((e) => { e.frame = { ...e.frame, [k]: v ?? 0 }; });
    return html`
      <h2 class="ed-h">${this.t(TYPE_LABELS[el.type] ?? el.type)}</h2>
      ${this.field("Name", html`<input .value=${el.name ?? ""} maxlength="100"
        @change=${(e: Event) => this.patchSelected((x) => { x.name = (e.target as HTMLInputElement).value; })}>`)}
      <div class="ed-add">
        <button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: reorder(this.elements, el.id, 1) })}>${this.t("Bring forward")}</button>
        <button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: reorder(this.elements, el.id, -1) })}>${this.t("Send backward")}</button>
        <button class="btn btn-sm" @click=${() => this.duplicateSelected()}>${this.t("Duplicate")}</button>
        <button class="btn btn-sm btn-danger" @click=${() => this.removeSelected()}>${this.t("Delete")}</button></div>
      <fieldset class="ed-group"><legend>${this.t("Position and size")}</legend><div class="ed-grid">
        ${this.num("X", f.x, setFrame("x"))}${this.num("Y", f.y, setFrame("y"))}
        ${this.num("Width", f.w, setFrame("w"), { min: 0 })}${this.num("Height", f.h, setFrame("h"), { min: 0 })}
        ${this.num("Rotation", f.rotate, setFrame("rotate"), { min: -360, max: 360 })}</div>
        ${this.check("Hidden", el.hidden, (v) => this.patchSelected((x) => { x.hidden = v || undefined; }))}
        ${this.check("Locked", el.locked, (v) => this.patchSelected((x) => { x.locked = v || undefined; }))}</fieldset>
      <fieldset class="ed-group"><legend>${this.t("Content")}</legend>${this.contentFields(el.type, p)}</fieldset>
      <fieldset class="ed-group"><legend>${this.t("Style")}</legend>
        ${this.colour("Colour", s.color, (v) => this.setStyle("color", v))}
        ${this.colour("Background", s.background, (v) => this.setStyle("background", v))}
        ${this.choice("Font", s.fontFamily ?? "", [["", "None"], ["token:body", "Body font"], ["token:heading", "Heading font"],
          ...this.cfg.fontChoices.map((c): [string, string] => [c.value, c.label])], (v) => this.setStyle("fontFamily", v || undefined))}
        <div class="ed-grid">
          ${this.num("Font size", s.fontSize, (v) => this.setStyle("fontSize", v), { min: 0.5, max: 100 })}
          ${this.num("Weight", s.fontWeight, (v) => this.setStyle("fontWeight", v), { min: 100, max: 900, step: 100 })}
          ${this.num("Line height", s.lineHeight, (v) => this.setStyle("lineHeight", v), { min: 0.5, max: 4 })}
          ${this.num("Letter spacing", s.letterSpacing, (v) => this.setStyle("letterSpacing", v), { min: -0.5, max: 2 })}
          ${this.num("Padding", s.padding, (v) => this.setStyle("padding", v), { min: 0, max: 50 })}
          ${this.num("Corner radius", s.radius, (v) => this.setStyle("radius", v), { min: 0, max: 50 })}
          ${this.num("Border", s.borderWidth, (v) => this.setStyle("borderWidth", v), { min: 0, max: 20 })}
          ${this.num("Opacity", s.opacity, (v) => this.setStyle("opacity", v), { min: 0, max: 1, step: 0.05 })}</div>
        ${this.colour("Border colour", s.borderColor, (v) => this.setStyle("borderColor", v))}
        ${this.choice("Alignment", s.textAlign, [["", "None"], ["left", "Left"], ["center", "Center"], ["right", "Right"],
          ["justify", "Justify"]], (v) => this.setStyle("textAlign", (v || undefined) as ElementStyle["textAlign"]))}
        ${this.choice("Vertical", s.verticalAlign, [["", "None"], ["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]],
          (v) => this.setStyle("verticalAlign", (v || undefined) as ElementStyle["verticalAlign"]))}
        ${this.choice("Style of text", s.fontStyle, [["", "None"], ["normal", "Normal"], ["italic", "Italic"]],
          (v) => this.setStyle("fontStyle", (v || undefined) as ElementStyle["fontStyle"]))}
        ${this.choice("Text case", s.textTransform, [["", "None"], ["uppercase", "Uppercase"], ["lowercase", "Lowercase"],
          ["capitalize", "Capitalise"]], (v) => this.setStyle("textTransform", (v || undefined) as ElementStyle["textTransform"]))}
        ${this.check("Shadow", s.shadow, (v) => this.setStyle("shadow", v || undefined))}
        ${this.check("Tabular numbers", s.tabularNumbers, (v) => this.setStyle("tabularNumbers", v || undefined))}</fieldset>
      <fieldset class="ed-group"><legend>${this.t("Animation")}</legend>
        ${this.choice("Entrance", el.animation?.enter ?? "none", [["none", "None"], ["fade", "Fade"], ["slide-up", "Slide up"],
          ["slide-left", "Slide in"], ["zoom", "Zoom in"]], (v) => this.patchSelected((x) => {
            x.animation = { ...(x.animation ?? {}), enter: v as never }; }))}
        <div class="ed-grid">${this.num("Duration (ms)", el.animation?.duration, (v) => this.patchSelected((x) => {
            x.animation = { ...(x.animation ?? {}), duration: v }; }), { min: 0, max: 10000, step: 50 })}
          ${this.num("Delay (ms)", el.animation?.delay, (v) => this.patchSelected((x) => {
            x.animation = { ...(x.animation ?? {}), delay: v }; }), { min: 0, max: 60000, step: 50 })}</div></fieldset>
      ${this.field("Show only if", html`<input .value=${el.visible_if ?? ""} maxlength="300" placeholder="screen.zone"
        @change=${(e: Event) => this.patchSelected((x) => { x.visible_if = (e.target as HTMLInputElement).value || undefined; })}>`)}`;
  }

  private contentFields(type: string, p: Record<string, unknown>): TemplateResult {
    const text = (label: string, key: string, rows = 3) => this.field(label, html`<textarea rows=${rows}
      .value=${String(p[key] ?? "")} @change=${(e: Event) => this.setProp(key, (e.target as HTMLTextAreaElement).value)}></textarea>`);
    const fit = this.choice("Fit mode", String(p.fit ?? ""), [["contain", "Contain"], ["cover", "Cover"], ["fill", "Stretch"]],
                            (v) => this.setProp("fit", v));
    const hint = html`<p class="small muted">${this.t("Template variables: {{ event.name }}, {{ screen.name }}, {{ screen.zone }}, {{ now|time }}")}</p>`;
    switch (type) {
      case "text":
        return html`${text("Text", "text")}${hint}${this.check("Shrink text to fit", p.autofit as boolean, (v) => this.setProp("autofit", v))}
          ${this.check("Ticker (scrolling)", p.marquee as boolean, (v) => this.setProp("marquee", v))}
          ${this.num("Maximum lines", p.clamp as number, (v) => this.setProp("clamp", v), { min: 0, max: 50, step: 1 })}`;
      case "richtext":
        return html`${text("Text", "text", 6)}${hint}`;
      case "image":
        return html`${this.assetSelect("File", p.asset, ["image", "svg"], (v) => this.setProp("asset", v))}${fit}
          <a class="small" href=${this.cfg.urls.assets} target="_blank" rel="noopener">${this.t("Upload files")}</a>`;
      case "slideshow": {
        const chosen = new Set((p.assets as string[]) ?? []);
        return html`<p class="ed-label">${this.t("Images")}</p><div class="ed-list">${Object.values(this.cfg.assets)
          .filter((a) => a.kind === "image" || a.kind === "svg").map((a) => this.check(a.name, chosen.has(a.id), (v) => {
            const next = new Set(chosen);
            if (v) next.add(a.id); else next.delete(a.id);
            this.setProp("assets", [...next]);
          }))}</div>${this.num("Seconds per image", p.interval as number, (v) => this.setProp("interval", v), { min: 1, max: 3600 })}${fit}`;
      }
      case "video":
        return html`${this.assetSelect("File", p.asset, ["video"], (v) => this.setProp("asset", v))}${fit}
          ${this.check("Loop", p.loop as boolean, (v) => this.setProp("loop", v))}${this.check("Muted", p.muted as boolean, (v) => this.setProp("muted", v))}`;
      case "audio":
        return html`${this.assetSelect("File", p.asset, ["audio"], (v) => this.setProp("asset", v))}
          ${this.check("Loop", p.loop as boolean, (v) => this.setProp("loop", v))}`;
      case "shape":
        return this.choice("Form", String(p.shape ?? "rect"), [["rect", "Rectangle"], ["ellipse", "Ellipse"], ["line", "Line"]],
                           (v) => this.setProp("shape", v));
      case "qr":
        return html`${text("Text", "text", 2)}${hint}`;
      case "clock":
        return html`${this.choice("Format", String(p.format ?? "HH:mm"), [["HH:mm", "HH:mm"], ["HH:mm:ss", "HH:mm:ss"], ["h:mm a", "h:mm a"]],
                                  (v) => this.setProp("format", v))}
          ${this.field("Time zone (empty = event)", html`<input .value=${String(p.timezone ?? "")} placeholder="Europe/Berlin"
            @change=${(e: Event) => this.setProp("timezone", (e.target as HTMLInputElement).value)}>`)}`;
      case "countdown":
        return html`${this.field("Target time", html`<input type="datetime-local" .value=${String(p.target ?? "").slice(0, 16)}
            @change=${(e: Event) => this.setProp("target", (e.target as HTMLInputElement).value)}>`)}
          ${this.choice("Format", String(p.format ?? "auto"), [["auto", "Automatic"], ["hms", "Hours:minutes:seconds"],
            ["ms", "Minutes:seconds"], ["days", "Days"]], (v) => this.setProp("format", v))}
          ${text("Text when finished", "finished", 1)}`;
      case "date":
        return this.choice("Format", String(p.format ?? "long"), [["long", "Long"], ["short", "Short"], ["weekday", "Weekday"],
                           ["iso", "ISO"]], (v) => this.setProp("format", v));
      case "code":
        return this.codeFields(p);
      default:
        return html``;
    }
  }

  private codeFields(p: Record<string, unknown>): TemplateResult {
    const can = this.cfg.canCode;
    const code = (label: string, key: string, rows: number) => this.field(label, html`<textarea class="ed-code" rows=${rows}
      spellcheck="false" ?readonly=${!can} .value=${String(p[key] ?? "")}
      @change=${(e: Event) => this.setProp(key, (e.target as HTMLTextAreaElement).value)}></textarea>`);
    const data = new Set((p.data as string[]) ?? []);
    const toggle = (kind: string) => (v: boolean) => {
      const next = new Set(data);
      if (v) next.add(kind); else next.delete(kind);
      this.setProp("data", ["event", "screen", "time", "assets"].filter((k) => next.has(k)));
    };
    const chosen = new Set((p.assets as string[]) ?? []);
    return html`${can ? nothing : html`<p class="small muted">${this.t("Only people allowed to write code can change this element.")}</p>`}
      ${code("HTML", "html", 5)}${code("CSS", "css", 5)}${code("JavaScript", "js", 8)}
      <p class="small muted">${this.t("Code runs in a sandbox without network. Read data with evac.data and evac.onData(fn); evac.now() is the server time.")}</p>
      <fieldset class="ed-group" ?disabled=${!can}><legend>${this.t("Data for the code")}</legend>
        ${this.check("Event", data.has("event"), toggle("event"))}${this.check("Screen", data.has("screen"), toggle("screen"))}
        ${this.check("Time", data.has("time"), toggle("time"))}${this.check("Files", data.has("assets"), toggle("assets"))}
        ${data.has("assets") ? html`<div class="ed-list">${Object.values(this.cfg.assets).map((a) => this.check(a.name,
          chosen.has(a.id), (v) => {
            const next = new Set(chosen);
            if (v) next.add(a.id); else next.delete(a.id);
            this.setProp("assets", [...next].slice(0, 20));
          }))}</div>` : nothing}</fieldset>`;
  }

  private layoutPanel(): TemplateResult {
    const d = this.data;
    const bg = d.background ?? {};
    const setBg = (k: "color" | "asset", v: string | undefined) => {
      const next = { ...bg, [k]: v };
      if (!v) delete next[k];
      this.commit({ ...d, background: Object.keys(next).length ? next : undefined });
    };
    return html`<h2 class="ed-h">${this.t("Layout")}</h2>
      <p class="small muted">${this.t("Select an element on the canvas or in the layers list.")}</p>
      <div class="ed-grid">
        ${this.num("Width", d.width, (v) => this.commit({ ...d, width: Math.max(64, Math.round(v ?? 1920)) }), { min: 64, max: 16384, step: 1 })}
        ${this.num("Height", d.height, (v) => this.commit({ ...d, height: Math.max(64, Math.round(v ?? 1080)) }), { min: 64, max: 16384, step: 1 })}</div>
      ${this.colour("Background", bg.color, (v) => setBg("color", v))}
      ${this.assetSelect("Background image", bg.asset, ["image", "svg"], (v) => setBg("asset", v || undefined))}
      ${this.num("Seconds on screen (playlists)", d.duration, (v) => this.commit({ ...d, duration: v }), { min: 1, max: 86400, step: 1 })}`;
  }
}

if (!customElements.get("evac-layout-editor")) customElements.define("evac-layout-editor", LayoutEditor);
