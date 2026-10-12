// SPDX-License-Identifier: AGPL-3.0-or-later
// What the screen shows until content arrives: the pairing view, an idle slide with clock, and the identify
// overlay. Content rendering (layouts, widgets, playlists) builds on this in the next steps of phase 1.
import { renderLayout, type RenderedLayout } from "../renderer/render";
import type { LayoutData, RenderContext } from "../renderer/types";
import type { ScreenConfig } from "./api";
import type { Clock } from "./clock";
import { qrSvg } from "../renderer/qr";
import type { Transition } from "./transition";

const TRANSITION_CLASSES = ["evac-tr-fade", "evac-tr-slide-left", "evac-tr-slide-up", "evac-tr-zoom"];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = ""): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text) node.textContent = text;
  return node;
}

export class Display {
  private clockTimer: ReturnType<typeof setInterval> | null = null;
  private overlay: HTMLElement | null = null;
  private overlayTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private root: HTMLElement, private clock: Clock) {}

  private rendered: RenderedLayout | null = null;
  /** the view on screen (a layout keeps it for the next transition) */
  private view: HTMLElement | null = null;
  /** a running slide transition: the outgoing view goes when it ends (ADR-0051) */
  private leaving: { view: HTMLElement; rendered: RenderedLayout | null; timer: ReturnType<typeof setTimeout> } | null
    = null;

  /** Whether a slide transition is running. */
  get transitioning(): boolean { return this.leaving !== null; }

  /** End a running transition at once: the outgoing slide goes, the incoming one stands still. Alarms and
   *  urgent content call this, so nothing waits for an animation. */
  settle(): void {
    const t = this.leaving;
    if (!t) return;
    this.leaving = null;
    clearTimeout(t.timer);
    t.rendered?.destroy();
    t.view.remove();
    this.view?.classList.remove("evac-tr-in", ...TRANSITION_CLASSES);
  }

  private reset(): HTMLElement {
    this.settle();
    if (this.clockTimer) clearInterval(this.clockTimer);
    this.clockTimer = null;
    this.rendered?.destroy();
    this.rendered = null;
    this.root.replaceChildren();
    const main = el("main", "view");
    this.root.appendChild(main);
    this.view = main;
    return main;
  }

  pairing(code: string, url: string, s: { title: string; step1: string; step2: string; waiting: string }): void {
    const main = this.reset();
    main.classList.add("pairing");
    main.append(el("h1", "", s.title));
    const box = el("div", "pairing-box");
    const codeBox = el("p", "code", code);
    codeBox.setAttribute("aria-label", code.split("").join(" "));
    const qr = qrSvg(url);
    qr.setAttribute("role", "img");
    qr.setAttribute("aria-label", url);
    box.append(codeBox, qr);
    const steps = el("ol", "steps");
    steps.append(el("li", "", s.step1), el("li", "", s.step2));
    main.append(box, steps, el("p", "url", url), el("p", "waiting", s.waiting));
  }

  message(title: string, detail = ""): void {
    const main = this.reset();
    main.classList.add("message");
    main.append(el("h1", "", title));
    if (detail) main.append(el("p", "", detail));
  }

  idle(cfg: ScreenConfig): void {
    const main = this.reset();
    main.classList.add("idle");
    const time = el("p", "clock");
    const date = el("p", "date");
    main.append(el("h1", "event-name", cfg.event.name), time, date);
    const tz = cfg.event.timezone || undefined;
    const fmtTime = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz });
    const fmtDate = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: tz });
    const tick = () => {
      const now = new Date(this.clock.now());
      time.textContent = fmtTime.format(now);
      date.textContent = fmtDate.format(now);
    };
    tick();
    this.clockTimer = setInterval(tick, 1000);
  }

  /** Show a layout. With a ``transition`` and a layout on screen, the new slide comes in over the old one, which
   *  is removed when the transition ends (or at once by :meth:`settle`). */
  layout(data: LayoutData, ctx: RenderContext, variables?: Record<string, string>,
         transition: Transition | null = null): void {
    const outgoing = transition && this.view?.classList.contains("layout") && this.view.parentElement === this.root
      ? this.view : null;
    if (!outgoing || !transition) {
      const main = this.reset();
      main.classList.add("layout");
      for (const [k, v] of Object.entries(variables ?? {})) main.style.setProperty(k, v);
      this.rendered = renderLayout(main, data, ctx);
      return;
    }
    this.settle();
    const leaving = this.rendered;
    if (this.clockTimer) clearInterval(this.clockTimer);
    this.clockTimer = null;
    // everything but the outgoing slide goes, as with any slide change (overlays are attached again afterwards)
    for (const child of [...this.root.children]) if (child !== outgoing) child.remove();
    const main = el("main", "view layout");
    for (const [k, v] of Object.entries(variables ?? {})) main.style.setProperty(k, v);
    this.root.appendChild(main);
    this.view = main;
    this.rendered = renderLayout(main, data, ctx);
    outgoing.setAttribute("aria-hidden", "true");
    outgoing.inert = true;
    for (const node of [main, outgoing]) {
      node.style.setProperty("--evac-tr-ms", `${transition.ms}ms`);
      node.classList.add(`evac-tr-${transition.effect}`);
    }
    main.classList.add("evac-tr-in");
    outgoing.classList.add("evac-tr-out");
    this.leaving = { view: outgoing, rendered: leaving, timer: setTimeout(() => this.settle(), transition.ms + 50) };
  }

  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(title: string, lines: string[], seconds = 30): void {
    this.overlay?.remove();
    if (this.overlayTimer) clearTimeout(this.overlayTimer);
    const ov = el("div", "test-pattern");
    ov.setAttribute("role", "img");
    ov.setAttribute("aria-label", title);
    const bars = el("div", "tp-bars");
    for (const c of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"]) {
      bars.appendChild(el("span", `tp-bar tp-${c}`));
    }
    const ramp = el("div", "tp-ramp");
    const info = el("div", "tp-info");
    info.append(el("p", "tp-title", title), ...lines.map((l) => el("p", "", l)));
    ov.append(bars, ramp, el("div", "tp-grid"), el("div", "tp-circle"), el("div", "tp-corners"), info);
    this.root.appendChild(ov);
    this.overlay = ov;
    this.overlayTimer = setTimeout(() => ov.remove(), seconds * 1000);
  }

  identify(name: string, detail: string, seconds = 10): void {
    this.overlay?.remove();
    if (this.overlayTimer) clearTimeout(this.overlayTimer);
    const ov = el("div", "identify");
    ov.setAttribute("role", "status");
    ov.append(el("p", "identify-name", name), el("p", "identify-detail", detail));
    this.root.appendChild(ov);
    this.overlay = ov;
    this.overlayTimer = setTimeout(() => ov.remove(), seconds * 1000);
  }
}
