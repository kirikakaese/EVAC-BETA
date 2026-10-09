// SPDX-License-Identifier: AGPL-3.0-or-later
// Announcement overlays on top of whatever the screen shows: a banner along the bottom, a scrolling ticker or a
// card. They come with the program (``program.overlays``, ADR-0019), so they also appear and disappear on time
// without network. Full-screen announcements are program entries instead and need nothing here.
import type { Window } from "../program/engine";
import type { Speaker } from "./speech";

/** pause between the level's sound and the spoken text */
export const SPEECH_DELAY_MS = 1600;

export type OverlayStyle = "banner" | "ticker" | "card";

export interface Overlay {
  id: string; style: OverlayStyle; rank: number; level: string; colour: string; sound: string; title: string;
  text: string; windows: Window[];
  /** URL of the spoken version (ADR-0022), played after the sound */
  speech?: string;
}

export interface Active { overlay: Overlay; start: number; end: number | null }

/** Overlays visible at ``t`` (highest rank first, then the newest). */
export function activeOverlays(overlays: Overlay[] | undefined, t: number): Active[] {
  const out: Active[] = [];
  for (const o of overlays ?? []) {
    for (const [a, b] of o.windows) {
      if ((a === null || a <= t) && (b === null || t < b)) {
        out.push({ overlay: o, start: a ?? 0, end: b });
        break;
      }
    }
  }
  return out.sort((x, y) => y.overlay.rank - x.overlay.rank || y.start - x.start);
}

/** The next moment an overlay appears or disappears after ``t`` (null: none in the program). */
export function nextOverlayChange(overlays: Overlay[] | undefined, t: number): number | null {
  let next: number | null = null;
  for (const o of overlays ?? []) {
    for (const [a, b] of o.windows) {
      for (const edge of [a, b]) {
        if (edge !== null && edge > t && (next === null || edge < next)) next = edge;
      }
    }
  }
  return next;
}

/** What to draw: at most one card and one banner (the highest ranks), all tickers in one line. */
export function arrange(active: Active[]): { card: Active | null; banner: Active | null; ticker: Active[] } {
  return {
    card: active.find((a) => a.overlay.style === "card") ?? null,
    banner: active.find((a) => a.overlay.style === "banner") ?? null,
    ticker: active.filter((a) => a.overlay.style === "ticker"),
  };
}

/** Black or white text, whichever reads better on ``hex``. */
export function textOn(hex: string): string {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return "#ffffff";
  const [r, g, b] = m.slice(1).map((h) => {
    const c = parseInt(h, 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  // the colour with the higher WCAG contrast ratio: (L + 0.05) / 0.05 vs 1.05 / (L + 0.05)
  return lum > 0.179 ? "#000000" : "#ffffff";
}

function el(tag: string, cls: string, text = ""): HTMLElement {
  const node = document.createElement(tag);
  node.className = cls;
  if (text) node.textContent = text;
  return node;
}

function paint(node: HTMLElement, colour: string): void {
  // style properties set from script are allowed under the CSP (no style attribute in markup)
  node.style.setProperty("--ann-bg", /^#[0-9a-f]{6}$/i.test(colour) ? colour : "#2563eb");
  node.style.setProperty("--ann-fg", textOn(colour));
}

/** Short synthesised tones (no audio files): chime, gong and alert. */
export function playSound(kind: string, volume = 100): void {
  if (kind === "none" || typeof AudioContext === "undefined") return;
  let ctx: AudioContext;
  try {
    ctx = new AudioContext();
  } catch {
    return;
  }
  const gainAll = Math.max(0, Math.min(1, volume / 100)) * 0.4;
  const notes: [number, number, number][] = kind === "chime" ? [[660, 0, 0.6], [880, 0.35, 0.9]]
    : kind === "gong" ? [[196, 0, 2.5], [392, 0, 1.5], [294, 0.02, 2]]
      : [[880, 0, 0.25], [660, 0.3, 0.25], [880, 0.6, 0.25], [660, 0.9, 0.25]];
  let end = 0;
  for (const [freq, at, len] of notes) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = kind === "alert" ? "square" : "sine";
    osc.frequency.value = freq;
    const t0 = ctx.currentTime + at;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(gainAll, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + len);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0);
    osc.stop(t0 + len + 0.05);
    end = Math.max(end, at + len);
  }
  setTimeout(() => void ctx.close().catch(() => undefined), (end + 0.5) * 1000);
}

export class OverlayLayer {
  readonly node: HTMLElement;
  private drawn = "";
  private heard = new Set<string>();

  constructor(private speaker?: Speaker) {
    this.node = el("div", "ann-layer");
    this.node.setAttribute("aria-live", "polite");
  }

  /** Keep the layer on top of the content (the display replaces its children on every slide). */
  attach(root: HTMLElement): void {
    if (this.node.parentElement !== root || root.lastElementChild !== this.node) root.appendChild(this.node);
  }

  update(overlays: Overlay[] | undefined, t: number, opts: { hidden?: boolean; audio?: { enabled: boolean; volume: number } } = {}): void {
    const active = opts.hidden ? [] : activeOverlays(overlays, t);
    const { card, banner, ticker } = arrange(active);
    const loud = opts.audio?.enabled !== false;
    for (const a of active) {
      const key = `${a.overlay.id}@${a.start}`;
      const chimed = a.overlay.sound && a.overlay.sound !== "none";
      if (!this.heard.has(key)) {
        this.heard.add(key);
        if (loud && chimed) playSound(a.overlay.sound, opts.audio?.volume ?? 100);
      }
      // the spoken file may arrive after the overlay appeared (rendered on the server meanwhile)
      if (loud && a.overlay.speech) {
        this.speaker?.say(key, a.overlay.speech, { volume: opts.audio?.volume, delayMs: chimed ? SPEECH_DELAY_MS : 0 });
      }
    }
    if (this.heard.size > 500) this.heard = new Set([...this.heard].slice(-100));
    const sig = JSON.stringify([card?.overlay.id, card?.overlay.title, card?.overlay.text, banner?.overlay.id,
                                banner?.overlay.text, ticker.map((a) => [a.overlay.id, a.overlay.text])]);
    if (sig === this.drawn) return;
    this.drawn = sig;
    this.node.replaceChildren();
    if (card) {
      const box = el("section", "ann-card");
      paint(box, card.overlay.colour);
      box.append(el("p", "ann-level", card.overlay.level), el("h2", "ann-title", card.overlay.title));
      if (card.overlay.text && card.overlay.text !== card.overlay.title) box.append(el("p", "ann-text", card.overlay.text));
      this.node.append(box);
    }
    if (banner) {
      const bar = el("div", "ann-banner");
      paint(bar, banner.overlay.colour);
      bar.append(el("span", "ann-level", banner.overlay.level), el("span", "ann-text", banner.overlay.text));
      this.node.append(bar);
    }
    if (ticker.length) {
      const bar = el("div", "ann-ticker");
      paint(bar, ticker[0].overlay.colour);
      const track = el("div", "ann-track");
      const line = ticker.map((a) => a.overlay.text).join("   ◆   ");
      // two copies make the scroll seamless; the speed follows the length
      const copy = el("span", "", line);
      copy.setAttribute("aria-hidden", "true");
      track.append(el("span", "", line), copy);
      track.style.setProperty("--ann-duration", `${Math.max(12, Math.round(line.length / 6))}s`);
      bar.append(el("span", "ann-level", ticker[0].overlay.level), track);
      this.node.append(bar);
    }
    this.node.classList.toggle("has-bottom", !!(banner && ticker.length));
  }
}
