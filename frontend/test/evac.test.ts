// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { accepts, currentState, EvacController, effective, frames, fromFallback, mainSign, STALE_CLEAR_MS,
         type EvacBundle, type EvacPayload } from "../src/player/evac";
import { arrowAngle, pictogram } from "../src/renderer/pictograms";
import vectors from "./fixtures/ed25519-vectors.json";

const NOW = Date.parse("2026-10-10T12:00:00Z");

function payload(over: Partial<EvacPayload> = {}): EvacPayload {
  return { event: "demo", screen: "s1", seq: 1, v: "a", state: "evacuate", label: "Evacuate", drill: false,
           drill_text: "DRILL", since: null, clear_until: null, takeover: true, role: "participant", model: "zones",
           guidance: { kind: "route", arrow: "left", text: "", target: "Meadow" }, direction: "Meadow",
           texts: ["Leave now.", "No lifts."], rotate_seconds: 8, pictograms_only: true, sound: "none",
           sound_every: 30, speech: "", layout: null, issued: NOW, ...over };
}

describe("rules", () => {
  it("newest message wins, never older", () => {
    const cur = payload({ seq: 5 });
    expect(accepts(null, cur, NOW)).toBe(true);
    expect(accepts(cur, payload({ seq: 4 }), NOW)).toBe(false);
    expect(accepts(cur, payload({ seq: 5 }), NOW)).toBe(false);
    expect(accepts(cur, payload({ seq: 5, v: "b" }), NOW)).toBe(true);
    expect(accepts(cur, payload({ seq: 6, state: "shelter_in_place" }), NOW)).toBe(true);
  });

  it("never applies a stale all clear or normal over an alarm", () => {
    const cur = payload({ seq: 5 });
    const old = NOW - STALE_CLEAR_MS - 1;
    expect(accepts(cur, payload({ seq: 6, state: "all_clear", issued: old }), NOW)).toBe(false);
    expect(accepts(cur, payload({ seq: 6, state: "normal", issued: old }), NOW)).toBe(false);
    expect(accepts(cur, payload({ seq: 6, state: "all_clear", issued: NOW - 1000 }), NOW)).toBe(true);
    // a stale alarm is applied (fail-safe direction)
    expect(accepts(payload({ seq: 5, state: "normal" }), payload({ seq: 6, issued: old }), NOW)).toBe(true);
  });

  it("all clear ends at its time", () => {
    const p = payload({ state: "all_clear", clear_until: new Date(NOW + 1000).toISOString() });
    expect(currentState(p, NOW)).toBe("all_clear");
    expect(currentState(p, NOW + 1000)).toBe("normal");
    expect(currentState(payload(), NOW + 10 ** 9)).toBe("evacuate"); // never auto-clear
  });

  it("effective matches the server: severity, real before drill, drills ignored during a real alarm", () => {
    expect(effective([], NOW)).toEqual({ st: "normal", d: false });
    expect(effective([{ st: "attention", d: false }, { st: "evacuate", d: false }], NOW).st).toBe("evacuate");
    expect(effective([{ st: "evacuate", d: true }, { st: "staff_alert", d: false }], NOW))
      .toEqual({ st: "staff_alert", d: false });
    expect(effective([{ st: "evacuate", d: true }], NOW)).toEqual({ st: "evacuate", d: true });
    expect(effective([{ st: "attention", d: true }, { st: "attention", d: false }], NOW).d).toBe(false);
    expect(effective([{ st: "all_clear", d: false, cu: NOW - 1 }], NOW).st).toBe("normal");
  });

  it("frames and signs", () => {
    expect(frames({ texts: ["a", "b"], pictograms_only: true })).toEqual(["a", "b", ""]);
    expect(frames({ texts: [], pictograms_only: false })).toEqual([""]);
    expect(mainSign("evacuate", "left")).toBe("E001");
    expect(mainSign("evacuate", "right")).toBe("E002");
    expect(mainSign("evacuate", null)).toBe("E002");
    expect(mainSign("all_clear", null)).toBe("check");
    expect(mainSign("shelter_in_place", null)).toBe("W001");
    expect(arrowAngle("right")).toBe(90);
    expect(arrowAngle("nonsense")).toBe(0);
    for (const code of ["E001", "E002", "E003", "E007", "W001", "arrow", "X"]) {
      expect(pictogram(code, "back_left")).toContain("<svg");
    }
    expect(pictogram("arrow", "back_left")).toContain("rotate(225 50 50)");
  });
});

