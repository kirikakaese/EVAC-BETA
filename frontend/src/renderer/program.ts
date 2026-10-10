// SPDX-License-Identifier: AGPL-3.0-or-later
// Program on screens (ADR-0038): the "program" element shows now and next on a stage, the day's sessions, or the
// live changes. Sessions arrive from a ProgramStore (player: /player/api/schedule/, kept offline; editor: inline);
// the element works out "now" itself from the screen clock, so it moves on to the next session without the server.
import { EvacWidget, WIDGETS } from "./widgets";

export interface ProgramSession {
  id: string; title: string; subtitle?: string; start: string; end: string; stage: string | null;
  stage_name: string; track?: string; colour?: string; speakers: string[]; status: string; delay: number;
  moved_from?: string; planned_start?: string | null; note?: string;
}
export interface ProgramData {
  timezone?: string;
  stages: { id: string; name: string; room: string | null }[];
  sessions: ProgramSession[];
  changes: { text: string; kind: string; at: string; session: string }[];
  screen_room?: string | null;
}

export class ProgramStore {
  private listeners = new Set<() => void>();
  constructor(private data: ProgramData | null = null) {}
  get(): ProgramData | null { return this.data; }
  set(data: ProgramData | null): void {
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

export function hhmm(iso: string, timezone?: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const opts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hour12: false };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: timezone }).format(d);
  } catch {
    return new Intl.DateTimeFormat("en-GB", opts).format(d);
  }
}

function dayKey(ms: number, timezone?: string): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" })
      .format(new Date(ms));
  } catch {
    return new Date(ms).toISOString().slice(0, 10);
  }
}

/** The session running at ``now`` and the one after it on a stage (cancelled sessions are skipped). */
export function nowNext(sessions: ProgramSession[], stage: string | null, now: number):
    { now: ProgramSession | null; next: ProgramSession | null } {
  const list = sessions.filter((s) => (stage === null || s.stage === stage) && s.status !== "cancelled")
    .sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
  const current = list.find((s) => Date.parse(s.start) <= now && Date.parse(s.end) > now) ?? null;
  const next = list.find((s) => Date.parse(s.start) > now) ?? null;
  return { now: current, next };
}

/** Which stage this element shows: its own choice, else the stage in the screen's room, else none (all). */
export function stageFor(data: ProgramData, chosen: string): string | null {
  if (chosen) return chosen;
  if (data.screen_room) return data.stages.find((s) => s.room === data.screen_room)?.id ?? null;
  return null;
}

export class ProgramWidget extends EvacWidget {
  private unsubscribe: (() => void) | null = null;
  private ticking = false;

  draw(): void {
    if (!this.unsubscribe && this.ctx.program) {
      this.unsubscribe = this.ctx.program.subscribe(() => this.safely(() => this.paint()));
    }
    this.paint();
    if (!this.ticking) {
      this.ticking = true;
      this.every(15_000, () => this.paint());  // the next session starts without any message from the server
    }
  }

  private get tz(): string | undefined { return this.ctx.program?.get()?.timezone || this.ctx.timezone; }

  private paint(): void {
    const data = this.ctx.program?.get();
    const view = String(this.props.view ?? "now_next");
    if (!data) {
      this.replaceChildren();
      this.placeholder("Program (no sessions yet)");
      return;
    }
    this.classList.remove("evac-placeholder");
    const box = el("div", `evac-program evac-program-${view}`);
    const heading = String(this.props.title ?? "");
    if (heading) box.appendChild(el("div", "evac-program-heading", heading));
    const now = this.ctx.now();
    const stage = stageFor(data, String(this.props.stage ?? ""));
    const count = Math.max(1, Math.min(20, Number(this.props.count) || 6));
    if (view === "changes") this.changes(box, data, count);
    else if (view === "day") this.day(box, data, stage, now, count);
    else this.nowNext(box, data, stage, now);
    this.replaceChildren(box);
  }

