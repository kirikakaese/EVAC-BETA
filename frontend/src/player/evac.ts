// SPDX-License-Identifier: AGPL-3.0-or-later
// Evacuation on the screen (ADR-0033/0034): takes over every participating screen, wakes it from dim/sleep,
// shows the stage's layout (or the built-in fallback with ISO 7010 signs), rotates texts, plays the alarm
// sound and spoken message, marks drills, and acknowledges what it rendered.
//
// Rules (the same as the server's state machine, so a screen deciding offline reaches the same result):
// - the newest message wins (``seq``, persisted); a message is never replaced by an older one;
// - nothing returns to normal by itself, a reconnect or a restart: the last state stays until a newer message;
// - a stale "all clear" or "normal" (issued more than 10 minutes ago) is never applied over an alarm;
// - "all clear" turns into normal at its stored end time;
// - messages from fallback origins must carry a valid signature of the event's alarm key.
import { renderLayout, type RenderedLayout } from "../renderer/render";
import { checkMark, pictogram } from "../renderer/pictograms";
import type { LayoutData, RenderContext } from "../renderer/types";
import { verifySigned, type Signed } from "./ed25519";
import { playSound } from "./overlays";
import type { Speaker } from "./speech";

export const ALARMS = ["staff_alert", "attention", "shelter_in_place", "evacuate"];
const SEVERITY: Record<string, number> = { normal: 0, all_clear: 1, staff_alert: 2, attention: 3,
                                           shelter_in_place: 4, evacuate: 5 };
export const STALE_CLEAR_MS = 10 * 60_000;
const KEY_PAYLOAD = "evac.player.evac";
const KEY_BUNDLE = "evac.player.evacbundle";

export interface Guidance { kind: string; arrow: string | null; text: string; toward?: string; target: string;
                            distance?: number | null }
export interface EvacPayload {
  event: string; screen: string; seq: number; v: string; state: string; label: string; drill: boolean;
  drill_text: string; since: string | null; clear_until: string | null; takeover: boolean; role: string;
  model: string; guidance: Guidance; direction: string; texts: string[]; rotate_seconds: number;
  pictograms_only: boolean; sound: string; sound_every: number; speech: string; layout: LayoutData | null;
  issued?: number; sig?: Signed; via?: string;
}
export interface StageInfo { label: string; texts: string[]; rotate_seconds: number; pictograms_only: boolean;
                             sound: string; sound_every: number; speech: string; layout: LayoutData | null;
                             takeover: boolean }
export interface EvacBundle {
  event: string; screen: string; keys: string[]; drill_text: string; model: string; role: string; zones: string[];
  stages: Record<string, StageInfo>; directions: Record<string, { kind: string; arrow: string | null; text: string;
                                                                  target: string; direction: string }>;
  blocked: string[]; fallback_origins: string[]; labels: Record<string, string>; version: string;
}
export interface Status { st: string; d: boolean; cu?: number }

// ---------------------------------------------------------------- pure rules
export const isAlarm = (state: string): boolean => ALARMS.includes(state);

/** "all clear" whose end time has passed counts as normal. */
export function currentState(p: Pick<EvacPayload, "state" | "clear_until">, now: number): string {
  if (p.state === "all_clear" && p.clear_until && Date.parse(p.clear_until) <= now) return "normal";
  return p.state;
}

/** Whether ``incoming`` replaces ``current`` (``now`` = server-synchronised ms). */
export function accepts(current: EvacPayload | null, incoming: EvacPayload, now: number): boolean {
  if (!current) return true;
  if (incoming.seq < current.seq) return false;
  if (incoming.seq === current.seq && incoming.v === current.v) return false;
  const ending = !isAlarm(incoming.state);
  if (ending && isAlarm(currentState(current, now))) {
    const issued = incoming.issued ?? (incoming.sig ? Number(JSON.parse(incoming.sig.m).ia) * 1000 : now);
    if (now - issued > STALE_CLEAR_MS) return false;
  }
  return true;
}

/** What a screen in ``zones`` shows: highest severity wins, real before drill, drills ignored while a real
 *  alarm applies (the server's ``machine.effective``). */
