// SPDX-License-Identifier: AGPL-3.0-or-later
// Screen motion (ADR-0051): slide transitions, entrance effects, the slide timer, reduced motion - and the safety
// rule that alarms never wait for any of it.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Clock } from "../src/player/clock";
import { Display } from "../src/player/display";
import { EvacController, type EvacPayload } from "../src/player/evac";
import { isUrgent, transitionFor } from "../src/player/transition";
import type { Program, Slide } from "../src/program/engine";
import { motionOn, renderLayout } from "../src/renderer/render";
import { filled, slideTiming } from "../src/renderer/timer";
import type { LayoutData, LayoutElement, RenderContext } from "../src/renderer/types";

const NOW = Date.parse("2026-10-12T12:00:00Z");

const el = (over: Partial<LayoutElement> = {}): LayoutElement => ({
  id: "t", type: "text", frame: { x: 0, y: 0, w: 50, h: 10 }, props: { text: "Hello" }, ...over });
const layout = (elements: LayoutElement[], over: Partial<LayoutData> = {}): LayoutData => ({
  format: 1, width: 1920, height: 1080, elements, ...over });
const ctx = (over: Partial<RenderContext> = {}): RenderContext => ({
  vars: {}, now: () => Date.now(), assets: {}, fonts: {}, ...over });

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  localStorage.clear();
  document.body.replaceChildren();
});
afterEach(() => vi.useRealTimers());

describe("entrance effects", () => {
  const animated = el({ animation: { enter: "slide-up", duration: 50_000, delay: 200 } });

  it("play on screens and previews, not in the editor, with reduced motion or for urgent content", () => {
    expect(motionOn(ctx())).toBe(true);
    expect(motionOn(ctx({ editing: true }))).toBe(false);
    expect(motionOn(ctx({ editing: true, motion: true }))).toBe(true); // "Play animations"
    expect(motionOn(ctx({ motion: false }))).toBe(false);
    expect(motionOn(ctx({ reducedMotion: true, motion: true }))).toBe(false);
    const host = document.createElement("div");
    const box = renderLayout(host, layout([animated]), ctx()).elements.get("t") as HTMLElement;
    expect(box.classList.contains("evac-enter-slide-up")).toBe(true);
    expect(box.style.animationDuration).toBe("10000ms"); // bounded like the layout format
    expect(box.style.animationDelay).toBe("200ms");
    for (const c of [ctx({ motion: false }), ctx({ reducedMotion: true }), ctx({ editing: true })]) {
      const node = renderLayout(host, layout([animated]), c).elements.get("t") as HTMLElement;
      expect(node.className).not.toContain("evac-enter");
    }
    const unknown = el({ animation: { enter: "spin" as never } });
    expect((renderLayout(host, layout([unknown]), ctx()).elements.get("t") as HTMLElement).className)
      .not.toContain("evac-enter");
  });
});

describe("slide timer", () => {
  it("knows the slide's window, loops without one and is untimed for a slide without end", () => {
    expect(slideTiming({ slide: { start: NOW - 2000, end: NOW + 8000 } }, NOW)).toEqual(
      { start: NOW - 2000, total: 10_000, loop: false });
    expect(slideTiming({ slide: null }, NOW)).toBeNull();
    expect(slideTiming({ slide: { start: NOW, end: NOW } }, NOW)).toBeNull();
    const loop = slideTiming({ loopMs: 7000 }, NOW + 1234) as NonNullable<ReturnType<typeof slideTiming>>;
    expect(loop.loop).toBe(true);
    expect(loop.total).toBe(7000);
    expect((NOW + 1234 - loop.start) < 7000 && loop.start % 7000 === 0).toBe(true);
    const t = { start: NOW, total: 10_000, loop: false };
    expect(filled(t, NOW + 2500, false)).toBeCloseTo(0.75);
    expect(filled(t, NOW + 2500, true)).toBeCloseTo(0.25);
    expect(filled(t, NOW + 99_000, false)).toBe(0);
  });

  const timer = (props: Record<string, unknown> = {}) => el({ id: "bar", type: "progress", props });
  const bar = (r: ReturnType<typeof renderLayout>) =>
    (r.elements.get("bar") as HTMLElement).querySelector<HTMLElement>(".evac-progress-bar") as HTMLElement;

  it("runs as one CSS animation from the slide's start (synchronised)", () => {
    const host = document.createElement("div");
    const r = renderLayout(host, layout([timer()]), ctx({ slide: { start: NOW - 3000, end: NOW + 7000 } }));
    const b = bar(r);
    expect(b.style.animationName).toBe("evac-timer-shrink-x");
    expect(b.style.animationDuration).toBe("10000ms");
    expect(b.style.animationDelay).toBe("-3000ms");
    expect(b.style.animationIterationCount).toBe("1");
    const v = bar(renderLayout(host, layout([timer({ orientation: "vertical", mode: "grow" })]),
                               ctx({ slide: { start: NOW, end: NOW + 5000 } })));
    expect(v.style.animationName).toBe("evac-timer-grow-y");
    // editor and previews: loops over the layout's seconds on screen
    const looped = bar(renderLayout(host, layout([timer()], { duration: 12 }), ctx({ editing: true })));
    expect(looped.style.animationDuration).toBe("12000ms");
    expect(looped.style.animationIterationCount).toBe("infinite");
  });

  it("steps once a second with reduced motion", () => {
    const host = document.createElement("div");
    const b = bar(renderLayout(host, layout([timer()]),
                               ctx({ reducedMotion: true, slide: { start: NOW, end: NOW + 10_000 } })));
    expect(b.style.animationName).toBe("");
    expect(b.style.transform).toBe("scaleX(1.0000)");
    vi.advanceTimersByTime(4000);
    expect(b.style.transform).toBe("scaleX(0.6000)");
  });

  it("shows full or hides when the slide has no end", () => {
    const host = document.createElement("div");
    const full = renderLayout(host, layout([timer()]), ctx({ slide: null }));
    expect(bar(full).style.transform).toBe("scaleX(1.0000)");
    expect(full.elements.get("bar")?.classList.contains("evac-off")).toBe(false);
    const hidden = renderLayout(host, layout([timer({ untimed: "hide" })]), ctx({ slide: null }));
    expect(hidden.elements.get("bar")?.classList.contains("evac-off")).toBe(true);
  });
});

