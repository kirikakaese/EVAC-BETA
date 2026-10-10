// SPDX-License-Identifier: AGPL-3.0-or-later
// The stored layout format (version 1) - mirrors apps/content/layout_format.py.

export type Fit = "cover" | "contain" | "fill";

export interface Frame { x: number; y: number; w: number; h: number; rotate?: number }

export interface ElementStyle {
  color?: string; background?: string; borderColor?: string; borderWidth?: number; radius?: number;
  padding?: number; opacity?: number; fontFamily?: string; fontSize?: number; fontWeight?: number;
  fontStyle?: "normal" | "italic"; textAlign?: "left" | "center" | "right" | "justify";
  verticalAlign?: "top" | "middle" | "bottom"; lineHeight?: number; letterSpacing?: number;
  textTransform?: "none" | "uppercase" | "lowercase" | "capitalize"; tabularNumbers?: boolean; shadow?: boolean;
}

export interface LayoutElement {
  id: string;
  type: string;
  name?: string;
  frame: Frame;
  style?: ElementStyle;
  props?: Record<string, unknown>;
  visible_if?: string;
  animation?: { enter?: "none" | "fade" | "slide-up" | "slide-left" | "zoom"; duration?: number; delay?: number };
  locked?: boolean;
  hidden?: boolean;
}

export interface LayoutData {
  format: 1;
  width: number;
  height: number;
  background?: { color?: string; asset?: string; fit?: "cover" | "contain" };
  duration?: number;
  elements: LayoutElement[];
}

export interface AssetEntry {
  id: string; kind: string; name: string; alt: string; width: number | null; height: number | null;
  duration: number | null; urls: Record<string, string>; mimes: Record<string, string>;
}

export type Row = Record<string, string | number | boolean | null>;

/** one custom widget with its rows, as /player/api/widgets/data/ sends it (ADR-0023) */
export interface WidgetData {
  id: string; name: string; visual: string; options: Record<string, unknown>; rows: Row[];
  updated: string | null; stale: boolean;
}

export interface DataStore {
  get(id: string): WidgetData | undefined;
  subscribe(fn: () => void): () => void;
}

export interface RenderContext {
  /** template variables: event, screen, data, ... */
  vars: Record<string, unknown>;
  /** milliseconds since epoch, synchronised with the server */
  now: () => number;
  timezone?: string;
  assets: Record<string, AssetEntry>;
  /** font family id -> CSS font stack */
  fonts: Record<string, string>;
  /** editor: show placeholders and error outlines instead of hiding problems */
  editing?: boolean;
  reducedMotion?: boolean;
  /** CSP nonce of the page: code elements need it (their sandboxed frame inherits the page policy) */
  nonce?: string;
  /** rows of custom widgets ("data" elements) */
  data?: DataStore;
  /** the event's program ("program" elements, ADR-0038) */
  program?: import("./program").ProgramStore;
  /** screen audio settings: off mutes every media widget */
  audio?: { enabled: boolean; volume: number };
  onError?: (elementId: string, error: unknown) => void;
  /** messages from code elements (evac.log) */
  onLog?: (elementId: string, message: string) => void;
}
