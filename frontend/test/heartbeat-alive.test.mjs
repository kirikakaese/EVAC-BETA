// SPDX-License-Identifier: AGPL-3.0-or-later
// The heartbeat module's alive indicator (apps/heartbeat/static/heartbeat/alive.js, ADR-0052): a plugin widget that
// shows a dot and the time, and "Offline since HH:MM" once fresh payloads stop arriving.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { freshAt, hhmm, offlineAfter, state } from "../../apps/heartbeat/static/heartbeat/alive.js";

describe("alive indicator", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date("2026-07-01T10:00:00Z")); });
  afterEach(() => { vi.useRealTimers(); document.body.replaceChildren(); });

  it("goes offline after three refreshes without a fresh payload or when the browser is offline", () => {
    expect(offlineAfter(10)).toBe(35000);
    expect(offlineAfter(undefined)).toBe(35000);
    const t0 = Date.now();
    expect(state({ lastFresh: t0, now: t0 + 30000, ttl: 10, online: true })).toEqual({ live: true, since: null });
    expect(state({ lastFresh: t0, now: t0 + 36000, ttl: 10, online: true })).toEqual({ live: false, since: t0 });
    expect(state({ lastFresh: t0, now: t0 + 1000, ttl: 10, online: false })).toEqual({ live: false, since: t0 });
    expect(state({ lastFresh: null, now: t0, ttl: 10, online: true }).live).toBe(true);
  });

  it("dates a stored payload from an offline start back to its server time", () => {
    const now = Date.now();
    const old = { server_time: new Date(now - 3600000).toISOString(), ttl: 10 };
    expect(freshAt(old, true, now)).toBe(now - 3600000);
    expect(freshAt(old, false, now)).toBe(now);
    expect(freshAt({ server_time: new Date(now - 5000).toISOString(), ttl: 10 }, true, now)).toBe(now);
  });

  it("formats the time in the event's time zone", () => {
    expect(hhmm(Date.parse("2026-07-01T10:05:09Z"), "Europe/Berlin", false)).toBe("12:05");
    expect(hhmm(Date.parse("2026-07-01T10:05:09Z"), "Europe/Berlin", true)).toBe("12:05:09");
    expect(hhmm(Date.parse("2026-07-01T10:05:09Z"), "Not/AZone", false)).toMatch(/^\d\d:\d\d$/);
  });

  it("renders live, then grey with the time it lost the server", () => {
    const el = document.createElement("evac-heartbeat-alive");
    el.settings = { label: "Screen 4" };
    document.body.append(el);
    el.data = { "heartbeat.alive": { server_time: "2026-07-01T10:00:00+00:00", timezone: "Europe/Berlin", ttl: 10 } };
    const box = el.shadowRoot.querySelector(".box");
    expect(box.className).toBe("box live pulse");
    expect(el.shadowRoot.querySelector(".t").textContent).toBe("12:00");
    expect(el.shadowRoot.querySelector(".l").textContent).toBe("Screen 4");
    // the renderer hands over the same (cached) payload while the server is unreachable
    vi.advanceTimersByTime(40000);
    el.data = { "heartbeat.alive": { server_time: "2026-07-01T10:00:00+00:00", timezone: "Europe/Berlin", ttl: 10 } };
    expect(el.shadowRoot.querySelector(".box")).toBe(box);  // not rebuilt: the pulse animation keeps running
    expect(box.className).toBe("box offline pulse");
    expect(el.shadowRoot.querySelector(".t").textContent).toBe("Offline since 12:00");
    el.data = { "heartbeat.alive": { server_time: "2026-07-01T10:00:41+00:00", timezone: "Europe/Berlin", ttl: 10 } };
    expect(box.className).toBe("box live pulse");
    el.settings = { pulse: false };
    expect(box.className).toBe("box live");
    expect(el.shadowRoot.querySelector(".l").hidden).toBe(true);
  });
});
