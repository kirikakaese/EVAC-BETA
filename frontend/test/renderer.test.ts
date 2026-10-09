// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, vi } from "vitest";

import { renderLayout } from "../src/renderer/render";
import { condition, render } from "../src/renderer/template";
import type { LayoutData, RenderContext } from "../src/renderer/types";
import { formatRemaining } from "../src/renderer/widgets";

const vars = { event: { name: "Demo Camp", tags: ["a", "b"] }, screen: { name: "Foyer", zone: "" } };

describe("template", () => {
  it("renders variables with filters", () => {
    expect(render("Hi {{ event.name }}!", vars)).toBe("Hi Demo Camp!");
    expect(render("{{ event.name|upper }}", vars)).toBe("DEMO CAMP");
    expect(render("{{ event.name|truncate:5 }}", vars)).toBe("Demo…");
    expect(render("{{ screen.zone|default:\"Lobby\" }}", vars)).toBe("Lobby");
    expect(render("{{ event.tags|join:\" / \" }}", vars)).toBe("a / b");
    expect(render("{{ missing.path }}", vars)).toBe("");
    expect(render("<b>{{ event.name }}</b>", vars)).toBe("<b>Demo Camp</b>"); // plain text, inserted safely
  });

  it("handles conditions and nesting", () => {
    const t = "{% if screen.zone %}Zone {{ screen.zone }}{% else %}{% if screen.name %}{{ screen.name }}{% endif %}" +
      "{% endif %}";
    expect(render(t, vars)).toBe("Foyer");
    expect(render(t, { screen: { zone: "North" } })).toBe("Zone North");
    expect(condition("not screen.zone", vars)).toBe(true);
    expect(condition('event.name == "Demo Camp"', vars)).toBe(true);
    expect(condition("event.name != 'Demo Camp'", vars)).toBe(false);
    expect(condition("", vars)).toBe(true);
  });

  it("formats time from the synchronised clock", () => {
    const now = () => Date.UTC(2026, 6, 1, 18, 30, 5);
    expect(render("{{ now|time }}", {}, { now, timezone: "UTC" })).toBe("18:30");
    expect(render('{{ now|date:"iso" }}', {}, { now })).toBe("2026-07-01");
  });
});

describe("countdown", () => {
  it("formats remaining time", () => {
    expect(formatRemaining(65_000, "auto")).toBe("00:01:05");
    expect(formatRemaining(65_000, "ms")).toBe("01:05");
    expect(formatRemaining(90_061_000, "auto")).toBe("1d 01:01:01");
    expect(formatRemaining(-5, "auto")).toBe("00:00:00");
    expect(formatRemaining(2 * 86_400_000, "days")).toBe("2 days");
  });
});

function ctx(extra: Partial<RenderContext> = {}): RenderContext {
  return { vars, now: () => 0, assets: {}, fonts: { f1: '"evac-f1", sans-serif' }, ...extra };
}

describe("renderer", () => {
  const layout: LayoutData = {
    format: 1, width: 1920, height: 1080, elements: [
      { id: "t", type: "text", frame: { x: 10, y: 20, w: 50, h: 10, rotate: 5 },
        style: { color: "token:accent", fontSize: 6, fontFamily: "f1", shadow: true }, props: { text: "{{ event.name }}" } },
      { id: "hidden", type: "text", frame: { x: 0, y: 0, w: 1, h: 1 }, hidden: true, props: { text: "x" } },
      { id: "cond", type: "text", frame: { x: 0, y: 0, w: 1, h: 1 }, visible_if: "screen.zone", props: { text: "y" } },
      { id: "img", type: "image", frame: { x: 0, y: 0, w: 10, h: 10 }, props: { asset: "missing" } },
      { id: "bad", type: "nonsense", frame: { x: 0, y: 0, w: 1, h: 1 } },
    ],
  };

  it("positions elements in percent and applies styles", () => {
    const host = document.createElement("div");
    const errors: string[] = [];
    const r = renderLayout(host, layout, ctx({ onError: (id) => errors.push(id) }));
    const t = r.elements.get("t") as HTMLElement;
    expect(t.style.left).toBe("10%");
    expect(t.style.width).toBe("50%");
    expect(t.style.transform).toBe("rotate(5deg)");
    expect(t.style.color).toBe("var(--evac-color-accent)");
    expect(t.style.fontFamily).toContain("evac-f1");
    expect(t.textContent).toBe("Demo Camp");
    expect(r.elements.has("hidden") || r.elements.has("cond") || r.elements.has("bad")).toBe(false);
    expect(r.elements.get("img")?.textContent).toBe(""); // missing asset: nothing on a public screen
    expect(errors).toEqual(["bad"]);
    r.destroy();
    expect(host.children.length).toBe(0);
  });

  it("shows placeholders, hidden and conditional elements dimmed in the editor", () => {
    const host = document.createElement("div");
    const r = renderLayout(host, layout, ctx({ editing: true }));
    expect(r.elements.get("hidden")?.classList.contains("evac-dimmed")).toBe(true);
    expect(r.elements.get("cond")?.classList.contains("evac-dimmed")).toBe(true);
    expect(r.elements.get("img")?.textContent).toBe("Image");
  });

  it("keeps a failing widget from breaking the screen", () => {
    const host = document.createElement("div");
    const errors: unknown[] = [];
    const broken: LayoutData = { format: 1, width: 100, height: 100, elements: [
      { id: "c", type: "countdown", frame: { x: 0, y: 0, w: 10, h: 10 }, props: { target: "{{ now }}" } },
      { id: "q", type: "qr", frame: { x: 0, y: 0, w: 10, h: 10 }, props: { text: "https://evac.pm" } },
    ] };
    const r = renderLayout(host, broken, ctx({ onError: (_id, e) => errors.push(e), now: () => Date.now() }));
    expect(r.elements.get("q")?.querySelector("svg")).not.toBeNull();
    expect(r.elements.size).toBe(2);
  });

  it("shows the same slideshow image on every screen at the same time", () => {
    vi.useFakeTimers();
    const asset = (id: string) => ({ id, kind: "image", name: id, alt: "", width: 1, height: 1, duration: null,
                                     urls: { original: `/${id}.png` }, mimes: { original: "image/png" } });
    const show: LayoutData = { format: 1, width: 100, height: 100, elements: [
      { id: "s", type: "slideshow", frame: { x: 0, y: 0, w: 100, h: 100 },
        props: { assets: ["a", "b", "c"], interval: 10 } }] };
    const c = ctx({ assets: { a: asset("a"), b: asset("b"), c: asset("c") }, now: () => 25_000 });
    const r = renderLayout(document.createElement("div"), show, c);
    const active = r.elements.get("s")?.querySelector(".evac-slide.active img") as HTMLImageElement;
    expect(active.getAttribute("src")).toBe("/c.png"); // floor(25 s / 10 s) % 3 = 2
    vi.useRealTimers();
  });
});
