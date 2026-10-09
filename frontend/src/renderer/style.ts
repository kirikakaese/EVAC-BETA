// SPDX-License-Identifier: AGPL-3.0-or-later
// Element style -> CSS. Sizes are relative to the stage (container query units), so a layout renders the same
// at every resolution. Applied through the CSSOM (allowed by the strict CSP, unlike style attributes in HTML).
import type { ElementStyle, RenderContext } from "./types";

export function color(value: string | undefined): string {
  if (!value) return "";
  if (value.startsWith("token:")) return `var(--evac-color-${value.slice(6)})`;
  return /^#[0-9a-fA-F]{6}$/.test(value) || value === "transparent" ? value : "";
}

export function font(value: string | undefined, ctx: RenderContext): string {
  if (!value) return "";
  if (value === "token:heading") return "var(--evac-font-heading)";
  if (value === "token:body") return "var(--evac-font-body)";
  return ctx.fonts[value] ?? "";
}

export function applyStyle(node: HTMLElement, s: ElementStyle | undefined, ctx: RenderContext): void {
  const st = node.style;
  if (!s) return;
  const set = (prop: string, value: string) => { if (value) st.setProperty(prop, value); };
  set("color", color(s.color));
  set("background", color(s.background));
  if (s.borderWidth) {
    st.setProperty("border", `${s.borderWidth / 10}cqh solid ${color(s.borderColor) || "currentColor"}`);
  }
  if (s.radius !== undefined) st.setProperty("border-radius", `${s.radius}cqh`);
  if (s.padding !== undefined) st.setProperty("padding", `${s.padding}cqh`);
  if (s.opacity !== undefined) st.setProperty("opacity", String(s.opacity));
  set("font-family", font(s.fontFamily, ctx));
  if (s.fontSize) st.setProperty("font-size", `${s.fontSize}cqh`);
  if (s.fontWeight) st.setProperty("font-weight", String(s.fontWeight));
  set("font-style", s.fontStyle ?? "");
  set("text-align", s.textAlign ?? "");
  if (s.verticalAlign) {
    st.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[s.verticalAlign]);
  }
  if (s.lineHeight) st.setProperty("line-height", String(s.lineHeight));
  if (s.letterSpacing !== undefined) st.setProperty("letter-spacing", `${s.letterSpacing}em`);
  set("text-transform", s.textTransform ?? "");
  if (s.tabularNumbers) st.setProperty("font-variant-numeric", "tabular-nums");
  if (s.shadow) st.setProperty("box-shadow", "var(--evac-shadow)");
}
