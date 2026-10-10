// SPDX-License-Identifier: AGPL-3.0-or-later
// Venue map editor island (ADR-0027): floor plan with the route graph, zone outlines and screens. Tools: select
// and drag, add point, connect two points, draw a zone outline, place an item of a map layer (screens, with the
// direction it faces) and measure a known distance to set the plan's scale. Every change is saved at once
// through /map/op/ and the map reloads from the server (routes and plan checks stay authoritative there).
import "./mapeditor.css";

import { html, LitElement, nothing, svg, type TemplateResult } from "lit";

import {
  arrow, type Box, distance, extent, facingTriangle, GLYPHS, type LayerItem, type MapData, type MapPoint,
  pixelsFor, r3, zoom,
} from "./model";

interface Config { dataUrl: string; opUrl: string; strings: Record<string, string> }
type Tool = "select" | "point" | "connect" | "zone" | "place" | "measure";
type Selection = { type: "point" | "edge" | "item"; id: string; layer?: string } | null;

function csrf(): string {
  return document.cookie.split("; ").find((c) => c.startsWith("csrftoken="))?.split("=")[1] ?? "";
}

function readConfig(): Config | null {
  const el = document.getElementById("map-config");
  return el?.textContent ? (JSON.parse(el.textContent) as Config) : null;
}

export class EvacMapEditor extends LitElement {
  static properties = {
    data: { state: true }, view: { state: true }, tool: { state: true }, selected: { state: true },
    status: { state: true }, pointKind: { state: true }, pending: { state: true }, corners: { state: true },
    zoneId: { state: true }, placing: { state: true }, measured: { state: true },
  };

  data: MapData | null = null;
  view: Box = { x: 0, y: 0, w: 100, h: 60 };
  tool: Tool = "select";
  selected: Selection = null;
  status = "";
  pointKind = "exit";
  pending: string | null = null; // first point of a connection
  corners: [number, number][] = [];
  zoneId = "";
  placing: { layer: string; id: string } | null = null;
  measured: [number, number][] = [];
  private cfg: Config | null = readConfig();
  private drag: { kind: "pan" | "point" | "item"; id?: string; layer?: string; sx: number; sy: number;
                  start: Box; moved: boolean; x?: number; y?: number } | null = null;

  createRenderRoot() { return this; } // light DOM: portal styles apply

  connectedCallback() {
    super.connectedCallback();
    this.textContent = "";
    void this.load(true);
  }

  t(s: string): string { return this.cfg?.strings[s] ?? s; }

  async load(fit = false) {
    if (!this.cfg) return;
    const res = await fetch(this.cfg.dataUrl, { credentials: "same-origin" });
    if (!res.ok) { this.status = this.t("Could not save"); return; }
    this.data = (await res.json()) as MapData;
    if (fit) this.view = extent(this.data);
  }

  private queue: Promise<unknown> = Promise.resolve();

  /** One operation at a time, in order (a drag and a click must not race). */
  op(body: Record<string, unknown>): Promise<Record<string, unknown> | null> {
    const next = this.queue.then(() => this.send(body), () => this.send(body));
    this.queue = next;
    return next;
  }