describe("transitions", () => {
  const program: Program = {
    entries: [{ id: "default", source: "default", name: "Loop", priority: 0, content: { playlist: "p" },
                windows: [[null, null]] }],
    playlists: { p: { mode: "ordered", default: 10_000, items: [
      { id: "a", layout: "A", duration: null, weight: 1, tags: [], when: "", from: null, until: null,
        transition: { effect: "fade", ms: 800 } },
      { id: "b", layout: "B", duration: null, weight: 1, tags: [], when: "", from: null, until: null },
      { id: "c", layout: "C", duration: null, weight: 1, tags: [], when: "", from: null, until: null,
        transition: { effect: "slide-left", ms: 4000 } },
      { id: "d", layout: "D", duration: null, weight: 1, tags: [], when: "", from: null, until: null,
        transition: { effect: "wobble", ms: 500 } },
    ] } },
    layouts: { A: null, B: null, C: null, D: null },
  };
  const slide = (item: string, len = 10_000): Slide => ({ entry: "default", layout: item.toUpperCase(), item,
                                                          index: 0, count: 4, start: NOW, end: NOW + len });

  it("come from the playlist item and stay below half of the slide", () => {
    expect(transitionFor(program, slide("a"))).toEqual({ effect: "fade", ms: 800 });
    expect(transitionFor(program, slide("b"))).toBeNull(); // a cut, as before
    expect(transitionFor(program, slide("c", 3000))).toEqual({ effect: "slide-left", ms: 1500 });
    expect(transitionFor(program, slide("d"))).toBeNull(); // unknown effect: a cut
    expect(transitionFor(program, slide("a"), { reduced: true })).toBeNull();
    expect(transitionFor(program, slide("a"), { urgent: true })).toBeNull();
    expect(transitionFor(program, { ...slide("a"), item: undefined })).toBeNull();
    expect(transitionFor(null, slide("a"))).toBeNull();
  });

  it("never for evacuation, full-screen announcements and emergency overrides", () => {
    expect(isUrgent({ id: "announcement:1", source: "announcement" })).toBe(true);
    expect(isUrgent({ id: "evacuation", source: "evacuation" })).toBe(true);
    expect(isUrgent({ id: "override:1", source: "override", level: "emergency" })).toBe(true);
    expect(isUrgent({ id: "override:2", source: "override", level: "override" })).toBe(false);
    expect(isUrgent({ id: "default", source: "default" })).toBe(false);
    expect(isUrgent(undefined)).toBe(false);
  });

  it("draw the new slide over the old one and remove the old one when done", () => {
    const root = document.createElement("div");
    document.body.append(root);
    const display = new Display(root, new Clock());
    display.layout(layout([el({ props: { text: "One" } })]), ctx());
    expect(root.querySelectorAll("main.view")).toHaveLength(1);
    display.layout(layout([el({ props: { text: "Two" } })]), ctx(), undefined, { effect: "slide-left", ms: 600 });
    const views = root.querySelectorAll<HTMLElement>("main.view");
    expect(views).toHaveLength(2);
    expect(views[0].classList.contains("evac-tr-out")).toBe(true);
    expect(views[0].getAttribute("aria-hidden")).toBe("true");
    expect(views[1].classList.contains("evac-tr-in")).toBe(true);
    expect(views[1].classList.contains("evac-tr-slide-left")).toBe(true);
    expect(views[1].style.getPropertyValue("--evac-tr-ms")).toBe("600ms");
    expect(display.transitioning).toBe(true);
    vi.advanceTimersByTime(650);
    expect(display.transitioning).toBe(false);
    expect(root.querySelectorAll("main.view")).toHaveLength(1);
    expect(root.textContent).toContain("Two");
    expect(root.querySelector("main.view")?.className).toBe("view layout");
    // without a transition, or from a non-layout view, it is a cut
    display.message("Offline");
    display.layout(layout([el()]), ctx(), undefined, { effect: "fade", ms: 600 });
    expect(root.querySelectorAll("main.view")).toHaveLength(1);
    expect(display.transitioning).toBe(false);
  });

  it("can be ended at once", () => {
    const root = document.createElement("div");
    const display = new Display(root, new Clock());
    display.layout(layout([el()]), ctx());
    display.layout(layout([el()]), ctx(), undefined, { effect: "fade", ms: 3000 });
    expect(display.transitioning).toBe(true);
    display.settle();
    expect(display.transitioning).toBe(false);
    expect(root.querySelectorAll("main.view")).toHaveLength(1);
    expect(root.querySelector("main.view")?.classList.contains("evac-tr-in")).toBe(false);
  });
});