export function effective(statuses: Status[], now: number): Status {
  const cur = statuses.map((s) => (s.st === "all_clear" && s.cu && s.cu <= now ? { st: "normal", d: false } : s));
  const real = cur.some((s) => isAlarm(s.st) && !s.d);
  let best: Status = { st: "normal", d: false };
  const rank = (s: Status) => [SEVERITY[s.st] ?? 0, s.d ? 0 : 1];
  for (const s of real ? cur.filter((x) => !x.d) : cur) {
    const [a, b] = rank(s), [c, d] = rank(best);
    if (a > c || (a === c && b > d)) best = s;
  }
  return best;
}

/** A payload built from a signed fallback message and the cached bundle (the server is unreachable). */
export function fromFallback(sig: Signed, bundle: EvacBundle, now: number): EvacPayload | null {
  const core = verifySigned(bundle.keys, sig) as null | { e: string; seq: number; ia: number; ev: Status;
                                                          z: Record<string, Status>; b?: string[] };
  if (!core || core.e !== bundle.event || typeof core.seq !== "number" || !core.ev || typeof core.ev.st !== "string") {
    return null;
  }
  const shown = effective([core.ev, ...bundle.zones.map((z) => core.z?.[z]).filter((s): s is Status => !!s)], now);
  const stage = bundle.stages[shown.st];
  const dir = bundle.directions[(core.b ?? []).slice().sort().join(",")];
  const status = [core.ev, ...Object.values(core.z ?? {})].find((s) => s.st === shown.st && s.cu);
  return {
    event: bundle.event, screen: bundle.screen, seq: core.seq, v: `fb-${core.seq}-${shown.st}-${shown.d}`,
    state: shown.st, label: bundle.labels[shown.st] ?? stage?.label ?? shown.st, drill: shown.d,
    drill_text: bundle.drill_text, since: null, clear_until: status?.cu ? new Date(status.cu).toISOString() : null,
    takeover: stage?.takeover ?? false, role: bundle.role, model: bundle.model,
    guidance: dir ? { kind: dir.kind, arrow: dir.arrow, text: dir.text, target: dir.target }
      : { kind: bundle.model === "zones" ? "follow_staff" : "none", arrow: null, text: "", target: "" },
    direction: dir?.direction ?? "", texts: stage?.texts ?? [], rotate_seconds: stage?.rotate_seconds ?? 8,
    pictograms_only: stage?.pictograms_only ?? false, sound: stage?.sound ?? "none",
    sound_every: stage?.sound_every ?? 30, speech: stage?.speech ?? "", layout: stage?.layout ?? null,
    issued: core.ia * 1000, sig, via: "fallback",
  };
}

/** The text frames shown in turn ("" = the signs-only frame). */
export function frames(p: Pick<EvacPayload, "texts" | "pictograms_only">): string[] {
  const out = p.texts.length ? [...p.texts] : [""];
  if (p.pictograms_only && p.texts.length) out.push("");
  return out;
}

/** The main sign of a stage: the exit sign points the way people should go. */
export function mainSign(state: string, arrow: string | null): string {
  if (state === "evacuate") return arrow && ["left", "back_left", "ahead_left"].includes(arrow) ? "E001" : "E002";
  if (state === "all_clear") return "check";
  return "W001";
}

export function load<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function save(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage full or blocked: the state still shows, it just does not survive a restart
  }
}

// ---------------------------------------------------------------- the controller
export interface EvacOptions {
  now: () => number;
  speaker: Speaker;
  audio: () => { enabled: boolean; volume: number };
  context: () => Omit<RenderContext, "vars"> & { vars: Record<string, unknown> };
  strings: Record<string, string>;
  /** called after something was rendered: acknowledge it */
  onRendered: (p: EvacPayload, info: { fallback: boolean; rendered_at: number }) => void;
  onChange?: (active: boolean) => void;
}

export class EvacController {
  payload: EvacPayload | null = load<EvacPayload>(KEY_PAYLOAD);
  bundle: EvacBundle | null = load<EvacBundle>(KEY_BUNDLE);
  readonly layer: HTMLElement;
  private rendered: RenderedLayout | null = null;
  private rotation: ReturnType<typeof setInterval> | null = null;
  private sound: ReturnType<typeof setInterval> | null = null;
  private expiry: ReturnType<typeof setTimeout> | null = null;
  private frame = 0;
  private shownKey = "";

  constructor(private opts: EvacOptions, doc: Document = document) {
    this.layer = doc.createElement("div");
    this.layer.id = "evac-layer";
    this.layer.hidden = true;
    doc.body.appendChild(this.layer);
  }

