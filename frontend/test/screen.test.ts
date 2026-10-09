// SPDX-License-Identifier: AGPL-3.0-or-later
import { beforeEach, describe, expect, it, vi } from "vitest";

import { applyRoot, applyState, displayState, inRange, localHHMM, rootTransform } from "../src/player/screen-settings";
import { bootCheck, markClean, recentReloads, safeReload } from "../src/player/resilience";
import { log, logLines, onErrorStorm, recordError } from "../src/player/report";
import { clearCaches } from "../src/player/remote";

describe("display settings", () => {
  it("handles time ranges across midnight", () => {
    expect(inRange("23:30", "22:00", "06:00")).toBe(true);
    expect(inRange("05:59", "22:00", "06:00")).toBe(true);
    expect(inRange("06:00", "22:00", "06:00")).toBe(false);
    expect(inRange("12:00", "09:00", "17:00")).toBe(true);
    expect(inRange("12:00", "", "17:00")).toBe(false);
    expect(inRange("12:00", "09:00", "09:00")).toBe(false);
  });

  it("sleep wins over dim", () => {
    const s = { dim_from: "20:00", dim_until: "08:00", sleep_from: "01:00", sleep_until: "06:00" };
    expect(displayState(s, "21:00")).toBe("dimmed");
    expect(displayState(s, "02:00")).toBe("sleeping");
    expect(displayState(s, "12:00")).toBe("on");
  });

  it("formats local time in the event time zone", () => {
    const t = Date.UTC(2026, 6, 1, 22, 5);
    expect(localHHMM(t, "Europe/Berlin")).toBe("00:05");
    expect(localHHMM(t, "UTC")).toBe("22:05");
    expect(localHHMM(t, "Not/AZone")).toMatch(/^\d\d:\d\d$/);
  });

  it("builds the root transform", () => {
    expect(rootTransform({})).toEqual({ width: "100vw", height: "100vh", transform: "translate(-50%, -50%)",
                                        overscan: "0%" });
    const t = rootTransform({ rotation: "90", scale: 90, keystone_x: 5, keystone_y: -3, overscan: 4 });
    expect(t.width).toBe("100vh");
    expect(t.transform).toBe("translate(-50%, -50%) rotate(90deg) perspective(1200px) rotateX(-3deg) rotateY(5deg) "
                             + "scale(0.9)");
    expect(t.overscan).toBe("4%");
    const root = document.createElement("div");
    applyRoot(root, { rotation: "270" });
    expect(root.classList.contains("evac-root")).toBe(true);
    expect(root.style.height).toBe("100vw");
  });

  it("puts an overlay over the screen when dimmed or sleeping", () => {
    applyState("dimmed", { dim_level: 30 });
    const ov = document.getElementById("evac-dim") as HTMLElement;
    expect(ov.style.opacity).toBe("0.7");
    applyState("sleeping", {});
    expect(ov.style.opacity).toBe("1");
    applyState("on", {});
    expect(document.getElementById("evac-dim")).toBeNull();
  });
});

describe("resilience", () => {
  beforeEach(() => localStorage.clear());

  it("refuses a 4th reload within 10 minutes unless forced", () => {
    const win = { reload: vi.fn() };
    expect(safeReload("a", { win })).toBe(true);
    expect(safeReload("b", { win })).toBe(true);
    expect(safeReload("c", { win })).toBe(true);
    expect(safeReload("d", { win })).toBe(false);
    expect(win.reload).toHaveBeenCalledTimes(3);
    expect(safeReload("staff", { win, force: true })).toBe(true);
    expect(recentReloads().length).toBe(4);
    expect(recentReloads(Date.now() + 11 * 60_000)).toEqual([]);
  });

  it("notices an unclean stop", () => {
    expect(bootCheck(1000)).toBe("");
    expect(bootCheck(2000)).toMatch(/unclean stop/);
    markClean();
    expect(bootCheck(3000)).toBe("");
  });

  it("keeps a log and reacts to error storms", () => {
    log("info", "hello");
    expect(logLines()[logLines().length - 1]).toMatch(/INFO hello$/);
    const storm = vi.fn();
    onErrorStorm(storm);
    for (let i = 0; i < 50; i++) recordError(`e${i}`);
    expect(storm).toHaveBeenCalledTimes(1);
  });

  it("clears caches but keeps the device token", async () => {
    localStorage.setItem("evac.player.token", "evacscreen_x");
    localStorage.setItem("evac.player.bundle", "{}");
    localStorage.setItem("other", "1");
    await clearCaches();
    expect(localStorage.getItem("evac.player.token")).toBe("evacscreen_x");
    expect(localStorage.getItem("evac.player.bundle")).toBeNull();
    expect(localStorage.getItem("other")).toBe("1");
  });
});