describe("safety: alarms never wait for motion (brief §8)", () => {
  const evacLayout = layout([
    el({ id: "sign", type: "pictogram", props: { code: "E002" }, animation: { enter: "fade", delay: 5000, duration: 5000 } }),
    el({ id: "msg", props: { text: "Leave the building" }, animation: { enter: "zoom", duration: 3000 } }),
    el({ id: "bar", type: "progress", props: {} }),
  ]);
  const payload = (over: Partial<EvacPayload> = {}): EvacPayload => ({
    event: "demo", screen: "s1", seq: 1, v: "a", state: "evacuate", label: "Evacuate", drill: true,
    drill_text: "DRILL", since: null, clear_until: null, takeover: true, role: "participant", model: "simple",
    guidance: { kind: "none", arrow: null, text: "", target: "" }, direction: "", texts: ["Leave now."],
    rotate_seconds: 8, pictograms_only: false, sound: "none", sound_every: 30, speech: "", layout: evacLayout,
    issued: NOW, ...over });

  it("the evacuation layer shows at once and still, in the middle of a slide transition", () => {
    const root = document.createElement("div");
    document.body.append(root);
    const display = new Display(root, new Clock());
    const acks: number[] = [];
    // wired like the player: a takeover ends any running transition
    const ctl = new EvacController({
      now: () => Date.now(), speaker: { say: () => true } as never, audio: () => ({ enabled: false, volume: 0 }),
      strings: {}, onRendered: (_p, info) => acks.push(info.rendered_at),
      // the content context would allow motion: the controller must override it
      context: () => ({ vars: {}, now: () => Date.now(), assets: {}, fonts: {}, motion: true, reducedMotion: false,
                        slide: { start: NOW, end: NOW + 10_000 } }),
      onChange: () => display.settle(),
    });
    display.layout(layout([el()]), ctx());
    display.layout(layout([el()]), ctx(), undefined, { effect: "fade", ms: 5000 });
    expect(display.transitioning).toBe(true);

    expect(ctl.offer(payload(), "websocket")).toBe(true);
    // no timer advanced: everything below happened synchronously
    const layer = document.getElementById("evac-layer") as HTMLElement;
    expect(layer.hidden).toBe(false);
    expect(layer.dataset.mode).toBe("takeover");
    expect(layer.textContent).toContain("Leave the building");
    expect(layer.querySelector(".evac-drill")?.textContent).toBe("DRILL");
    expect(layer.querySelectorAll("[class*='evac-enter-']")).toHaveLength(0);
    for (const node of layer.querySelectorAll<HTMLElement>(".evac-el")) {
      expect(node.style.animationDelay).toBe("");
      expect(node.style.animationName).toBe("");
    }
    // a slide timer in an alarm layout shows full and does not count
    const bar = layer.querySelector<HTMLElement>(".evac-progress-bar") as HTMLElement;
    expect(bar.style.animationName).toBe("");
    expect(bar.style.transform).toBe("scaleX(1.0000)");
    expect(acks).toEqual([NOW]);
    expect(display.transitioning).toBe(false); // the running transition was ended, not waited for
    expect(root.querySelectorAll("main.view")).toHaveLength(1);
  });
});
