// SPDX-License-Identifier: AGPL-3.0-or-later
// ISO 7010 safety signs drawn by EVAC (simplified, after the standard's geometry; ADR-0033). Safe-condition signs
// (E…) are white on safety green, W001 black on safety yellow. Every sign is a square SVG with a text alternative.

export const SAFETY_GREEN = "#00843d";
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

// a running person in a 100×100 box, facing right; mirrored for "left"
const RUNNER = `<circle cx="57" cy="20" r="8"/>
<path d="M52 32 L44 56 L30 62 M48 44 L64 50 L74 42 M44 56 L56 70 L52 86 M44 56 L34 74 L20 78" fill="none"
 stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M50 30 L58 32 L62 36 L50 58 L42 54 Z"/>`;

function svg(body: string, label: string, bg: string, fg: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${label}"
 color="${fg}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${bg}"/>${body}</svg>`;
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
  switch (code) {
    case "E001":
    case "E002": {
      // E002: the person runs right into the door on the right; E001 is the mirror image
      const door = `<path d="M66 10 H92 V90 H66 Z" fill="none" stroke="currentColor" stroke-width="5"/>
<path d="M72 18 H86 V82 H72 Z" opacity=".35"/>`;
      const person = `<g transform="translate(0 8) scale(.84)">${RUNNER}</g>`;
      const body = `${door}${person}`;
      return svg(code === "E001" ? `<g transform="translate(100 0) scale(-1 1)">${body}</g>` : body, label,
                 SAFETY_GREEN, "#fff");
    }
    case "E003":
      return svg(`<path d="M40 18 H60 V40 H82 V60 H60 V82 H40 V60 H18 V40 H40 Z"/>`, label, SAFETY_GREEN, "#fff");
    case "E007": {
      const people = [30, 50, 70].map((x) => `<circle cx="${x}" cy="44" r="6"/><path d="M${x - 6} 74 V56 a6 6 0 0 1 12 0 V74 Z"/>`)
        .join("");
      // four arrows in the corners pointing at the group (inwards)
      const arrow = (r: number) => `<g transform="rotate(${r} 50 50)"><path d="M50 24 L58 14 H53 V5 H47 V14 H42 Z"/></g>`;
      return svg(`${people}${[45, 135, 225, 315].map((r) => arrow(r)).join("")}`, label, SAFETY_GREEN, "#fff");
    }
    case "W001":
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${label}">
<path d="M50 6 L96 90 H4 Z" fill="${SAFETY_YELLOW}" stroke="#000" stroke-width="6" stroke-linejoin="round"/>
<rect x="45" y="32" width="10" height="34" rx="3"/><circle cx="50" cy="77" r="6"/></svg>`;
    default: {
      const angle = arrowAngle(direction);
      return svg(`<g transform="rotate(${angle} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
                 `${label}: ${String(direction).replace("_", " ")}`, SAFETY_GREEN, "#fff");
    }
  }
}
