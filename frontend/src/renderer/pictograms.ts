// SPDX-License-Identifier: AGPL-3.0-or-later
// Safety signs (ADR-0033). E001, E002, E003, E007 and W001 are the official ISO 7010 artwork, imported from
// @iso-safety-signs/core by scripts/import-iso7010.mjs (iso7010.generated.ts). The direction arrow and the
// all-clear check mark are not ISO 7010 signs and are drawn here. Every sign is a square SVG with a text
// alternative.
import { ISO7010 } from "./iso7010.generated";

export const SAFETY_GREEN = "#237f52";
export const SAFETY_YELLOW = "#f9a800";

export type PictogramCode = "E001" | "E002" | "E003" | "E007" | "W001" | "arrow";
export const ARROWS = ["ahead", "ahead_right", "right", "back_right", "back", "back_left", "left", "ahead_left"] as const;
export type Arrow = (typeof ARROWS)[number];

const LABELS: Record<PictogramCode, string> = {
  E001: "Emergency exit (left)", E002: "Emergency exit (right)", E003: "First aid", E007: "Assembly point",
  W001: "General warning", arrow: "Direction",
};

/** Degrees clockwise from up for an arrow name. "ahead" points up (for people reading the screen). */
export function arrowAngle(a: Arrow | string): number {
  const i = ARROWS.indexOf(a as Arrow);
  return i < 0 ? 0 : i * 45;
}

function svg(body: string, label: string, bg: string, fg: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${label}"
 color="${fg}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${bg}"/>${body}</svg>`;
}

/** An imported ISO 7010 sign with its text alternative. */
function iso(code: string, label: string): string {
  const sign = ISO7010[code];
  return sign.svg.replace(/^<svg\b/, `<svg role="img" aria-label="${label}"`);
}

/** A plain check mark (not an ISO 7010 sign) for the all clear. */
export function checkMark(): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="All clear"
 color="#fff"><circle cx="50" cy="50" r="44" fill="none" stroke="currentColor" stroke-width="8"/>
<path d="M28 52 L44 68 L74 34" fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round"
 stroke-linejoin="round"/></svg>`;
}

/** The SVG markup of a sign. ``direction`` turns the arrow (and picks the exit side for "auto" exits). */
export function pictogram(code: PictogramCode | string, direction: Arrow | string = "ahead"): string {
  const label = LABELS[code as PictogramCode] ?? "Safety sign";
  if (code in ISO7010) return iso(code, label);
  const angle = arrowAngle(direction);
  return svg(`<g transform="rotate(${angle} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
             `${label}: ${String(direction).replace("_", " ")}`, SAFETY_GREEN, "#fff");
}
