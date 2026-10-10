// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { nowNext, type ProgramData, ProgramStore, type ProgramSession, stageFor } from "../src/renderer/program";
import { renderLayout } from "../src/renderer/render";
import type { LayoutData, RenderContext } from "../src/renderer/types";

const T0 = Date.parse("2026-07-01T10:00:00Z");
const iso = (min: number) => new Date(T0 + min * 60_000).toISOString();

function session(id: string, start: number, end: number, extra: Partial<ProgramSession> = {}): ProgramSession {
  return { id, title: `Talk ${id}`, start: iso(start), end: iso(end), stage: "s1", stage_name: "Main stage",
           speakers: ["Ada"], status: "scheduled", delay: 0, ...extra };
}

const data: ProgramData = {
  timezone: "UTC",
  stages: [{ id: "s1", name: "Main stage", room: "r1" }, { id: "s2", name: "Workshop", room: null }],
  sessions: [session("a", -30, 15), session("b", 20, 60, { delay: 5, planned_start: iso(15) }),
             session("c", 0, 45, { stage: "s2", stage_name: "Workshop" }),
             session("x", 15, 30, { status: "cancelled" })],
  changes: [{ text: "Talk b starts 5 minutes later", kind: "delay", at: iso(-2), session: "b" }],
};

describe("program", () => {
  it("finds now and next on a stage, skipping cancelled sessions", () => {
    const r = nowNext(data.sessions, "s1", T0);
    expect(r.now?.id).toBe("a");
    expect(r.next?.id).toBe("b");
    expect(nowNext(data.sessions, "s1", T0 + 16 * 60_000).now).toBeNull();  // "x" is cancelled
    expect(nowNext(data.sessions, "s1", T0 + 61 * 60_000)).toEqual({ now: null, next: null });
  });

  it("picks the stage: own choice, else the screen's room, else all", () => {
    expect(stageFor(data, "s2")).toBe("s2");
    expect(stageFor({ ...data, screen_room: "r1" }, "")).toBe("s1");
    expect(stageFor({ ...data, screen_room: "elsewhere" }, "")).toBeNull();
    expect(stageFor(data, "")).toBeNull();
  });

  it("renders now/next, the day and changes, and repaints when the store changes", () => {
    const store = new ProgramStore(data);
    let now = T0;
    const ctx: RenderContext = { vars: {}, now: () => now, assets: {}, fonts: {}, program: store, timezone: "UTC" };
    const layout: LayoutData = { format: 1, width: 1920, height: 1080, elements: [
      { id: "p1", type: "program", frame: { x: 0, y: 0, w: 50, h: 100 }, props: { view: "now_next", stage: "s1" } },
      { id: "p2", type: "program", frame: { x: 50, y: 0, w: 50, h: 50 }, props: { view: "day", count: 2 } },
      { id: "p3", type: "program", frame: { x: 50, y: 50, w: 50, h: 50 }, props: { view: "changes" } },
    ] } as LayoutData;
    const host = document.createElement("div");
    const r = renderLayout(host, layout, ctx);
    const p1 = r.elements.get("p1")!;
    expect(p1.textContent).toContain("Now");
    expect(p1.textContent).toContain("Talk a");
    expect(p1.textContent).toContain("Talk b");
    expect(p1.textContent).toContain("+5 min");
    expect(p1.textContent).toContain("Cancelled");  // "x" would have started within the hour
    expect(r.elements.get("p2")!.querySelectorAll(".evac-program-session").length).toBe(2);
    expect(r.elements.get("p3")!.textContent).toContain("starts 5 minutes later");

    store.set({ ...data, sessions: [session("a", -30, 15, { title: "Renamed" })] });
    expect(p1.textContent).toContain("Renamed");
    now = T0 + 20 * 60_000;
    store.set({ ...data, sessions: [] });
    expect(p1.textContent).toContain("Nothing more today");
    store.set(null);
    expect(p1.textContent).toBe("");  // nothing on a screen (the editor shows a placeholder)
    r.destroy();
  });
});
