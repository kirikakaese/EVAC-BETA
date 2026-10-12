// SPDX-License-Identifier: AGPL-3.0-or-later
// The deterministic layout renderer shared by the player and the editor preview (brief §5.1): the stage keeps
// the layout's aspect ratio inside its host (letterboxed), every element is positioned in percent of the
// stage and sized in container-query units, so the preview is pixel-identical to the screen.
import "./renderer.css";

import { applyStyle, color } from "./style";
import { condition } from "./template";
import type { LayoutData, LayoutElement, RenderContext } from "./types";
import { defineWidgets, EvacWidget } from "./widgets";
import "./data";  // registers the "data" element (custom widgets)
import "./program";  // registers the "program" element (ADR-0038)
import "./plugin";  // registers the "plugin" element (ADR-0045)
import "./timer";  // registers the "progress" element (slide timer, ADR-0051)

export interface RenderedLayout {
  stage: HTMLElement;
  elements: Map<string, HTMLElement>;
  destroy(): void;
}

const ENTRANCES = new Set(["fade", "slide-up", "slide-left", "zoom"]);
/** the layout format's bounds (apps/content/layout_format.py) */
export const MAX_EFFECT_MS = 10_000;
export const MAX_DELAY_MS = 60_000;

const clamp = (v: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, Number(v) || 0));

/** Whether entrance effects play: not with reduced motion, not for evacuation or urgent content
 *  (``motion: false``), and in the editor only when asked for (ADR-0051). */
export function motionOn(ctx: RenderContext): boolean {
  return !ctx.reducedMotion && (ctx.motion ?? !ctx.editing);
}

export function frameStyle(node: HTMLElement, el: LayoutElement): void {
  const f = el.frame;
  node.style.left = `${f.x}%`;
  node.style.top = `${f.y}%`;
  node.style.width = `${f.w}%`;
  node.style.height = `${f.h}%`;
  node.style.transform = f.rotate ? `rotate(${f.rotate}deg)` : "";
}

export function renderElement(el: LayoutElement, ctx: RenderContext): HTMLElement | null {
  const visible = !el.visible_if || condition(el.visible_if, ctx.vars, { now: ctx.now, timezone: ctx.timezone });
  if (el.hidden && !ctx.editing) return null;
  if (!visible && !ctx.editing) return null;
  const box = document.createElement("div");
  box.className = `evac-el evac-el-${el.type}`;
  box.dataset.id = el.id;
  if (!visible || el.hidden) box.classList.add("evac-dimmed");
  frameStyle(box, el);
  applyStyle(box, el.style, ctx);
  const anim = el.animation;
  if (anim?.enter && ENTRANCES.has(anim.enter) && motionOn(ctx)) {
    box.classList.add(`evac-enter-${anim.enter}`);
    box.style.animationDuration = `${clamp(anim.duration ?? 600, 0, MAX_EFFECT_MS)}ms`;
    box.style.animationDelay = `${clamp(anim.delay ?? 0, 0, MAX_DELAY_MS)}ms`;
  }
  const tag = `evac-${el.type}`;
  if (!customElements.get(tag)) {
    ctx.onError?.(el.id, new Error(`unknown element type ${el.type}`));
    return ctx.editing ? box : null;
  }
  const widget = document.createElement(tag) as EvacWidget;
  widget.className = "evac-widget";
  box.appendChild(widget);
  widget.configure(el, ctx);
  return box;
}

export function renderLayout(host: HTMLElement, layout: LayoutData, ctx: RenderContext): RenderedLayout {
  defineWidgets();
  // slide timers outside the player loop over the layout's own duration (or 10 s)
  if (ctx.loopMs === undefined) ctx = { ...ctx, loopMs: Math.max(1, layout.duration ?? 10) * 1000 };
  const stage = document.createElement("div");
  stage.className = "evac-stage";
  const bg = layout.background;
  if (bg?.color) stage.style.background = color(bg.color);
  if (bg?.asset && ctx.assets[bg.asset]) {
    const a = ctx.assets[bg.asset];
    const url = a.urls.webp ?? a.urls.original;
    stage.style.backgroundImage = `url("${url}")`;
    stage.style.backgroundSize = bg.fit ?? "cover";
    stage.style.backgroundPosition = "center";
  }
  const elements = new Map<string, HTMLElement>();
  for (const el of layout.elements) {
    const node = renderElement(el, ctx);
    if (node) {
      elements.set(el.id, node);
      stage.appendChild(node);
    }
  }
  host.replaceChildren(stage);
  const fit = () => {
    const w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    const scale = Math.min(w / layout.width, h / layout.height);
    stage.style.width = `${Math.round(layout.width * scale)}px`;
    stage.style.height = `${Math.round(layout.height * scale)}px`;
  };
  fit();
  const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(fit) : null;
  ro?.observe(host);
  return {
    stage, elements,
    destroy() {
      ro?.disconnect();
      stage.remove();
    },
  };
}