  private async send(body: Record<string, unknown>): Promise<Record<string, unknown> | null> {
    if (!this.cfg) return null;
    this.status = this.t("Saving…");
    const res = await fetch(this.cfg.opUrl, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body),
    });
    const out = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    this.status = res.ok ? this.t("Saved") : `${this.t("Could not save")}: ${String(out.error ?? res.status)}`;
    await this.load();
    return res.ok ? out : null;
  }

  // ---------------------------------------------------------------- coordinates
  private svgEl(): SVGSVGElement | null { return this.querySelector("svg.mapeditor-canvas"); }

  private toMap(e: PointerEvent | WheelEvent | MouseEvent): [number, number] {
    const el = this.svgEl();
    const m = el?.getScreenCTM();
    if (!el || !m) return [0, 0];
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
    return [r3(p.x), r3(p.y)];
  }

  private pointById(id: string): MapPoint | undefined { return this.data?.points.find((p) => p.id === id); }

  private item(layer: string, id: string): LayerItem | undefined {
    return this.data?.layers.find((l) => l.key === layer)?.items.find((i) => i.id === id);
  }

  // ---------------------------------------------------------------- pointer handling
  private onWheel(e: WheelEvent) {
    e.preventDefault();
    const [x, y] = this.toMap(e);
    this.view = zoom(this.view, e.deltaY < 0 ? 1.2 : 1 / 1.2, x, y);
  }

  private onDown(e: PointerEvent) {
    const target = e.target as Element;
    const pointId = target.closest("[data-point]")?.getAttribute("data-point");
    const itemEl = target.closest("[data-item]");
    const [x, y] = this.toMap(e);
    const edit = this.data?.canEdit ?? false;
    if (this.tool === "select" && pointId && edit) {
      this.selected = { type: "point", id: pointId };
      this.drag = { kind: "point", id: pointId, sx: e.clientX, sy: e.clientY, start: this.view, moved: false };
    } else if (this.tool === "select" && itemEl) {
      const id = itemEl.getAttribute("data-item") ?? "", layer = itemEl.getAttribute("data-layer") ?? "";
      this.selected = { type: "item", id, layer };
      if (edit) this.drag = { kind: "item", id, layer, sx: e.clientX, sy: e.clientY, start: this.view, moved: false };
    } else if (this.tool === "select") {
      const edgeId = target.closest("[data-edge]")?.getAttribute("data-edge");
      this.selected = edgeId ? { type: "edge", id: edgeId } : null;
      this.drag = { kind: "pan", sx: e.clientX, sy: e.clientY, start: this.view, moved: false };
    } else {
      void this.mapClick(x, y, pointId ?? null);
      return;
    }
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  }

  private onMove(e: PointerEvent) {
    const d = this.drag;
    if (!d) return;
    d.moved = d.moved || Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) > 3;
    if (!d.moved) return;
    if (d.kind === "pan") {
      const el = this.svgEl();
      const scale = el ? d.start.w / el.clientWidth : 1;
      this.view = { ...d.start, x: d.start.x - (e.clientX - d.sx) * scale, y: d.start.y - (e.clientY - d.sy) * scale };
      return;
    }
    const [x, y] = this.toMap(e);
    d.x = x;
    d.y = y;
    if (d.kind === "point") {
      const p = this.pointById(d.id ?? "");
      if (p) { p.x = x; p.y = y; }
    } else {
      const it = this.item(d.layer ?? "", d.id ?? "");
      if (it) { it.x = x; it.y = y; }
    }
    this.requestUpdate();
  }

  private onUp() {
    const d = this.drag;
    this.drag = null;
    if (!d || !d.moved || d.x === undefined) return;
    if (d.kind === "point") void this.op({ op: "point.update", id: d.id, x: d.x, y: d.y });
    if (d.kind === "item") {
      const it = this.item(d.layer ?? "", d.id ?? "");
      void this.op({ op: "layer.place", layer: d.layer, id: d.id, x: d.x, y: d.y, facing: it?.facing ?? 0 });
    }
  }

  private async mapClick(x: number, y: number, pointId: string | null) {
    if (!this.data?.canEdit && this.tool !== "measure") return;
    if (this.tool === "point") {
      const out = await this.op({ op: "point.add", kind: this.pointKind, x, y });
      if (out?.id) this.selected = { type: "point", id: String(out.id) };
    } else if (this.tool === "connect" && pointId) {
      if (!this.pending) { this.pending = pointId; return; }
      if (pointId !== this.pending) await this.op({ op: "edge.add", a: this.pending, b: pointId });
      this.pending = null;
    } else if (this.tool === "zone" && this.zoneId) {
      this.corners = [...this.corners, [x, y]];
    } else if (this.tool === "place" && this.placing) {
      const it = this.item(this.placing.layer, this.placing.id);
      await this.op({ op: "layer.place", layer: this.placing.layer, id: this.placing.id, x, y,
                      facing: it?.facing ?? 0 });
      this.selected = { type: "item", ...this.placing };
      this.placing = null;
      this.tool = "select";
    } else if (this.tool === "measure") {
      this.measured = this.measured.length >= 2 ? [[x, y]] : [...this.measured, [x, y]];
    }
  }

  private setTool(tool: Tool) {
    this.tool = tool;
    this.pending = null;
    this.corners = [];
    this.measured = [];
    if (tool !== "place") this.placing = null;
  }

  // ---------------------------------------------------------------- rendering
  render(): TemplateResult {
    const d = this.data;
    if (!d) return html`<p class="muted">${this.t("Loading…")}</p>`;
    const tools: [Tool, string][] = [["select", "Select"], ["point", "Add point"], ["connect", "Connect"],
      ["zone", "Zone outline"], ["place", "Place"], ["measure", "Measure"]];
    return html`
      <div class="mapeditor">
        <div class="mapeditor-toolbar" role="toolbar" aria-label=${this.t("Tools")}>
          ${tools.filter(([k]) => d.canEdit || k === "select" || k === "measure").map(([k, label]) => html`
            <button type="button" class="btn btn-sm ${this.tool === k ? "btn-primary" : ""}" aria-pressed=${this.tool === k}
              @click=${() => this.setTool(k)}>${this.t(label)}</button>`)}
          <span class="mapeditor-sep"></span>
          <button type="button" class="btn btn-sm" aria-label=${this.t("Zoom in")}
            @click=${() => { this.view = zoom(this.view, 1.4, this.view.x + this.view.w / 2, this.view.y + this.view.h / 2); }}>+</button>
          <button type="button" class="btn btn-sm" aria-label=${this.t("Zoom out")}
            @click=${() => { this.view = zoom(this.view, 1 / 1.4, this.view.x + this.view.w / 2, this.view.y + this.view.h / 2); }}>−</button>
          <button type="button" class="btn btn-sm" @click=${() => { this.view = extent(d); }}>${this.t("Fit")}</button>
          <span class="mapeditor-status small muted" role="status" aria-live="polite">${this.status}</span>
        </div>
        <div class="mapeditor-body">
          ${this.canvas(d)}
          <aside class="mapeditor-panel">${this.panel(d)}</aside>
        </div>
      </div>`;
  }

  private canvas(d: MapData): TemplateResult {
    const v = this.view;
    const unit = v.w / 120; // marker size in metres at the current zoom
    const pts = new Map(d.points.map((p) => [p.id, p]));
    const plan = d.plan;
    return html`<svg class="mapeditor-canvas tool-${this.tool}" viewBox="${v.x} ${v.y} ${v.w} ${v.h}"
        role="img" aria-label=${this.t("Map")} @wheel=${this.onWheel} @pointerdown=${this.onDown}
        @pointermove=${this.onMove} @pointerup=${this.onUp} @pointercancel=${this.onUp}>
      <defs><pattern id="mapeditor-grid" width="10" height="10" patternUnits="userSpaceOnUse">
        <path d="M 10 0 L 0 0 0 10" class="mapeditor-gridline"></path></pattern></defs>
      ${plan ? svg`<image href=${plan.url} x="0" y="0" width=${plan.width * plan.metresPerPx}
          height=${plan.height * plan.metresPerPx} preserveAspectRatio="none"></image>`
        : svg`<rect x=${v.x - v.w} y=${v.y - v.h} width=${v.w * 3} height=${v.h * 3} fill="url(#mapeditor-grid)"></rect>`}
      ${d.zones.filter((z) => z.area).map((z) => svg`<g class="mapeditor-zone">
          <polygon points=${(z.area ?? []).map(([x, y]) => `${x},${y}`).join(" ")} fill=${z.color} stroke=${z.color}
            stroke-width=${unit * 0.3}></polygon>
          <text x=${(z.area ?? [[0, 0]])[0][0]} y=${(z.area ?? [[0, 0]])[0][1] - unit} font-size=${unit * 1.8}>${z.name}</text></g>`)}
      ${d.edges.map((e) => {
        const a = pts.get(e.a), b = pts.get(e.b);
        if (!a || !b) {
          const here = a ?? b;
          return here ? svg`<g class="mapeditor-edge elsewhere" data-edge=${e.id}><title>${e.elsewhere ?? ""}</title>
            <circle cx=${here.x} cy=${here.y} r=${unit * 1.6} stroke-width=${unit * 0.25}></circle></g>` : nothing;
        }
        const sel = this.selected?.type === "edge" && this.selected.id === e.id;
        const head = e.oneWay ? arrow({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }, b, unit * 1.5, unit) : null;
        return svg`<g class="mapeditor-edge ${e.stepFree ? "" : "steps"} ${sel ? "selected" : ""}" data-edge=${e.id}>
          <line x1=${a.x} y1=${a.y} x2=${b.x} y2=${b.y} class="hit" stroke-width=${unit * 1.5}></line>
          <line x1=${a.x} y1=${a.y} x2=${b.x} y2=${b.y} stroke-width=${unit * 0.35}></line>
          ${head ? svg`<polyline points="${head.barbs[0].join(",")} ${head.x2},${head.y2} ${head.barbs[1].join(",")}"
            stroke-width=${unit * 0.35}></polyline>` : nothing}</g>`;
      })}
      ${d.points.map((p) => {
        const next = p.next ? pts.get(p.next) : undefined;
        const hint = next ? arrow(p, next, unit * 4, unit * 1.2) : null;
        return hint ? svg`<g class="mapeditor-route"><line x1=${hint.x1} y1=${hint.y1} x2=${hint.x2} y2=${hint.y2}
          stroke-width=${unit * 0.5}></line><polyline points="${hint.barbs[0].join(",")} ${hint.x2},${hint.y2} ${hint.barbs[1].join(",")}"
          stroke-width=${unit * 0.5}></polyline></g>` : nothing;
      })}
      ${d.points.map((p) => {
        const sel = (this.selected?.type === "point" && this.selected.id === p.id) || this.pending === p.id;
        return svg`<g class="mapeditor-point kind-${p.kind} ${sel ? "selected" : ""} ${p.noWayOut ? "no-way-out" : ""}"
            data-point=${p.id}><title>${p.name}${p.noWayOut ? ` – ${this.t("No way out")}` : ""}</title>
          <circle cx=${p.x} cy=${p.y} r=${unit * 1.4} stroke-width=${unit * 0.3}></circle>
          <text x=${p.x} y=${p.y + unit * 0.55} font-size=${unit * 1.5} text-anchor="middle">${GLYPHS[p.kind] ?? "?"}</text>
          <text x=${p.x + unit * 2} y=${p.y + unit * 0.5} font-size=${unit * 1.4} class="label">${p.name}${p.noWayOut ? " !" : ""}</text></g>`;
      })}
      ${d.layers.flatMap((l) => l.items.filter((i) => i.placed && i.x !== null && i.y !== null).map((i) => {
        const sel = this.selected?.type === "item" && this.selected.id === i.id;
        return svg`<g class="mapeditor-item layer-${l.key} ${sel ? "selected" : ""}" data-item=${i.id} data-layer=${l.key}>
          <title>${i.label}</title>
          <polygon points=${facingTriangle(i.x ?? 0, i.y ?? 0, i.facing ?? 0, unit)} class="facing"></polygon>
          <rect x=${(i.x ?? 0) - unit} y=${(i.y ?? 0) - unit * 0.7} width=${unit * 2} height=${unit * 1.4}
            stroke-width=${unit * 0.25}></rect>
          <text x=${(i.x ?? 0) + unit * 2} y=${(i.y ?? 0) + unit * 0.5} font-size=${unit * 1.3} class="label">${i.label}</text></g>`;
      }))}
      ${this.corners.length ? svg`<polyline class="mapeditor-draft" points=${this.corners.map(([x, y]) => `${x},${y}`).join(" ")}
        stroke-width=${unit * 0.4}></polyline>` : nothing}
      ${this.measured.length ? svg`<polyline class="mapeditor-measure" points=${this.measured.map(([x, y]) => `${x},${y}`).join(" ")}
        stroke-width=${unit * 0.4}></polyline>${this.measured.map(([x, y]) => svg`<circle class="mapeditor-measure"
        cx=${x} cy=${y} r=${unit * 0.6}></circle>`)}` : nothing}
    </svg>`;
  }

  // ---------------------------------------------------------------- side panel
  private panel(d: MapData): TemplateResult {
    return html`
      ${this.hint(d)}
      ${this.toolPanel(d)}
      ${this.selectionPanel(d)}
      <details class="mapeditor-list" open><summary>${this.t("Points")} (${d.points.length})</summary>
        <ul class="plain small">${d.points.map((p) => html`<li><button type="button" class="link-button"
          @click=${() => { this.selected = { type: "point", id: p.id }; this.tool = "select"; }}>
          ${GLYPHS[p.kind]} ${p.name}</button>${p.noWayOut ? html` <span class="badge badge-err">${this.t("No way out")}</span>` : nothing}</li>`)}</ul>
      </details>
      ${d.layers.map((l) => html`<details class="mapeditor-list" open><summary>${l.title}</summary>
        <ul class="plain small">${l.items.map((i) => html`<li><button type="button" class="link-button"
          @click=${() => { this.selected = { type: "item", id: i.id, layer: l.key }; this.tool = "select"; }}>${i.label}</button>
          ${i.placed ? nothing : html` <span class="muted">(${this.t("Not on this map")})</span>`}</li>`)}</ul></details>`)}`;
  }

  private hint(d: MapData): TemplateResult {
    const text: Record<Tool, string> = {
      select: "Drag points to move them. Arrows show the way out.", point: "Click on the map to place it.",
      connect: "Click two points to connect them.", zone: "Click the corners, then Finish outline.",
      place: "Click on the map to place it.", measure: "Click two ends of a known distance.",
    };
    return html`<p class="small muted">${this.t(text[this.tool])}${d.plan && !d.plan.scaled
      ? html`<br><span class="badge badge-warn">${this.t("Plan not measured yet")}</span>` : nothing}</p>`;
  }

  private toolPanel(d: MapData): TemplateResult | typeof nothing {
    if (this.tool === "point") {
      return html`<label class="field">${this.t("Kind")}<select .value=${this.pointKind}
        @change=${(e: Event) => { this.pointKind = (e.target as HTMLSelectElement).value; }}>
        ${d.kinds.map(([k, label]) => html`<option value=${k} ?selected=${k === this.pointKind}>${label}</option>`)}</select></label>`;
    }
    if (this.tool === "zone") {
      return html`<label class="field">${this.t("Zone")}<select @change=${(e: Event) => {
          this.zoneId = (e.target as HTMLSelectElement).value; this.corners = []; }}>
        <option value="">${this.t("Choose a zone")}</option>
        ${d.zones.map((z) => html`<option value=${z.id} ?selected=${z.id === this.zoneId}>${z.name}</option>`)}</select></label>
        <div class="form-actions">
          <button type="button" class="btn btn-sm btn-primary" ?disabled=${this.corners.length < 3}
            @click=${async () => { await this.op({ op: "zone.area", zone: this.zoneId, points: this.corners }); this.corners = []; }}>
            ${this.t("Finish outline")}</button>
          <button type="button" class="btn btn-sm" ?disabled=${!this.zoneId}
            @click=${async () => { await this.op({ op: "zone.area", zone: this.zoneId, points: [] }); this.corners = []; }}>
            ${this.t("Clear outline")}</button></div>`;
    }
    if (this.tool === "place") {
      const items = d.layers.filter((l) => l.editable).flatMap((l) => l.items.map((i) => ({ l, i })));
      return html`<label class="field">${this.t("Choose what to place")}<select @change=${(e: Event) => {
          const [layer, id] = (e.target as HTMLSelectElement).value.split("|");
          this.placing = id ? { layer, id } : null; }}>
        <option value="">–</option>
        ${items.map(({ l, i }) => html`<option value="${l.key}|${i.id}">${l.title}: ${i.label}${i.placed ? ` (${this.t("On this floor")})` : ""}</option>`)}
      </select></label>`;
    }
    if (this.tool === "measure" && this.measured.length === 2 && d.plan) {
      const m = distance(this.measured[0], this.measured[1]);
      return html`<form class="field" @submit=${async (e: Event) => {
          e.preventDefault();
          const metres = Number((e.target as HTMLFormElement).elements.namedItem("metres") instanceof HTMLInputElement
            ? ((e.target as HTMLFormElement).elements.namedItem("metres") as HTMLInputElement).value : 0);
          if (d.plan && metres > 0) {
            await this.op({ op: "scale", px: pixelsFor(m, d.plan), metres });
            this.measured = [];
            await this.load(true);
          }
        }}>
        <label>${this.t("Distance in metres")} <input name="metres" type="number" min="0.01" step="0.01" required
          .value=${String(Math.round(m * 100) / 100)}></label>
        ${d.canEdit ? html`<button class="btn btn-sm btn-primary">${this.t("Set scale")}</button>` : nothing}</form>`;
    }
    return nothing;
  }

  private selectionPanel(d: MapData): TemplateResult | typeof nothing {
    const s = this.selected;
    if (!s) return nothing;
    const edit = d.canEdit;
    if (s.type === "point") {
      const p = this.pointById(s.id);
      if (!p) return nothing;
      const next = p.next ? this.pointById(p.next) ?? d.elsewhere[p.next] : undefined;
      return html`<section class="mapeditor-props"><h2 class="h3">${GLYPHS[p.kind]} ${p.name}</h2>
        <label class="field">${this.t("Name")}<input .value=${p.name} ?disabled=${!edit}
          @change=${(e: Event) => this.op({ op: "point.update", id: p.id, name: (e.target as HTMLInputElement).value })}></label>
        <label class="field">${this.t("Kind")}<select ?disabled=${!edit}
          @change=${(e: Event) => this.op({ op: "point.update", id: p.id, kind: (e.target as HTMLSelectElement).value })}>
          ${d.kinds.map(([k, label]) => html`<option value=${k} ?selected=${k === p.kind}>${label}</option>`)}</select></label>
        <label class="field">${this.t("Zone")}<select ?disabled=${!edit}
          @change=${(e: Event) => this.op({ op: "point.update", id: p.id, zone: (e.target as HTMLSelectElement).value || null })}>
          <option value="">–</option>
          ${d.zones.map((z) => html`<option value=${z.id} ?selected=${z.id === p.zone}>${z.name}</option>`)}</select></label>
        <div class="grid-xy"><label class="field">x (m)<input type="number" step="0.1" .value=${String(p.x)} ?disabled=${!edit}
          @change=${(e: Event) => this.op({ op: "point.update", id: p.id, x: Number((e.target as HTMLInputElement).value) })}></label>
        <label class="field">y (m)<input type="number" step="0.1" .value=${String(p.y)} ?disabled=${!edit}
          @change=${(e: Event) => this.op({ op: "point.update", id: p.id, y: Number((e.target as HTMLInputElement).value) })}></label></div>
        <label class="check"><input type="checkbox" .checked=${p.stepFree} ?disabled=${!edit}
          @change=${(e: Event) => this.op({ op: "point.update", id: p.id, stepFree: (e.target as HTMLInputElement).checked })}>
          ${this.t("Step-free")}</label>
        <p class="small">${this.t("Next step")}: ${next ? next.name : html`<span class="badge badge-err">${this.t("No way out")}</span>`}</p>
        ${edit ? html`<button type="button" class="btn btn-sm btn-ghost" @click=${async () => {
          await this.op({ op: "point.delete", id: p.id }); this.selected = null; }}>${this.t("Delete")}</button>` : nothing}
      </section>`;
    }
    if (s.type === "edge") {
      const e = d.edges.find((x) => x.id === s.id);
      if (!e) return nothing;
      const name = (id: string) => this.pointById(id)?.name ?? d.elsewhere[id]?.name ?? "?";
      return html`<section class="mapeditor-props"><h2 class="h3">${name(e.a)} ${e.oneWay ? "→" : "↔"} ${name(e.b)}</h2>
        <label class="check"><input type="checkbox" .checked=${e.oneWay} ?disabled=${!edit}
          @change=${(ev: Event) => this.op({ op: "edge.update", id: e.id, oneWay: (ev.target as HTMLInputElement).checked })}>
          ${this.t("One way")}</label>
        <label class="check"><input type="checkbox" .checked=${e.stepFree} ?disabled=${!edit}
          @change=${(ev: Event) => this.op({ op: "edge.update", id: e.id, stepFree: (ev.target as HTMLInputElement).checked })}>
          ${this.t("Step-free")}</label>
        ${edit ? html`<button type="button" class="btn btn-sm btn-ghost" @click=${async () => {
          await this.op({ op: "edge.delete", id: e.id }); this.selected = null; }}>${this.t("Delete")}</button>` : nothing}
      </section>`;
    }
    const layer = d.layers.find((l) => l.key === s.layer);
    const it = layer?.items.find((i) => i.id === s.id);
    if (!layer || !it) return nothing;
    const can = layer.editable;
    return html`<section class="mapeditor-props"><h2 class="h3">${layer.title}: ${it.label}</h2>
      ${it.placed ? html`
        <label class="field">${this.t("Facing")} (°)<input type="range" min="0" max="359" step="1" .value=${String(it.facing ?? 0)}
          ?disabled=${!can} @change=${(e: Event) => this.op({ op: "layer.place", layer: layer.key, id: it.id, x: it.x, y: it.y,
            facing: Number((e.target as HTMLInputElement).value) })}></label>
        <p class="small muted">${Math.round(it.facing ?? 0)}°</p>
        ${can ? html`<button type="button" class="btn btn-sm btn-ghost"
          @click=${() => this.op({ op: "layer.place", layer: layer.key, id: it.id, x: null })}>${this.t("Remove from map")}</button>` : nothing}`
        : html`<p class="small">${this.t("Not on this map")}</p>${can ? html`<button type="button" class="btn btn-sm"
          @click=${() => { this.tool = "place"; this.placing = { layer: layer.key, id: it.id }; }}>${this.t("Place")}</button>` : nothing}`}
    </section>`;
  }
}

if (!customElements.get("evac-map-editor")) customElements.define("evac-map-editor", EvacMapEditor);
