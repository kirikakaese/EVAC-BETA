// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, vi } from "vitest";

import { activeOverlays, arrange, nextOverlayChange, OverlayLayer, playSound, textOn, type Overlay } from "../src/player/overlays";

const ov = (id: string, style: Overlay["style"], rank: number, windows: Overlay["windows"], text = id): Overlay => ({
  id, style, rank, level: "Info", colour: "#2563eb", sound: "none", title: `T ${id}`, text, windows,
});

describe("announcement overlays", () => {
  const list = [
    ov("a", "ticker", 10, [[0, 100], [200, 300]]),
    ov("b", "banner", 20, [[50, null]]),
    ov("c", "card", 30, [[60, 80]]),
    ov("d", "banner", 25, [[70, 90]]),
  ];

  it("finds what is visible, highest rank first", () => {
    expect(activeOverlays(list, 10).map((a) => a.overlay.id)).toEqual(["a"]);
    expect(activeOverlays(list, 75).map((a) => a.overlay.id)).toEqual(["c", "d", "b", "a"]);
    expect(activeOverlays(list, 150).map((a) => a.overlay.id)).toEqual(["b"]);
    expect(activeOverlays(list, 250).map((a) => a.overlay.id)).toEqual(["b", "a"]);
    expect(activeOverlays(undefined, 0)).toEqual([]);
  });

  it("knows the next change", () => {
    expect(nextOverlayChange(list, 0)).toBe(50);
    expect(nextOverlayChange(list, 75)).toBe(80);
    expect(nextOverlayChange(list, 300)).toBeNull();
    expect(nextOverlayChange(undefined, 0)).toBeNull();
  });

  it("arranges one card, one banner and all tickers", () => {
    const r = arrange(activeOverlays(list, 75));
    expect(r.card?.overlay.id).toBe("c");
    expect(r.banner?.overlay.id).toBe("d");
    expect(r.ticker.map((a) => a.overlay.id)).toEqual(["a"]);
  });

  it("picks readable text colours", () => {
    expect(textOn("#ffffff")).toBe("#000000");
    expect(textOn("#fde047")).toBe("#000000");
    expect(textOn("#b91c1c")).toBe("#ffffff");
    expect(textOn("#d97706")).toBe("#000000"); // amber: black reads better than white
    expect(textOn("#dc2626")).toBe("#ffffff");
    expect(textOn("bogus")).toBe("#ffffff");
  });

  it("draws, hides and plays each occurrence's sound once", () => {
    const layer = new OverlayLayer();
    const root = document.createElement("div");
    root.append(document.createElement("main"));
    layer.attach(root);
    expect(root.lastElementChild).toBe(layer.node);
    const start = vi.fn();
    class FakeCtx {
      currentTime = 0; destination = {};
      createOscillator() { return { type: "", frequency: { value: 0 }, connect: (g: unknown) => g, start, stop() {} }; }
      createGain() { return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect: (d: unknown) => d }; }
      close() { return Promise.resolve(); }
    }
    vi.stubGlobal("AudioContext", FakeCtx);
    const loud = [{ ...list[2], sound: "chime" }, list[0], list[1]];
    layer.update(loud, 75, { audio: { enabled: true, volume: 50 } });
    expect(layer.node.querySelector(".ann-card .ann-title")?.textContent).toBe("T c");
    expect(layer.node.querySelector(".ann-banner .ann-text")?.textContent).toBe("b");
    expect(layer.node.querySelectorAll(".ann-ticker .ann-track span").length).toBe(2);
    expect(layer.node.classList.contains("has-bottom")).toBe(true);
    expect((layer.node.querySelector(".ann-card") as HTMLElement).style.getPropertyValue("--ann-fg")).toBe("#ffffff");
    expect(start).toHaveBeenCalledTimes(2);
    layer.update(loud, 76, { audio: { enabled: true, volume: 50 } });
    expect(start).toHaveBeenCalledTimes(2); // same occurrence: no second chime
    layer.update(loud, 75, { hidden: true });
    expect(layer.node.children.length).toBe(0);
    playSound("none");
    playSound("gong", 100);
    playSound("alert", 100);
    expect(start).toHaveBeenCalledTimes(2 + 3 + 4);
    vi.unstubAllGlobals();
    playSound("chime"); // no AudioContext: silently nothing
  });
});