  private t(s: string): string { return this.opts.strings[s] ?? s; }

  setBundle(b: EvacBundle | null): void {
    if (!b) return;
    this.bundle = b;
    save(KEY_BUNDLE, b);
  }

  /** Offer a payload from any path; returns whether it was taken. */
  offer(p: EvacPayload | null | undefined, via: string): boolean {
    if (!p || (this.bundle && p.event !== this.bundle.event && this.payload && p.event !== this.payload.event)) {
      return false;
    }
    if (via === "fallback" && !p.sig) return false;
    if (!accepts(this.payload, p, this.opts.now())) return false;
    this.payload = { ...p, via };
    save(KEY_PAYLOAD, this.payload);
    this.render(true);
    return true;
  }

  /** A signed event-wide message from a fallback origin. */
  offerFallback(sig: Signed): boolean {
    if (!this.bundle) return false;
    const p = fromFallback(sig, this.bundle, this.opts.now());
    return p ? this.offer(p, "fallback") : false;
  }

  /** Whether the screen is taken over (normal content is hidden). */
  get active(): boolean {
    const p = this.payload;
    if (!p) return false;
    const st = currentState(p, this.opts.now());
    return p.role === "participant" && p.takeover && st !== "normal";
  }

  /** Draw the current payload. ``force`` redraws even when nothing visible changed (a new message). */
  render(force = false): void {
    const p = this.payload;
    const now = this.opts.now();
    const state = p ? currentState(p, now) : "normal";
    const role = p?.role ?? "participant";
    const visible = !!p && role !== "excluded" && state !== "normal" && state !== "staff_alert";
    const mode = !visible ? "none" : p.takeover && role === "participant" ? "takeover" : "banner";
    const key = `${mode}|${p?.seq}|${p?.v}|${state}`;
    if (!force && key === this.shownKey) return;
    this.shownKey = key;
    this.stop();
    this.layer.replaceChildren();
    this.layer.hidden = mode === "none";
    this.layer.dataset.mode = mode;
    this.layer.dataset.state = state;
    document.documentElement.classList.toggle("evac-active", mode === "takeover");
    this.opts.onChange?.(mode === "takeover");
    if (!p) return;
    if (p.state === "all_clear" && p.clear_until) {
      const left = Date.parse(p.clear_until) - now;
      if (left > 0) this.expiry = setTimeout(() => this.render(true), Math.min(left + 50, 2_147_000_000));
    }
    let fallback = false;
    if (mode === "takeover") fallback = this.drawTakeover(p, state);
    else if (mode === "banner") this.drawBanner(p, state);
    if (mode !== "none" && p.drill) this.drawDrill(p);
    if (mode !== "none") this.startAudio(p);
    this.opts.onRendered(p, { fallback, rendered_at: this.opts.now() });
  }

  private vars(p: EvacPayload, text: string): Record<string, unknown> {
    return { ...this.opts.context().vars,
             evac: { stage: p.label, state: p.state, text, direction: p.direction || this.followStaff(p),
                     target: p.guidance.target, arrow: p.guidance.arrow, drill: p.drill ? p.drill_text : "" } };
  }

  private followStaff(p: EvacPayload): string {
    return p.guidance.kind === "follow_staff" && p.state === "evacuate" ? this.t("Follow the instructions of the staff")
      : "";
  }

  private drawTakeover(p: EvacPayload, state: string): boolean {
    const host = document.createElement("div");
    host.className = `evac-takeover evac-stage-${state}`;
    this.layer.append(host);
    const texts = frames(p);
    const draw = (): boolean => {
      const text = texts[this.frame % texts.length];
      if (p.layout) {
        let failed = false;
        try {
          this.rendered?.destroy();
          host.replaceChildren();
          const ctx = this.opts.context();
          this.rendered = renderLayout(host, p.layout, { ...ctx, vars: this.vars(p, text),
            onError: (id, err) => { failed = true; ctx.onError?.(id, err); } });
        } catch {
          failed = true;
        }
        if (!failed) return false;
        this.rendered?.destroy(); // the own layout failed: the built-in layout takes over
        this.rendered = null;
      }
      host.replaceChildren(this.fallbackLayout(p, state, text));
      return true;
    };
    const fallback = draw();
    if (texts.length > 1) {
      this.rotation = setInterval(() => { this.frame += 1; draw(); },
                                  Math.max(3, p.rotate_seconds || 8) * 1000);
    }
    return fallback;
  }

