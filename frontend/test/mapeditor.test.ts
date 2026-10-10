// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { arrow, bearing, distance, extent, facingTriangle, type MapData, pixelsFor, zoom } from "../src/mapeditor/model";

const empty: MapData = { floor: null, floors: [], plan: null, points: [], elsewhere: {}, edges: [], zones: [],
  layers: [], kinds: [], canEdit: true };

describe("map editor geometry", () => {
  it("fits the plan, the drawing or a default area", () => {
    const plan = { url: "/p", width: 1000, height: 500, metresPerPx: 0.1, scaled: true };
    const close = (a: { x: number; y: number; w: number; h: number }, b: typeof a) =>
      (["x", "y", "w", "h"] as const).forEach((k) => expect(a[k]).toBeCloseTo(b[k]));
    close(extent({ ...empty, plan }), { x: -5, y: -2.5, w: 110, h: 55 });
    close(extent(empty), { x: -5, y: -3, w: 110, h: 66 });
    const drawn = extent({ ...empty, points: [
      { id: "a", kind: "exit", name: "A", x: 10, y: 10, stepFree: true, zone: null, next: null, noWayOut: false },
      { id: "b", kind: "exit", name: "B", x: 70, y: 40, stepFree: true, zone: null, next: null, noWayOut: false }],
      zones: [{ id: "z", name: "Z", color: "#000", area: [[0, 0], [5, 0], [5, 5]] }],
      layers: [{ key: "screens", title: "Screens", editable: true, items: [
        { id: "s", label: "S", placed: true, floor: null, x: 80, y: 45, facing: 0 },
        { id: "t", label: "T", placed: false, floor: null, x: null, y: null, facing: null }] }] });
    expect(drawn.x).toBeCloseTo(-4);
    expect(drawn.w).toBeCloseTo(88);
  });

  it("zooms around a point", () => {
    const v = zoom({ x: 0, y: 0, w: 100, h: 50 }, 2, 50, 25);
    expect(v).toEqual({ x: 25, y: 12.5, w: 50, h: 25 });
    expect(zoom({ x: 0, y: 0, w: 1, h: 1 }, 10, 0, 0).w).toBe(1); // at most 1 m wide
  });

  it("draws route arrows, facing triangles and bearings", () => {
    expect(arrow({ x: 0, y: 0 }, { x: 0, y: 0 }, 5, 1)).toBeNull();
    const a = arrow({ x: 0, y: 0 }, { x: 10, y: 0 }, 4, 1);
    expect(a).not.toBeNull();
    expect([a?.x2, a?.y2]).toEqual([4, 0]);
    expect(arrow({ x: 0, y: 0 }, { x: 2, y: 0 }, 4, 1)?.x2).toBeCloseTo(1.2); // at most 60 % of the way
    expect(facingTriangle(0, 0, 0, 1).split(" ")[0]).toBe("0,-3"); // facing up
    expect(facingTriangle(0, 0, 90, 1).split(" ")[0]).toBe("3,0"); // facing right
    expect(bearing([0, 0], [0, -5])).toBe(0);
    expect(bearing([0, 0], [5, 0])).toBe(90);
    expect(bearing([0, 0], [0, 5])).toBe(180);
    expect(bearing([0, 0], [-5, 0])).toBe(270);
    expect(distance([0, 0], [3, 4])).toBe(5);
    expect(pixelsFor(10, { url: "", width: 1, height: 1, metresPerPx: 0.5, scaled: false })).toBe(20);
  });
});
