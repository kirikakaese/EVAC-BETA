// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { b64url, sha512, verify, verifySigned } from "../src/player/ed25519";
import vectors from "./fixtures/ed25519-vectors.json";

const hex = (b: Uint8Array) => [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
const enc = (s: string) => new TextEncoder().encode(s);
type Vec = { key: string; m: string; s: string };
const sigs = vectors.filter((v): v is Vec & typeof v => "key" in v) as Vec[];
const hashes = vectors.find((v) => "sha512_abc" in v) as { sha512_abc: string; sha512_long: string };

describe("sha512", () => {
  it("matches Python's hashlib", () => {
    expect(hex(sha512(enc("abc")))).toBe(hashes.sha512_abc);
    expect(hex(sha512(enc("a".repeat(300))))).toBe(hashes.sha512_long);
    expect(hex(sha512(new Uint8Array()))).toMatch(/^cf83e1357eefb8bd/);
  });
});

describe("ed25519", () => {
  it("verifies signatures made by the server", () => {
    for (const v of sigs) expect(verify(b64url(v.key), enc(v.m), b64url(v.s))).toBe(true);
  });

  it("rejects tampering, wrong keys and junk", () => {
    const [a, b] = sigs;
    expect(verify(b64url(a.key), enc(a.m.replace("evacuate", "normal")), b64url(a.s))).toBe(false);
    expect(verify(b64url(b.key), enc(a.m), b64url(a.s))).toBe(false);
    const bad = b64url(a.s);
    bad[5] ^= 1;
    expect(verify(b64url(a.key), enc(a.m), bad)).toBe(false);
    expect(verify(new Uint8Array(31), enc(a.m), b64url(a.s))).toBe(false);
    expect(verify(b64url(a.key), enc(a.m), new Uint8Array(10))).toBe(false);
  });

  it("verifySigned returns the core for any accepted key", () => {
    const [a, b] = sigs;
    expect(verifySigned([b.key, a.key], { kid: "x", m: a.m, s: a.s })).toEqual({ e: "demo", seq: 0, st: "evacuate" });
    expect(verifySigned([b.key], { kid: "x", m: a.m, s: a.s })).toBeNull();
    expect(verifySigned(["!!"], { kid: "x", m: a.m, s: a.s })).toBeNull();
    expect(verifySigned([a.key], null)).toBeNull();
  });
});
