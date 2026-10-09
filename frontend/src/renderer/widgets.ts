// SPDX-License-Identifier: AGPL-3.0-or-later
// Built-in widgets as custom elements (the widget contract of brief §5.5; extensions register their own).
// Every widget renders inside an error boundary: a failing widget shows nothing on a public screen (and an
// outline in the editor) - never a broken or blank screen.
import { qrSvg } from "./qr";
import { render as renderTemplate } from "./template";
import type { AssetEntry, LayoutElement, RenderContext } from "./types";

type Props = Record<string, unknown>;

export abstract class EvacWidget extends HTMLElement {
  protected el!: LayoutElement;
  protected ctx!: RenderContext;
  private timers: ReturnType<typeof setInterval>[] = [];
  private observers: ResizeObserver[] = [];

  get props(): Props { return this.el.props ?? {}; }

  configure(el: LayoutElement, ctx: RenderContext): void {
    this.el = el;
    this.ctx = ctx;
    this.safely(() => this.draw());
  }

  protected safely(fn: () => void): void {
    try {
      fn();
    } catch (err) {
      this.ctx.onError?.(this.el.id, err);
      this.replaceChildren();
      if (this.ctx.editing) {
        this.classList.add("evac-error");
        this.textContent = `⚠ ${String((err as Error)?.message ?? err)}`;
      }
    }
  }

