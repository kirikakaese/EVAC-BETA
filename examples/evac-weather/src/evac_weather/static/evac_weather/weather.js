// SPDX-License-Identifier: AGPL-3.0-or-later
// <evac-x-weather>: the screen widget of the example plugin. EVAC's renderer loads this module, creates the element
// and sets three properties (docs/PLUGIN_SDK.md): settings (the element's settings from the layout editor), vars
// (template variables: event, screen, …) and data ({"weather.current": payload}, refreshed every minute; the last
// payload stays while the server is unreachable). The element only renders. No inline styles: screens run a strict
// Content Security Policy, so the look comes from a constructed style sheet and the theme's CSS variables.
const CSS = `
:host { display: flex; flex-direction: column; justify-content: center; gap: .2em; height: 100%; box-sizing: border-box;
        padding: .4em .6em; font-family: var(--evac-font-body, system-ui, sans-serif);
        color: var(--evac-color-text, currentColor); container-type: size; }
.h { font-size: max(12px, 12cqh); color: var(--evac-color-muted, inherit); text-transform: uppercase;
     letter-spacing: .06em; }
.t { font-size: max(24px, 42cqh); font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; }
.c { font-size: max(14px, 16cqh); }
.w { font-size: max(12px, 12cqh); color: var(--evac-color-muted, inherit); }
`;
let sheet = null;

class EvacWeather extends HTMLElement {
  constructor() {
    super();
    this._settings = {};
    this._data = {};
    const root = this.attachShadow({ mode: "open" });
    try {
      sheet = sheet || new CSSStyleSheet();
      if (!sheet.cssRules.length) sheet.replaceSync(CSS);
      root.adoptedStyleSheets = [sheet];
    } catch (e) { /* very old engine: unstyled but readable */ }
  }
  set settings(v) { this._settings = v || {}; this.render(); }
  get settings() { return this._settings; }
  set vars(v) { this._vars = v || {}; }
  get vars() { return this._vars; }
  set data(v) { this._data = v || {}; this.render(); }
  get data() { return this._data; }
  connectedCallback() { this.render(); }

  render() {
    const root = this.shadowRoot;
    const payload = this._data["weather.current"];
    const s = this._settings;
    const line = (cls, text) => { const el = document.createElement("div"); el.className = cls; el.textContent = text; return el; };
    const heading = s.title || "Weather";
    const obs = payload && payload.observation;
    if (!obs) {
      root.replaceChildren(line("h", heading), line("c", payload ? "No reading yet" : "…"));
      return;
    }
    const f = s.unit === "F";
    const temp = f ? obs.temperature_c * 9 / 5 + 32 : obs.temperature_c;
    const parts = [line("h", payload.location ? `${heading} · ${payload.location}` : heading),
                   line("t", `${Math.round(temp)}°${f ? "F" : "C"}`), line("c", obs.condition)];
    if (s.wind !== false && obs.wind_kmh !== null && obs.wind_kmh !== undefined) {
      parts.push(line("w", `Wind ${Math.round(obs.wind_kmh)} km/h`));
    }
    root.replaceChildren(...parts);
  }
}

if (!customElements.get("evac-x-weather")) customElements.define("evac-x-weather", EvacWeather);