const vec = vectors[0] as { key: string; m: string; s: string };

function bundle(over: Partial<EvacBundle> = {}): EvacBundle {
  return { event: "demo", screen: "s1", keys: [vec.key], drill_text: "DRILL", model: "zones", role: "participant",
           zones: ["z1"], stages: { evacuate: { label: "Evacuate", texts: ["Go"], rotate_seconds: 8,
                                                pictograms_only: false, sound: "siren", sound_every: 30, speech: "",
                                                layout: null, takeover: true } },
           directions: { "": { kind: "route", arrow: "right", text: "", target: "Meadow", direction: "Meadow" } },
           blocked: [], fallback_origins: ["http://10.0.0.5:8088"], labels: { evacuate: "Evacuate" }, version: "x",
           ...over };
}

const st = vectors.find((v) => "state_m" in v) as unknown as { state_key: string; state_m: string; state_s: string };
const stateSig = { kid: "x", m: st.state_m, s: st.state_s };

describe("fallback messages", () => {
  it("builds the screen's state from a signed event-wide message and its bundle", () => {
    const p = fromFallback(stateSig, bundle({ keys: [st.state_key] }), NOW) as EvacPayload;
    // the event shows attention, the screen's zone z1 evacuates: highest severity wins
    expect(p.state).toBe("evacuate");
    expect(p.seq).toBe(42);
    expect(p.via).toBe("fallback");
    expect(p.direction).toBe("Meadow");
    expect(p.sound).toBe("siren");
    const other = fromFallback(stateSig, bundle({ keys: [st.state_key], zones: ["z9"] }), NOW) as EvacPayload;
    expect(other.state).toBe("attention");
    expect(other.takeover).toBe(false);
  });

  it("rejects unsigned, foreign and malformed messages", () => {
    expect(fromFallback(stateSig, bundle({ keys: [] }), NOW)).toBeNull();
    expect(fromFallback(stateSig, bundle({ keys: [st.state_key], event: "other" }), NOW)).toBeNull();
    expect(fromFallback({ kid: "x", m: vec.m, s: vec.s }, bundle(), NOW)).toBeNull(); // signed, but no state
  });

  it("the controller takes a verified fallback message", () => {
    document.body.replaceChildren();
    localStorage.clear();
    const ctl = new EvacController({ now: () => NOW, speaker: { say: () => true } as never,
                                     audio: () => ({ enabled: false, volume: 0 }), strings: {},
                                     context: () => ({ vars: {}, now: () => NOW, assets: {}, fonts: {} }),
                                     onRendered: () => undefined });
    expect(ctl.offerFallback(stateSig)).toBe(false); // no bundle yet
    ctl.setBundle(bundle({ keys: [st.state_key] }));
    expect(ctl.offerFallback(stateSig)).toBe(true);
    expect(ctl.payload?.state).toBe("evacuate");
    expect(ctl.offerFallback(stateSig)).toBe(false); // same message again
  });
});