  /** The built-in layout every screen keeps in its code: sign(s), stage, text, direction. */
  fallbackLayout(p: EvacPayload, state: string, text: string): HTMLElement {
    const box = document.createElement("div");
    box.className = `evac-fb evac-fb-${state}`;
    const signs = document.createElement("div");
    signs.className = "evac-fb-signs";
    const arrow = p.guidance.arrow;
    const main = mainSign(state, arrow);
    signs.innerHTML = (main === "check" ? checkMark() : pictogram(main, "ahead")) + (state === "evacuate" && arrow
      ? pictogram("arrow", arrow) : "");
    const label = document.createElement("h1");
    label.className = "evac-fb-label";
    label.textContent = p.label;
    box.append(signs, label);
    if (text) {
      const t = document.createElement("p");
      t.className = "evac-fb-text";
      t.textContent = text;
      box.append(t);
    }
    const dir = p.direction || this.followStaff(p);
    if (dir && state === "evacuate") {
      const d = document.createElement("p");
      d.className = "evac-fb-dir";
      d.textContent = dir;
      box.append(d);
    }
    return box;
  }

  private drawBanner(p: EvacPayload, state: string): void {
    const bar = document.createElement("div");
    bar.className = `evac-banner evac-stage-${state}`;
    bar.setAttribute("role", "alert");
    const texts = frames(p).filter(Boolean);
    const icon = document.createElement("span");
    icon.className = "evac-banner-icon";
    icon.innerHTML = pictogram(state === "evacuate" ? mainSign(state, p.guidance.arrow) : "W001");
    const label = document.createElement("strong");
    label.textContent = p.label;
    const text = document.createElement("span");
    text.className = "evac-banner-text";
    text.textContent = texts[0] ?? "";
    bar.append(icon, label, text);
    this.layer.append(bar);
    if (texts.length > 1) {
      this.rotation = setInterval(() => { this.frame += 1; text.textContent = texts[this.frame % texts.length]; },
                                  Math.max(3, p.rotate_seconds || 8) * 1000);
    }
  }

  private drawDrill(p: EvacPayload): void {
    const tag = document.createElement("div");
    tag.className = "evac-drill";
    tag.textContent = p.drill_text || "DRILL";
    this.layer.append(tag);
  }

  private startAudio(p: EvacPayload): void {
    const audio = this.opts.audio();
    if (!audio.enabled || p.role !== "participant") return;
    const play = (n: number) => {
      if (p.sound && p.sound !== "none") playAlarm(p.sound, audio.volume);
      if (p.speech) {
        this.opts.speaker.say(`evac:${p.seq}:${p.v}:${n}`, p.speech, { volume: audio.volume,
                                                                     delayMs: p.sound !== "none" ? 2600 : 0 });
      }
    };
    if ((!p.sound || p.sound === "none") && !p.speech) return;
    let n = 0;
    play(n);
    this.sound = setInterval(() => play(++n), Math.max(5, p.sound_every || 30) * 1000);
  }

  private stop(): void {
    if (this.rotation) clearInterval(this.rotation);
    if (this.sound) clearInterval(this.sound);
    if (this.expiry) clearTimeout(this.expiry);
    this.rotation = this.sound = this.expiry = null;
    this.rendered?.destroy();
    this.rendered = null;
    this.frame = 0;
  }
}

/** Alarm sounds: "siren" sweeps (a slow whoop), the others are the announcement tones. */
export function playAlarm(kind: string, volume = 100): void {
  if (kind !== "siren") return playSound(kind, volume);
  if (typeof AudioContext === "undefined") return;
  let ctx: AudioContext;
  try {
    ctx = new AudioContext();
  } catch {
    return;
  }
  const gain = ctx.createGain();
  gain.gain.value = Math.max(0, Math.min(1, volume / 100)) * 0.35;
  gain.connect(ctx.destination);
  for (let i = 0; i < 3; i++) {
    const osc = ctx.createOscillator();
    osc.type = "sawtooth";
    const t0 = ctx.currentTime + i * 0.8;
    osc.frequency.setValueAtTime(500, t0);
    osc.frequency.linearRampToValueAtTime(1100, t0 + 0.7);
    osc.connect(gain);
    osc.start(t0);
    osc.stop(t0 + 0.75);
  }
  setTimeout(() => void ctx.close().catch(() => undefined), 3000);
}
