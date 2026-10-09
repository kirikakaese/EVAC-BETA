// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { align, createElement, duplicate, guidesFor, History, reorder, resize, snap, snapMove } from "../src/editor/model";
import type { LayoutData, LayoutElement } from "../src/renderer/types";

const el = (id: string, x: number, y: number, w = 10, h = 10): LayoutElement =>
  ({ id, type: "text", frame: { x, y, w, h } });

describe("editor model", () => {
  it("undoes and redoes", () => {
    const h = new History();
    const a: LayoutData = { format: 1, width: 10, height: 10, elements: [] };
    const b: LayoutData = { ...a, elements: [el("t1", 0, 0)] };
    h.push(a);
    expect(h.undo(b)).toEqual(a);
    expect(h.redo(a)).toEqual(b);
    expect(h.canRedo).toBe(false);
  });

  it("creates unique ids and offsets copies", () => {
    const one = createElement("text", [], "Text");
    const two = createElement("text", [one], "Text");
    expect([one.id, two.id]).toEqual(["text1", "text2"]);
    expect(two.frame.x).toBeGreaterThan(one.frame.x);
    const copy = duplicate(one, [one, two]);
    expect(copy.id).toBe("text3");
    expect(copy.name).toBe("Text copy");
  });

  it("snaps to guides and the grid", () => {
    expect(snap(49.6, [50])).toEqual([50, 50]);
    expect(snap(33.3, [50])).toEqual([33.5, null]);
    const guides = guidesFor([el("a", 20, 0, 30), el("b", 0, 0)], new Set(["b"]), "x");
    expect(guides).toEqual([0, 50, 100, 20, 35, 50]);
    expect(snapMove(39.6, 20, [50])).toEqual([40, 50]); // centre 49.6 -> 50
    expect(snapMove(30.2, 20, [50])).toEqual([30, 50]); // right edge 50.2 -> 50
  });

  it("aligns, reorders and resizes", () => {
    const els = [el("a", 10, 10), el("b", 30, 40, 20)];
    const left = align(els, new Set(["a", "b"]), "left");
    expect(left.map((e) => e.frame.x)).toEqual([10, 10]);
    const centre = align(els, new Set(["a"]), "center");
    expect(centre[0].frame.x).toBe(45);
    expect(reorder(els, "a", 1).map((e) => e.id)).toEqual(["b", "a"]);
    expect(resize({ x: 10, y: 10, w: 20, h: 20 }, "nw", 5, -5)).toEqual({ x: 15, y: 5, w: 15, h: 25 });
    expect(resize({ x: 10, y: 10, w: 20, h: 20 }, "e", -30, 0).w).toBe(1);
  });
});