  protected text(template: unknown): string {
    return renderTemplate(String(template ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
  }

  protected every(ms: number, fn: () => void): void {
    this.timers.push(setInterval(() => this.safely(fn), ms));
  }

  protected observe(fn: () => void): void {
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => this.safely(fn));
    ro.observe(this);
    this.observers.push(ro);
  }

  protected asset(id: unknown): AssetEntry | undefined {
    return typeof id === "string" ? this.ctx.assets[id] : undefined;
  }

  protected placeholder(label: string): void {
    if (this.ctx.editing) {
      this.classList.add("evac-placeholder");
      this.textContent = label;
    }
  }

  disconnectedCallback(): void {
    this.timers.splice(0).forEach(clearInterval);
    this.observers.splice(0).forEach((o) => o.disconnect());
  }

  abstract draw(): void;
}

/** Shrink the font size until the text fits its box (binary search on the computed size). */
export function autofit(box: HTMLElement, inner: HTMLElement): void {
  inner.style.removeProperty("font-size");
  const max = parseFloat(getComputedStyle(inner).fontSize) || 16;
  const fits = () => inner.scrollHeight <= box.clientHeight + 1 && inner.scrollWidth <= box.clientWidth + 1;
  if (!box.clientHeight || fits()) return;
  let lo = Math.max(4, max * 0.1), hi = max;
  for (let i = 0; i < 12 && hi - lo > 0.5; i++) {
    const mid = (lo + hi) / 2;
    inner.style.fontSize = `${mid}px`;
    if (fits()) lo = mid;
    else hi = mid;
  }
  inner.style.fontSize = `${lo}px`;
}

class TextWidget extends EvacWidget {
  draw(): void {
    const inner = document.createElement("div");
    inner.className = "evac-text";
    const value = this.text(this.props.text);
    const clamp = Number(this.props.clamp) || 0;
    if (this.props.marquee) {
      const run = document.createElement("span");
      run.className = "evac-marquee";
      run.textContent = value;
      run.style.animationDuration = `${Math.max(8, value.length / 6)}s`;
      inner.classList.add("evac-marquee-box");
      inner.appendChild(run);
    } else {
      inner.textContent = value;
      if (clamp) {
        inner.classList.add("evac-clamp");
        inner.style.setProperty("-webkit-line-clamp", String(clamp));
      }
    }
    this.replaceChildren(inner);
    if (this.props.autofit && !this.props.marquee) {
      const fit = () => autofit(this, inner);
      requestAnimationFrame(fit);
      document.fonts?.ready.then(fit).catch(() => undefined);
      this.observe(fit);
    }
    if (/\{\{\s*now/.test(String(this.props.text ?? ""))) {
      this.every(1000, () => { inner.textContent = this.text(this.props.text); });
    }
  }
}

class RichTextWidget extends EvacWidget {
  draw(): void {
    const box = document.createElement("div");
    box.className = "evac-richtext";
    for (const para of this.text(this.props.text).split(/\n{2,}/)) {
      const p = document.createElement("p");
      para.split("\n").forEach((line, i) => {
        if (i) p.appendChild(document.createElement("br"));
        // **bold** and *italic*, built as DOM nodes (no HTML parsing)
        for (const part of line.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/)) {
          if (/^\*\*[^*]+\*\*$/.test(part)) p.appendChild(Object.assign(document.createElement("strong"),
                                                                           { textContent: part.slice(2, -2) }));
          else if (/^\*[^*]+\*$/.test(part)) p.appendChild(Object.assign(document.createElement("em"),
                                                                         { textContent: part.slice(1, -1) }));
          else if (part) p.appendChild(document.createTextNode(part));
        }
      });
      box.appendChild(p);
    }
    this.replaceChildren(box);
  }
}

function picture(a: AssetEntry, fit: string, alt: string): HTMLElement {
  const pic = document.createElement("picture");
  for (const [variant, type] of [["avif", "image/avif"], ["webp", "image/webp"]]) {
    if (a.urls[variant]) {
      const src = document.createElement("source");
      src.type = type;
      src.srcset = a.urls[variant];
      pic.appendChild(src);
    }
  }
  const img = document.createElement("img");
  img.src = a.urls.original;
  img.alt = alt || a.alt || "";
  img.decoding = "async";
  img.style.objectFit = fit;
  pic.appendChild(img);
  return pic;
}

class ImageWidget extends EvacWidget {
  draw(): void {
    const a = this.asset(this.props.asset);
    if (!a) return this.placeholder("Image");
    this.replaceChildren(picture(a, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}

class SlideshowWidget extends EvacWidget {
  draw(): void {
    const list = (Array.isArray(this.props.assets) ? this.props.assets : []).map((id) => this.asset(id))
      .filter((a): a is AssetEntry => Boolean(a));
    if (!list.length) return this.placeholder("Slideshow");
    const fit = String(this.props.fit ?? "cover");
    const slides = list.map((a) => {
      const p = picture(a, fit, "");
      p.className = "evac-slide";
      return p;
    });
    this.replaceChildren(...slides);
    const interval = Math.max(1, Number(this.props.interval) || 8) * 1000;
    // index from the synchronised clock: all screens show the same slide at the same moment
    const show = () => {
      const idx = Math.floor(this.ctx.now() / interval) % slides.length;
      slides.forEach((s, i) => s.classList.toggle("active", i === idx));
    };
    show();
    this.every(500, show);
  }
}

class VideoWidget extends EvacWidget {
  draw(): void {
    const a = this.asset(this.props.asset);
    if (!a) return this.placeholder("Video");
    const v = document.createElement("video");
    v.muted = this.props.muted !== false;
    v.loop = this.props.loop !== false;
    v.playsInline = true;
    v.preload = "auto";
    v.style.objectFit = String(this.props.fit ?? "cover");
    if (a.urls.poster) v.poster = a.urls.poster;
    for (const variant of ["webm", "mp4", "original"]) {
      if (!a.urls[variant]) continue;
      const s = document.createElement("source");
      s.src = a.urls[variant];
      s.type = a.mimes[variant] || "";
      v.appendChild(s);
    }
    if (!this.ctx.editing) {
      v.autoplay = true;
      void v.play?.()?.catch(() => undefined);
    }
    this.replaceChildren(v);
  }
}

class AudioWidget extends EvacWidget {
  draw(): void {
    const a = this.asset(this.props.asset);
    if (!a) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${a.name}`);
    const audio = document.createElement("audio");
    audio.src = a.urls.audio ?? a.urls.original;
    audio.loop = this.props.loop !== false;
    audio.autoplay = true;
    this.replaceChildren(audio);
  }
}

class ShapeWidget extends EvacWidget {
  draw(): void {
    this.dataset.shape = String(this.props.shape ?? "rect");
    this.replaceChildren();
  }
}

class QrWidget extends EvacWidget {
  draw(): void {
    const value = this.text(this.props.text);
    if (!value) return this.placeholder("QR code");
    const svg = qrSvg(value);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", value);
    this.replaceChildren(svg);
  }
}

const TIME_FORMATS: Record<string, Intl.DateTimeFormatOptions> = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" },
};

class ClockWidget extends EvacWidget {
  draw(): void {
    const fmt = String(this.props.format ?? "HH:mm");
    const tz = String(this.props.timezone || this.ctx.timezone || "") || undefined;
    const f = new Intl.DateTimeFormat(fmt === "h:mm a" ? "en-US" : "en-GB", { ...TIME_FORMATS[fmt], timeZone: tz });
    const out = document.createElement("time");
    const tick = () => { out.textContent = f.format(new Date(this.ctx.now())); };
    tick();
    this.replaceChildren(out);
    this.every(1000, tick);
  }
}

class DateWidget extends EvacWidget {
  draw(): void {
    const fmt = String(this.props.format ?? "long");
    const tz = String(this.props.timezone || this.ctx.timezone || "") || undefined;
    const opts: Record<string, Intl.DateTimeFormatOptions> = {
      long: { weekday: "long", day: "numeric", month: "long" }, short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" }, iso: { year: "numeric", month: "2-digit", day: "2-digit" },
    };
    const f = new Intl.DateTimeFormat(fmt === "iso" ? "sv-SE" : "en-GB", { ...opts[fmt], timeZone: tz });
    const out = document.createElement("time");
    const tick = () => { out.textContent = f.format(new Date(this.ctx.now())); };
    tick();
    this.replaceChildren(out);
    this.every(30000, tick);
  }
}

export function formatRemaining(ms: number, fmt: string): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  if (fmt === "days") return `${d} ${d === 1 ? "day" : "days"}`;
  if (fmt === "ms") return `${p(Math.floor(s / 60))}:${p(sec)}`;
  if (fmt === "hms" || d === 0) return `${p(h + d * 24)}:${p(m)}:${p(sec)}`;
  return `${d}d ${p(h)}:${p(m)}:${p(sec)}`;
}

class CountdownWidget extends EvacWidget {
  draw(): void {
    const target = new Date(this.text(this.props.target)).getTime();
    if (isNaN(target)) return this.placeholder("Countdown");
    const out = document.createElement("span");
    const tick = () => {
      const left = target - this.ctx.now();
      out.textContent = left <= 0 && this.props.finished ? this.text(this.props.finished)
        : formatRemaining(left, String(this.props.format ?? "auto"));
    };
    tick();
    this.replaceChildren(out);
    this.every(250, tick);
  }
}

export const WIDGETS: Record<string, CustomElementConstructor> = {
  text: TextWidget, richtext: RichTextWidget, image: ImageWidget, slideshow: SlideshowWidget, video: VideoWidget,
  audio: AudioWidget, shape: ShapeWidget, qr: QrWidget, clock: ClockWidget, countdown: CountdownWidget,
  date: DateWidget,
};

export function defineWidgets(registry: CustomElementRegistry = customElements): void {
  for (const [type, cls] of Object.entries(WIDGETS)) {
    if (!registry.get(`evac-${type}`)) registry.define(`evac-${type}`, cls);
  }
}
