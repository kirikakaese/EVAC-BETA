// SPDX-License-Identifier: AGPL-3.0-or-later
// What the screen shows until content arrives: the pairing view, an idle slide with clock, and the identify
// overlay. Content rendering (layouts, widgets, playlists) builds on this in the next steps of phase 1.
import type { ScreenConfig } from "./api";
import type { Clock } from "./clock";
import { qrSvg } from "./qr";

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

  private reset(): HTMLElement {
    if (this.clockTimer) clearInterval(this.clockTimer);
    this.clockTimer = null;
    this.root.replaceChildren();
    const main = el("main", "view");
    this.root.appendChild(main);
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
