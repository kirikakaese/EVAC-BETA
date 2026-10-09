// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import vectors from "./fixtures/program-vectors.json";
import { fnv1a, nextChange, shuffled, slideAt, weighted, type Program } from "../src/program/engine";

const V = vectors as unknown as {
  program: Program; contexts: Record<string, Record<string, unknown>>;
  cases: { ctx: string; t: number; variant: string; slide: unknown; next: number | null }[];
  units: { fnv: Record<string, number>; shuffle: Record<string, number[]>; weighted: string[] };
};

function program(variant: string): Program {
  return variant === "no-urgent" ? { ...V.program, entries: V.program.entries.filter((e) => e.id !== "override:o2") }
    : V.program;
}

describe("program engine (shared vectors with apps/playlists/engine.py)", () => {
  it("resolves every case like the server", () => {
    for (const c of V.cases) {
      const p = program(c.variant);
      const slide = slideAt(p, V.contexts[c.ctx], c.t);
      const strip = (s: unknown) => (s ? JSON.parse(JSON.stringify(s)) : null);
      expect(strip(slide), `${c.ctx} ${c.t} ${c.variant}`).toEqual(c.slide);
      expect(nextChange(p, c.t, slide)).toBe(c.next);
    }
  });

  it("hashes, shuffles and weights identically", () => {
    for (const [s, h] of Object.entries(V.units.fnv)) expect(fnv1a(s)).toBe(h);
    for (const [seed, out] of Object.entries(V.units.shuffle)) {
      expect(shuffled([0, 1, 2, 3, 4, 5, 6, 7], Number(seed))).toEqual(out);
    }
    expect(weighted(["a", "b", "c"], [3, 1, 2])).toEqual(V.units.weighted);
  });
});
