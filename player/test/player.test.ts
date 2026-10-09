// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from "vitest";

import { Clock } from "../src/clock";
import { readEnv, t, wsUrl } from "../src/env";
import { qrSvg } from "../src/qr";
import { recordError, report } from "../src/report";
import { getConfig, getToken, setConfig, setToken } from "../src/storage";

describe("clock", () => {
  it("uses the sample with the shortest round trip", () => {
    const c = new Clock();
    c.add(1000, 1400, 10); // rtt 400 -> offset 10000 - 1200 = 8800
    c.add(2000, 2020, 12); // rtt 20  -> offset 12000 - 2010 = 9990
    c.add(3000, 3300, 99); // noisy, long rtt: ignored
    expect(c.offset).toBe(9990);
    expect(Math.abs(c.now() - (Date.now() + 9990))).toBeLessThan(50);
    c.add(5, 1, 1); // negative rtt ignored
    expect(c.offset).toBe(9990);
  });
});

describe("env", () => {
  it("reads settings and strings from the page", () => {
    document.body.innerHTML = `<script id="player-env" type="application/json">
      {"version": "1.2", "api": "/player/api/", "ws": "", "strings": {"hi": "Hello {name}"}}</script>`;
    const env = readEnv();
    expect(env.version).toBe("1.2");
    expect(t(env, "hi", { name: "Foyer" })).toBe("Hello Foyer");
    expect(t(env, "missing")).toBe("missing");
    expect(wsUrl(env, { protocol: "https:", host: "evac.pm" } as Location)).toBe("wss://evac.pm/ws/screen/");
    expect(wsUrl({ ...env, ws: "http://localhost:8001/" })).toBe("http://localhost:8001/ws/screen/");
  });
});

describe("storage", () => {
  it("keeps token and config, forgets both on unpair", () => {
    setToken("evacscreen_x");
    setConfig({ a: 1 });
    expect(getToken()).toBe("evacscreen_x");
    expect(getConfig<{ a: number }>()?.a).toBe(1);
    setToken(null);
    expect(getToken()).toBeNull();
    expect(getConfig()).toBeNull();
  });
});

describe("report and qr", () => {
  it("reports the state and the last ten errors", () => {
    for (let i = 0; i < 12; i++) recordError(`boom ${i}`);
    const r = report({ version: "1", slide: "idle", lastSync: 0, online: true });
    expect(r.version).toBe("1");
    expect((r.errors as string[]).length).toBe(10);
    expect(String((r.errors as string[])[9])).toContain("boom 11");
  });

  it("draws a QR code as SVG", () => {
    const svg = qrSvg("https://evac.pm/screens/pair/?code=ABCDEF");
    expect(svg.getAttribute("viewBox")).toMatch(/^0 0 \d+ \d+$/);
    expect(svg.querySelector("path")?.getAttribute("d")?.length).toBeGreaterThan(100);
  });
});