describe("controller", () => {
  let acks: { p: EvacPayload; fallback: boolean }[];
  let ctl: EvacController;
  const speaker = { say: vi.fn(() => true) } as unknown as import("../src/player/speech").Speaker;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
    localStorage.clear();
    document.body.replaceChildren();
    acks = [];
    ctl = new EvacController({
      now: () => Date.now(), speaker, audio: () => ({ enabled: true, volume: 80 }), strings: {},
      context: () => ({ vars: {}, now: () => Date.now(), assets: {}, fonts: {} }),
      onRendered: (p, info) => acks.push({ p, fallback: info.fallback }),
    });
  });
  afterEach(() => vi.useRealTimers());

  it("takes over with the built-in layout, rotates texts, marks drills and acknowledges", () => {
    expect(ctl.offer(payload({ drill: true, speech: "/s.m4a" }), "websocket")).toBe(true);
    const layer = document.getElementById("evac-layer") as HTMLElement;
    expect(layer.hidden).toBe(false);
    expect(layer.dataset.mode).toBe("takeover");
    expect(layer.querySelector(".evac-fb-label")?.textContent).toBe("Evacuate");
    expect(layer.querySelector(".evac-fb-text")?.textContent).toBe("Leave now.");
    expect(layer.querySelector(".evac-fb-dir")?.textContent).toBe("Meadow");
    expect(layer.querySelector(".evac-drill")?.textContent).toBe("DRILL");
    expect(layer.querySelectorAll(".evac-fb-signs svg").length).toBe(2);
    expect(acks).toHaveLength(1);
    expect(acks[0].fallback).toBe(true);
    expect(ctl.active).toBe(true);
    expect(speaker.say).toHaveBeenCalled();
    vi.advanceTimersByTime(8000);
    expect(layer.querySelector(".evac-fb-text")?.textContent).toBe("No lifts.");
    vi.advanceTimersByTime(8000);
    expect(layer.querySelector(".evac-fb-text")).toBeNull(); // the signs-only frame
    // survives a restart: a new controller shows the stored state at once
    document.body.replaceChildren();
    const again = new EvacController({ now: () => Date.now(), speaker, audio: () => ({ enabled: false, volume: 0 }),
                                       strings: {}, context: () => ({ vars: {}, now: () => Date.now(), assets: {}, fonts: {} }),
                                       onRendered: () => undefined });
    again.render(true);
    expect(again.active).toBe(true);
  });

  it("follows staff without a route and shows attention as a banner", () => {
    ctl.offer(payload({ guidance: { kind: "follow_staff", arrow: null, text: "", target: "" }, direction: "" }), "fetch");
    expect(document.querySelector(".evac-fb-dir")?.textContent).toBe("Follow the instructions of the staff");
    ctl.offer(payload({ seq: 2, state: "attention", takeover: false, texts: ["Listen"] }), "fetch");
    const layer = document.getElementById("evac-layer") as HTMLElement;
    expect(layer.dataset.mode).toBe("banner");
    expect(layer.querySelector(".evac-banner")?.textContent).toContain("Listen");
    expect(ctl.active).toBe(false);
  });

  it("hides for normal, staff alert and excluded screens; ends the all clear on time", () => {
    const layer = () => document.getElementById("evac-layer") as HTMLElement;
    ctl.offer(payload({ state: "staff_alert", takeover: false }), "fetch");
    expect(layer().hidden).toBe(true);
    ctl.offer(payload({ seq: 2, role: "excluded" }), "fetch");
    expect(layer().hidden).toBe(true);
    ctl.offer(payload({ seq: 3, role: "info" }), "fetch");
    expect(layer().dataset.mode).toBe("banner");
    ctl.offer(payload({ seq: 4, state: "all_clear", clear_until: new Date(NOW + 5000).toISOString() }), "fetch");
    expect(layer().dataset.state).toBe("all_clear");
    vi.advanceTimersByTime(5100);
    expect(layer().hidden).toBe(true);
    expect(ctl.offer(payload({ seq: 1 }), "fetch")).toBe(false);
    expect(ctl.offer(payload({ seq: 9 }), "fallback")).toBe(false); // unsigned fallback
    expect(ctl.offerFallback(stateSig)).toBe(false); // no bundle yet
  });

  it("renders an own layout and falls back when it fails", () => {
    const layout = { format: 1 as const, width: 1920, height: 1080, elements: [
      { id: "t", type: "text", frame: { x: 0, y: 0, w: 100, h: 20 }, props: { text: "{{ evac.text }} → {{ evac.direction }}" } },
      { id: "p", type: "pictogram", frame: { x: 0, y: 30, w: 20, h: 20 }, props: { code: "arrow", direction: "auto" } },
    ] };
    ctl.offer(payload({ layout }), "fetch");
    const layer = document.getElementById("evac-layer") as HTMLElement;
    expect(layer.textContent).toContain("Leave now. → Meadow");
    expect(layer.querySelector("evac-pictogram svg")?.getAttribute("aria-label")).toContain("left");
    expect(acks[acks.length - 1]?.fallback).toBe(false);
    ctl.offer(payload({ seq: 2, layout: { ...layout, elements: [{ id: "x", type: "nope", frame: { x: 0, y: 0, w: 1, h: 1 } }] } }),
              "fetch");
    expect(acks[acks.length - 1]?.fallback).toBe(true);
    expect(layer.querySelector(".evac-fb")).not.toBeNull();
  });
});
