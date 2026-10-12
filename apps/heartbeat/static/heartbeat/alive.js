// SPDX-License-Identifier: AGPL-3.0-or-later
// <evac-heartbeat-alive>: the alive indicator of the heartbeat module (ADR-0052), a plugin widget (ADR-0045). A small
// pulsing dot and the current time show that the screen is live; when the screen loses the server the dot turns grey
// and the text says "Offline since HH:MM".
//
// The renderer sets settings (label, seconds, pulse), vars and data {"heartbeat.alive": {server_time, timezone, ttl}}
// and refreshes the data every ttl seconds. While the server is unreachable the renderer hands over the last payload
// again, so the element watches the payload's server_time: when no new one arrived for a while (or the browser says
// it is offline) the screen is offline since the last fresh answer. The element never talks to the server itself.
// No inline styles (strict CSP): a constructed style sheet; no pulse with prefers-reduced-motion.
const SOURCE = "heartbeat.alive";
const CSS = `
:host { display: flex; align-items: center; gap: .45em; height: 100%; box-sizing: border-box; padding: 0 .4em;
        font-family: var(--evac-font-body, system-ui, sans-serif); color: var(--evac-color-text, currentColor);
        container-type: size; font-size: max(12px, 55cqh); line-height: 1; white-space: nowrap; overflow: hidden; }
.dot { flex: none; width: .55em; height: .55em; border-radius: 50%; background: #16a34a; }
.live.pulse .dot { animation: evac-alive-pulse 2s ease-in-out infinite; }
.offline .dot { background: #9ca3af; }
.offline .t { color: var(--evac-color-muted, inherit); }
.t { font-variant-numeric: tabular-nums; }
.l { color: var(--evac-color-muted, inherit); }
.box { display: flex; align-items: center; gap: .45em; }
@keyframes evac-alive-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .35; transform: scale(.8); } }
@media (prefers-reduced-motion: reduce) { .live.pulse .dot { animation: none; } }
`;
let sheet = null;

/** Offline after this many milliseconds without a fresh payload: three refreshes plus slack (the server caches the
 * payload for one refresh period, so a fresh one arrives at least every second refresh). */
export function offlineAfter(ttlSeconds) {
  const ttl = Math.max(10, Number(ttlSeconds) || 10);
  return Math.max(30, 3 * ttl + 5) * 1000;
}

/** The indicator's state: "live" or "offline" with the time of the last fresh answer. */
export function state({ lastFresh, now, ttl, online }) {
  if (lastFresh === null || lastFresh === undefined) return online === false ? { live: false, since: null } : { live: true, since: null };
  if (online === false || now - lastFresh > offlineAfter(ttl)) return { live: false, since: lastFresh };
  return { live: true, since: null };
}

/** When a new payload counts as heard from the server. The first payload after a start may come from the device's
 * storage (the renderer keeps the last one for offline starts): when it is clearly old, the screen has been offline
 * since then, not since now (two minutes of tolerance for a device clock that is off). */
export function freshAt(payload, first, now) {
  const t = Date.parse(payload.server_time);
  if (first && !Number.isNaN(t) && now - t > offlineAfter(payload.ttl) + 120000) return t;
  return now;
}

export function hhmm(ms, timeZone, seconds) {
  const opts = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
  if (seconds) opts.second = "2-digit";
  try {
    return new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: timeZone || undefined }).format(new Date(ms));
  } catch (e) {
    return new Intl.DateTimeFormat("en-GB", opts).format(new Date(ms));  // unknown time zone: the device's
  }
}

export class EvacHeartbeatAlive extends HTMLElement {
  constructor() {
    super();
    this._settings = {};
    this._vars = {};
    this._data = {};
    this._stamp = null;      // server_time of the last fresh payload
    this._lastFresh = null;  // device time when it arrived
    this._timer = null;
    this._box = null;
    const root = this.attachShadow({ mode: "open" });
    try {
      sheet = sheet || new CSSStyleSheet();
      if (!sheet.cssRules.length) sheet.replaceSync(CSS);
      root.adoptedStyleSheets = [sheet];
    } catch (e) { /* very old engine: unstyled but readable */ }
    this._onNet = () => this.render();
  }
  set settings(v) { this._settings = v || {}; this.render(); }
  get settings() { return this._settings; }
  set vars(v) { this._vars = v || {}; }
  get vars() { return this._vars; }
  set data(v) {
    this._data = v || {};
    const p = this._data[SOURCE];
    if (p && p.server_time && p.server_time !== this._stamp) {
      this._lastFresh = freshAt(p, this._stamp === null, Date.now());
      this._stamp = p.server_time;
    }
    this.render();
  }
  get data() { return this._data; }

  connectedCallback() {
    window.addEventListener("online", this._onNet);
    window.addEventListener("offline", this._onNet);
    if (this._timer === null) this._timer = setInterval(() => this.render(), 1000);
    this.render();
  }
  disconnectedCallback() {
    window.removeEventListener("online", this._onNet);
    window.removeEventListener("offline", this._onNet);
    if (this._timer !== null) clearInterval(this._timer);
    this._timer = null;
  }

  render() {
    const root = this.shadowRoot;
    if (!root) return;
    if (!this._box) {  // built once: re-creating it every second would restart the pulse animation
      this._box = document.createElement("div");
      const dot = document.createElement("span");
      dot.className = "dot";
      dot.setAttribute("aria-hidden", "true");
      this._text = document.createElement("span");
      this._text.className = "t";
      this._label = document.createElement("span");
      this._label.className = "l";
      this._box.replaceChildren(dot, this._text, this._label);
      root.replaceChildren(this._box);
    }
    const p = this._data[SOURCE] || {};
    const s = this._settings;
    const now = Date.now();
    const st = state({ lastFresh: this._lastFresh, now, ttl: p.ttl, online: navigator.onLine });
    const cls = `box ${st.live ? "live" : "offline"}${s.pulse === false ? "" : " pulse"}`;
    if (this._box.className !== cls) this._box.className = cls;
    this._text.textContent = st.live ? hhmm(now, p.timezone, Boolean(s.seconds))
      : (st.since ? `Offline since ${hhmm(st.since, p.timezone, false)}` : "Offline");
    this._label.textContent = s.label ? String(s.label) : "";
    this._label.hidden = !s.label;
  }
}

if (!customElements.get("evac-heartbeat-alive")) customElements.define("evac-heartbeat-alive", EvacHeartbeatAlive);