  private badge(s: ProgramSession): HTMLElement | null {
    if (s.status === "cancelled") return el("span", "evac-program-badge evac-program-cancelled", "Cancelled");
    if (s.delay > 0) return el("span", "evac-program-badge evac-program-late", `+${s.delay} min`);
    if (s.delay < 0) return el("span", "evac-program-badge evac-program-late", `${s.delay} min`);
    if (s.moved_from) return el("span", "evac-program-badge evac-program-late", "Room changed");
    return null;
  }

  private session(s: ProgramSession, label: string, showStage: boolean): HTMLElement {
    const row = el("div", `evac-program-session${s.status === "cancelled" ? " is-cancelled" : ""}`);
    if (s.colour) row.style.setProperty("--evac-track", s.colour);
    const head = el("div", "evac-program-when");
    if (label) head.appendChild(el("span", "evac-program-label", label));
    head.appendChild(el("span", "evac-program-time", `${hhmm(s.start, this.tz)}–${hhmm(s.end, this.tz)}`));
    if (s.planned_start && s.delay) head.appendChild(el("s", "evac-program-was", hhmm(s.planned_start, this.tz)));
    const b = this.badge(s);
    if (b) head.appendChild(b);
    row.appendChild(head);
    row.appendChild(el("div", "evac-program-title", s.title));
    const meta = [showStage ? s.stage_name : "", s.speakers.join(", ")].filter(Boolean).join(" · ");
    if (meta) row.appendChild(el("div", "evac-program-meta", meta));
    if (s.note) row.appendChild(el("div", "evac-program-note", s.note));
    return row;
  }

  private nowNext(box: HTMLElement, data: ProgramData, stage: string | null, now: number): void {
    const stages = stage ? data.stages.filter((s) => s.id === stage) : data.stages;
    let shown = 0;
    for (const st of stages) {
      const { now: cur, next } = nowNext(data.sessions, st.id, now);
      if (!cur && !next) continue;
      const block = el("div", "evac-program-stage");
      if (!stage) block.appendChild(el("div", "evac-program-stage-name", st.name));
      if (cur) block.appendChild(this.session(cur, "Now", false));
      if (next) block.appendChild(this.session(next, "Next", false));
      box.appendChild(block);
      shown++;
    }
    // cancelled sessions that would have been on now: say so, people are looking for them
    const cancelled = data.sessions.filter((s) => s.status === "cancelled" && (!stage || s.stage === stage) &&
      Date.parse(s.end) > now && Date.parse(s.start) - 3_600_000 < now);
    for (const s of cancelled.slice(0, 2)) box.appendChild(this.session(s, "", !stage));
    if (!shown && !cancelled.length) box.appendChild(el("div", "evac-program-empty", "Nothing more today"));
  }

  private day(box: HTMLElement, data: ProgramData, stage: string | null, now: number, count: number): void {
    const today = dayKey(now, this.tz);
    const list = data.sessions.filter((s) => (!stage || s.stage === stage) && Date.parse(s.end) > now &&
      dayKey(Date.parse(s.start), this.tz) === today).sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
    if (!list.length) {
      box.appendChild(el("div", "evac-program-empty", "Nothing more today"));
      return;
    }
    for (const s of list.slice(0, count)) {
      const running = Date.parse(s.start) <= now && s.status !== "cancelled";
      box.appendChild(this.session(s, running ? "Now" : "", !stage));
    }
  }

  private changes(box: HTMLElement, data: ProgramData, count: number): void {
    if (!data.changes.length) {
      box.appendChild(el("div", "evac-program-empty", "No changes"));
      return;
    }
    const ul = el("ul", "evac-program-changes");
    for (const c of data.changes.slice(0, count)) {
      const li = el("li", `evac-program-change evac-program-change-${c.kind}`);
      li.appendChild(el("span", "evac-program-time", hhmm(c.at, this.tz)));
      li.appendChild(el("span", "evac-program-change-text", c.text));
      ul.appendChild(li);
    }
    box.appendChild(ul);
  }

  disconnectedCallback(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.ticking = false;
    super.disconnectedCallback();
  }
}

WIDGETS.program = ProgramWidget;
