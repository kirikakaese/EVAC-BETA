// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var $e = Object.defineProperty;
var Ce = (n, t, e) => t in n ? $e(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var O = (n, t, e) => Ce(n, typeof t != "symbol" ? t + "" : t, e);
class E extends Error {
}
async function _(n, t, e = {}) {
  const s = new AbortController(), i = setTimeout(() => s.abort(), e.timeout ?? 1e4), r = new Headers(e.headers);
  r.set("Accept", "application/json"), e.body && r.set("Content-Type", "application/json"), e.token && r.set("Authorization", `Screen ${e.token}`);
  try {
    const a = await fetch(n + t, {
      ...e,
      headers: r,
      signal: s.signal,
      cache: "no-store",
      credentials: "omit"
    });
    if (a.status === 401) throw new E("token rejected");
    if (!a.ok) throw new Error(`HTTP ${a.status}`);
    return await a.json();
  } finally {
    clearTimeout(i);
  }
}
const Ae = (n, t) => _(n, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), Me = (n, t) => _(n, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), Mt = (n, t) => _(n, "config/", { token: t });
class Te {
  constructor() {
    this.samples = [], this.offset = 0;
  }
  add(t, e, s) {
    const i = e - t;
    i < 0 || !Number.isFinite(s) || (this.samples.push({ offset: s * 1e3 - (t + e) / 2, rtt: i }), this.samples.length > 8 && this.samples.shift(), this.offset = this.samples.reduce((r, a) => a.rtt < r.rtt ? a : r).offset);
  }
  now() {
    return Date.now() + this.offset;
  }
}
const _e = 3e4, Ne = 3e5;
class Ie {
  constructor(t) {
    this.o = t, this.ws = null, this.transport = "connecting", this.wsFailures = 0, this.backoff = 1e3, this.heartbeatTimer = null, this.pendingBeat = null, this.stopped = !1, this.fallbackSince = 0, this.abort = null, this.seq = t.since;
  }
  start() {
    this.stopped = !1, this.heartbeatTimer = setInterval(() => this.beat(), Math.max(2, this.o.heartbeatSeconds) * 1e3), typeof WebSocket > "u" ? this.fallback() : this.openWebSocket();
  }
  stop() {
    this.stopped = !0, this.heartbeatTimer && clearInterval(this.heartbeatTimer), this.abort?.abort(), this.ws?.close();
  }
  setHeartbeat(t) {
    t === this.o.heartbeatSeconds || !this.heartbeatTimer || (this.o.heartbeatSeconds = t, clearInterval(this.heartbeatTimer), this.heartbeatTimer = setInterval(() => this.beat(), Math.max(2, t) * 1e3));
  }
  setTransport(t) {
    t !== this.transport && (this.transport = t, this.o.onTransport(t));
  }
  deliver(t) {
    if (typeof t.seq == "number") {
      if (t.seq <= this.seq) return;
      this.seq = t.seq;
    }
    if (t.type === "revoked") {
      this.stop(), this.o.onUnauthorized();
      return;
    }
    this.o.onMessage(t);
  }
  retry(t) {
    if (this.stopped) return;
    const e = this.backoff + Math.random() * 500;
    this.backoff = Math.min(this.backoff * 2, _e), setTimeout(() => !this.stopped && t(), e);
  }
  // ---------------------------------------------------------------- WebSocket
  openWebSocket() {
    let t = !1, e;
    try {
      e = new WebSocket(this.o.ws);
    } catch {
      this.fallback();
      return;
    }
    this.ws = e, e.onopen = () => {
      t = !0, e.send(JSON.stringify({ type: "auth", token: this.o.token, since: this.seq }));
    }, e.onmessage = (s) => {
      let i;
      try {
        i = JSON.parse(String(s.data));
      } catch {
        return;
      }
      i.type === "hello" ? (this.wsFailures = 0, this.backoff = 1e3, this.setTransport("websocket"), this.beat()) : i.type === "heartbeat.ack" ? this.ack(i.server_time ?? NaN) : i.type !== "pong" && this.deliver(i);
    }, e.onclose = (s) => {
      if (this.ws = null, !this.stopped) {
        if (s.code === 4401) {
          this.stop(), this.o.onUnauthorized();
          return;
        }
        t || (this.wsFailures += 1), this.wsFailures >= 2 ? this.fallback() : (this.setTransport("connecting"), this.retry(() => this.openWebSocket()));
      }
    };
  }
  // ---------------------------------------------------------------- SSE and long-poll fallbacks
  fallback() {
    this.fallbackSince = Date.now(), this.sse();
  }
  maybeBackToWebSocket() {
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > Ne ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
  }
  async sse() {
    if (!(this.stopped || this.maybeBackToWebSocket())) {
      this.abort = new AbortController();
      try {
        const t = await fetch(`${this.o.api}stream/?since=${this.seq}`, {
          headers: { Authorization: `Screen ${this.o.token}`, Accept: "text/event-stream" },
          signal: this.abort.signal,
          cache: "no-store",
          credentials: "omit"
        });
        if (t.status === 401) throw new E("token rejected");
        if (!t.ok || !t.body) throw new Error(`SSE HTTP ${t.status}`);
        this.setTransport("sse"), this.backoff = 1e3;
        const e = t.body.getReader(), s = new TextDecoder();
        let i = "";
        for (; ; ) {
          const { value: r, done: a } = await e.read();
          if (a) break;
          i += s.decode(r, { stream: !0 });
          let o;
          for (; (o = i.indexOf(`

`)) >= 0; ) {
            const c = i.slice(0, o);
            i = i.slice(o + 2);
            const l = c.split(`
`).filter((h) => h.startsWith("data: ")).map((h) => h.slice(6)).join(`
`);
            if (l)
              try {
                this.deliver(JSON.parse(l));
              } catch {
              }
          }
        }
        this.sse();
      } catch (t) {
        t instanceof E ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
      }
    }
  }
  async poll() {
    if (!(this.stopped || this.maybeBackToWebSocket()))
      try {
        const t = await _(
          this.o.api,
          `poll/?since=${this.seq}&wait=10`,
          { token: this.o.token, timeout: 2e4 }
        );
        this.setTransport("poll"), this.backoff = 1e3, t.messages.forEach((e) => this.deliver(e)), this.poll();
      } catch (t) {
        if (t instanceof E) {
          this.stop(), this.o.onUnauthorized();
          return;
        }
        this.setTransport("offline"), this.retry(() => {
          this.sse();
        });
      }
  }
  // ---------------------------------------------------------------- heartbeat + time sync
  ack(t) {
    if (this.pendingBeat !== null) {
      const e = Date.now();
      this.o.clock.add(this.pendingBeat, e, t), this.pendingBeat = null, this.o.onSync(e);
    }
  }
  beat() {
    if (this.stopped) return;
    const t = this.o.report();
    if (this.pendingBeat = Date.now(), this.ws && this.ws.readyState === WebSocket.OPEN && this.transport === "websocket") {
      this.ws.send(JSON.stringify({ type: "heartbeat", data: t }));
      return;
    }
    _(this.o.api, "heartbeat/", {
      method: "POST",
      token: this.o.token,
      body: JSON.stringify({ data: t })
    }).then((e) => this.ack(e.server_time)).catch((e) => {
      e instanceof E ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function V(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function Pe(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function De(n, t, e) {
  const s = n.style;
  if (!t) return;
  const i = (r, a) => {
    a && s.setProperty(r, a);
  };
  i("color", V(t.color)), i("background", V(t.background)), t.borderWidth && s.setProperty("border", `${t.borderWidth / 10}cqh solid ${V(t.borderColor) || "currentColor"}`), t.radius !== void 0 && s.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && s.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && s.setProperty("opacity", String(t.opacity)), i("font-family", Pe(t.fontFamily, e)), t.fontSize && s.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && s.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && s.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && s.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && s.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && s.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && s.setProperty("box-shadow", "var(--evac-shadow)");
}
function Le(n, t, e) {
  const s = t.trim();
  if (s === "now") return new Date(e.now ? e.now() : Date.now());
  if (/^".*"$|^'.*'$/.test(s)) return s.slice(1, -1);
  if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
  let i = n;
  for (const r of s.split(".")) {
    if (i == null || typeof i != "object") return;
    i = i[r];
  }
  return i;
}
function ze(n) {
  const t = [];
  let e = "", s = "";
  for (const i of n)
    s ? (i === s && (s = ""), e += i) : i === '"' || i === "'" ? (s = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function Oe(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function Tt(n, t, e) {
  const s = e ? { timeZone: e } : {};
  switch (t) {
    case "short":
      return new Intl.DateTimeFormat("en-GB", { ...s, day: "numeric", month: "short" }).format(n);
    case "weekday":
      return new Intl.DateTimeFormat("en-GB", { ...s, weekday: "long" }).format(n);
    case "iso":
      return n.toISOString().slice(0, 10);
    case "HH:mm":
      return new Intl.DateTimeFormat("en-GB", { ...s, hour: "2-digit", minute: "2-digit" }).format(n);
    case "HH:mm:ss":
      return new Intl.DateTimeFormat("en-GB", { ...s, hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(n);
    case "h:mm a":
      return new Intl.DateTimeFormat("en-US", { ...s, hour: "numeric", minute: "2-digit" }).format(n);
    default:
      return new Intl.DateTimeFormat("en-GB", {
        ...s,
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
      }).format(n);
  }
}
function C(n) {
  return n == null ? "" : Array.isArray(n) ? n.map(C).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function Re(n, t, e) {
  const [s, ...i] = t.split(":"), r = Oe(i.join(":")), a = () => n instanceof Date ? n : new Date(String(n));
  switch (s.trim()) {
    case "upper":
      return C(n).toUpperCase();
    case "lower":
      return C(n).toLowerCase();
    case "title":
      return C(n).replace(/\b\p{L}/gu, (o) => o.toUpperCase());
    case "truncate": {
      const o = Number(r) || 30, c = C(n);
      return c.length > o ? `${c.slice(0, Math.max(0, o - 1))}…` : c;
    }
    case "default":
      return C(n) === "" ? r : n;
    case "date":
      return isNaN(a().getTime()) ? "" : Tt(a(), r || "long", e.timezone);
    case "time":
      return isNaN(a().getTime()) ? "" : Tt(a(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map(C).join(r || ", ") : C(n);
    default:
      return n;
  }
}
function J(n, t, e = {}) {
  const [s, ...i] = ze(n);
  let r = Le(t, s, e);
  for (const a of i) r = Re(r, a, e);
  return r;
}
function Be(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function et(n, t, e = {}) {
  const s = n.trim();
  if (!s) return !0;
  if (s.startsWith("not ")) return !et(s.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(s);
  if (i) {
    const r = C(J(i[1], t, e)), a = C(J(i[3], t, e));
    return i[2] === "==" ? r === a : r !== a;
  }
  return Be(J(s.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const Fe = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function ee(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const s = n.split(Fe);
  let i = 0;
  const r = (a) => {
    let o = "";
    for (; i < s.length; ) {
      const c = s[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (a.includes(h)) return [o, h];
        if (h === "if") {
          const d = et(l[2], t, e), [u, p] = r(["else", "endif"]);
          let m = "";
          p === "else" && (m = r(["endif"])[0]), o += d ? u : m;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? o += C(J(c.slice(2, -2), t, e)) : o += c;
    }
    return [o, ""];
  };
  return r([])[0];
}
const We = `(() => {
  let data = {}, received = 0;
  const listeners = [];
  const post = (m) => parent.postMessage(m, "*");
  window.evac = Object.freeze({
    get data() { return data; },
    now() { return typeof data.now === "number" ? data.now + (Date.now() - received) : Date.now(); },
    onData(fn) { listeners.push(fn); if (received) fn(data); },
    log(...args) { post({ type: "evac:log", message: args.map(String).join(" ").slice(0, 500) }); },
  });
  addEventListener("message", (e) => {
    if (e.source !== parent || !e.data || e.data.type !== "evac:data") return;
    data = e.data.data || {};
    received = Date.now();
    for (const fn of listeners) {
      try { fn(data); } catch (err) { post({ type: "evac:error", message: String(err) }); }
    }
  });
  addEventListener("error", (e) => post({ type: "evac:error", message: String(e.message || e) }));
  addEventListener("unhandledrejection", (e) => post({ type: "evac:error", message: String(e.reason) }));
  post({ type: "evac:ready" });
})();`;
function _t(n) {
  return n.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function je(n, t, e, s = "") {
  const i = _t(t), r = e ? ` ${e}` : "", a = [
    "default-src 'none'",
    `script-src 'nonce-${t}'`,
    `style-src 'nonce-${t}'`,
    `img-src data: blob:${r}`,
    `media-src data: blob:${r}`,
    `font-src data:${r}`,
    "connect-src 'none'",
    "form-action 'none'",
    "base-uri 'none'",
    "frame-src 'none'",
    "worker-src 'none'"
  ].join("; "), o = String(n.css ?? "").replace(/<\/style/gi, "<\\/style"), c = String(n.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${_t(a)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${s}</style><style nonce="${i}">${o}</style><script nonce="${i}">${We}<\/script></head><body>${String(n.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function He(n) {
  const t = [];
  try {
    const e = getComputedStyle(n);
    for (let s = 0; s < e.length; s++) {
      const i = e[s];
      if (i.startsWith("--evac-")) {
        const r = e.getPropertyValue(i).trim().replace(/[<>{};]/g, "");
        r && t.push(`${i}:${r}`);
      }
    }
  } catch {
  }
  return t.length ? `:root{${t.join(";")}}` : "";
}
function Nt(n = document) {
  const t = n.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
const W = "#00843d", qe = "#f9a800", Ue = ["ahead", "ahead_right", "right", "back_right", "back", "back_left", "left", "ahead_left"], Ve = {
  E001: "Emergency exit (left)",
  E002: "Emergency exit (right)",
  E003: "First aid",
  E007: "Assembly point",
  W001: "General warning",
  arrow: "Direction"
};
function Je(n) {
  const t = Ue.indexOf(n);
  return t < 0 ? 0 : t * 45;
}
const Ge = `<circle cx="57" cy="20" r="8"/>
<path d="M52 32 L44 56 L30 62 M48 44 L64 50 L74 42 M44 56 L56 70 L52 86 M44 56 L34 74 L20 78" fill="none"
 stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M50 30 L58 32 L62 36 L50 58 L42 54 Z"/>`;
function j(n, t, e, s) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${t}"
 color="${s}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${e}"/>${n}</svg>`;
}
function Ye() {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="All clear"
 color="#fff"><circle cx="50" cy="50" r="44" fill="none" stroke="currentColor" stroke-width="8"/>
<path d="M28 52 L44 68 L74 34" fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round"
 stroke-linejoin="round"/></svg>`;
}
function G(n, t = "ahead") {
  const e = Ve[n] ?? "Safety sign";
  switch (n) {
    case "E001":
    case "E002": {
      const s = `<path d="M66 10 H92 V90 H66 Z" fill="none" stroke="currentColor" stroke-width="5"/>
<path d="M72 18 H86 V82 H72 Z" opacity=".35"/>`, i = `<g transform="translate(0 8) scale(.84)">${Ge}</g>`, r = `${s}${i}`;
      return j(
        n === "E001" ? `<g transform="translate(100 0) scale(-1 1)">${r}</g>` : r,
        e,
        W,
        "#fff"
      );
    }
    case "E003":
      return j('<path d="M40 18 H60 V40 H82 V60 H60 V82 H40 V60 H18 V40 H40 Z"/>', e, W, "#fff");
    case "E007": {
      const s = [30, 50, 70].map((r) => `<circle cx="${r}" cy="44" r="6"/><path d="M${r - 6} 74 V56 a6 6 0 0 1 12 0 V74 Z"/>`).join(""), i = (r) => `<g transform="rotate(${r} 50 50)"><path d="M50 24 L58 14 H53 V5 H47 V14 H42 Z"/></g>`;
      return j(`${s}${[45, 135, 225, 315].map((r) => i(r)).join("")}`, e, W, "#fff");
    }
    case "W001":
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${e}">
<path d="M50 6 L96 90 H4 Z" fill="${qe}" stroke="#000" stroke-width="6" stroke-linejoin="round"/>
<rect x="45" y="32" width="10" height="34" rx="3"/><circle cx="50" cy="77" r="6"/></svg>`;
    default: {
      const s = Je(t);
      return j(
        `<g transform="rotate(${s} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
        `${e}: ${String(t).replace("_", " ")}`,
        W,
        "#fff"
      );
    }
  }
}
var L = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(L || {});
const Ke = [0, 1], ne = [1, 0], se = [2, 3], ie = [3, 2], Ze = {
  L: Ke,
  M: ne,
  Q: se,
  H: ie
}, Xe = /^\d*$/, Qe = /^[A-Z0-9 $%*+./:-]*$/, st = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", wt = 1, St = 40, It = 3, tn = 3, H = 40, en = 10, re = [
  // Version: (note that index 0 is for padding, and is set to an illegal value)
  // 0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40    Error correction level
  [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  // Low
  [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
  // Medium
  [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
  // Quartile
  [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]
  // High
], ae = [
  // Version: (note that index 0 is for padding, and is set to an illegal value)
  // 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40    Error correction level
  [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
  // Low
  [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
  // Medium
  [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68],
  // Quartile
  [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81]
  // High
];
class nn {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, s, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    O(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    O(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    O(this, "modules", []);
    O(this, "types", []);
    if (this.version = t, this.ecc = e, t < wt || t > St)
      throw new RangeError("Version value out of range");
    if (i < -1 || i > 7)
      throw new RangeError("Mask value out of range");
    this.size = t * 4 + 17;
    const r = Array.from({ length: this.size }).fill(!1);
    for (let o = 0; o < this.size; o++)
      this.modules.push(r.slice()), this.types.push(r.map(() => 0));
    this.drawFunctionPatterns();
    const a = this.addEccAndInterleave(s);
    if (this.drawCodewords(a), i === -1) {
      let o = 1e9;
      for (let c = 0; c < 8; c++) {
        this.applyMask(c), this.drawFormatBits(c);
        const l = this.getPenaltyScore();
        l < o && (i = c, o = l), this.applyMask(c);
      }
    }
    this.mask = i, this.applyMask(i), this.drawFormatBits(i);
  }
  /* -- Accessor methods -- */
  // Returns the color of the module (pixel) at the given coordinates, which is false
  // for light or true for dark. The top left corner has the coordinates (x=0, y=0).
  // If the given coordinates are out of bounds, then false (light) is returned.
  getModule(t, e) {
    return t >= 0 && t < this.size && e >= 0 && e < this.size && this.modules[e][t];
  }
  /* -- Private helper methods for constructor: Drawing function modules -- */
  // Reads this object's version field, and draws and marks all function modules.
  drawFunctionPatterns() {
    for (let s = 0; s < this.size; s++)
      this.setFunctionModule(6, s, s % 2 === 0, L.Timing), this.setFunctionModule(s, 6, s % 2 === 0, L.Timing);
    this.drawFinderPattern(3, 3), this.drawFinderPattern(this.size - 4, 3), this.drawFinderPattern(3, this.size - 4);
    const t = this.getAlignmentPatternPositions(), e = t.length;
    for (let s = 0; s < e; s++)
      for (let i = 0; i < e; i++)
        s === 0 && i === 0 || s === 0 && i === e - 1 || s === e - 1 && i === 0 || this.drawAlignmentPattern(t[s], t[i]);
    this.drawFormatBits(0), this.drawVersion();
  }
  // Draws two copies of the format bits (with its own error correction code)
  // based on the given mask and this object's error correction level field.
  drawFormatBits(t) {
    const e = this.ecc[1] << 3 | t;
    let s = e;
    for (let r = 0; r < 10; r++)
      s = s << 1 ^ (s >>> 9) * 1335;
    const i = (e << 10 | s) ^ 21522;
    for (let r = 0; r <= 5; r++)
      this.setFunctionModule(8, r, M(i, r));
    this.setFunctionModule(8, 7, M(i, 6)), this.setFunctionModule(8, 8, M(i, 7)), this.setFunctionModule(7, 8, M(i, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, M(i, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, M(i, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, M(i, r));
    this.setFunctionModule(8, this.size - 8, !0);
  }
  // Draws two copies of the version bits (with its own error correction code),
  // based on this object's version field, iff 7 <= version <= 40.
  drawVersion() {
    if (this.version < 7)
      return;
    let t = this.version;
    for (let s = 0; s < 12; s++)
      t = t << 1 ^ (t >>> 11) * 7973;
    const e = this.version << 12 | t;
    for (let s = 0; s < 18; s++) {
      const i = M(e, s), r = this.size - 11 + s % 3, a = Math.floor(s / 3);
      this.setFunctionModule(r, a, i), this.setFunctionModule(a, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let s = -4; s <= 4; s++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(s)), a = t + i, o = e + s;
        a >= 0 && a < this.size && o >= 0 && o < this.size && this.setFunctionModule(a, o, r !== 2 && r !== 4, L.Position);
      }
  }
  // Draws a 5*5 alignment pattern, with the center module
  // at (x, y). All modules must be in bounds.
  drawAlignmentPattern(t, e) {
    for (let s = -2; s <= 2; s++)
      for (let i = -2; i <= 2; i++)
        this.setFunctionModule(
          t + i,
          e + s,
          Math.max(Math.abs(i), Math.abs(s)) !== 1,
          L.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, s, i = L.Function) {
    this.modules[e][t] = s, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, s = this.ecc;
    if (t.length !== Y(e, s))
      throw new RangeError("Invalid argument");
    const i = ae[s[0]][e], r = re[s[0]][e], a = Math.floor(ct(e) / 8), o = i - a % i, c = Math.floor(a / i), l = [], h = un(r);
    for (let u = 0, p = 0; u < i; u++) {
      const m = t.slice(p, p + c - r + (u < o ? 0 : 1));
      p += m.length;
      const b = fn(m, h);
      u < o && m.push(0), l.push(m.concat(b));
    }
    const d = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((p, m) => {
        (u !== c - r || m >= o) && d.push(p[u]);
      });
    return d;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(ct(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let s = this.size - 1; s >= 1; s -= 2) {
      s === 6 && (s = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const a = s - r, c = (s + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][a] && e < t.length * 8 && (this.modules[c][a] = M(t[e >>> 3], 7 - (e & 7)), e++);
        }
    }
  }
  // XORs the codeword modules in this QR Code with the given mask pattern.
  // The function modules must be marked and the codeword bits must be drawn
  // before masking. Due to the arithmetic of XOR, calling applyMask() with
  // the same mask value a second time will undo the mask. A final well-formed
  // QR Code needs exactly one (not zero, two, etc.) mask applied.
  applyMask(t) {
    if (t < 0 || t > 7)
      throw new RangeError("Mask value out of range");
    for (let e = 0; e < this.size; e++)
      for (let s = 0; s < this.size; s++) {
        let i;
        switch (t) {
          case 0:
            i = (s + e) % 2 === 0;
            break;
          case 1:
            i = e % 2 === 0;
            break;
          case 2:
            i = s % 3 === 0;
            break;
          case 3:
            i = (s + e) % 3 === 0;
            break;
          case 4:
            i = (Math.floor(s / 3) + Math.floor(e / 2)) % 2 === 0;
            break;
          case 5:
            i = s * e % 2 + s * e % 3 === 0;
            break;
          case 6:
            i = (s * e % 2 + s * e % 3) % 2 === 0;
            break;
          case 7:
            i = ((s + e) % 2 + s * e % 3) % 2 === 0;
            break;
          default:
            throw new Error("Unreachable");
        }
        !this.types[e][s] && i && (this.modules[e][s] = !this.modules[e][s]);
      }
  }
  // Calculates and returns the penalty score based on state of this QR Code's current modules.
  // This is used by the automatic mask choice algorithm to find the mask pattern that yields the lowest score.
  getPenaltyScore() {
    let t = 0;
    for (let r = 0; r < this.size; r++) {
      let a = !1, o = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[r][l] === a ? (o++, o === 5 ? t += It : o > 5 && t++) : (this.finderPenaltyAddHistory(o, c), a || (t += this.finderPenaltyCountPatterns(c) * H), a = this.modules[r][l], o = 1);
      t += this.finderPenaltyTerminateAndCount(a, o, c) * H;
    }
    for (let r = 0; r < this.size; r++) {
      let a = !1, o = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === a ? (o++, o === 5 ? t += It : o > 5 && t++) : (this.finderPenaltyAddHistory(o, c), a || (t += this.finderPenaltyCountPatterns(c) * H), a = this.modules[l][r], o = 1);
      t += this.finderPenaltyTerminateAndCount(a, o, c) * H;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let a = 0; a < this.size - 1; a++) {
        const o = this.modules[r][a];
        o === this.modules[r][a + 1] && o === this.modules[r + 1][a] && o === this.modules[r + 1][a + 1] && (t += tn);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((a, o) => a + (o ? 1 : 0), e);
    const s = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - s * 10) / s) - 1;
    return t += i * en, t;
  }
  /* -- Private helper functions -- */
  // Returns an ascending list of positions of alignment patterns for this version number.
  // Each position is in the range [0,177), and are used on both the x and y axes.
  // This could be implemented as lookup table of 40 variable-length lists of integers.
  getAlignmentPatternPositions() {
    if (this.version === 1)
      return [];
    {
      const t = Math.floor(this.version / 7) + 2, e = this.version === 32 ? 26 : Math.ceil((this.version * 4 + 4) / (t * 2 - 2)) * 2, s = [6];
      for (let i = this.size - 7; s.length < t; i -= e)
        s.splice(1, 0, i);
      return s;
    }
  }
  // Can only be called immediately after a light run is added, and
  // returns either 0, 1, or 2. A helper function for getPenaltyScore().
  finderPenaltyCountPatterns(t) {
    const e = t[1], s = e > 0 && t[2] === e && t[3] === e * 3 && t[4] === e && t[5] === e;
    return (s && t[0] >= e * 4 && t[6] >= e ? 1 : 0) + (s && t[6] >= e * 4 && t[0] >= e ? 1 : 0);
  }
  // Must be called at the end of a line (row or column) of modules. A helper function for getPenaltyScore().
  finderPenaltyTerminateAndCount(t, e, s) {
    return t && (this.finderPenaltyAddHistory(e, s), e = 0), e += this.size, this.finderPenaltyAddHistory(e, s), this.finderPenaltyCountPatterns(s);
  }
  // Pushes the given value to the front and drops the last value. A helper function for getPenaltyScore().
  finderPenaltyAddHistory(t, e) {
    e[0] === 0 && (t += this.size), e.pop(), e.unshift(t);
  }
}
function T(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let s = t - 1; s >= 0; s--)
    e.push(n >>> s & 1);
}
function M(n, t) {
  return (n >>> t & 1) !== 0;
}
class kt {
  // Creates a new QR Code segment with the given attributes and data.
  // The character count (numChars) must agree with the mode and the bit buffer length,
  // but the constraint isn't checked. The given bit buffer is cloned and stored.
  constructor(t, e, s) {
    if (this.mode = t, this.numChars = e, this.bitData = s, e < 0)
      throw new RangeError("Invalid argument");
    this.bitData = s.slice();
  }
  /* -- Methods -- */
  // Returns a new copy of the data bits of this segment.
  getData() {
    return this.bitData.slice();
  }
}
const sn = [1, 10, 12, 14], rn = [2, 9, 11, 13], an = [4, 8, 16, 16];
function oe(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function ce(n) {
  const t = [];
  for (const e of n)
    T(e, 8, t);
  return new kt(an, n.length, t);
}
function on(n) {
  if (!le(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const s = Math.min(n.length - e, 3);
    T(Number.parseInt(n.substring(e, e + s), 10), s * 3 + 1, t), e += s;
  }
  return new kt(sn, n.length, t);
}
function cn(n) {
  if (!he(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let s = st.indexOf(n.charAt(e)) * 45;
    s += st.indexOf(n.charAt(e + 1)), T(s, 11, t);
  }
  return e < n.length && T(st.indexOf(n.charAt(e)), 6, t), new kt(rn, n.length, t);
}
function ln(n) {
  return n === "" ? [] : le(n) ? [on(n)] : he(n) ? [cn(n)] : [ce(dn(n))];
}
function le(n) {
  return Xe.test(n);
}
function he(n) {
  return Qe.test(n);
}
function hn(n, t) {
  let e = 0;
  for (const s of n) {
    const i = oe(s.mode, t);
    if (s.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + s.bitData.length;
  }
  return e;
}
function dn(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function ct(n) {
  if (n < wt || n > St)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function Y(n, t) {
  return Math.floor(ct(n) / 8) - re[t[0]][n] * ae[t[0]][n];
}
function un(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let s = 0; s < n - 1; s++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < t.length; i++)
      t[i] = lt(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = lt(e, 2);
  }
  return t;
}
function fn(n, t) {
  const e = t.map((s) => 0);
  for (const s of n) {
    const i = s ^ e.shift();
    e.push(0), t.forEach((r, a) => e[a] ^= lt(r, i));
  }
  return e;
}
function lt(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let s = 7; s >= 0; s--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> s & 1) * n;
  return e;
}
function pn(n, t, e = 1, s = 40, i = -1, r = !0) {
  if (!(wt <= e && e <= s && s <= St) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let a, o;
  for (a = e; ; a++) {
    const d = Y(a, t) * 8, u = hn(n, a);
    if (u <= d) {
      o = u;
      break;
    }
    if (a >= s)
      throw new RangeError("Data too long");
  }
  for (const d of [ne, se, ie])
    r && o <= Y(a, d) * 8 && (t = d);
  const c = [];
  for (const d of n) {
    T(d.mode[0], 4, c), T(d.numChars, oe(d.mode, a), c);
    for (const u of d.getData())
      c.push(u);
  }
  const l = Y(a, t) * 8;
  T(0, Math.min(4, l - c.length), c), T(0, (8 - c.length % 8) % 8, c);
  for (let d = 236; c.length < l; d ^= 253)
    T(d, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((d, u) => h[u >>> 3] |= d << 7 - (u & 7)), new nn(a, t, h, i);
}
function mn(n, t) {
  const {
    ecc: e = "L",
    boostEcc: s = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: a = -1,
    border: o = 1
  } = t || {}, c = typeof n == "string" ? ln(n) : Array.isArray(n) ? [ce(n)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const l = pn(
    c,
    Ze[e],
    i,
    r,
    a,
    s
  ), h = gn({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, o);
  return t?.invert && (h.data = h.data.map((d) => d.map((u) => !u))), t?.onEncoded?.(h), h;
}
function gn(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, s = e + t * 2;
  n.size = s, n.data.forEach((r) => {
    for (let a = 0; a < t; a++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    n.data.unshift(Array.from({ length: s }, (a) => !1)), n.data.push(Array.from({ length: s }, (a) => !1));
  const i = L.Border;
  n.types.forEach((r) => {
    for (let a = 0; a < t; a++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    n.types.unshift(Array.from({ length: s }, (a) => i)), n.types.push(Array.from({ length: s }, (a) => i));
  return n;
}
const it = "http://www.w3.org/2000/svg";
function de(n, t = document) {
  const { data: e, size: s } = mn(n, { ecc: "M", border: 2 }), i = t.createElementNS(it, "svg");
  i.setAttribute("viewBox", `0 0 ${s} ${s}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(it, "rect");
  r.setAttribute("width", String(s)), r.setAttribute("height", String(s)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let a = "";
  e.forEach((c, l) => c.forEach((h, d) => {
    h && (a += `M${d} ${l}h1v1h-1z`);
  }));
  const o = t.createElementNS(it, "path");
  return o.setAttribute("d", a), o.setAttribute("fill", "#000"), i.appendChild(o), i;
}
class S extends HTMLElement {
  constructor() {
    super(...arguments), this.timers = [], this.observers = [];
  }
  get props() {
    return this.el.props ?? {};
  }
  configure(t, e) {
    this.el = t, this.ctx = e, this.safely(() => this.draw());
  }
  safely(t) {
    try {
      t();
    } catch (e) {
      this.ctx.onError?.(this.el.id, e), this.replaceChildren(), this.ctx.editing && (this.classList.add("evac-error"), this.textContent = `⚠ ${String(e?.message ?? e)}`);
    }
  }
  text(t) {
    return ee(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
  }
  every(t, e) {
    this.timers.push(setInterval(() => this.safely(e), t));
  }
  observe(t) {
    if (typeof ResizeObserver > "u") return;
    const e = new ResizeObserver(() => this.safely(t));
    e.observe(this), this.observers.push(e);
  }
  asset(t) {
    return typeof t == "string" ? this.ctx.assets[t] : void 0;
  }
  placeholder(t) {
    this.ctx.editing && (this.classList.add("evac-placeholder"), this.textContent = t);
  }
  disconnectedCallback() {
    this.timers.splice(0).forEach(clearInterval), this.observers.splice(0).forEach((t) => t.disconnect());
  }
}
function yn(n, t) {
  t.style.removeProperty("font-size");
  const e = parseFloat(getComputedStyle(t).fontSize) || 16, s = () => t.scrollHeight <= n.clientHeight + 1 && t.scrollWidth <= n.clientWidth + 1;
  if (!n.clientHeight || s()) return;
  let i = Math.max(4, e * 0.1), r = e;
  for (let a = 0; a < 12 && r - i > 0.5; a++) {
    const o = (i + r) / 2;
    t.style.fontSize = `${o}px`, s() ? i = o : r = o;
  }
  t.style.fontSize = `${i}px`;
}
class vn extends S {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-text";
    const e = this.text(this.props.text), s = Number(this.props.clamp) || 0;
    if (this.props.marquee) {
      const i = document.createElement("span");
      i.className = "evac-marquee", i.textContent = e, i.style.animationDuration = `${Math.max(8, e.length / 6)}s`, t.classList.add("evac-marquee-box"), t.appendChild(i);
    } else
      t.textContent = e, s && (t.classList.add("evac-clamp"), t.style.setProperty("-webkit-line-clamp", String(s)));
    if (this.replaceChildren(t), this.props.autofit && !this.props.marquee) {
      const i = () => yn(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class bn extends S {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-richtext";
    for (const e of this.text(this.props.text).split(/\n{2,}/)) {
      const s = document.createElement("p");
      e.split(`
`).forEach((i, r) => {
        r && s.appendChild(document.createElement("br"));
        for (const a of i.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/))
          /^\*\*[^*]+\*\*$/.test(a) ? s.appendChild(Object.assign(
            document.createElement("strong"),
            { textContent: a.slice(2, -2) }
          )) : /^\*[^*]+\*$/.test(a) ? s.appendChild(Object.assign(
            document.createElement("em"),
            { textContent: a.slice(1, -1) }
          )) : a && s.appendChild(document.createTextNode(a));
      }), t.appendChild(s);
    }
    this.replaceChildren(t);
  }
}
function ue(n, t, e) {
  const s = document.createElement("picture");
  for (const [r, a] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[r]) {
      const o = document.createElement("source");
      o.type = a, o.srcset = n.urls[r], s.appendChild(o);
    }
  const i = document.createElement("img");
  return i.src = n.urls.original, i.alt = e || n.alt || "", i.decoding = "async", i.style.objectFit = t, s.appendChild(i), s;
}
class wn extends S {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(ue(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class Sn extends S {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((a) => this.asset(a)).filter((a) => !!a);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), s = t.map((a) => {
      const o = ue(a, e, "");
      return o.className = "evac-slide", o;
    });
    this.replaceChildren(...s);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const a = Math.floor(this.ctx.now() / i) % s.length;
      s.forEach((o, c) => o.classList.toggle("active", c === a));
    };
    r(), this.every(500, r);
  }
}
class kn extends S {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Video");
    const e = document.createElement("video");
    e.muted = this.props.muted !== !1 || this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.loop = this.props.loop !== !1, e.playsInline = !0, e.preload = "auto", e.style.objectFit = String(this.props.fit ?? "cover"), t.urls.poster && (e.poster = t.urls.poster);
    for (const s of ["webm", "mp4", "original"]) {
      if (!t.urls[s]) continue;
      const i = document.createElement("source");
      i.src = t.urls[s], i.type = t.mimes[s] || "", e.appendChild(i);
    }
    this.ctx.editing || (e.autoplay = !0, e.play?.()?.catch(() => {
    })), this.replaceChildren(e);
  }
}
class xn extends S {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class En extends S {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class $n extends S {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = de(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Cn = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class An extends S {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Cn[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = s.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class Mn extends S {
  draw() {
    const t = String(this.props.format ?? "long"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = {
      long: { weekday: "long", day: "numeric", month: "long" },
      short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" },
      iso: { year: "numeric", month: "2-digit", day: "2-digit" }
    }, i = new Intl.DateTimeFormat(t === "iso" ? "sv-SE" : "en-GB", { ...s[t], timeZone: e }), r = document.createElement("time"), a = () => {
      r.textContent = i.format(new Date(this.ctx.now()));
    };
    a(), this.replaceChildren(r), this.every(3e4, a);
  }
}
function Tn(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), s = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), a = e % 60, o = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${s} ${s === 1 ? "day" : "days"}` : t === "ms" ? `${o(Math.floor(e / 60))}:${o(a)}` : t === "hms" || s === 0 ? `${o(i + s * 24)}:${o(r)}:${o(a)}` : `${s}d ${o(i)}:${o(r)}:${o(a)}`;
}
class _n extends S {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), s = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : Tn(i, String(this.props.format ?? "auto"));
    };
    s(), this.replaceChildren(e), this.every(250, s);
  }
}
class Nn extends S {
  constructor() {
    super(...arguments), this.frame = null, this.onMessage = (t) => {
      if (!this.frame || t.source !== this.frame.contentWindow || typeof t.data != "object" || !t.data) return;
      const e = t.data;
      e.type === "evac:ready" ? this.send() : e.type === "evac:error" ? this.ctx.onError?.(this.el.id, new Error(String(e.message).slice(0, 300))) : e.type === "evac:log" && this.ctx.onLog?.(this.el.id, String(e.message).slice(0, 500));
    };
  }
  draw() {
    const t = this.ctx.nonce ?? "";
    if (!t) return this.placeholder("Code (not available on this page)");
    const e = this.props, s = document.createElement("iframe");
    s.setAttribute("sandbox", "allow-scripts"), s.setAttribute("referrerpolicy", "no-referrer"), s.setAttribute("allow", "autoplay"), s.setAttribute("title", this.el.name || "Code"), s.setAttribute("tabindex", "-1"), s.className = "evac-code-frame", s.srcdoc = je(e, t, location.origin, He(this)), this.frame = s, window.addEventListener("message", this.onMessage), this.replaceChildren(s), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
  }
  /** Only the kinds of data the element asked for (and that the server let it ask for). */
  send() {
    const t = new Set(this.props.data ?? []), e = this.ctx.vars, s = {};
    if (t.has("event") && (s.event = e.event ?? null), t.has("screen") && (s.screen = e.screen ?? null), t.has("time") && (s.now = this.ctx.now(), s.timezone = this.ctx.timezone ?? ""), t.has("assets")) {
      const i = {};
      for (const r of this.props.assets ?? []) {
        const a = this.ctx.assets[r];
        if (!a) continue;
        const o = {};
        for (const [c, l] of Object.entries(a.urls)) o[c] = new URL(l, location.href).href;
        i[r] = { name: a.name, kind: a.kind, alt: a.alt, width: a.width, height: a.height, urls: o };
      }
      s.assets = i;
    }
    this.frame?.contentWindow?.postMessage({ type: "evac:data", data: JSON.parse(JSON.stringify(s)) }, "*");
  }
  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage), this.frame = null, super.disconnectedCallback();
  }
}
const xt = {
  text: vn,
  richtext: bn,
  image: wn,
  slideshow: Sn,
  video: kn,
  audio: xn,
  shape: En,
  qr: $n,
  clock: An,
  countdown: _n,
  date: Mn,
  code: Nn
};
function In(n = customElements) {
  for (const [t, e] of Object.entries(xt))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
class Pn extends S {
  draw() {
    const t = String(this.props.code ?? "E002");
    let e = String(this.props.direction ?? "auto");
    if (e === "auto") {
      const s = this.ctx.vars.evac;
      if (t === "arrow" && !s?.arrow) {
        this.replaceChildren(), this.hidden = !0;
        return;
      }
      e = s?.arrow ?? "ahead";
    }
    this.hidden = !1, this.innerHTML = G(t, e);
  }
}
xt.pictogram = Pn;
class Dn {
  constructor(t = {}) {
    this.data = t, this.listeners = /* @__PURE__ */ new Set();
  }
  get(t) {
    return this.data[t];
  }
  set(t) {
    this.data = t, this.listeners.forEach((e) => e());
  }
  subscribe(t) {
    return this.listeners.add(t), () => this.listeners.delete(t);
  }
}
function f(n, t = "", e) {
  const s = document.createElement(n);
  return t && (s.className = t), e != null && e !== "" && (s.textContent = String(e)), s;
}
function z(n) {
  if (typeof n == "number") return Number.isFinite(n) ? n : null;
  if (typeof n == "string" && n.trim() !== "") {
    const t = Number(n.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function q(n, t) {
  if (typeof n != "string" || !n) return "";
  const e = /^\d{4}-\d{2}-\d{2}$/.test(n), s = new Date(e ? `${n}T12:00:00Z` : n);
  if (Number.isNaN(s.getTime())) return n;
  const i = e ? { weekday: "short", day: "numeric", month: "short" } : { hour: "2-digit", minute: "2-digit", hour12: !1 };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...i, timeZone: e ? "UTC" : t }).format(s);
  } catch {
    return new Intl.DateTimeFormat("en-GB", i).format(s);
  }
}
const Ln = ["time", "title", "subtitle", "label", "value"];
class zn extends S {
  constructor() {
    super(...arguments), this.unsubscribe = null;
  }
  draw() {
    !this.unsubscribe && this.ctx.data && (this.unsubscribe = this.ctx.data.subscribe(() => this.safely(() => this.paint()))), this.paint();
  }
  paint() {
    const t = String(this.props.widget ?? ""), e = t ? this.ctx.data?.get(t) : void 0;
    if (!e) {
      this.replaceChildren(), this.placeholder(t ? "Data widget (no data yet)" : "Data widget: choose a widget");
      return;
    }
    this.classList.remove("evac-placeholder");
    const s = f("div", `evac-data evac-data-${e.visual}`), i = String(this.props.title || e.options.heading || "");
    i && s.appendChild(f("div", "evac-data-heading", i));
    const r = f("div", "evac-data-body");
    s.appendChild(r), (Pt[e.visual] ?? Pt.list)(r, e, this), this.ctx.editing && e.stale && s.appendChild(f("span", "evac-data-stale", "stale")), this.replaceChildren(s);
  }
  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(t, e) {
    return ee(
      t,
      { ...this.ctx.vars, data: {
        first: e.rows[0] ?? {},
        rows: e.rows,
        count: e.rows.length
      } },
      { now: this.ctx.now, timezone: this.ctx.timezone }
    );
  }
  get tz() {
    return this.ctx.timezone;
  }
  disconnectedCallback() {
    this.unsubscribe?.(), this.unsubscribe = null, super.disconnectedCallback();
  }
}
function R(n, t) {
  return t.rows.length ? !1 : (n.appendChild(f("div", "evac-data-empty", "–")), !0);
}
const Pt = {
  text(n, t, e) {
    n.appendChild(f("div", "evac-data-text", e.tmpl(
      String(t.options.template || "{{ data.first.title }}"),
      t
    )));
  },
  list(n, t, e) {
    if (R(n, t)) return;
    const s = f("ul", "evac-data-list");
    for (const i of t.rows) {
      const r = f("li");
      i.time && r.appendChild(f("span", "evac-data-time", q(i.time, e.tz)));
      const a = f("span", "evac-data-main");
      a.appendChild(f("span", "evac-data-title", i.title ?? i.label ?? i.value)), i.subtitle && a.appendChild(f("span", "evac-data-sub", i.subtitle)), r.appendChild(a), i.value !== void 0 && i.value !== null && i.title && r.appendChild(f("span", "evac-data-value", i.value)), s.appendChild(r);
    }
    n.appendChild(s);
  },
  table(n, t, e) {
    if (R(n, t)) return;
    const s = Ln.filter((a) => t.rows.some((o) => o[a] !== void 0 && o[a] !== null && o[a] !== "")), i = f("table", "evac-data-table"), r = f("tbody");
    for (const a of t.rows) {
      const o = f("tr");
      for (const c of s) o.appendChild(f("td", `evac-data-${c}`, c === "time" ? q(a[c], e.tz) : a[c]));
      r.appendChild(o);
    }
    i.appendChild(r), n.appendChild(i);
  },
  cards(n, t, e) {
    if (R(n, t)) return;
    const s = f("div", "evac-data-cards");
    for (const i of t.rows) {
      const r = f("div", "evac-data-card");
      if (typeof i.image == "string" && i.image.startsWith("/")) {
        const a = f("img");
        a.src = i.image, a.alt = "", r.appendChild(a);
      }
      i.time && r.appendChild(f("div", "evac-data-time", q(i.time, e.tz))), r.appendChild(f("div", "evac-data-title", i.title ?? i.label)), i.subtitle && r.appendChild(f("div", "evac-data-sub", i.subtitle)), i.value !== void 0 && i.value !== null && r.appendChild(f("div", "evac-data-value", i.value)), s.appendChild(r);
    }
    n.appendChild(s);
  },
  counter(n, t) {
    const e = t.rows[0] ?? {}, s = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, i = z(s), r = f("div", "evac-data-number", i === null ? s : i.toLocaleString("en-GB"));
    t.options.unit && r.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(r), (e.label || e.title) && n.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(n, t) {
    const e = t.rows[0] ?? {}, s = z(e.value) ?? 0, i = z(t.options.minimum) ?? 0, r = z(t.options.maximum) ?? 100, a = Math.max(0, Math.min(1, (s - i) / (r - i || 1))), o = "http://www.w3.org/2000/svg", c = document.createElementNS(o, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${s}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (d, u) => {
      const p = Math.PI * (1 - d), m = document.createElementNS(o, "path");
      m.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(p)} ${100 - 80 * Math.sin(p)}`), m.setAttribute("class", u), c.appendChild(m);
    };
    l(1, "evac-gauge-track"), a > 0 && l(a, "evac-gauge-fill"), n.appendChild(c);
    const h = f("div", "evac-data-number", s.toLocaleString("en-GB"));
    t.options.unit && h.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(h), (e.label || e.title) && n.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(n, t, e) {
    if (R(n, t)) return;
    const s = t.rows.map((a) => [a.time ? q(a.time, e.tz) : "", a.title ?? a.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), i = f("div", "evac-marquee-box"), r = f("span", "evac-marquee", s);
    r.style.animationDuration = `${Math.max(10, s.length / 5)}s`, i.appendChild(r), n.appendChild(i);
  },
  bars(n, t) {
    if (R(n, t)) return;
    const e = t.rows.map((r) => z(r.value) ?? 0), s = z(t.options.maximum) || Math.max(...e, 1), i = f("div", "evac-data-bars");
    t.rows.forEach((r, a) => {
      const o = f("div", "evac-bar");
      o.appendChild(f("span", "evac-bar-label", r.label ?? r.title));
      const c = f("span", "evac-bar-track"), l = f("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[a] / s * 100))}%`, c.appendChild(l), o.appendChild(c), o.appendChild(f("span", "evac-bar-value", `${e[a].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), i.appendChild(o);
    }), n.appendChild(i);
  }
};
xt.data = zn;
function On(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function Rn(n, t) {
  const e = !n.visible_if || et(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const s = document.createElement("div");
  s.className = `evac-el evac-el-${n.type}`, s.dataset.id = n.id, (!e || n.hidden) && s.classList.add("evac-dimmed"), On(s, n), De(s, n.style, t);
  const i = n.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (s.classList.add(`evac-enter-${i.enter}`), s.style.animationDuration = `${i.duration ?? 600}ms`, s.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${n.type}`;
  if (!customElements.get(r))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? s : null;
  const a = document.createElement(r);
  return a.className = "evac-widget", s.appendChild(a), a.configure(n, t), s;
}
function fe(n, t, e) {
  In();
  const s = document.createElement("div");
  s.className = "evac-stage";
  const i = t.background;
  if (i?.color && (s.style.background = V(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    s.style.backgroundImage = `url("${l}")`, s.style.backgroundSize = i.fit ?? "cover", s.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = Rn(c, e);
    l && (r.set(c.id, l), s.appendChild(l));
  }
  n.replaceChildren(s);
  const a = () => {
    const c = n.clientWidth, l = n.clientHeight;
    if (!c || !l) return;
    const h = Math.min(c / t.width, l / t.height);
    s.style.width = `${Math.round(t.width * h)}px`, s.style.height = `${Math.round(t.height * h)}px`;
  };
  a();
  const o = typeof ResizeObserver < "u" ? new ResizeObserver(a) : null;
  return o?.observe(n), {
    stage: s,
    elements: r,
    destroy() {
      o?.disconnect(), s.remove();
    }
  };
}
function y(n, t = "", e = "") {
  const s = document.createElement(n);
  return t && (s.className = t), e && (s.textContent = e), s;
}
class Bn {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = y("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, s) {
    const i = this.reset();
    i.classList.add("pairing"), i.append(y("h1", "", s.title));
    const r = y("div", "pairing-box"), a = y("p", "code", t);
    a.setAttribute("aria-label", t.split("").join(" "));
    const o = de(e);
    o.setAttribute("role", "img"), o.setAttribute("aria-label", e), r.append(a, o);
    const c = y("ol", "steps");
    c.append(y("li", "", s.step1), y("li", "", s.step2)), i.append(r, c, y("p", "url", e), y("p", "waiting", s.waiting));
  }
  message(t, e = "") {
    const s = this.reset();
    s.classList.add("message"), s.append(y("h1", "", t)), e && s.append(y("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const s = y("p", "clock"), i = y("p", "date");
    e.append(y("h1", "event-name", t.event.name), s, i);
    const r = t.event.timezone || void 0, a = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: r }), o = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: r }), c = () => {
      const l = new Date(this.clock.now());
      s.textContent = a.format(l), i.textContent = o.format(l);
    };
    c(), this.clockTimer = setInterval(c, 1e3);
  }
  layout(t, e, s) {
    const i = this.reset();
    i.classList.add("layout");
    for (const [r, a] of Object.entries(s ?? {})) i.style.setProperty(r, a);
    this.rendered = fe(i, t, e);
  }
  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(t, e, s = 30) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = y("div", "test-pattern");
    i.setAttribute("role", "img"), i.setAttribute("aria-label", t);
    const r = y("div", "tp-bars");
    for (const c of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"])
      r.appendChild(y("span", `tp-bar tp-${c}`));
    const a = y("div", "tp-ramp"), o = y("div", "tp-info");
    o.append(y("p", "tp-title", t), ...e.map((c) => y("p", "", c))), i.append(r, a, y("div", "tp-grid"), y("div", "tp-circle"), y("div", "tp-corners"), o), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), s * 1e3);
  }
  identify(t, e, s = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = y("div", "identify");
    i.setAttribute("role", "status"), i.append(y("p", "identify-name", t), y("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), s * 1e3);
  }
}
const Et = "evac.player.bundle";
async function Fn(n, t) {
  try {
    const e = await _(n, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(Et, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof E) throw e;
    return ht();
  }
}
function ht() {
  try {
    const n = localStorage.getItem(Et);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function Wn() {
  try {
    localStorage.removeItem(Et);
  } catch {
  }
}
function jn(n) {
  return n?.layouts.length ? n.layouts.find((t) => t.default) ?? n.layouts[0] : null;
}
async function Hn(n) {
  const t = /* @__PURE__ */ new Set();
  for (const s of Object.values(n.assets)) Object.values(s.urls).forEach((i) => t.add(i));
  let e = 0;
  return await Promise.all([...t].map(async (s) => {
    try {
      const i = await fetch(s, { credentials: "omit" });
      i.ok && (e += 1), await i.body?.cancel();
    } catch {
    }
  })), e;
}
const Q = "evac.player.program";
async function qn(n, t) {
  try {
    const e = await _(n, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(Q, JSON.stringify(e.program)) : localStorage.removeItem(Q);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof E) throw e;
    return dt();
  }
}
function dt() {
  try {
    const n = localStorage.getItem(Q);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function Un() {
  try {
    localStorage.removeItem(Q);
  } catch {
  }
}
const pe = 1600;
function Vn(n, t) {
  const e = [];
  for (const s of n ?? [])
    for (const [i, r] of s.windows)
      if ((i === null || i <= t) && (r === null || t < r)) {
        e.push({ overlay: s, start: i ?? 0, end: r });
        break;
      }
  return e.sort((s, i) => i.overlay.rank - s.overlay.rank || i.start - s.start);
}
function Jn(n, t) {
  let e = null;
  for (const s of n ?? [])
    for (const [i, r] of s.windows)
      for (const a of [i, r])
        a !== null && a > t && (e === null || a < e) && (e = a);
  return e;
}
function Gn(n) {
  return {
    card: n.find((t) => t.overlay.style === "card") ?? null,
    banner: n.find((t) => t.overlay.style === "banner") ?? null,
    ticker: n.filter((t) => t.overlay.style === "ticker")
  };
}
function Yn(n) {
  const t = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(n);
  if (!t) return "#ffffff";
  const [e, s, i] = t.slice(1).map((a) => {
    const o = parseInt(a, 16) / 255;
    return o <= 0.03928 ? o / 12.92 : ((o + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * e + 0.7152 * s + 0.0722 * i > 0.179 ? "#000000" : "#ffffff";
}
function x(n, t, e = "") {
  const s = document.createElement(n);
  return s.className = t, e && (s.textContent = e), s;
}
function rt(n, t) {
  n.style.setProperty("--ann-bg", /^#[0-9a-f]{6}$/i.test(t) ? t : "#2563eb"), n.style.setProperty("--ann-fg", Yn(t));
}
function me(n, t = 100) {
  if (n === "none" || typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const s = Math.max(0, Math.min(1, t / 100)) * 0.4, i = n === "chime" ? [[660, 0, 0.6], [880, 0.35, 0.9]] : n === "gong" ? [[196, 0, 2.5], [392, 0, 1.5], [294, 0.02, 2]] : [[880, 0, 0.25], [660, 0.3, 0.25], [880, 0.6, 0.25], [660, 0.9, 0.25]];
  let r = 0;
  for (const [a, o, c] of i) {
    const l = e.createOscillator(), h = e.createGain();
    l.type = n === "alert" ? "square" : "sine", l.frequency.value = a;
    const d = e.currentTime + o;
    h.gain.setValueAtTime(1e-4, d), h.gain.exponentialRampToValueAtTime(s, d + 0.02), h.gain.exponentialRampToValueAtTime(1e-4, d + c), l.connect(h).connect(e.destination), l.start(d), l.stop(d + c + 0.05), r = Math.max(r, o + c);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, (r + 0.5) * 1e3);
}
class Kn {
  constructor(t) {
    this.speaker = t, this.drawn = "", this.heard = /* @__PURE__ */ new Set(), this.node = x("div", "ann-layer"), this.node.setAttribute("aria-live", "polite");
  }
  /** Keep the layer on top of the content (the display replaces its children on every slide). */
  attach(t) {
    (this.node.parentElement !== t || t.lastElementChild !== this.node) && t.appendChild(this.node);
  }
  update(t, e, s = {}) {
    const i = s.hidden ? [] : Vn(t, e), { card: r, banner: a, ticker: o } = Gn(i), c = s.audio?.enabled !== !1;
    for (const h of i) {
      const d = `${h.overlay.id}@${h.start}`, u = h.overlay.sound && h.overlay.sound !== "none";
      this.heard.has(d) || (this.heard.add(d), c && u && me(h.overlay.sound, s.audio?.volume ?? 100)), c && h.overlay.speech && this.speaker?.say(d, h.overlay.speech, { volume: s.audio?.volume, delayMs: u ? pe : 0 });
    }
    this.heard.size > 500 && (this.heard = new Set([...this.heard].slice(-100)));
    const l = JSON.stringify([
      r?.overlay.id,
      r?.overlay.title,
      r?.overlay.text,
      a?.overlay.id,
      a?.overlay.text,
      o.map((h) => [h.overlay.id, h.overlay.text])
    ]);
    if (l !== this.drawn) {
      if (this.drawn = l, this.node.replaceChildren(), r) {
        const h = x("section", "ann-card");
        rt(h, r.overlay.colour), h.append(x("p", "ann-level", r.overlay.level), x("h2", "ann-title", r.overlay.title)), r.overlay.text && r.overlay.text !== r.overlay.title && h.append(x("p", "ann-text", r.overlay.text)), this.node.append(h);
      }
      if (a) {
        const h = x("div", "ann-banner");
        rt(h, a.overlay.colour), h.append(x("span", "ann-level", a.overlay.level), x("span", "ann-text", a.overlay.text)), this.node.append(h);
      }
      if (o.length) {
        const h = x("div", "ann-ticker");
        rt(h, o[0].overlay.colour);
        const d = x("div", "ann-track"), u = o.map((m) => m.overlay.text).join("   ◆   "), p = x("span", "", u);
        p.setAttribute("aria-hidden", "true"), d.append(x("span", "", u), p), d.style.setProperty("--ann-duration", `${Math.max(12, Math.round(u.length / 6))}s`), h.append(x("span", "ann-level", o[0].overlay.level), d), this.node.append(h);
      }
      this.node.classList.toggle("has-bottom", !!(a && o.length));
    }
  }
}
class Zn {
  constructor(t = (e) => new Audio(e)) {
    this.make = t, this.spoken = /* @__PURE__ */ new Set(), this.queue = [], this.playing = !1;
  }
  /** Speak ``url`` once for ``key`` (an announcement occurrence); later calls with the same key do nothing. */
  say(t, e, s = {}) {
    if (!e || this.spoken.has(t)) return !1;
    this.spoken.add(t), this.spoken.size > 500 && (this.spoken = new Set([...this.spoken].slice(-100)));
    const i = { url: e, volume: Math.max(0, Math.min(1, (s.volume ?? 100) / 100)) };
    return setTimeout(() => {
      this.queue.push(i), this.next();
    }, s.delayMs ?? 0), !0;
  }
  get busy() {
    return this.playing;
  }
  next() {
    if (this.playing) return;
    const t = this.queue.shift();
    if (!t) return;
    this.playing = !0;
    const e = this.make(t.url);
    e.volume = t.volume;
    const s = () => {
      this.playing = !1, this.next();
    };
    e.addEventListener("ended", s, { once: !0 }), e.addEventListener("error", s, { once: !0 });
    const i = e.play();
    i && typeof i.catch == "function" && i.catch(s);
  }
}
async function Xn(n) {
  let t = 0;
  return await Promise.all([...new Set(n)].map(async (e) => {
    try {
      const s = await fetch(e, { credentials: "omit" });
      s.ok && (t += 1), await s.body?.cancel();
    } catch {
    }
  })), t;
}
const $t = "evac.player.widgets";
function Qn() {
  try {
    const n = localStorage.getItem($t);
    return n ? JSON.parse(n) : {};
  } catch {
    return {};
  }
}
async function ts(n, t, e) {
  try {
    const s = await _(n, "widgets/data/", { token: t, timeout: 15e3 });
    e.set(s.widgets ?? {});
    try {
      localStorage.setItem($t, JSON.stringify(s.widgets ?? {}));
    } catch {
    }
    return !0;
  } catch (s) {
    if (s instanceof E) throw s;
    return !1;
  }
}
function es() {
  try {
    localStorage.removeItem($t);
  } catch {
  }
}
const ns = 5, ss = 1e4;
function is(n) {
  let t = 2166136261;
  for (let e = 0; e < n.length; e++)
    t ^= n.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function rs(n, t) {
  let e = t >>> 0 || 1;
  const s = [...n];
  for (let i = s.length - 1; i > 0; i--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (i + 1);
    [s[i], s[r]] = [s[r], s[i]];
  }
  return s;
}
function as(n, t) {
  const e = t.reduce((r, a) => r + a, 0), s = t.map(() => 0), i = [];
  for (let r = 0; r < e; r++) {
    t.forEach((o, c) => {
      s[c] += o;
    });
    let a = 0;
    for (let o = 1; o < n.length; o++) s[o] > s[a] && (a = o);
    s[a] -= e, i.push(n[a]);
  }
  return i;
}
function os(n, t, e) {
  if (n.from !== null && n.from !== void 0 && t < n.from || n.until !== null && n.until !== void 0 && t >= n.until) return !1;
  const s = n.tags ?? [], i = e.screen?.tags ?? [];
  return s.length && !s.some((r) => i.includes(r)) ? !1 : et(n.when ?? "", e);
}
function ut(n, t, e, s, i, r = []) {
  const a = n.playlists[t];
  if (!a || r.includes(t) || r.length >= ns) return [];
  let o = [];
  const c = [];
  for (const l of a.items ?? []) {
    if (!os(l, s, e)) continue;
    let h = [];
    if (l.playlist) h = ut(n, l.playlist, e, s, i, [...r, t]);
    else if (l.layout && l.layout in n.layouts) {
      const d = l.duration || n.layouts[l.layout] || a.default || ss;
      h = [{ layout: l.layout, duration: d, item: l.id }];
    }
    h.length && (o.push(h), c.push(Math.max(1, Math.trunc(l.weight || 1))));
  }
  return a.mode === "weighted" ? o = as(o, c) : a.mode === "shuffle" && (o = rs(o, is(`${t}:${i}`))), o.flat();
}
function cs(n, t) {
  return (n[0] === null || n[0] <= t) && (n[1] === null || t < n[1]);
}
function ls(n, t) {
  const e = [];
  return n.entries.forEach((s, i) => {
    const r = s.windows.find((a) => cs(a, t));
    r && e.push({ key: [-s.priority, -(r[0] ?? -1), i], entry: s, w: r });
  }), e.sort((s, i) => s.key[0] - i.key[0] || s.key[1] - i.key[1] || s.key[2] - i.key[2]), e.map((s) => [s.entry, s.w]);
}
function hs(n, t, e, s, i) {
  const r = s.content, a = { entry: s.id, index: 0, count: 1, start: i[0], end: i[1] };
  if (r.message !== void 0) return r.message in (n.messages ?? {}) ? { ...a, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in n.layouts ? { ...a, layout: r.layout } : null;
  const o = r.playlist, c = i[0] ?? 0;
  let l = ut(n, o, t, e, 0);
  const h = l.reduce((m, b) => m + b.duration, 0);
  if (!h) return null;
  const d = Math.floor((e - c) / h);
  d && (l = ut(n, o, t, e, d));
  let u = e - c - d * h, p = c + d * h;
  for (let m = 0; m < l.length; m++) {
    const b = l[m];
    if (u < b.duration) {
      let g = p + b.duration;
      return i[1] !== null && (g = Math.min(g, i[1])), { ...a, layout: b.layout, item: b.item, index: m, count: l.length, start: p, end: g };
    }
    u -= b.duration, p += b.duration;
  }
  return null;
}
function ds(n, t, e) {
  for (const [s, i] of ls(n, e)) {
    const r = hs(n, t, e, s, i);
    if (r) return r;
  }
  return null;
}
function us(n, t, e) {
  const s = e?.end != null ? [e.end] : [];
  for (const i of n.entries)
    for (const [r, a] of i.windows)
      r !== null && r > t && s.push(r), a !== null && a > t && s.push(a);
  return s.length ? Math.min(...s) : null;
}
const fs = "evac-player-content-v1", ps = "content/theme/", ms = /url\("([^"]+)"\)/g;
async function Dt(n, t) {
  const e = await caches.open(fs).catch(() => null), s = await e?.match(n).catch(() => {
  });
  if (s) return s;
  const i = new AbortController(), r = setTimeout(() => i.abort(), 1e4);
  try {
    const a = await fetch(n, {
      headers: { Authorization: `Screen ${t}` },
      credentials: "omit",
      signal: i.signal
    });
    if (a.ok)
      return await e?.put(n, a.clone()), a;
  } catch {
  } finally {
    clearTimeout(r);
  }
  return null;
}
async function gs(n, t) {
  try {
    const e = await _(n, ps, { token: t });
    return e.theme && localStorage.setItem("evac.player.theme", JSON.stringify(e.theme)), e.theme;
  } catch {
    try {
      const e = localStorage.getItem("evac.player.theme");
      return e ? JSON.parse(e) : null;
    } catch {
      return null;
    }
  }
}
function ys(n) {
  const t = [];
  for (const e of n.match(/@font-face\{[^}]*\}/g) ?? []) {
    const s = /font-family:"([^"]+)"/.exec(e)?.[1], i = /src:url\("([^"]+)"\)/.exec(e)?.[1];
    !s || !i || t.push({
      family: s,
      url: i,
      weight: /font-weight:([^;]+);/.exec(e)?.[1] ?? "400",
      style: /font-style:([^;]+);/.exec(e)?.[1] ?? "normal",
      unicodeRange: /unicode-range:([^;]+);/.exec(e)?.[1]
    });
  }
  return t;
}
const Lt = [];
async function zt(n, t, e = document.documentElement) {
  const s = document.fonts;
  await Promise.all(ys(n.fonts_css).map(async (i) => {
    const r = await Dt(i.url, t);
    if (r)
      try {
        const a = new FontFace(i.family, await r.arrayBuffer(), {
          weight: i.weight,
          style: i.style,
          unicodeRange: i.unicodeRange
        });
        s.add(await a.load());
      } catch {
      }
  })), Lt.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, r] of Object.entries(n.variables)) {
    let a = r;
    for (const o of r.matchAll(ms)) {
      const c = await Dt(o[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        Lt.push(l), a = a.replace(o[1], l);
      }
    }
    e.style.setProperty(i, a);
  }
  e.dataset.theme = n.key || "default";
}
function vs(n = document) {
  const t = n.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, s = new URLSearchParams(n.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: s.get("mode") === "obs" ? "obs" : "screen"
  };
}
function N(n, t, e = {}) {
  let s = n.strings[t] ?? t;
  for (const [i, r] of Object.entries(e)) s = s.replace(`{${i}}`, String(r));
  return s;
}
function bs(n, t = location) {
  return n.ws ? n.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const K = [], Z = [], ws = Date.now(), Ss = 300;
let B = [], ft = null;
function $(n, t) {
  Z.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n.toUpperCase()} ${t}`.slice(0, 500)), Z.length > Ss && Z.shift();
}
function ks() {
  return [...Z];
}
function w(n) {
  K.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n}`.slice(0, 300)), K.length > 10 && K.shift(), $("error", n);
  const t = Date.now();
  B = B.filter((e) => t - e < 6e4), B.push(t), B.length >= 50 && ft && (B = [], ft());
}
function xs(n) {
  ft = n;
}
function Es(n = window) {
  n.addEventListener("error", (t) => w(t.message || "error")), n.addEventListener("unhandledrejection", (t) => w(String(t.reason)));
  for (const t of ["warn", "info"]) {
    const e = console[t].bind(console);
    console[t] = (...s) => {
      $(t, s.map(String).join(" ")), e(...s);
    };
  }
}
function Ot(n) {
  const t = window.innerWidth, e = window.innerHeight, s = performance.memory;
  return {
    version: n.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - ws) / 1e3),
    slide: n.slide,
    errors: [...K],
    memory: s ? Math.round(s.usedJSHeapSize / 1048576) : null,
    last_sync: n.lastSync ? new Date(n.lastSync).toISOString() : null,
    online: n.online,
    user_agent: navigator.userAgent,
    ...n.contentVersion ? { content_version: n.contentVersion } : {},
    ...n.displayState ? { display_state: n.displayState } : {},
    ...n.capture !== void 0 ? { capture: n.capture } : {},
    ...n.recovered ? { recovered: n.recovered } : {},
    ...n.evacAck ? { evac_ack: n.evacAck } : {}
  };
}
const ge = "evac.player.reloads", tt = "evac.player.alive", $s = 3, Cs = 10 * 6e4;
function ye(n) {
  try {
    return localStorage.getItem(n);
  } catch {
    return null;
  }
}
function nt(n, t) {
  try {
    t === null ? localStorage.removeItem(n) : localStorage.setItem(n, t);
  } catch {
  }
}
function As(n = Date.now()) {
  try {
    return JSON.parse(ye(ge) ?? "[]").filter((t) => n - t < Cs);
  } catch {
    return [];
  }
}
function X(n, t = {}) {
  const e = Date.now(), s = As(e);
  return !t.force && s.length >= $s ? (w(`reload (${n}) skipped: ${s.length} reloads in the last 10 minutes`), !1) : (nt(ge, JSON.stringify([...s, e])), $("info", `reload: ${n}`), ve(), (t.win ?? location).reload(), !0);
}
function Ms(n = Date.now()) {
  const t = ye(tt);
  if (nt(tt, String(n)), !t || t === "clean") return "";
  const e = Number(t);
  return Number.isFinite(e) ? `restarted after an unclean stop (last sign of life ${new Date(e).toISOString()})` : "";
}
function Ts(n = Date.now()) {
  nt(tt, String(n));
}
function ve() {
  nt(tt, "clean");
}
function _s(n = window) {
  n.addEventListener("pagehide", () => ve());
}
function Ns() {
  const n = performance.memory;
  return !!n && n.jsHeapSizeLimit > 0 && n.usedJSHeapSize / n.jsHeapSizeLimit > 0.85;
}
function be() {
  return typeof navigator < "u" && !!navigator.mediaDevices?.getDisplayMedia;
}
function Is(n, t, e) {
  return new Promise((s, i) => {
    const r = setTimeout(() => i(new Error(`${e} timed out`)), t);
    n.then((a) => {
      clearTimeout(r), s(a);
    }, (a) => {
      clearTimeout(r), i(a);
    });
  });
}
async function Ps(n = 1e4) {
  return Is(Ds(), n, "screen capture");
}
async function Ds() {
  if (!be()) throw new Error("screen capture is not available in this browser");
  const n = document.createElement("div");
  n.className = "evac-capture-dot", document.body.appendChild(n);
  let t = 0;
  const e = setInterval(() => n.classList.toggle("on", t++ % 2 === 0), 16);
  try {
    return await Ls();
  } finally {
    clearInterval(e), n.remove();
  }
}
async function Ls() {
  const n = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "browser" },
    audio: !1,
    preferCurrentTab: !0,
    selfBrowserSurface: "include"
  });
  try {
    const t = document.createElement("video");
    t.muted = !0, t.srcObject = n, await t.play(), t.videoWidth || await new Promise((s) => t.addEventListener("loadeddata", s, { once: !0 }));
    const e = document.createElement("canvas");
    return e.width = t.videoWidth || window.innerWidth, e.height = t.videoHeight || window.innerHeight, e.getContext("2d")?.drawImage(t, 0, 0, e.width, e.height), t.srcObject = null, await new Promise((s, i) => e.toBlob((r) => r ? s(r) : i(new Error("encoding failed")), "image/jpeg", 0.85));
  } finally {
    n.getTracks().forEach((t) => t.stop());
  }
}
async function at(n, t, e, s) {
  const i = typeof Blob < "u" && s instanceof Blob;
  await fetch(`${n}upload/${e}/`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Screen ${t}`, "Content-Type": i ? s.type : "application/json" },
    body: i ? s : JSON.stringify(s)
  });
}
const zs = /* @__PURE__ */ new Set(["evac.player.token", "evac.player.evac", "evac.player.evacbundle", "evac.player.evacseq"]);
async function Os() {
  try {
    if (typeof caches < "u") for (const n of await caches.keys()) await caches.delete(n);
  } catch {
  }
  try {
    for (const n of Object.keys(localStorage))
      n.startsWith("evac.player.") && !zs.has(n) && localStorage.removeItem(n);
  } catch {
  }
  try {
    for (const n of await navigator.serviceWorker?.getRegistrations?.() ?? []) await n.unregister();
  } catch {
  }
}
function Rt(n, t) {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: t || void 0
    }).format(new Date(n));
  } catch {
    return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(n));
  }
}
function Bt(n, t, e) {
  return !t || !e || t === e ? !1 : t < e ? n >= t && n < e : n >= t || n < e;
}
function Rs(n, t) {
  return Bt(t, n.sleep_from, n.sleep_until) ? "sleeping" : Bt(t, n.dim_from, n.dim_until) ? "dimmed" : "on";
}
function Bs(n) {
  const t = Number(n.rotation ?? 0) || 0, e = t === 90 || t === 270, s = ["translate(-50%, -50%)"];
  t && s.push(`rotate(${t}deg)`), (n.keystone_x || n.keystone_y) && (s.push("perspective(1200px)"), n.keystone_y && s.push(`rotateX(${n.keystone_y}deg)`), n.keystone_x && s.push(`rotateY(${n.keystone_x}deg)`));
  const i = (n.scale ?? 100) / 100;
  i !== 1 && s.push(`scale(${i})`);
  const r = Math.max(0, Math.min(15, n.overscan ?? 0));
  return {
    width: e ? "100vh" : "100vw",
    height: e ? "100vw" : "100vh",
    transform: s.join(" "),
    overscan: `${r}%`
  };
}
function ot(n, t) {
  const e = Bs(t);
  n.classList.add("evac-root"), n.style.width = e.width, n.style.height = e.height, n.style.transform = e.transform, n.style.setProperty("--evac-overscan", e.overscan);
}
function Fs(n, t, e = document) {
  let s = e.getElementById("evac-dim");
  if (n === "on") {
    s?.remove();
    return;
  }
  s || (s = e.createElement("div"), s.id = "evac-dim", s.setAttribute("aria-hidden", "true"), e.body.appendChild(s));
  const i = n === "sleeping" ? 0 : Math.max(10, Math.min(90, t.dim_level ?? 40));
  s.style.opacity = String(1 - i / 100), s.dataset.state = n;
}
const pt = "evac.player.token", Ct = "evac.player.config";
function Ws() {
  try {
    return localStorage.getItem(pt);
  } catch {
    return null;
  }
}
function Ft(n) {
  try {
    n ? localStorage.setItem(pt, n) : (localStorage.removeItem(pt), localStorage.removeItem(Ct));
  } catch {
  }
}
function js() {
  try {
    const n = localStorage.getItem(Ct);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function Wt(n) {
  try {
    localStorage.setItem(Ct, JSON.stringify(n));
  } catch {
  }
}
const I = (1n << 64n) - 1n, Hs = [
  "428a2f98d728ae22",
  "7137449123ef65cd",
  "b5c0fbcfec4d3b2f",
  "e9b5dba58189dbbc",
  "3956c25bf348b538",
  "59f111f1b605d019",
  "923f82a4af194f9b",
  "ab1c5ed5da6d8118",
  "d807aa98a3030242",
  "12835b0145706fbe",
  "243185be4ee4b28c",
  "550c7dc3d5ffb4e2",
  "72be5d74f27b896f",
  "80deb1fe3b1696b1",
  "9bdc06a725c71235",
  "c19bf174cf692694",
  "e49b69c19ef14ad2",
  "efbe4786384f25e3",
  "0fc19dc68b8cd5b5",
  "240ca1cc77ac9c65",
  "2de92c6f592b0275",
  "4a7484aa6ea6e483",
  "5cb0a9dcbd41fbd4",
  "76f988da831153b5",
  "983e5152ee66dfab",
  "a831c66d2db43210",
  "b00327c898fb213f",
  "bf597fc7beef0ee4",
  "c6e00bf33da88fc2",
  "d5a79147930aa725",
  "06ca6351e003826f",
  "142929670a0e6e70",
  "27b70a8546d22ffc",
  "2e1b21385c26c926",
  "4d2c6dfc5ac42aed",
  "53380d139d95b3df",
  "650a73548baf63de",
  "766a0abb3c77b2a8",
  "81c2c92e47edaee6",
  "92722c851482353b",
  "a2bfe8a14cf10364",
  "a81a664bbc423001",
  "c24b8b70d0f89791",
  "c76c51a30654be30",
  "d192e819d6ef5218",
  "d69906245565a910",
  "f40e35855771202a",
  "106aa07032bbd1b8",
  "19a4c116b8d2d0c8",
  "1e376c085141ab53",
  "2748774cdf8eeb99",
  "34b0bcb5e19b48a8",
  "391c0cb3c5c95a63",
  "4ed8aa4ae3418acb",
  "5b9cca4f7763e373",
  "682e6ff3d6b2b8a3",
  "748f82ee5defb2fc",
  "78a5636f43172f60",
  "84c87814a1f0ab72",
  "8cc702081a6439ec",
  "90befffa23631e28",
  "a4506cebde82bde9",
  "bef9a3f7b2c67915",
  "c67178f2e372532b",
  "ca273eceea26619c",
  "d186b8c721c0c207",
  "eada7dd6cde0eb1e",
  "f57d4f7fee6ed178",
  "06f067aa72176fba",
  "0a637dc5a2c898a6",
  "113f9804bef90dae",
  "1b710b35131c471b",
  "28db77f523047d84",
  "32caab7b40c72493",
  "3c9ebe0a15c9bebc",
  "431d67c49c100d4c",
  "4cc5d4becb3e42b6",
  "597f299cfc657e2a",
  "5fcb6fab3ad6faec",
  "6c44198c4a475817"
].map((n) => BigInt(`0x${n}`)), qs = [
  "6a09e667f3bcc908",
  "bb67ae8584caa73b",
  "3c6ef372fe94f82b",
  "a54ff53a5f1d36f1",
  "510e527fade682d1",
  "9b05688c2b3e6c1f",
  "1f83d9abfb41bd6b",
  "5be0cd19137e2179"
].map((n) => BigInt(`0x${n}`)), A = (n, t) => (n >> t | n << 64n - t) & I;
function Us(n) {
  const t = BigInt(n.length) * 8n, e = n.length + 17 + 127 & -128, s = new Uint8Array(e);
  s.set(n), s[n.length] = 128;
  for (let o = 0; o < 16; o++) s[e - 1 - o] = Number(t >> BigInt(8 * o) & 0xffn);
  const i = [...qs], r = new Array(80);
  for (let o = 0; o < e; o += 128) {
    for (let g = 0; g < 16; g++) {
      let k = 0n;
      for (let D = 0; D < 8; D++) k = k << 8n | BigInt(s[o + g * 8 + D]);
      r[g] = k;
    }
    for (let g = 16; g < 80; g++) {
      const k = A(r[g - 15], 1n) ^ A(r[g - 15], 8n) ^ r[g - 15] >> 7n, D = A(r[g - 2], 19n) ^ A(r[g - 2], 61n) ^ r[g - 2] >> 6n;
      r[g] = r[g - 16] + k + r[g - 7] + D & I;
    }
    let [c, l, h, d, u, p, m, b] = i;
    for (let g = 0; g < 80; g++) {
      const k = A(u, 14n) ^ A(u, 18n) ^ A(u, 41n), D = u & p ^ ~u & I & m, At = b + k + D + Hs[g] + r[g] & I, ke = A(c, 28n) ^ A(c, 34n) ^ A(c, 39n), xe = c & l ^ c & h ^ l & h, Ee = ke + xe & I;
      b = m, m = p, p = u, u = d + At & I, d = h, h = l, l = c, c = At + Ee & I;
    }
    [c, l, h, d, u, p, m, b].forEach((g, k) => {
      i[k] = i[k] + g & I;
    });
  }
  const a = new Uint8Array(64);
  return i.forEach((o, c) => {
    for (let l = 0; l < 8; l++) a[c * 8 + l] = Number(o >> BigInt(56 - 8 * l) & 0xffn);
  }), a;
}
const P = (1n << 255n) - 19n, jt = (1n << 252n) + 27742317777372353535851937790883648493n, v = (n, t = P) => {
  const e = n % t;
  return e >= 0n ? e : e + t;
};
function F(n, t, e = P) {
  let s = 1n;
  for (n = v(n, e); t > 0n; )
    t & 1n && (s = s * n % e), n = n * n % e, t >>= 1n;
  return s;
}
const we = (n) => F(n, P - 2n), Se = v(-121665n * we(121666n)), Vs = F(2n, (P - 1n) / 4n), Js = [0n, 1n, 1n, 0n];
function mt(n, t) {
  const [e, s, i, r] = n, [a, o, c, l] = t, h = v((s - e) * (o - a)), d = v((s + e) * (o + a)), u = v(2n * Se * r * l), p = v(2n * i * c), m = d - h, b = p - u, g = p + u, k = d + h;
  return [v(m * b), v(g * k), v(b * g), v(m * k)];
}
function Ht(n, t) {
  let e = Js, s = n;
  for (; t > 0n; )
    t & 1n && (e = mt(e, s)), s = mt(s, s), t >>= 1n;
  return e;
}
const gt = (n) => n.reduceRight((t, e) => t << 8n | BigInt(e), 0n);
function yt(n) {
  if (n.length !== 32) return null;
  const t = (n[31] & 128) !== 0, e = n.slice();
  e[31] &= 127;
  const s = gt(e);
  if (s >= P) return null;
  const i = v(s * s), r = v(i - 1n), a = v(Se * i + 1n);
  let o = v(r * F(a, 3n) * F(r * F(a, 7n), (P - 5n) / 8n));
  const c = v(a * o * o);
  if (c === v(-r)) o = v(o * Vs);
  else if (c !== r) return null;
  return o === 0n && t ? null : ((o & 1n) === 1n ? t || (o = P - o) : t && (o = P - o), [o, s, 1n, v(o * s)]);
}
function qt(n) {
  const t = we(n[2]), e = v(n[0] * t), s = v(n[1] * t), i = new Uint8Array(32);
  let r = s;
  for (let a = 0; a < 32; a++)
    i[a] = Number(r & 0xffn), r >>= 8n;
  return e & 1n && (i[31] |= 128), i;
}
const Gs = yt(Uint8Array.from([88, ...new Array(31).fill(102)]));
function Ys(n, t, e) {
  if (e.length !== 64 || n.length !== 32) return !1;
  const s = yt(n), i = yt(e.slice(0, 32)), r = gt(e.slice(32));
  if (!s || !i || r >= jt) return !1;
  const a = Us(Uint8Array.from([...e.slice(0, 32), ...n, ...t])), o = v(gt(a), jt), c = qt(Ht(Gs, r)), l = qt(mt(i, Ht(s, o)));
  return c.every((h, d) => h === l[d]);
}
function Ut(n) {
  const t = n.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((n.length + 3) % 4), e = atob(t);
  return Uint8Array.from(e, (s) => s.charCodeAt(0));
}
function Ks(n, t) {
  if (!t || typeof t.m != "string" || typeof t.s != "string") return null;
  const e = new TextEncoder().encode(t.m);
  for (const s of n)
    try {
      if (Ys(Ut(s), e, Ut(t.s))) return JSON.parse(t.m);
    } catch {
    }
  return null;
}
const Zs = ["staff_alert", "attention", "shelter_in_place", "evacuate"], Xs = {
  normal: 0,
  all_clear: 1,
  staff_alert: 2,
  attention: 3,
  shelter_in_place: 4,
  evacuate: 5
}, Qs = 10 * 6e4, Vt = "evac.player.evac", Jt = "evac.player.evacbundle", vt = (n) => Zs.includes(n);
function bt(n, t) {
  return n.state === "all_clear" && n.clear_until && Date.parse(n.clear_until) <= t ? "normal" : n.state;
}
function ti(n, t, e) {
  if (!n) return !0;
  if (t.seq < n.seq || t.seq === n.seq && t.v === n.v) return !1;
  if (!vt(t.state) && vt(bt(n, e))) {
    const i = t.issued ?? (t.sig ? Number(JSON.parse(t.sig.m).ia) * 1e3 : e);
    if (e - i > Qs) return !1;
  }
  return !0;
}
function ei(n, t) {
  const e = n.map((a) => a.st === "all_clear" && a.cu && a.cu <= t ? { st: "normal", d: !1 } : a), s = e.some((a) => vt(a.st) && !a.d);
  let i = { st: "normal", d: !1 };
  const r = (a) => [Xs[a.st] ?? 0, a.d ? 0 : 1];
  for (const a of s ? e.filter((o) => !o.d) : e) {
    const [o, c] = r(a), [l, h] = r(i);
    (o > l || o === l && c > h) && (i = a);
  }
  return i;
}
function ni(n, t, e) {
  const s = Ks(t.keys, n);
  if (!s || s.e !== t.event || typeof s.seq != "number" || !s.ev || typeof s.ev.st != "string")
    return null;
  const i = ei([s.ev, ...t.zones.map((c) => s.z?.[c]).filter((c) => !!c)], e), r = t.stages[i.st], a = t.directions[(s.b ?? []).slice().sort().join(",")], o = [s.ev, ...Object.values(s.z ?? {})].find((c) => c.st === i.st && c.cu);
  return {
    event: t.event,
    screen: t.screen,
    seq: s.seq,
    v: `fb-${s.seq}-${i.st}-${i.d}`,
    state: i.st,
    label: t.labels[i.st] ?? r?.label ?? i.st,
    drill: i.d,
    drill_text: t.drill_text,
    since: null,
    clear_until: o?.cu ? new Date(o.cu).toISOString() : null,
    takeover: r?.takeover ?? !1,
    role: t.role,
    model: t.model,
    guidance: a ? { kind: a.kind, arrow: a.arrow, text: a.text, target: a.target } : { kind: t.model === "zones" ? "follow_staff" : "none", arrow: null, text: "", target: "" },
    direction: a?.direction ?? "",
    texts: r?.texts ?? [],
    rotate_seconds: r?.rotate_seconds ?? 8,
    pictograms_only: r?.pictograms_only ?? !1,
    sound: r?.sound ?? "none",
    sound_every: r?.sound_every ?? 30,
    speech: r?.speech ?? "",
    layout: r?.layout ?? null,
    issued: s.ia * 1e3,
    sig: n,
    via: "fallback"
  };
}
function Gt(n) {
  const t = n.texts.length ? [...n.texts] : [""];
  return n.pictograms_only && n.texts.length && t.push(""), t;
}
function Yt(n, t) {
  return n === "evacuate" ? t && ["left", "back_left", "ahead_left"].includes(t) ? "E001" : "E002" : n === "all_clear" ? "check" : "W001";
}
function Kt(n) {
  try {
    const t = localStorage.getItem(n);
    return t ? JSON.parse(t) : null;
  } catch {
    return null;
  }
}
function Zt(n, t) {
  try {
    localStorage.setItem(n, JSON.stringify(t));
  } catch {
  }
}
class si {
  constructor(t, e = document) {
    this.opts = t, this.payload = Kt(Vt), this.bundle = Kt(Jt), this.rendered = null, this.rotation = null, this.sound = null, this.expiry = null, this.frame = 0, this.shownKey = "", this.layer = e.createElement("div"), this.layer.id = "evac-layer", this.layer.hidden = !0, e.body.appendChild(this.layer);
  }
  t(t) {
    return this.opts.strings[t] ?? t;
  }
  setBundle(t) {
    t && (this.bundle = t, Zt(Jt, t));
  }
  /** Offer a payload from any path; returns whether it was taken. */
  offer(t, e) {
    return !t || this.bundle && t.event !== this.bundle.event && this.payload && t.event !== this.payload.event || e === "fallback" && !t.sig || !ti(this.payload, t, this.opts.now()) ? !1 : (this.payload = { ...t, via: e }, Zt(Vt, this.payload), this.render(!0), !0);
  }
  /** A signed event-wide message from a fallback origin. */
  offerFallback(t) {
    if (!this.bundle) return !1;
    const e = ni(t, this.bundle, this.opts.now());
    return e ? this.offer(e, "fallback") : !1;
  }
  /** Whether the screen is taken over (normal content is hidden). */
  get active() {
    const t = this.payload;
    if (!t) return !1;
    const e = bt(t, this.opts.now());
    return t.role === "participant" && t.takeover && e !== "normal";
  }
  /** Draw the current payload. ``force`` redraws even when nothing visible changed (a new message). */
  render(t = !1) {
    const e = this.payload, s = this.opts.now(), i = e ? bt(e, s) : "normal", r = e?.role ?? "participant", o = !!e && r !== "excluded" && i !== "normal" && i !== "staff_alert" ? e.takeover && r === "participant" ? "takeover" : "banner" : "none", c = `${o}|${e?.seq}|${e?.v}|${i}`;
    if (!t && c === this.shownKey || (this.shownKey = c, this.stop(), this.layer.replaceChildren(), this.layer.hidden = o === "none", this.layer.dataset.mode = o, this.layer.dataset.state = i, document.documentElement.classList.toggle("evac-active", o === "takeover"), this.opts.onChange?.(o === "takeover"), !e)) return;
    if (e.state === "all_clear" && e.clear_until) {
      const h = Date.parse(e.clear_until) - s;
      h > 0 && (this.expiry = setTimeout(() => this.render(!0), Math.min(h + 50, 2147e6)));
    }
    let l = !1;
    o === "takeover" ? l = this.drawTakeover(e, i) : o === "banner" && this.drawBanner(e, i), o !== "none" && e.drill && this.drawDrill(e), o !== "none" && this.startAudio(e), this.opts.onRendered(e, { fallback: l, rendered_at: this.opts.now() });
  }
  vars(t, e) {
    return {
      ...this.opts.context().vars,
      evac: {
        stage: t.label,
        state: t.state,
        text: e,
        direction: t.direction || this.followStaff(t),
        target: t.guidance.target,
        arrow: t.guidance.arrow,
        drill: t.drill ? t.drill_text : ""
      }
    };
  }
  followStaff(t) {
    return t.guidance.kind === "follow_staff" && t.state === "evacuate" ? this.t("Follow the instructions of the staff") : "";
  }
  drawTakeover(t, e) {
    const s = document.createElement("div");
    s.className = `evac-takeover evac-stage-${e}`, this.layer.append(s);
    const i = Gt(t), r = () => {
      const o = i[this.frame % i.length];
      if (t.layout) {
        let c = !1;
        try {
          this.rendered?.destroy(), s.replaceChildren();
          const l = this.opts.context();
          this.rendered = fe(s, t.layout, {
            ...l,
            vars: this.vars(t, o),
            onError: (h, d) => {
              c = !0, l.onError?.(h, d);
            }
          });
        } catch {
          c = !0;
        }
        if (!c) return !1;
        this.rendered?.destroy(), this.rendered = null;
      }
      return s.replaceChildren(this.fallbackLayout(t, e, o)), !0;
    }, a = r();
    return i.length > 1 && (this.rotation = setInterval(
      () => {
        this.frame += 1, r();
      },
      Math.max(3, t.rotate_seconds || 8) * 1e3
    )), a;
  }
  /** The built-in layout every screen keeps in its code: sign(s), stage, text, direction. */
  fallbackLayout(t, e, s) {
    const i = document.createElement("div");
    i.className = `evac-fb evac-fb-${e}`;
    const r = document.createElement("div");
    r.className = "evac-fb-signs";
    const a = t.guidance.arrow, o = Yt(e, a);
    r.innerHTML = (o === "check" ? Ye() : G(o, "ahead")) + (e === "evacuate" && a ? G("arrow", a) : "");
    const c = document.createElement("h1");
    if (c.className = "evac-fb-label", c.textContent = t.label, i.append(r, c), s) {
      const h = document.createElement("p");
      h.className = "evac-fb-text", h.textContent = s, i.append(h);
    }
    const l = t.direction || this.followStaff(t);
    if (l && e === "evacuate") {
      const h = document.createElement("p");
      h.className = "evac-fb-dir", h.textContent = l, i.append(h);
    }
    return i;
  }
  drawBanner(t, e) {
    const s = document.createElement("div");
    s.className = `evac-banner evac-stage-${e}`, s.setAttribute("role", "alert");
    const i = Gt(t).filter(Boolean), r = document.createElement("span");
    r.className = "evac-banner-icon", r.innerHTML = G(e === "evacuate" ? Yt(e, t.guidance.arrow) : "W001");
    const a = document.createElement("strong");
    a.textContent = t.label;
    const o = document.createElement("span");
    o.className = "evac-banner-text", o.textContent = i[0] ?? "", s.append(r, a, o), this.layer.append(s), i.length > 1 && (this.rotation = setInterval(
      () => {
        this.frame += 1, o.textContent = i[this.frame % i.length];
      },
      Math.max(3, t.rotate_seconds || 8) * 1e3
    ));
  }
  drawDrill(t) {
    const e = document.createElement("div");
    e.className = "evac-drill", e.textContent = t.drill_text || "DRILL", this.layer.append(e);
  }
  startAudio(t) {
    const e = this.opts.audio();
    if (!e.enabled || t.role !== "participant") return;
    const s = (r) => {
      t.sound && t.sound !== "none" && ii(t.sound, e.volume), t.speech && this.opts.speaker.say(`evac:${t.seq}:${t.v}:${r}`, t.speech, {
        volume: e.volume,
        delayMs: t.sound !== "none" ? 2600 : 0
      });
    };
    if ((!t.sound || t.sound === "none") && !t.speech) return;
    let i = 0;
    s(i), this.sound = setInterval(() => s(++i), Math.max(5, t.sound_every || 30) * 1e3);
  }
  stop() {
    this.rotation && clearInterval(this.rotation), this.sound && clearInterval(this.sound), this.expiry && clearTimeout(this.expiry), this.rotation = this.sound = this.expiry = null, this.rendered?.destroy(), this.rendered = null, this.frame = 0;
  }
}
function ii(n, t = 100) {
  if (n !== "siren") return me(n, t);
  if (typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const s = e.createGain();
  s.gain.value = Math.max(0, Math.min(1, t / 100)) * 0.35, s.connect(e.destination);
  for (let i = 0; i < 3; i++) {
    const r = e.createOscillator();
    r.type = "sawtooth";
    const a = e.currentTime + i * 0.8;
    r.frequency.setValueAtTime(500, a), r.frequency.linearRampToValueAtTime(1100, a + 0.7), r.connect(s), r.start(a), r.stop(a + 0.75);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, 3e3);
}
const Xt = 3e3;
function U(n) {
  document.documentElement.dataset.boot = n;
}
const Qt = 6e4, ri = 36e5, ai = 3e5, te = 15e3, oi = 6e4, ci = 3e3;
class li {
  constructor(t, e) {
    this.env = t, this.root = e, this.clock = new Te(), this.speaker = new Zn(), this.widgetData = new Dn(Qn()), this.dataRefresher = null, this.overlays = new Kn(this.speaker), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.program = null, this.shown = "", this.timer = null, this.refresher = null, this.housekeeping = null, this.displayState = "on", this.recovered = "", this.lastTick = Date.now(), this.reloadAtNextSlide = "", this.lastDailyReload = "", this.evac = null, this.evacAck = "", this.evacTimer = null, this.fallbackTimer = null, this.display = new Bn(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    U("boot"), this.recovered = Ms(), $("info", `player ${this.env.version} started (${navigator.userAgent})`), this.recovered && $("warn", this.recovered);
    const t = Ws();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: N(this.env, "pair_title"),
      step1: N(this.env, "pair_step1"),
      step2: N(this.env, "pair_step2"),
      waiting: N(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await Ae(this.env.api, Ot({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (i) {
      w(String(i)), this.display.message(N(this.env, "no_server"), N(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const s = async () => {
      try {
        const i = await Me(this.env.api, e);
        if (i.status === "paired")
          return Ft(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        w(String(i));
      }
      setTimeout(() => {
        s();
      }, Xt);
    };
    setTimeout(() => {
      s();
    }, Xt);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = js();
    this.evac = this.evac ?? this.makeEvac(t), e && ot(this.evac.layer, e.display ?? {}), this.evac.render(!0), U(e ? "play: cached config" : "play: no cached config"), e && (this.config = e, this.bundle = ht(), this.program = dt(), this.applySettings(), this.bundle && zt({ ...this.bundle.theme, fonts_css: this.bundle.fonts_css }, t).catch((s) => w(String(s))), this.show(), U("play: shown from cache"));
    try {
      const s = Date.now();
      this.config = await Mt(this.env.api, t), this.clock.add(s, Date.now(), this.config.server_time), this.lastSync = Date.now(), Wt(this.config);
    } catch (s) {
      if (s instanceof E) return this.unpair();
      w(String(s)), this.config = e;
    }
    this.applySettings(), this.bundle = this.bundle ?? ht(), this.program = this.program ?? dt(), await this.loadContent(t), await this.loadProgram(t), this.show(), this.loadEvac(t), this.evacTimer = setInterval(() => {
      this.loadEvac(t);
    }, oi), this.fallbackTimer = setInterval(() => {
      this.pollFallback();
    }, ci), U("play: online"), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, ri), this.loadWidgetData(t), this.dataRefresher = setInterval(() => {
      this.loadWidgetData(t);
    }, ai), this.housekeeping = setInterval(() => this.tick(), te), this.conn = new Ie({
      api: this.env.api,
      ws: bs(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => Ot({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline",
        displayState: this.displayState,
        capture: be(),
        recovered: this.recovered,
        evacAck: this.evacAck
      }),
      onMessage: (s) => {
        this.handle(s, t);
      },
      onTransport: (s) => {
        s !== this.transport && ($("info", `connection: ${s}`), (this.transport === "offline" || this.transport === "connecting") && this.loadEvac(t)), this.transport = s;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (s) => {
        this.lastSync = s;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch ($("info", `message: ${t.type}`), t.type) {
      case "config.changed":
        try {
          this.config = await Mt(this.env.api, e), Wt(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), this.applySettings();
          const s = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(e), await this.loadProgram(e), (`${this.bundle?.version}/${this.program?.version}` !== s || this.slide === "idle") && (this.shown = "", this.show());
        } catch (s) {
          s instanceof E && this.unpair();
        }
        break;
      case "identify": {
        const s = this.config?.screen.name ?? "", i = [this.config?.screen.venue, this.config?.screen.zone, this.config?.screen.room].filter(Boolean).join(" · ");
        this.display.identify(
          s,
          `${i}${i ? " · " : ""}${this.transport}`,
          Number(t.data.seconds) || 10
        );
        break;
      }
      case "program.changed": {
        const s = this.program?.version;
        await this.loadProgram(e), this.program?.version !== s && (this.shown = "", this.show());
        break;
      }
      case "data.changed":
        await this.loadWidgetData(e);
        break;
      case "evac.state":
        this.evac?.offer(t.data, this.transport);
        break;
      case "evac.bundle":
        this.loadEvac(e);
        break;
      case "reload":
        X("requested by staff", { force: !0 });
        break;
      case "clear_cache":
        await Os(), X("cache cleared by staff", { force: !0 });
        break;
      case "test_pattern": {
        const s = this.config?.screen.name ?? "", i = `${Math.round(innerWidth * devicePixelRatio)}×${Math.round(innerHeight * devicePixelRatio)}`;
        this.display.testPattern(
          s,
          [`${i} · DPR ${devicePixelRatio}`, `${this.env.version} · ${this.transport}`],
          Number(t.data.seconds) || 30
        );
        break;
      }
      case "screenshot":
        try {
          await at(this.env.api, e, "screenshot", await Ps());
        } catch (s) {
          w(`screenshot: ${String(s)}`), await at(this.env.api, e, "screenshot", { error: String(s).slice(0, 280) }).catch(() => {
          });
        }
        break;
      case "logs":
        await at(this.env.api, e, "logs", { lines: ks() }).catch((s) => w(String(s)));
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await Fn(this.env.api, t) ?? this.bundle;
    } catch (s) {
      if (s instanceof E) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await gs(this.env.api, t);
    e && await zt(e, t).catch((s) => w(String(s))), this.bundle && Hn(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await qn(this.env.api, t);
    } catch (s) {
      s instanceof E && this.unpair();
    }
    const e = [...this.program?.entries ?? [], ...this.program?.overlays ?? []].map((s) => s.speech).filter((s) => !!s);
    e.length && Xn(e);
  }
  /** Custom widget rows: "data" elements redraw themselves when the store changes. */
  async loadWidgetData(t) {
    try {
      await ts(this.env.api, t, this.widgetData);
    } catch (e) {
      e instanceof E && this.unpair();
    }
  }
  // ---------------------------------------------------------------- evacuation (ADR-0033/0034)
  makeEvac(t) {
    return new si({
      now: () => this.clock.now(),
      speaker: this.speaker,
      audio: () => ({ enabled: this.config?.display?.audio !== !1, volume: this.config?.display?.volume ?? 100 }),
      strings: this.env.strings,
      context: () => ({
        vars: this.config ? this.vars() : {},
        now: () => this.clock.now(),
        timezone: this.config?.event.timezone,
        assets: this.bundle?.assets ?? {},
        fonts: this.bundle?.fonts ?? {},
        nonce: Nt(),
        data: this.widgetData,
        onError: (e, s) => w(`evac ${e}: ${String(s)}`)
      }),
      onRendered: (e, s) => {
        this.evacAck = `${e.seq}:${e.v}`.slice(0, 40), $("info", `evacuation: ${e.state}${e.drill ? " (drill)" : ""} #${e.seq} via ${e.via ?? "cache"}`), fetch(`${this.env.api}evacuation/ack/`, {
          method: "POST",
          headers: { Authorization: `Screen ${t}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            seq: e.seq,
            v: e.v,
            state: e.state,
            drill: e.drill,
            rendered_at: s.rendered_at,
            issued: e.issued ?? null,
            via: e.via ?? "cache",
            fallback: s.fallback
          })
        }).catch(() => {
        });
      },
      onChange: () => {
        this.updateDisplayState(), this.shown = "", this.show();
      }
    });
  }
  async loadEvac(t) {
    try {
      const e = await fetch(`${this.env.api}evacuation/state/`, { headers: { Authorization: `Screen ${t}` } });
      if (e.status === 401) return this.unpair();
      if (!e.ok) return;
      const s = await e.json();
      if (!s.enabled) return;
      this.evac?.setBundle(s.bundle ?? null), this.evac?.offer(s.payload, "fetch");
    } catch {
    }
  }
  /** Without a connection, ask the fallback origins (secondary node, bridge) for the signed alarm state. */
  async pollFallback() {
    const t = this.evac?.bundle;
    if (!(this.transport !== "offline" || !t?.fallback_origins.length))
      for (const e of t.fallback_origins)
        try {
          const s = await fetch(`${e}/evac/${t.event}/state`, { cache: "no-store" });
          if (!s.ok) continue;
          const i = await s.json();
          if (i.sig && this.evac?.offerFallback(i.sig)) return;
        } catch {
        }
  }
  vars() {
    const t = this.config, e = t.screen;
    return { event: t.event, screen: {
      name: e.name,
      zone: e.zone ?? "",
      room: e.room ?? "",
      venue: e.venue ?? "",
      tags: e.tags,
      groups: e.groups.map((s) => s.name)
    } };
  }
  /** Show what the program says for now (or the default layout without one) and wake up at the next change. */
  show() {
    this.timer && clearTimeout(this.timer), this.timer = null;
    const t = this.config;
    if (!t) {
      this.slide = "error", this.display.message(N(this.env, "no_server"), N(this.env, "retrying"));
      return;
    }
    const e = this.clock.now();
    let s = null, i, r = "idle", a = null;
    if (this.program && this.bundle) {
      if (a = ds(this.program, this.vars(), e), a?.message)
        s = this.program.messages?.[a.message] ?? null, r = `${a.entry}|message`, this.slide = `${a.entry} message`;
      else if (a?.layout) {
        const p = this.bundle.layouts.find((m) => m.id === a?.layout);
        p && (s = p.data, i = p.variables, r = `${a.entry}|${p.id}|${p.version}|${a.count > 1 ? a.start : ""}`, this.slide = `${p.key} v${p.version} (${a.entry} ${a.index + 1}/${a.count})`);
      }
      const d = [us(this.program, e, a), Jn(this.program.overlays, e)].filter((p) => p !== null), u = Math.max(5, Math.min(Qt, (d.length ? Math.min(...d) : e + Qt) - e));
      this.timer = setTimeout(() => this.show(), u);
    } else {
      const d = jn(this.bundle);
      d && (s = d.data, i = d.variables, r = `default|${d.id}|${d.version}`, this.slide = `${d.key} v${d.version}`);
    }
    const o = { enabled: t.display?.audio !== !1, volume: t.display?.volume ?? 100 }, c = !!this.evac?.active, l = c || !!a && (a.entry.startsWith("announcement:") || a.entry.startsWith("evacuation"));
    this.overlays.update(this.program?.overlays, e, { hidden: l, audio: o });
    const h = a ? this.program?.entries.find((d) => d.id === a?.entry) : void 0;
    if (h?.speech && o.enabled && !c && this.speaker.say(`${h.id}@${a?.start ?? 0}`, h.speech, {
      volume: o.volume,
      delayMs: pe
    }), r !== this.shown && !(this.reloadAtNextSlide && this.shown && X(this.reloadAtNextSlide))) {
      this.reloadAtNextSlide = "", this.shown = r, $("info", `showing ${this.slide}`);
      try {
        if (!s || !this.bundle) throw new Error("nothing to show");
        this.display.layout(s, {
          vars: this.vars(),
          now: () => this.clock.now(),
          timezone: t.event.timezone,
          assets: this.bundle.assets,
          fonts: this.bundle.fonts,
          reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
          audio: o,
          nonce: Nt(),
          data: this.widgetData,
          onError: (d, u) => w(`${d}: ${String(u)}`),
          onLog: (d, u) => $("info", `${d}: ${u}`)
        }, i);
      } catch (d) {
        s && w(`render failed, showing the idle slide: ${String(d)}`), this.slide = "idle", this.display.idle(t);
      }
      this.overlays.attach(this.root);
    }
  }
  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  applySettings() {
    const t = this.config?.display ?? {};
    ot(this.root, t), this.evac && ot(this.evac.layer, t), this.updateDisplayState();
  }
  updateDisplayState() {
    const t = this.config?.display ?? {}, e = this.evac?.active ? "on" : Rs(t, Rt(this.clock.now(), this.config?.event.timezone));
    e !== this.displayState && $("info", `display ${e}`), this.displayState = e, Fs(e, t);
  }
  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  tick() {
    const t = Date.now(), e = t - this.lastTick > te * 3;
    this.lastTick = t, Ts(t), this.updateDisplayState(), e && ($("warn", "timers were stalled; resynchronising"), this.shown = "", this.show());
    const s = this.config?.display?.daily_reload, i = Rt(this.clock.now(), this.config?.event.timezone);
    s && i === s && this.lastDailyReload !== i && performance.now() > 36e5 && (this.lastDailyReload = i, this.reloadAtNextSlide = "daily reload"), Ns() && !this.reloadAtNextSlide && (this.reloadAtNextSlide = "memory pressure");
  }
  unpair() {
    this.housekeeping && clearInterval(this.housekeeping), this.housekeeping = null, this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.dataRefresher && clearInterval(this.dataRefresher), this.evacTimer && clearInterval(this.evacTimer), this.fallbackTimer && clearInterval(this.fallbackTimer), this.timer = this.refresher = this.dataRefresher = this.evacTimer = this.fallbackTimer = null, es(), this.widgetData.set({}), Un(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, Ft(null), Wn(), this.pair();
  }
}
function hi() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((n) => w(String(n)));
}
if (typeof document < "u" && document.getElementById("player")) {
  Es(), _s(), xs(() => X("50 errors within a minute")), hi();
  const n = vs();
  new li(n, document.getElementById("player")).boot();
}
export {
  li as Player
};
