// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var Te = Object.defineProperty;
var _e = (s, t, e) => t in s ? Te(s, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : s[t] = e;
var z = (s, t, e) => _e(s, typeof t != "symbol" ? t + "" : t, e);
class $ extends Error {
}
async function _(s, t, e = {}) {
  const n = new AbortController(), i = setTimeout(() => n.abort(), e.timeout ?? 1e4), r = new Headers(e.headers);
  r.set("Accept", "application/json"), e.body && r.set("Content-Type", "application/json"), e.token && r.set("Authorization", `Screen ${e.token}`);
  try {
    const a = await fetch(s + t, {
      ...e,
      headers: r,
      signal: n.signal,
      cache: "no-store",
      credentials: "omit"
    });
    if (a.status === 401) throw new $("token rejected");
    if (!a.ok) throw new Error(`HTTP ${a.status}`);
    return await a.json();
  } finally {
    clearTimeout(i);
  }
}
const Ne = (s, t) => _(s, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), Ie = (s, t) => _(s, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), Nt = (s, t) => _(s, "config/", { token: t });
class Pe {
  constructor() {
    this.samples = [], this.offset = 0;
  }
  add(t, e, n) {
    const i = e - t;
    i < 0 || !Number.isFinite(n) || (this.samples.push({ offset: n * 1e3 - (t + e) / 2, rtt: i }), this.samples.length > 8 && this.samples.shift(), this.offset = this.samples.reduce((r, a) => a.rtt < r.rtt ? a : r).offset);
  }
  now() {
    return Date.now() + this.offset;
  }
}
const De = 3e4, Le = 3e5;
class Oe {
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
    this.backoff = Math.min(this.backoff * 2, De), setTimeout(() => !this.stopped && t(), e);
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
    }, e.onmessage = (n) => {
      let i;
      try {
        i = JSON.parse(String(n.data));
      } catch {
        return;
      }
      i.type === "hello" ? (this.wsFailures = 0, this.backoff = 1e3, this.setTransport("websocket"), this.beat()) : i.type === "heartbeat.ack" ? this.ack(i.server_time ?? NaN) : i.type !== "pong" && this.deliver(i);
    }, e.onclose = (n) => {
      if (this.ws = null, !this.stopped) {
        if (n.code === 4401) {
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > Le ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        if (t.status === 401) throw new $("token rejected");
        if (!t.ok || !t.body) throw new Error(`SSE HTTP ${t.status}`);
        this.setTransport("sse"), this.backoff = 1e3;
        const e = t.body.getReader(), n = new TextDecoder();
        let i = "";
        for (; ; ) {
          const { value: r, done: a } = await e.read();
          if (a) break;
          i += n.decode(r, { stream: !0 });
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
        t instanceof $ ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
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
        if (t instanceof $) {
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
      e instanceof $ ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function V(s) {
  return s ? s.startsWith("token:") ? `var(--evac-color-${s.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(s) || s === "transparent" ? s : "" : "";
}
function ze(s, t) {
  return s ? s === "token:heading" ? "var(--evac-font-heading)" : s === "token:body" ? "var(--evac-font-body)" : t.fonts[s] ?? "" : "";
}
function Re(s, t, e) {
  const n = s.style;
  if (!t) return;
  const i = (r, a) => {
    a && n.setProperty(r, a);
  };
  i("color", V(t.color)), i("background", V(t.background)), t.borderWidth && n.setProperty("border", `${t.borderWidth / 10}cqh solid ${V(t.borderColor) || "currentColor"}`), t.radius !== void 0 && n.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && n.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && n.setProperty("opacity", String(t.opacity)), i("font-family", ze(t.fontFamily, e)), t.fontSize && n.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && n.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && n.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && n.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && n.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && n.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && n.setProperty("box-shadow", "var(--evac-shadow)");
}
function Be(s, t, e) {
  const n = t.trim();
  if (n === "now") return new Date(e.now ? e.now() : Date.now());
  if (/^".*"$|^'.*'$/.test(n)) return n.slice(1, -1);
  if (/^-?\d+(\.\d+)?$/.test(n)) return Number(n);
  let i = s;
  for (const r of n.split(".")) {
    if (i == null || typeof i != "object") return;
    i = i[r];
  }
  return i;
}
function Fe(s) {
  const t = [];
  let e = "", n = "";
  for (const i of s)
    n ? (i === n && (n = ""), e += i) : i === '"' || i === "'" ? (n = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function We(s) {
  if (!s) return "";
  const t = s.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function It(s, t, e) {
  const n = e ? { timeZone: e } : {};
  switch (t) {
    case "short":
      return new Intl.DateTimeFormat("en-GB", { ...n, day: "numeric", month: "short" }).format(s);
    case "weekday":
      return new Intl.DateTimeFormat("en-GB", { ...n, weekday: "long" }).format(s);
    case "iso":
      return s.toISOString().slice(0, 10);
    case "HH:mm":
      return new Intl.DateTimeFormat("en-GB", { ...n, hour: "2-digit", minute: "2-digit" }).format(s);
    case "HH:mm:ss":
      return new Intl.DateTimeFormat("en-GB", { ...n, hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(s);
    case "h:mm a":
      return new Intl.DateTimeFormat("en-US", { ...n, hour: "numeric", minute: "2-digit" }).format(s);
    default:
      return new Intl.DateTimeFormat("en-GB", {
        ...n,
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
      }).format(s);
  }
}
function C(s) {
  return s == null ? "" : Array.isArray(s) ? s.map(C).join(", ") : s instanceof Date ? s.toISOString() : typeof s == "object" ? s.name ?? "" : String(s);
}
function je(s, t, e) {
  const [n, ...i] = t.split(":"), r = We(i.join(":")), a = () => s instanceof Date ? s : new Date(String(s));
  switch (n.trim()) {
    case "upper":
      return C(s).toUpperCase();
    case "lower":
      return C(s).toLowerCase();
    case "title":
      return C(s).replace(/\b\p{L}/gu, (o) => o.toUpperCase());
    case "truncate": {
      const o = Number(r) || 30, c = C(s);
      return c.length > o ? `${c.slice(0, Math.max(0, o - 1))}…` : c;
    }
    case "default":
      return C(s) === "" ? r : s;
    case "date":
      return isNaN(a().getTime()) ? "" : It(a(), r || "long", e.timezone);
    case "time":
      return isNaN(a().getTime()) ? "" : It(a(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(s) ? s.map(C).join(r || ", ") : C(s);
    default:
      return s;
  }
}
function J(s, t, e = {}) {
  const [n, ...i] = Fe(s);
  let r = Be(t, n, e);
  for (const a of i) r = je(r, a, e);
  return r;
}
function He(s) {
  return Array.isArray(s) ? s.length > 0 : !(s == null || s === !1 || s === "" || s === 0);
}
function nt(s, t, e = {}) {
  const n = s.trim();
  if (!n) return !0;
  if (n.startsWith("not ")) return !nt(n.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(n);
  if (i) {
    const r = C(J(i[1], t, e)), a = C(J(i[3], t, e));
    return i[2] === "==" ? r === a : r !== a;
  }
  return He(J(n.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const qe = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function re(s, t, e = {}) {
  if (!s || !s.includes("{{") && !s.includes("{%")) return s ?? "";
  const n = s.split(qe);
  let i = 0;
  const r = (a) => {
    let o = "";
    for (; i < n.length; ) {
      const c = n[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (a.includes(h)) return [o, h];
        if (h === "if") {
          const d = nt(l[2], t, e), [u, p] = r(["else", "endif"]);
          let m = "";
          p === "else" && (m = r(["endif"])[0]), o += d ? u : m;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? o += C(J(c.slice(2, -2), t, e)) : o += c;
    }
    return [o, ""];
  };
  return r([])[0];
}
const Ue = `(() => {
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
function Pt(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function Ve(s, t, e, n = "") {
  const i = Pt(t), r = e ? ` ${e}` : "", a = [
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
  ].join("; "), o = String(s.css ?? "").replace(/<\/style/gi, "<\\/style"), c = String(s.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${Pt(a)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${n}</style><style nonce="${i}">${o}</style><script nonce="${i}">${Ue}<\/script></head><body>${String(s.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function Je(s) {
  const t = [];
  try {
    const e = getComputedStyle(s);
    for (let n = 0; n < e.length; n++) {
      const i = e[n];
      if (i.startsWith("--evac-")) {
        const r = e.getPropertyValue(i).trim().replace(/[<>{};]/g, "");
        r && t.push(`${i}:${r}`);
      }
    }
  } catch {
  }
  return t.length ? `:root{${t.join(";")}}` : "";
}
function Dt(s = document) {
  const t = s.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
const W = "#00843d", Ge = "#f9a800", Ye = ["ahead", "ahead_right", "right", "back_right", "back", "back_left", "left", "ahead_left"], Ke = {
  E001: "Emergency exit (left)",
  E002: "Emergency exit (right)",
  E003: "First aid",
  E007: "Assembly point",
  W001: "General warning",
  arrow: "Direction"
};
function Ze(s) {
  const t = Ye.indexOf(s);
  return t < 0 ? 0 : t * 45;
}
const Xe = `<circle cx="57" cy="20" r="8"/>
<path d="M52 32 L44 56 L30 62 M48 44 L64 50 L74 42 M44 56 L56 70 L52 86 M44 56 L34 74 L20 78" fill="none"
 stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M50 30 L58 32 L62 36 L50 58 L42 54 Z"/>`;
function j(s, t, e, n) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${t}"
 color="${n}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${e}"/>${s}</svg>`;
}
function Qe() {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="All clear"
 color="#fff"><circle cx="50" cy="50" r="44" fill="none" stroke="currentColor" stroke-width="8"/>
<path d="M28 52 L44 68 L74 34" fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round"
 stroke-linejoin="round"/></svg>`;
}
function G(s, t = "ahead") {
  const e = Ke[s] ?? "Safety sign";
  switch (s) {
    case "E001":
    case "E002": {
      const n = `<path d="M66 10 H92 V90 H66 Z" fill="none" stroke="currentColor" stroke-width="5"/>
<path d="M72 18 H86 V82 H72 Z" opacity=".35"/>`, i = `<g transform="translate(0 8) scale(.84)">${Xe}</g>`, r = `${n}${i}`;
      return j(
        s === "E001" ? `<g transform="translate(100 0) scale(-1 1)">${r}</g>` : r,
        e,
        W,
        "#fff"
      );
    }
    case "E003":
      return j('<path d="M40 18 H60 V40 H82 V60 H60 V82 H40 V60 H18 V40 H40 Z"/>', e, W, "#fff");
    case "E007": {
      const n = [30, 50, 70].map((r) => `<circle cx="${r}" cy="44" r="6"/><path d="M${r - 6} 74 V56 a6 6 0 0 1 12 0 V74 Z"/>`).join(""), i = (r) => `<g transform="rotate(${r} 50 50)"><path d="M50 24 L58 14 H53 V5 H47 V14 H42 Z"/></g>`;
      return j(`${n}${[45, 135, 225, 315].map((r) => i(r)).join("")}`, e, W, "#fff");
    }
    case "W001":
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${e}">
<path d="M50 6 L96 90 H4 Z" fill="${Ge}" stroke="#000" stroke-width="6" stroke-linejoin="round"/>
<rect x="45" y="32" width="10" height="34" rx="3"/><circle cx="50" cy="77" r="6"/></svg>`;
    default: {
      const n = Ze(t);
      return j(
        `<g transform="rotate(${n} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
        `${e}: ${String(t).replace("_", " ")}`,
        W,
        "#fff"
      );
    }
  }
}
var L = /* @__PURE__ */ ((s) => (s[s.Border = -1] = "Border", s[s.Data = 0] = "Data", s[s.Function = 1] = "Function", s[s.Position = 2] = "Position", s[s.Timing = 3] = "Timing", s[s.Alignment = 4] = "Alignment", s))(L || {});
const tn = [0, 1], ae = [1, 0], oe = [2, 3], ce = [3, 2], en = {
  L: tn,
  M: ae,
  Q: oe,
  H: ce
}, nn = /^\d*$/, sn = /^[A-Z0-9 $%*+./:-]*$/, it = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", kt = 1, xt = 40, Lt = 3, rn = 3, H = 40, an = 10, le = [
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
], he = [
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
class on {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, n, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    z(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    z(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    z(this, "modules", []);
    z(this, "types", []);
    if (this.version = t, this.ecc = e, t < kt || t > xt)
      throw new RangeError("Version value out of range");
    if (i < -1 || i > 7)
      throw new RangeError("Mask value out of range");
    this.size = t * 4 + 17;
    const r = Array.from({ length: this.size }).fill(!1);
    for (let o = 0; o < this.size; o++)
      this.modules.push(r.slice()), this.types.push(r.map(() => 0));
    this.drawFunctionPatterns();
    const a = this.addEccAndInterleave(n);
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
    for (let n = 0; n < this.size; n++)
      this.setFunctionModule(6, n, n % 2 === 0, L.Timing), this.setFunctionModule(n, 6, n % 2 === 0, L.Timing);
    this.drawFinderPattern(3, 3), this.drawFinderPattern(this.size - 4, 3), this.drawFinderPattern(3, this.size - 4);
    const t = this.getAlignmentPatternPositions(), e = t.length;
    for (let n = 0; n < e; n++)
      for (let i = 0; i < e; i++)
        n === 0 && i === 0 || n === 0 && i === e - 1 || n === e - 1 && i === 0 || this.drawAlignmentPattern(t[n], t[i]);
    this.drawFormatBits(0), this.drawVersion();
  }
  // Draws two copies of the format bits (with its own error correction code)
  // based on the given mask and this object's error correction level field.
  drawFormatBits(t) {
    const e = this.ecc[1] << 3 | t;
    let n = e;
    for (let r = 0; r < 10; r++)
      n = n << 1 ^ (n >>> 9) * 1335;
    const i = (e << 10 | n) ^ 21522;
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
    for (let n = 0; n < 12; n++)
      t = t << 1 ^ (t >>> 11) * 7973;
    const e = this.version << 12 | t;
    for (let n = 0; n < 18; n++) {
      const i = M(e, n), r = this.size - 11 + n % 3, a = Math.floor(n / 3);
      this.setFunctionModule(r, a, i), this.setFunctionModule(a, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let n = -4; n <= 4; n++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(n)), a = t + i, o = e + n;
        a >= 0 && a < this.size && o >= 0 && o < this.size && this.setFunctionModule(a, o, r !== 2 && r !== 4, L.Position);
      }
  }
  // Draws a 5*5 alignment pattern, with the center module
  // at (x, y). All modules must be in bounds.
  drawAlignmentPattern(t, e) {
    for (let n = -2; n <= 2; n++)
      for (let i = -2; i <= 2; i++)
        this.setFunctionModule(
          t + i,
          e + n,
          Math.max(Math.abs(i), Math.abs(n)) !== 1,
          L.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, n, i = L.Function) {
    this.modules[e][t] = n, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, n = this.ecc;
    if (t.length !== Y(e, n))
      throw new RangeError("Invalid argument");
    const i = he[n[0]][e], r = le[n[0]][e], a = Math.floor(lt(e) / 8), o = i - a % i, c = Math.floor(a / i), l = [], h = gn(r);
    for (let u = 0, p = 0; u < i; u++) {
      const m = t.slice(p, p + c - r + (u < o ? 0 : 1));
      p += m.length;
      const b = vn(m, h);
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
    if (t.length !== Math.floor(lt(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let n = this.size - 1; n >= 1; n -= 2) {
      n === 6 && (n = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const a = n - r, c = (n + 1 & 2) === 0 ? this.size - 1 - i : i;
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
      for (let n = 0; n < this.size; n++) {
        let i;
        switch (t) {
          case 0:
            i = (n + e) % 2 === 0;
            break;
          case 1:
            i = e % 2 === 0;
            break;
          case 2:
            i = n % 3 === 0;
            break;
          case 3:
            i = (n + e) % 3 === 0;
            break;
          case 4:
            i = (Math.floor(n / 3) + Math.floor(e / 2)) % 2 === 0;
            break;
          case 5:
            i = n * e % 2 + n * e % 3 === 0;
            break;
          case 6:
            i = (n * e % 2 + n * e % 3) % 2 === 0;
            break;
          case 7:
            i = ((n + e) % 2 + n * e % 3) % 2 === 0;
            break;
          default:
            throw new Error("Unreachable");
        }
        !this.types[e][n] && i && (this.modules[e][n] = !this.modules[e][n]);
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
        this.modules[r][l] === a ? (o++, o === 5 ? t += Lt : o > 5 && t++) : (this.finderPenaltyAddHistory(o, c), a || (t += this.finderPenaltyCountPatterns(c) * H), a = this.modules[r][l], o = 1);
      t += this.finderPenaltyTerminateAndCount(a, o, c) * H;
    }
    for (let r = 0; r < this.size; r++) {
      let a = !1, o = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === a ? (o++, o === 5 ? t += Lt : o > 5 && t++) : (this.finderPenaltyAddHistory(o, c), a || (t += this.finderPenaltyCountPatterns(c) * H), a = this.modules[l][r], o = 1);
      t += this.finderPenaltyTerminateAndCount(a, o, c) * H;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let a = 0; a < this.size - 1; a++) {
        const o = this.modules[r][a];
        o === this.modules[r][a + 1] && o === this.modules[r + 1][a] && o === this.modules[r + 1][a + 1] && (t += rn);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((a, o) => a + (o ? 1 : 0), e);
    const n = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - n * 10) / n) - 1;
    return t += i * an, t;
  }
  /* -- Private helper functions -- */
  // Returns an ascending list of positions of alignment patterns for this version number.
  // Each position is in the range [0,177), and are used on both the x and y axes.
  // This could be implemented as lookup table of 40 variable-length lists of integers.
  getAlignmentPatternPositions() {
    if (this.version === 1)
      return [];
    {
      const t = Math.floor(this.version / 7) + 2, e = this.version === 32 ? 26 : Math.ceil((this.version * 4 + 4) / (t * 2 - 2)) * 2, n = [6];
      for (let i = this.size - 7; n.length < t; i -= e)
        n.splice(1, 0, i);
      return n;
    }
  }
  // Can only be called immediately after a light run is added, and
  // returns either 0, 1, or 2. A helper function for getPenaltyScore().
  finderPenaltyCountPatterns(t) {
    const e = t[1], n = e > 0 && t[2] === e && t[3] === e * 3 && t[4] === e && t[5] === e;
    return (n && t[0] >= e * 4 && t[6] >= e ? 1 : 0) + (n && t[6] >= e * 4 && t[0] >= e ? 1 : 0);
  }
  // Must be called at the end of a line (row or column) of modules. A helper function for getPenaltyScore().
  finderPenaltyTerminateAndCount(t, e, n) {
    return t && (this.finderPenaltyAddHistory(e, n), e = 0), e += this.size, this.finderPenaltyAddHistory(e, n), this.finderPenaltyCountPatterns(n);
  }
  // Pushes the given value to the front and drops the last value. A helper function for getPenaltyScore().
  finderPenaltyAddHistory(t, e) {
    e[0] === 0 && (t += this.size), e.pop(), e.unshift(t);
  }
}
function T(s, t, e) {
  if (t < 0 || t > 31 || s >>> t)
    throw new RangeError("Value out of range");
  for (let n = t - 1; n >= 0; n--)
    e.push(s >>> n & 1);
}
function M(s, t) {
  return (s >>> t & 1) !== 0;
}
class Et {
  // Creates a new QR Code segment with the given attributes and data.
  // The character count (numChars) must agree with the mode and the bit buffer length,
  // but the constraint isn't checked. The given bit buffer is cloned and stored.
  constructor(t, e, n) {
    if (this.mode = t, this.numChars = e, this.bitData = n, e < 0)
      throw new RangeError("Invalid argument");
    this.bitData = n.slice();
  }
  /* -- Methods -- */
  // Returns a new copy of the data bits of this segment.
  getData() {
    return this.bitData.slice();
  }
}
const cn = [1, 10, 12, 14], ln = [2, 9, 11, 13], hn = [4, 8, 16, 16];
function de(s, t) {
  return s[Math.floor((t + 7) / 17) + 1];
}
function ue(s) {
  const t = [];
  for (const e of s)
    T(e, 8, t);
  return new Et(hn, s.length, t);
}
function dn(s) {
  if (!fe(s))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < s.length; ) {
    const n = Math.min(s.length - e, 3);
    T(Number.parseInt(s.substring(e, e + n), 10), n * 3 + 1, t), e += n;
  }
  return new Et(cn, s.length, t);
}
function un(s) {
  if (!pe(s))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= s.length; e += 2) {
    let n = it.indexOf(s.charAt(e)) * 45;
    n += it.indexOf(s.charAt(e + 1)), T(n, 11, t);
  }
  return e < s.length && T(it.indexOf(s.charAt(e)), 6, t), new Et(ln, s.length, t);
}
function fn(s) {
  return s === "" ? [] : fe(s) ? [dn(s)] : pe(s) ? [un(s)] : [ue(mn(s))];
}
function fe(s) {
  return nn.test(s);
}
function pe(s) {
  return sn.test(s);
}
function pn(s, t) {
  let e = 0;
  for (const n of s) {
    const i = de(n.mode, t);
    if (n.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + n.bitData.length;
  }
  return e;
}
function mn(s) {
  s = encodeURI(s);
  const t = [];
  for (let e = 0; e < s.length; e++)
    s.charAt(e) !== "%" ? t.push(s.charCodeAt(e)) : (t.push(Number.parseInt(s.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function lt(s) {
  if (s < kt || s > xt)
    throw new RangeError("Version number out of range");
  let t = (16 * s + 128) * s + 64;
  if (s >= 2) {
    const e = Math.floor(s / 7) + 2;
    t -= (25 * e - 10) * e - 55, s >= 7 && (t -= 36);
  }
  return t;
}
function Y(s, t) {
  return Math.floor(lt(s) / 8) - le[t[0]][s] * he[t[0]][s];
}
function gn(s) {
  if (s < 1 || s > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let n = 0; n < s - 1; n++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let n = 0; n < s; n++) {
    for (let i = 0; i < t.length; i++)
      t[i] = ht(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = ht(e, 2);
  }
  return t;
}
function vn(s, t) {
  const e = t.map((n) => 0);
  for (const n of s) {
    const i = n ^ e.shift();
    e.push(0), t.forEach((r, a) => e[a] ^= ht(r, i));
  }
  return e;
}
function ht(s, t) {
  if (s >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let n = 7; n >= 0; n--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> n & 1) * s;
  return e;
}
function yn(s, t, e = 1, n = 40, i = -1, r = !0) {
  if (!(kt <= e && e <= n && n <= xt) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let a, o;
  for (a = e; ; a++) {
    const d = Y(a, t) * 8, u = pn(s, a);
    if (u <= d) {
      o = u;
      break;
    }
    if (a >= n)
      throw new RangeError("Data too long");
  }
  for (const d of [ae, oe, ce])
    r && o <= Y(a, d) * 8 && (t = d);
  const c = [];
  for (const d of s) {
    T(d.mode[0], 4, c), T(d.numChars, de(d.mode, a), c);
    for (const u of d.getData())
      c.push(u);
  }
  const l = Y(a, t) * 8;
  T(0, Math.min(4, l - c.length), c), T(0, (8 - c.length % 8) % 8, c);
  for (let d = 236; c.length < l; d ^= 253)
    T(d, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((d, u) => h[u >>> 3] |= d << 7 - (u & 7)), new on(a, t, h, i);
}
function bn(s, t) {
  const {
    ecc: e = "L",
    boostEcc: n = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: a = -1,
    border: o = 1
  } = t || {}, c = typeof s == "string" ? fn(s) : Array.isArray(s) ? [ue(s)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof s}`);
  const l = yn(
    c,
    en[e],
    i,
    r,
    a,
    n
  ), h = wn({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, o);
  return t?.invert && (h.data = h.data.map((d) => d.map((u) => !u))), t?.onEncoded?.(h), h;
}
function wn(s, t = 1) {
  if (!t)
    return s;
  const { size: e } = s, n = e + t * 2;
  s.size = n, s.data.forEach((r) => {
    for (let a = 0; a < t; a++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    s.data.unshift(Array.from({ length: n }, (a) => !1)), s.data.push(Array.from({ length: n }, (a) => !1));
  const i = L.Border;
  s.types.forEach((r) => {
    for (let a = 0; a < t; a++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    s.types.unshift(Array.from({ length: n }, (a) => i)), s.types.push(Array.from({ length: n }, (a) => i));
  return s;
}
const rt = "http://www.w3.org/2000/svg";
function me(s, t = document) {
  const { data: e, size: n } = bn(s, { ecc: "M", border: 2 }), i = t.createElementNS(rt, "svg");
  i.setAttribute("viewBox", `0 0 ${n} ${n}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(rt, "rect");
  r.setAttribute("width", String(n)), r.setAttribute("height", String(n)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let a = "";
  e.forEach((c, l) => c.forEach((h, d) => {
    h && (a += `M${d} ${l}h1v1h-1z`);
  }));
  const o = t.createElementNS(rt, "path");
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
    return re(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function Sn(s, t) {
  t.style.removeProperty("font-size");
  const e = parseFloat(getComputedStyle(t).fontSize) || 16, n = () => t.scrollHeight <= s.clientHeight + 1 && t.scrollWidth <= s.clientWidth + 1;
  if (!s.clientHeight || n()) return;
  let i = Math.max(4, e * 0.1), r = e;
  for (let a = 0; a < 12 && r - i > 0.5; a++) {
    const o = (i + r) / 2;
    t.style.fontSize = `${o}px`, n() ? i = o : r = o;
  }
  t.style.fontSize = `${i}px`;
}
class kn extends S {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-text";
    const e = this.text(this.props.text), n = Number(this.props.clamp) || 0;
    if (this.props.marquee) {
      const i = document.createElement("span");
      i.className = "evac-marquee", i.textContent = e, i.style.animationDuration = `${Math.max(8, e.length / 6)}s`, t.classList.add("evac-marquee-box"), t.appendChild(i);
    } else
      t.textContent = e, n && (t.classList.add("evac-clamp"), t.style.setProperty("-webkit-line-clamp", String(n)));
    if (this.replaceChildren(t), this.props.autofit && !this.props.marquee) {
      const i = () => Sn(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class xn extends S {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-richtext";
    for (const e of this.text(this.props.text).split(/\n{2,}/)) {
      const n = document.createElement("p");
      e.split(`
`).forEach((i, r) => {
        r && n.appendChild(document.createElement("br"));
        for (const a of i.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/))
          /^\*\*[^*]+\*\*$/.test(a) ? n.appendChild(Object.assign(
            document.createElement("strong"),
            { textContent: a.slice(2, -2) }
          )) : /^\*[^*]+\*$/.test(a) ? n.appendChild(Object.assign(
            document.createElement("em"),
            { textContent: a.slice(1, -1) }
          )) : a && n.appendChild(document.createTextNode(a));
      }), t.appendChild(n);
    }
    this.replaceChildren(t);
  }
}
function ge(s, t, e) {
  const n = document.createElement("picture");
  for (const [r, a] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (s.urls[r]) {
      const o = document.createElement("source");
      o.type = a, o.srcset = s.urls[r], n.appendChild(o);
    }
  const i = document.createElement("img");
  return i.src = s.urls.original, i.alt = e || s.alt || "", i.decoding = "async", i.style.objectFit = t, n.appendChild(i), n;
}
class En extends S {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(ge(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class $n extends S {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((a) => this.asset(a)).filter((a) => !!a);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), n = t.map((a) => {
      const o = ge(a, e, "");
      return o.className = "evac-slide", o;
    });
    this.replaceChildren(...n);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const a = Math.floor(this.ctx.now() / i) % n.length;
      n.forEach((o, c) => o.classList.toggle("active", c === a));
    };
    r(), this.every(500, r);
  }
}
class Cn extends S {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Video");
    const e = document.createElement("video");
    e.muted = this.props.muted !== !1 || this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.loop = this.props.loop !== !1, e.playsInline = !0, e.preload = "auto", e.style.objectFit = String(this.props.fit ?? "cover"), t.urls.poster && (e.poster = t.urls.poster);
    for (const n of ["webm", "mp4", "original"]) {
      if (!t.urls[n]) continue;
      const i = document.createElement("source");
      i.src = t.urls[n], i.type = t.mimes[n] || "", e.appendChild(i);
    }
    this.ctx.editing || (e.autoplay = !0, e.play?.()?.catch(() => {
    })), this.replaceChildren(e);
  }
}
class An extends S {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Mn extends S {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Tn extends S {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = me(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const _n = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Nn extends S {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ..._n[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = n.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class In extends S {
  draw() {
    const t = String(this.props.format ?? "long"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = {
      long: { weekday: "long", day: "numeric", month: "long" },
      short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" },
      iso: { year: "numeric", month: "2-digit", day: "2-digit" }
    }, i = new Intl.DateTimeFormat(t === "iso" ? "sv-SE" : "en-GB", { ...n[t], timeZone: e }), r = document.createElement("time"), a = () => {
      r.textContent = i.format(new Date(this.ctx.now()));
    };
    a(), this.replaceChildren(r), this.every(3e4, a);
  }
}
function Pn(s, t) {
  const e = Math.max(0, Math.floor(s / 1e3)), n = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), a = e % 60, o = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${n} ${n === 1 ? "day" : "days"}` : t === "ms" ? `${o(Math.floor(e / 60))}:${o(a)}` : t === "hms" || n === 0 ? `${o(i + n * 24)}:${o(r)}:${o(a)}` : `${n}d ${o(i)}:${o(r)}:${o(a)}`;
}
class Dn extends S {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), n = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : Pn(i, String(this.props.format ?? "auto"));
    };
    n(), this.replaceChildren(e), this.every(250, n);
  }
}
class Ln extends S {
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
    const e = this.props, n = document.createElement("iframe");
    n.setAttribute("sandbox", "allow-scripts"), n.setAttribute("referrerpolicy", "no-referrer"), n.setAttribute("allow", "autoplay"), n.setAttribute("title", this.el.name || "Code"), n.setAttribute("tabindex", "-1"), n.className = "evac-code-frame", n.srcdoc = Ve(e, t, location.origin, Je(this)), this.frame = n, window.addEventListener("message", this.onMessage), this.replaceChildren(n), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
  }
  /** Only the kinds of data the element asked for (and that the server let it ask for). */
  send() {
    const t = new Set(this.props.data ?? []), e = this.ctx.vars, n = {};
    if (t.has("event") && (n.event = e.event ?? null), t.has("screen") && (n.screen = e.screen ?? null), t.has("time") && (n.now = this.ctx.now(), n.timezone = this.ctx.timezone ?? ""), t.has("assets")) {
      const i = {};
      for (const r of this.props.assets ?? []) {
        const a = this.ctx.assets[r];
        if (!a) continue;
        const o = {};
        for (const [c, l] of Object.entries(a.urls)) o[c] = new URL(l, location.href).href;
        i[r] = { name: a.name, kind: a.kind, alt: a.alt, width: a.width, height: a.height, urls: o };
      }
      n.assets = i;
    }
    this.frame?.contentWindow?.postMessage({ type: "evac:data", data: JSON.parse(JSON.stringify(n)) }, "*");
  }
  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage), this.frame = null, super.disconnectedCallback();
  }
}
const $t = {
  text: kn,
  richtext: xn,
  image: En,
  slideshow: $n,
  video: Cn,
  audio: An,
  shape: Mn,
  qr: Tn,
  clock: Nn,
  countdown: Dn,
  date: In,
  code: Ln
};
function On(s = customElements) {
  for (const [t, e] of Object.entries($t))
    s.get(`evac-${t}`) || s.define(`evac-${t}`, e);
}
class zn extends S {
  draw() {
    const t = String(this.props.code ?? "E002");
    let e = String(this.props.direction ?? "auto");
    if (e === "auto") {
      const n = this.ctx.vars.evac;
      if (t === "arrow" && !n?.arrow) {
        this.replaceChildren(), this.hidden = !0;
        return;
      }
      e = n?.arrow ?? "ahead";
    }
    this.hidden = !1, this.innerHTML = G(t, e);
  }
}
$t.pictogram = zn;
class Rn {
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
function f(s, t = "", e) {
  const n = document.createElement(s);
  return t && (n.className = t), e != null && e !== "" && (n.textContent = String(e)), n;
}
function O(s) {
  if (typeof s == "number") return Number.isFinite(s) ? s : null;
  if (typeof s == "string" && s.trim() !== "") {
    const t = Number(s.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function q(s, t) {
  if (typeof s != "string" || !s) return "";
  const e = /^\d{4}-\d{2}-\d{2}$/.test(s), n = new Date(e ? `${s}T12:00:00Z` : s);
  if (Number.isNaN(n.getTime())) return s;
  const i = e ? { weekday: "short", day: "numeric", month: "short" } : { hour: "2-digit", minute: "2-digit", hour12: !1 };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...i, timeZone: e ? "UTC" : t }).format(n);
  } catch {
    return new Intl.DateTimeFormat("en-GB", i).format(n);
  }
}
const Bn = ["time", "title", "subtitle", "label", "value"];
class Fn extends S {
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
    const n = f("div", `evac-data evac-data-${e.visual}`), i = String(this.props.title || e.options.heading || "");
    i && n.appendChild(f("div", "evac-data-heading", i));
    const r = f("div", "evac-data-body");
    n.appendChild(r), (Ot[e.visual] ?? Ot.list)(r, e, this), this.ctx.editing && e.stale && n.appendChild(f("span", "evac-data-stale", "stale")), this.replaceChildren(n);
  }
  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(t, e) {
    return re(
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
function R(s, t) {
  return t.rows.length ? !1 : (s.appendChild(f("div", "evac-data-empty", "–")), !0);
}
const Ot = {
  text(s, t, e) {
    s.appendChild(f("div", "evac-data-text", e.tmpl(
      String(t.options.template || "{{ data.first.title }}"),
      t
    )));
  },
  list(s, t, e) {
    if (R(s, t)) return;
    const n = f("ul", "evac-data-list");
    for (const i of t.rows) {
      const r = f("li");
      i.time && r.appendChild(f("span", "evac-data-time", q(i.time, e.tz)));
      const a = f("span", "evac-data-main");
      a.appendChild(f("span", "evac-data-title", i.title ?? i.label ?? i.value)), i.subtitle && a.appendChild(f("span", "evac-data-sub", i.subtitle)), r.appendChild(a), i.value !== void 0 && i.value !== null && i.title && r.appendChild(f("span", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  table(s, t, e) {
    if (R(s, t)) return;
    const n = Bn.filter((a) => t.rows.some((o) => o[a] !== void 0 && o[a] !== null && o[a] !== "")), i = f("table", "evac-data-table"), r = f("tbody");
    for (const a of t.rows) {
      const o = f("tr");
      for (const c of n) o.appendChild(f("td", `evac-data-${c}`, c === "time" ? q(a[c], e.tz) : a[c]));
      r.appendChild(o);
    }
    i.appendChild(r), s.appendChild(i);
  },
  cards(s, t, e) {
    if (R(s, t)) return;
    const n = f("div", "evac-data-cards");
    for (const i of t.rows) {
      const r = f("div", "evac-data-card");
      if (typeof i.image == "string" && i.image.startsWith("/")) {
        const a = f("img");
        a.src = i.image, a.alt = "", r.appendChild(a);
      }
      i.time && r.appendChild(f("div", "evac-data-time", q(i.time, e.tz))), r.appendChild(f("div", "evac-data-title", i.title ?? i.label)), i.subtitle && r.appendChild(f("div", "evac-data-sub", i.subtitle)), i.value !== void 0 && i.value !== null && r.appendChild(f("div", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  counter(s, t) {
    const e = t.rows[0] ?? {}, n = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, i = O(n), r = f("div", "evac-data-number", i === null ? n : i.toLocaleString("en-GB"));
    t.options.unit && r.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(r), (e.label || e.title) && s.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(s, t) {
    const e = t.rows[0] ?? {}, n = O(e.value) ?? 0, i = O(t.options.minimum) ?? 0, r = O(t.options.maximum) ?? 100, a = Math.max(0, Math.min(1, (n - i) / (r - i || 1))), o = "http://www.w3.org/2000/svg", c = document.createElementNS(o, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${n}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (d, u) => {
      const p = Math.PI * (1 - d), m = document.createElementNS(o, "path");
      m.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(p)} ${100 - 80 * Math.sin(p)}`), m.setAttribute("class", u), c.appendChild(m);
    };
    l(1, "evac-gauge-track"), a > 0 && l(a, "evac-gauge-fill"), s.appendChild(c);
    const h = f("div", "evac-data-number", n.toLocaleString("en-GB"));
    t.options.unit && h.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(h), (e.label || e.title) && s.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(s, t, e) {
    if (R(s, t)) return;
    const n = t.rows.map((a) => [a.time ? q(a.time, e.tz) : "", a.title ?? a.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), i = f("div", "evac-marquee-box"), r = f("span", "evac-marquee", n);
    r.style.animationDuration = `${Math.max(10, n.length / 5)}s`, i.appendChild(r), s.appendChild(i);
  },
  bars(s, t) {
    if (R(s, t)) return;
    const e = t.rows.map((r) => O(r.value) ?? 0), n = O(t.options.maximum) || Math.max(...e, 1), i = f("div", "evac-data-bars");
    t.rows.forEach((r, a) => {
      const o = f("div", "evac-bar");
      o.appendChild(f("span", "evac-bar-label", r.label ?? r.title));
      const c = f("span", "evac-bar-track"), l = f("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[a] / n * 100))}%`, c.appendChild(l), o.appendChild(c), o.appendChild(f("span", "evac-bar-value", `${e[a].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), i.appendChild(o);
    }), s.appendChild(i);
  }
};
$t.data = Fn;
function Wn(s, t) {
  const e = t.frame;
  s.style.left = `${e.x}%`, s.style.top = `${e.y}%`, s.style.width = `${e.w}%`, s.style.height = `${e.h}%`, s.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function jn(s, t) {
  const e = !s.visible_if || nt(s.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (s.hidden && !t.editing || !e && !t.editing) return null;
  const n = document.createElement("div");
  n.className = `evac-el evac-el-${s.type}`, n.dataset.id = s.id, (!e || s.hidden) && n.classList.add("evac-dimmed"), Wn(n, s), Re(n, s.style, t);
  const i = s.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (n.classList.add(`evac-enter-${i.enter}`), n.style.animationDuration = `${i.duration ?? 600}ms`, n.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${s.type}`;
  if (!customElements.get(r))
    return t.onError?.(s.id, new Error(`unknown element type ${s.type}`)), t.editing ? n : null;
  const a = document.createElement(r);
  return a.className = "evac-widget", n.appendChild(a), a.configure(s, t), n;
}
function dt(s, t, e) {
  On();
  const n = document.createElement("div");
  n.className = "evac-stage";
  const i = t.background;
  if (i?.color && (n.style.background = V(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    n.style.backgroundImage = `url("${l}")`, n.style.backgroundSize = i.fit ?? "cover", n.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = jn(c, e);
    l && (r.set(c.id, l), n.appendChild(l));
  }
  s.replaceChildren(n);
  const a = () => {
    const c = s.clientWidth, l = s.clientHeight;
    if (!c || !l) return;
    const h = Math.min(c / t.width, l / t.height);
    n.style.width = `${Math.round(t.width * h)}px`, n.style.height = `${Math.round(t.height * h)}px`;
  };
  a();
  const o = typeof ResizeObserver < "u" ? new ResizeObserver(a) : null;
  return o?.observe(s), {
    stage: n,
    elements: r,
    destroy() {
      o?.disconnect(), n.remove();
    }
  };
}
function v(s, t = "", e = "") {
  const n = document.createElement(s);
  return t && (n.className = t), e && (n.textContent = e), n;
}
class Hn {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = v("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, n) {
    const i = this.reset();
    i.classList.add("pairing"), i.append(v("h1", "", n.title));
    const r = v("div", "pairing-box"), a = v("p", "code", t);
    a.setAttribute("aria-label", t.split("").join(" "));
    const o = me(e);
    o.setAttribute("role", "img"), o.setAttribute("aria-label", e), r.append(a, o);
    const c = v("ol", "steps");
    c.append(v("li", "", n.step1), v("li", "", n.step2)), i.append(r, c, v("p", "url", e), v("p", "waiting", n.waiting));
  }
  message(t, e = "") {
    const n = this.reset();
    n.classList.add("message"), n.append(v("h1", "", t)), e && n.append(v("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const n = v("p", "clock"), i = v("p", "date");
    e.append(v("h1", "event-name", t.event.name), n, i);
    const r = t.event.timezone || void 0, a = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: r }), o = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: r }), c = () => {
      const l = new Date(this.clock.now());
      n.textContent = a.format(l), i.textContent = o.format(l);
    };
    c(), this.clockTimer = setInterval(c, 1e3);
  }
  layout(t, e, n) {
    const i = this.reset();
    i.classList.add("layout");
    for (const [r, a] of Object.entries(n ?? {})) i.style.setProperty(r, a);
    this.rendered = dt(i, t, e);
  }
  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(t, e, n = 30) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = v("div", "test-pattern");
    i.setAttribute("role", "img"), i.setAttribute("aria-label", t);
    const r = v("div", "tp-bars");
    for (const c of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"])
      r.appendChild(v("span", `tp-bar tp-${c}`));
    const a = v("div", "tp-ramp"), o = v("div", "tp-info");
    o.append(v("p", "tp-title", t), ...e.map((c) => v("p", "", c))), i.append(r, a, v("div", "tp-grid"), v("div", "tp-circle"), v("div", "tp-corners"), o), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), n * 1e3);
  }
  identify(t, e, n = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = v("div", "identify");
    i.setAttribute("role", "status"), i.append(v("p", "identify-name", t), v("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), n * 1e3);
  }
}
const Ct = "evac.player.bundle";
async function qn(s, t) {
  try {
    const e = await _(s, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(Ct, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof $) throw e;
    return ut();
  }
}
function ut() {
  try {
    const s = localStorage.getItem(Ct);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Un() {
  try {
    localStorage.removeItem(Ct);
  } catch {
  }
}
function Vn(s) {
  return s?.layouts.length ? s.layouts.find((t) => t.default) ?? s.layouts[0] : null;
}
async function Jn(s) {
  const t = /* @__PURE__ */ new Set();
  for (const n of Object.values(s.assets)) Object.values(n.urls).forEach((i) => t.add(i));
  let e = 0;
  return await Promise.all([...t].map(async (n) => {
    try {
      const i = await fetch(n, { credentials: "omit" });
      i.ok && (e += 1), await i.body?.cancel();
    } catch {
    }
  })), e;
}
const Q = "evac.player.program";
async function Gn(s, t) {
  try {
    const e = await _(s, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(Q, JSON.stringify(e.program)) : localStorage.removeItem(Q);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof $) throw e;
    return ft();
  }
}
function ft() {
  try {
    const s = localStorage.getItem(Q);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Yn() {
  try {
    localStorage.removeItem(Q);
  } catch {
  }
}
const ve = 1600;
function Kn(s, t) {
  const e = [];
  for (const n of s ?? [])
    for (const [i, r] of n.windows)
      if ((i === null || i <= t) && (r === null || t < r)) {
        e.push({ overlay: n, start: i ?? 0, end: r });
        break;
      }
  return e.sort((n, i) => i.overlay.rank - n.overlay.rank || i.start - n.start);
}
function Zn(s, t) {
  let e = null;
  for (const n of s ?? [])
    for (const [i, r] of n.windows)
      for (const a of [i, r])
        a !== null && a > t && (e === null || a < e) && (e = a);
  return e;
}
function Xn(s) {
  return {
    card: s.find((t) => t.overlay.style === "card") ?? null,
    banner: s.find((t) => t.overlay.style === "banner") ?? null,
    ticker: s.filter((t) => t.overlay.style === "ticker")
  };
}
function Qn(s) {
  const t = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(s);
  if (!t) return "#ffffff";
  const [e, n, i] = t.slice(1).map((a) => {
    const o = parseInt(a, 16) / 255;
    return o <= 0.03928 ? o / 12.92 : ((o + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * e + 0.7152 * n + 0.0722 * i > 0.179 ? "#000000" : "#ffffff";
}
function x(s, t, e = "") {
  const n = document.createElement(s);
  return n.className = t, e && (n.textContent = e), n;
}
function at(s, t) {
  s.style.setProperty("--ann-bg", /^#[0-9a-f]{6}$/i.test(t) ? t : "#2563eb"), s.style.setProperty("--ann-fg", Qn(t));
}
function ye(s, t = 100) {
  if (s === "none" || typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const n = Math.max(0, Math.min(1, t / 100)) * 0.4, i = s === "chime" ? [[660, 0, 0.6], [880, 0.35, 0.9]] : s === "gong" ? [[196, 0, 2.5], [392, 0, 1.5], [294, 0.02, 2]] : [[880, 0, 0.25], [660, 0.3, 0.25], [880, 0.6, 0.25], [660, 0.9, 0.25]];
  let r = 0;
  for (const [a, o, c] of i) {
    const l = e.createOscillator(), h = e.createGain();
    l.type = s === "alert" ? "square" : "sine", l.frequency.value = a;
    const d = e.currentTime + o;
    h.gain.setValueAtTime(1e-4, d), h.gain.exponentialRampToValueAtTime(n, d + 0.02), h.gain.exponentialRampToValueAtTime(1e-4, d + c), l.connect(h).connect(e.destination), l.start(d), l.stop(d + c + 0.05), r = Math.max(r, o + c);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, (r + 0.5) * 1e3);
}
class ts {
  constructor(t) {
    this.speaker = t, this.drawn = "", this.heard = /* @__PURE__ */ new Set(), this.node = x("div", "ann-layer"), this.node.setAttribute("aria-live", "polite");
  }
  /** Keep the layer on top of the content (the display replaces its children on every slide). */
  attach(t) {
    (this.node.parentElement !== t || t.lastElementChild !== this.node) && t.appendChild(this.node);
  }
  update(t, e, n = {}) {
    const i = n.hidden ? [] : Kn(t, e), { card: r, banner: a, ticker: o } = Xn(i), c = n.audio?.enabled !== !1;
    for (const h of i) {
      const d = `${h.overlay.id}@${h.start}`, u = h.overlay.sound && h.overlay.sound !== "none";
      this.heard.has(d) || (this.heard.add(d), c && u && ye(h.overlay.sound, n.audio?.volume ?? 100)), c && h.overlay.speech && this.speaker?.say(d, h.overlay.speech, { volume: n.audio?.volume, delayMs: u ? ve : 0 });
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
        at(h, r.overlay.colour), h.append(x("p", "ann-level", r.overlay.level), x("h2", "ann-title", r.overlay.title)), r.overlay.text && r.overlay.text !== r.overlay.title && h.append(x("p", "ann-text", r.overlay.text)), this.node.append(h);
      }
      if (a) {
        const h = x("div", "ann-banner");
        at(h, a.overlay.colour), h.append(x("span", "ann-level", a.overlay.level), x("span", "ann-text", a.overlay.text)), this.node.append(h);
      }
      if (o.length) {
        const h = x("div", "ann-ticker");
        at(h, o[0].overlay.colour);
        const d = x("div", "ann-track"), u = o.map((m) => m.overlay.text).join("   ◆   "), p = x("span", "", u);
        p.setAttribute("aria-hidden", "true"), d.append(x("span", "", u), p), d.style.setProperty("--ann-duration", `${Math.max(12, Math.round(u.length / 6))}s`), h.append(x("span", "ann-level", o[0].overlay.level), d), this.node.append(h);
      }
      this.node.classList.toggle("has-bottom", !!(a && o.length));
    }
  }
}
class es {
  constructor(t = (e) => new Audio(e)) {
    this.make = t, this.spoken = /* @__PURE__ */ new Set(), this.queue = [], this.playing = !1;
  }
  /** Speak ``url`` once for ``key`` (an announcement occurrence); later calls with the same key do nothing. */
  say(t, e, n = {}) {
    if (!e || this.spoken.has(t)) return !1;
    this.spoken.add(t), this.spoken.size > 500 && (this.spoken = new Set([...this.spoken].slice(-100)));
    const i = { url: e, volume: Math.max(0, Math.min(1, (n.volume ?? 100) / 100)) };
    return setTimeout(() => {
      this.queue.push(i), this.next();
    }, n.delayMs ?? 0), !0;
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
    const n = () => {
      this.playing = !1, this.next();
    };
    e.addEventListener("ended", n, { once: !0 }), e.addEventListener("error", n, { once: !0 });
    const i = e.play();
    i && typeof i.catch == "function" && i.catch(n);
  }
}
async function zt(s) {
  let t = 0;
  return await Promise.all([...new Set(s)].map(async (e) => {
    try {
      const n = await fetch(e, { credentials: "omit" });
      n.ok && (t += 1), await n.body?.cancel();
    } catch {
    }
  })), t;
}
const At = "evac.player.widgets";
function ns() {
  try {
    const s = localStorage.getItem(At);
    return s ? JSON.parse(s) : {};
  } catch {
    return {};
  }
}
async function ss(s, t, e) {
  try {
    const n = await _(s, "widgets/data/", { token: t, timeout: 15e3 });
    e.set(n.widgets ?? {});
    try {
      localStorage.setItem(At, JSON.stringify(n.widgets ?? {}));
    } catch {
    }
    return !0;
  } catch (n) {
    if (n instanceof $) throw n;
    return !1;
  }
}
function is() {
  try {
    localStorage.removeItem(At);
  } catch {
  }
}
const rs = 5, as = 1e4;
function os(s) {
  let t = 2166136261;
  for (let e = 0; e < s.length; e++)
    t ^= s.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function cs(s, t) {
  let e = t >>> 0 || 1;
  const n = [...s];
  for (let i = n.length - 1; i > 0; i--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (i + 1);
    [n[i], n[r]] = [n[r], n[i]];
  }
  return n;
}
function ls(s, t) {
  const e = t.reduce((r, a) => r + a, 0), n = t.map(() => 0), i = [];
  for (let r = 0; r < e; r++) {
    t.forEach((o, c) => {
      n[c] += o;
    });
    let a = 0;
    for (let o = 1; o < s.length; o++) n[o] > n[a] && (a = o);
    n[a] -= e, i.push(s[a]);
  }
  return i;
}
function hs(s, t, e) {
  if (s.from !== null && s.from !== void 0 && t < s.from || s.until !== null && s.until !== void 0 && t >= s.until) return !1;
  const n = s.tags ?? [], i = e.screen?.tags ?? [];
  return n.length && !n.some((r) => i.includes(r)) ? !1 : nt(s.when ?? "", e);
}
function pt(s, t, e, n, i, r = []) {
  const a = s.playlists[t];
  if (!a || r.includes(t) || r.length >= rs) return [];
  let o = [];
  const c = [];
  for (const l of a.items ?? []) {
    if (!hs(l, n, e)) continue;
    let h = [];
    if (l.playlist) h = pt(s, l.playlist, e, n, i, [...r, t]);
    else if (l.layout && l.layout in s.layouts) {
      const d = l.duration || s.layouts[l.layout] || a.default || as;
      h = [{ layout: l.layout, duration: d, item: l.id }];
    }
    h.length && (o.push(h), c.push(Math.max(1, Math.trunc(l.weight || 1))));
  }
  return a.mode === "weighted" ? o = ls(o, c) : a.mode === "shuffle" && (o = cs(o, os(`${t}:${i}`))), o.flat();
}
function ds(s, t) {
  return (s[0] === null || s[0] <= t) && (s[1] === null || t < s[1]);
}
function us(s, t) {
  const e = [];
  return s.entries.forEach((n, i) => {
    const r = n.windows.find((a) => ds(a, t));
    r && e.push({ key: [-n.priority, -(r[0] ?? -1), i], entry: n, w: r });
  }), e.sort((n, i) => n.key[0] - i.key[0] || n.key[1] - i.key[1] || n.key[2] - i.key[2]), e.map((n) => [n.entry, n.w]);
}
function fs(s, t, e, n, i) {
  const r = n.content, a = { entry: n.id, index: 0, count: 1, start: i[0], end: i[1] };
  if (r.message !== void 0) return r.message in (s.messages ?? {}) ? { ...a, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in s.layouts ? { ...a, layout: r.layout } : null;
  const o = r.playlist, c = i[0] ?? 0;
  let l = pt(s, o, t, e, 0);
  const h = l.reduce((m, b) => m + b.duration, 0);
  if (!h) return null;
  const d = Math.floor((e - c) / h);
  d && (l = pt(s, o, t, e, d));
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
function ps(s, t, e) {
  for (const [n, i] of us(s, e)) {
    const r = fs(s, t, e, n, i);
    if (r) return r;
  }
  return null;
}
function ms(s, t, e) {
  const n = e?.end != null ? [e.end] : [];
  for (const i of s.entries)
    for (const [r, a] of i.windows)
      r !== null && r > t && n.push(r), a !== null && a > t && n.push(a);
  return n.length ? Math.min(...n) : null;
}
const gs = "evac-player-content-v1", vs = "content/theme/", ys = /url\("([^"]+)"\)/g;
async function Rt(s, t) {
  const e = await caches.open(gs).catch(() => null), n = await e?.match(s).catch(() => {
  });
  if (n) return n;
  const i = new AbortController(), r = setTimeout(() => i.abort(), 1e4);
  try {
    const a = await fetch(s, {
      headers: { Authorization: `Screen ${t}` },
      credentials: "omit",
      signal: i.signal
    });
    if (a.ok)
      return await e?.put(s, a.clone()), a;
  } catch {
  } finally {
    clearTimeout(r);
  }
  return null;
}
async function bs(s, t) {
  try {
    const e = await _(s, vs, { token: t });
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
function ws(s) {
  const t = [];
  for (const e of s.match(/@font-face\{[^}]*\}/g) ?? []) {
    const n = /font-family:"([^"]+)"/.exec(e)?.[1], i = /src:url\("([^"]+)"\)/.exec(e)?.[1];
    !n || !i || t.push({
      family: n,
      url: i,
      weight: /font-weight:([^;]+);/.exec(e)?.[1] ?? "400",
      style: /font-style:([^;]+);/.exec(e)?.[1] ?? "normal",
      unicodeRange: /unicode-range:([^;]+);/.exec(e)?.[1]
    });
  }
  return t;
}
const Bt = [];
async function Ft(s, t, e = document.documentElement) {
  const n = document.fonts;
  await Promise.all(ws(s.fonts_css).map(async (i) => {
    const r = await Rt(i.url, t);
    if (r)
      try {
        const a = new FontFace(i.family, await r.arrayBuffer(), {
          weight: i.weight,
          style: i.style,
          unicodeRange: i.unicodeRange
        });
        n.add(await a.load());
      } catch {
      }
  })), Bt.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, r] of Object.entries(s.variables)) {
    let a = r;
    for (const o of r.matchAll(ys)) {
      const c = await Rt(o[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        Bt.push(l), a = a.replace(o[1], l);
      }
    }
    e.style.setProperty(i, a);
  }
  e.dataset.theme = s.key || "default";
}
function Ss(s = document) {
  const t = s.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, n = new URLSearchParams(s.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: n.get("mode") === "obs" ? "obs" : "screen"
  };
}
function N(s, t, e = {}) {
  let n = s.strings[t] ?? t;
  for (const [i, r] of Object.entries(e)) n = n.replace(`{${i}}`, String(r));
  return n;
}
function ks(s, t = location) {
  return s.ws ? s.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const K = [], Z = [], xs = Date.now(), Es = 300;
let B = [], mt = null;
function E(s, t) {
  Z.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${s.toUpperCase()} ${t}`.slice(0, 500)), Z.length > Es && Z.shift();
}
function $s() {
  return [...Z];
}
function w(s) {
  K.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${s}`.slice(0, 300)), K.length > 10 && K.shift(), E("error", s);
  const t = Date.now();
  B = B.filter((e) => t - e < 6e4), B.push(t), B.length >= 50 && mt && (B = [], mt());
}
function Cs(s) {
  mt = s;
}
function As(s = window) {
  s.addEventListener("error", (t) => w(t.message || "error")), s.addEventListener("unhandledrejection", (t) => w(String(t.reason)));
  for (const t of ["warn", "info"]) {
    const e = console[t].bind(console);
    console[t] = (...n) => {
      E(t, n.map(String).join(" ")), e(...n);
    };
  }
}
function Wt(s) {
  const t = window.innerWidth, e = window.innerHeight, n = performance.memory;
  return {
    version: s.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - xs) / 1e3),
    slide: s.slide,
    errors: [...K],
    memory: n ? Math.round(n.usedJSHeapSize / 1048576) : null,
    last_sync: s.lastSync ? new Date(s.lastSync).toISOString() : null,
    online: s.online,
    user_agent: navigator.userAgent,
    ...s.contentVersion ? { content_version: s.contentVersion } : {},
    ...s.displayState ? { display_state: s.displayState } : {},
    ...s.capture !== void 0 ? { capture: s.capture } : {},
    ...s.recovered ? { recovered: s.recovered } : {},
    ...s.evacAck ? { evac_ack: s.evacAck } : {},
    ...s.evacBundle ? { evac_bundle: s.evacBundle } : {},
    ...s.evacAudio ? { evac_audio: s.evacAudio } : {}
  };
}
const be = "evac.player.reloads", tt = "evac.player.alive", Ms = 3, Ts = 10 * 6e4;
function we(s) {
  try {
    return localStorage.getItem(s);
  } catch {
    return null;
  }
}
function st(s, t) {
  try {
    t === null ? localStorage.removeItem(s) : localStorage.setItem(s, t);
  } catch {
  }
}
function _s(s = Date.now()) {
  try {
    return JSON.parse(we(be) ?? "[]").filter((t) => s - t < Ts);
  } catch {
    return [];
  }
}
function X(s, t = {}) {
  const e = Date.now(), n = _s(e);
  return !t.force && n.length >= Ms ? (w(`reload (${s}) skipped: ${n.length} reloads in the last 10 minutes`), !1) : (st(be, JSON.stringify([...n, e])), E("info", `reload: ${s}`), Se(), (t.win ?? location).reload(), !0);
}
function Ns(s = Date.now()) {
  const t = we(tt);
  if (st(tt, String(s)), !t || t === "clean") return "";
  const e = Number(t);
  return Number.isFinite(e) ? `restarted after an unclean stop (last sign of life ${new Date(e).toISOString()})` : "";
}
function Is(s = Date.now()) {
  st(tt, String(s));
}
function Se() {
  st(tt, "clean");
}
function Ps(s = window) {
  s.addEventListener("pagehide", () => Se());
}
function Ds() {
  const s = performance.memory;
  return !!s && s.jsHeapSizeLimit > 0 && s.usedJSHeapSize / s.jsHeapSizeLimit > 0.85;
}
function ke() {
  return typeof navigator < "u" && !!navigator.mediaDevices?.getDisplayMedia;
}
function Ls(s, t, e) {
  return new Promise((n, i) => {
    const r = setTimeout(() => i(new Error(`${e} timed out`)), t);
    s.then((a) => {
      clearTimeout(r), n(a);
    }, (a) => {
      clearTimeout(r), i(a);
    });
  });
}
async function Os(s = 1e4) {
  return Ls(zs(), s, "screen capture");
}
async function zs() {
  if (!ke()) throw new Error("screen capture is not available in this browser");
  const s = document.createElement("div");
  s.className = "evac-capture-dot", document.body.appendChild(s);
  let t = 0;
  const e = setInterval(() => s.classList.toggle("on", t++ % 2 === 0), 16);
  try {
    return await Rs();
  } finally {
    clearInterval(e), s.remove();
  }
}
async function Rs() {
  const s = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "browser" },
    audio: !1,
    preferCurrentTab: !0,
    selfBrowserSurface: "include"
  });
  try {
    const t = document.createElement("video");
    t.muted = !0, t.srcObject = s, await t.play(), t.videoWidth || await new Promise((n) => t.addEventListener("loadeddata", n, { once: !0 }));
    const e = document.createElement("canvas");
    return e.width = t.videoWidth || window.innerWidth, e.height = t.videoHeight || window.innerHeight, e.getContext("2d")?.drawImage(t, 0, 0, e.width, e.height), t.srcObject = null, await new Promise((n, i) => e.toBlob((r) => r ? n(r) : i(new Error("encoding failed")), "image/jpeg", 0.85));
  } finally {
    s.getTracks().forEach((t) => t.stop());
  }
}
async function ot(s, t, e, n) {
  const i = typeof Blob < "u" && n instanceof Blob;
  await fetch(`${s}upload/${e}/`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Screen ${t}`, "Content-Type": i ? n.type : "application/json" },
    body: i ? n : JSON.stringify(n)
  });
}
const Bs = /* @__PURE__ */ new Set(["evac.player.token", "evac.player.evac", "evac.player.evacbundle", "evac.player.evacseq"]);
async function Fs() {
  try {
    if (typeof caches < "u") for (const s of await caches.keys()) await caches.delete(s);
  } catch {
  }
  try {
    for (const s of Object.keys(localStorage))
      s.startsWith("evac.player.") && !Bs.has(s) && localStorage.removeItem(s);
  } catch {
  }
  try {
    for (const s of await navigator.serviceWorker?.getRegistrations?.() ?? []) await s.unregister();
  } catch {
  }
}
function jt(s, t) {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: t || void 0
    }).format(new Date(s));
  } catch {
    return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(s));
  }
}
function Ht(s, t, e) {
  return !t || !e || t === e ? !1 : t < e ? s >= t && s < e : s >= t || s < e;
}
function Ws(s, t) {
  return Ht(t, s.sleep_from, s.sleep_until) ? "sleeping" : Ht(t, s.dim_from, s.dim_until) ? "dimmed" : "on";
}
function js(s) {
  const t = Number(s.rotation ?? 0) || 0, e = t === 90 || t === 270, n = ["translate(-50%, -50%)"];
  t && n.push(`rotate(${t}deg)`), (s.keystone_x || s.keystone_y) && (n.push("perspective(1200px)"), s.keystone_y && n.push(`rotateX(${s.keystone_y}deg)`), s.keystone_x && n.push(`rotateY(${s.keystone_x}deg)`));
  const i = (s.scale ?? 100) / 100;
  i !== 1 && n.push(`scale(${i})`);
  const r = Math.max(0, Math.min(15, s.overscan ?? 0));
  return {
    width: e ? "100vh" : "100vw",
    height: e ? "100vw" : "100vh",
    transform: n.join(" "),
    overscan: `${r}%`
  };
}
function ct(s, t) {
  const e = js(t);
  s.classList.add("evac-root"), s.style.width = e.width, s.style.height = e.height, s.style.transform = e.transform, s.style.setProperty("--evac-overscan", e.overscan);
}
function Hs(s, t, e = document) {
  let n = e.getElementById("evac-dim");
  if (s === "on") {
    n?.remove();
    return;
  }
  n || (n = e.createElement("div"), n.id = "evac-dim", n.setAttribute("aria-hidden", "true"), e.body.appendChild(n));
  const i = s === "sleeping" ? 0 : Math.max(10, Math.min(90, t.dim_level ?? 40));
  n.style.opacity = String(1 - i / 100), n.dataset.state = s;
}
const gt = "evac.player.token", Mt = "evac.player.config";
function qs() {
  try {
    return localStorage.getItem(gt);
  } catch {
    return null;
  }
}
function qt(s) {
  try {
    s ? localStorage.setItem(gt, s) : (localStorage.removeItem(gt), localStorage.removeItem(Mt));
  } catch {
  }
}
function Us() {
  try {
    const s = localStorage.getItem(Mt);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Ut(s) {
  try {
    localStorage.setItem(Mt, JSON.stringify(s));
  } catch {
  }
}
const I = (1n << 64n) - 1n, Vs = [
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
].map((s) => BigInt(`0x${s}`)), Js = [
  "6a09e667f3bcc908",
  "bb67ae8584caa73b",
  "3c6ef372fe94f82b",
  "a54ff53a5f1d36f1",
  "510e527fade682d1",
  "9b05688c2b3e6c1f",
  "1f83d9abfb41bd6b",
  "5be0cd19137e2179"
].map((s) => BigInt(`0x${s}`)), A = (s, t) => (s >> t | s << 64n - t) & I;
function Gs(s) {
  const t = BigInt(s.length) * 8n, e = s.length + 17 + 127 & -128, n = new Uint8Array(e);
  n.set(s), n[s.length] = 128;
  for (let o = 0; o < 16; o++) n[e - 1 - o] = Number(t >> BigInt(8 * o) & 0xffn);
  const i = [...Js], r = new Array(80);
  for (let o = 0; o < e; o += 128) {
    for (let g = 0; g < 16; g++) {
      let k = 0n;
      for (let D = 0; D < 8; D++) k = k << 8n | BigInt(n[o + g * 8 + D]);
      r[g] = k;
    }
    for (let g = 16; g < 80; g++) {
      const k = A(r[g - 15], 1n) ^ A(r[g - 15], 8n) ^ r[g - 15] >> 7n, D = A(r[g - 2], 19n) ^ A(r[g - 2], 61n) ^ r[g - 2] >> 6n;
      r[g] = r[g - 16] + k + r[g - 7] + D & I;
    }
    let [c, l, h, d, u, p, m, b] = i;
    for (let g = 0; g < 80; g++) {
      const k = A(u, 14n) ^ A(u, 18n) ^ A(u, 41n), D = u & p ^ ~u & I & m, _t = b + k + D + Vs[g] + r[g] & I, Ce = A(c, 28n) ^ A(c, 34n) ^ A(c, 39n), Ae = c & l ^ c & h ^ l & h, Me = Ce + Ae & I;
      b = m, m = p, p = u, u = d + _t & I, d = h, h = l, l = c, c = _t + Me & I;
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
const P = (1n << 255n) - 19n, Vt = (1n << 252n) + 27742317777372353535851937790883648493n, y = (s, t = P) => {
  const e = s % t;
  return e >= 0n ? e : e + t;
};
function F(s, t, e = P) {
  let n = 1n;
  for (s = y(s, e); t > 0n; )
    t & 1n && (n = n * s % e), s = s * s % e, t >>= 1n;
  return n;
}
const xe = (s) => F(s, P - 2n), Ee = y(-121665n * xe(121666n)), Ys = F(2n, (P - 1n) / 4n), Ks = [0n, 1n, 1n, 0n];
function vt(s, t) {
  const [e, n, i, r] = s, [a, o, c, l] = t, h = y((n - e) * (o - a)), d = y((n + e) * (o + a)), u = y(2n * Ee * r * l), p = y(2n * i * c), m = d - h, b = p - u, g = p + u, k = d + h;
  return [y(m * b), y(g * k), y(b * g), y(m * k)];
}
function Jt(s, t) {
  let e = Ks, n = s;
  for (; t > 0n; )
    t & 1n && (e = vt(e, n)), n = vt(n, n), t >>= 1n;
  return e;
}
const yt = (s) => s.reduceRight((t, e) => t << 8n | BigInt(e), 0n);
function bt(s) {
  if (s.length !== 32) return null;
  const t = (s[31] & 128) !== 0, e = s.slice();
  e[31] &= 127;
  const n = yt(e);
  if (n >= P) return null;
  const i = y(n * n), r = y(i - 1n), a = y(Ee * i + 1n);
  let o = y(r * F(a, 3n) * F(r * F(a, 7n), (P - 5n) / 8n));
  const c = y(a * o * o);
  if (c === y(-r)) o = y(o * Ys);
  else if (c !== r) return null;
  return o === 0n && t ? null : ((o & 1n) === 1n ? t || (o = P - o) : t && (o = P - o), [o, n, 1n, y(o * n)]);
}
function Gt(s) {
  const t = xe(s[2]), e = y(s[0] * t), n = y(s[1] * t), i = new Uint8Array(32);
  let r = n;
  for (let a = 0; a < 32; a++)
    i[a] = Number(r & 0xffn), r >>= 8n;
  return e & 1n && (i[31] |= 128), i;
}
const Zs = bt(Uint8Array.from([88, ...new Array(31).fill(102)]));
function Xs(s, t, e) {
  if (e.length !== 64 || s.length !== 32) return !1;
  const n = bt(s), i = bt(e.slice(0, 32)), r = yt(e.slice(32));
  if (!n || !i || r >= Vt) return !1;
  const a = Gs(Uint8Array.from([...e.slice(0, 32), ...s, ...t])), o = y(yt(a), Vt), c = Gt(Jt(Zs, r)), l = Gt(vt(i, Jt(n, o)));
  return c.every((h, d) => h === l[d]);
}
function Yt(s) {
  const t = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4), e = atob(t);
  return Uint8Array.from(e, (n) => n.charCodeAt(0));
}
function Tt(s, t) {
  if (!t || typeof t.m != "string" || typeof t.s != "string") return null;
  const e = new TextEncoder().encode(t.m);
  for (const n of s)
    try {
      if (Xs(Yt(n), e, Yt(t.s))) return JSON.parse(t.m);
    } catch {
    }
  return null;
}
const Qs = ["staff_alert", "attention", "shelter_in_place", "evacuate"], ti = {
  normal: 0,
  all_clear: 1,
  staff_alert: 2,
  attention: 3,
  shelter_in_place: 4,
  evacuate: 5
}, ei = 10 * 6e4, Kt = "evac.player.evac", Zt = "evac.player.evacbundle", et = (s) => Qs.includes(s);
function wt(s, t) {
  return s.state === "all_clear" && s.clear_until && Date.parse(s.clear_until) <= t ? "normal" : s.state;
}
function ni(s, t, e) {
  if (!s) return !0;
  if (t.seq < s.seq || t.seq === s.seq && t.v === s.v) return !1;
  if (!et(t.state) && et(wt(s, e))) {
    const i = t.issued ?? (t.sig ? Number(JSON.parse(t.sig.m).ia) * 1e3 : e);
    if (e - i > ei) return !1;
  }
  return !0;
}
function si(s, t) {
  const e = s.map((a) => a.st === "all_clear" && a.cu && a.cu <= t ? { st: "normal", d: !1 } : a), n = e.some((a) => et(a.st) && !a.d);
  let i = { st: "normal", d: !1 };
  const r = (a) => [ti[a.st] ?? 0, a.d ? 0 : 1];
  for (const a of n ? e.filter((o) => !o.d) : e) {
    const [o, c] = r(a), [l, h] = r(i);
    (o > l || o === l && c > h) && (i = a);
  }
  return i;
}
function St(s, t, e, n = []) {
  const i = s.stages[t], r = s.directions[n.slice().sort().join(",")];
  return {
    event: s.event,
    screen: s.screen,
    seq: 0,
    v: "",
    state: t,
    label: s.labels[t] ?? i?.label ?? t,
    drill: e,
    drill_text: s.drill_text,
    since: null,
    clear_until: null,
    takeover: i?.takeover ?? !1,
    role: s.role,
    model: s.model,
    guidance: r ? { kind: r.kind, arrow: r.arrow, text: r.text, target: r.target } : { kind: s.model === "zones" ? "follow_staff" : "none", arrow: null, text: "", target: "" },
    direction: r?.direction ?? "",
    texts: i?.texts ?? [],
    rotate_seconds: i?.rotate_seconds ?? 8,
    pictograms_only: i?.pictograms_only ?? !1,
    sound: i?.sound ?? "none",
    sound_every: i?.sound_every ?? 30,
    speech: i?.speech ?? "",
    layout: i?.layout ?? null
  };
}
function ii(s, t, e) {
  const n = Tt(t.keys, s);
  if (!n || n.e !== t.event || typeof n.seq != "number" || !n.ev || typeof n.ev.st != "string")
    return null;
  const i = [n.ev, ...Object.values(n.z ?? {})];
  if (n.is && i.some((o) => !et(o.st) && o.st !== "normal")) return null;
  const r = si([n.ev, ...t.zones.map((o) => n.z?.[o]).filter((o) => !!o)], e), a = i.find((o) => o.st === r.st && o.cu);
  return {
    ...St(t, r.st, r.d, n.b ?? []),
    seq: n.seq,
    v: `fb-${n.seq}-${r.st}-${r.d}`,
    clear_until: a?.cu ? new Date(a.cu).toISOString() : null,
    issued: n.ia * 1e3,
    sig: s,
    via: "fallback"
  };
}
function Xt(s) {
  const t = s.texts.length ? [...s.texts] : [""];
  return s.pictograms_only && s.texts.length && t.push(""), t;
}
function Qt(s, t) {
  return s === "evacuate" ? t && ["left", "back_left", "ahead_left"].includes(t) ? "E001" : "E002" : s === "all_clear" ? "check" : "W001";
}
function te(s) {
  try {
    const t = localStorage.getItem(s);
    return t ? JSON.parse(t) : null;
  } catch {
    return null;
  }
}
function ee(s, t) {
  try {
    localStorage.setItem(s, JSON.stringify(t));
  } catch {
  }
}
class ri {
  constructor(t, e = document) {
    this.opts = t, this.payload = te(Kt), this.bundle = te(Zt), this.rendered = null, this.rotation = null, this.sound = null, this.expiry = null, this.frame = 0, this.shownKey = "", this.layer = e.createElement("div"), this.layer.id = "evac-layer", this.layer.hidden = !0, e.body.appendChild(this.layer);
  }
  t(t) {
    return this.opts.strings[t] ?? t;
  }
  setBundle(t) {
    t && (this.bundle = t, ee(Zt, t));
  }
  /** Offer a payload from any path; returns whether it was taken. */
  offer(t, e) {
    return !t || this.bundle && t.event !== this.bundle.event && this.payload && t.event !== this.payload.event || e === "fallback" && !t.sig || !ni(this.payload, t, this.opts.now()) ? !1 : (this.payload = { ...t, via: e }, ee(Kt, this.payload), this.render(!0), !0);
  }
  /** A signed event-wide message from a fallback origin. */
  offerFallback(t) {
    if (!this.bundle) return !1;
    const e = ii(t, this.bundle, this.opts.now());
    return e ? this.offer(e, "fallback") : !1;
  }
  /** Self-test (ADR-0034): render every stage off screen (own layout and built-in), check the signature of the
   *  current message, the audio permission and each fallback origin. ``visible`` also shows a test frame for
   *  ``seconds`` (never over a running alarm). */
  async selfTest(t) {
    const e = this.opts.now(), n = this.bundle, i = {}, r = document.createElement("div");
    r.className = "evac-selftest-host", r.setAttribute("aria-hidden", "true"), document.body.append(r);
    try {
      for (const u of Object.keys(n?.stages ?? {})) i[u] = this.testStage(r, St(n, u, !1));
    } finally {
      r.remove();
    }
    const a = this.payload?.sig, o = a ? n && Tt(n.keys, a) ? "ok" : "invalid" : "missing", c = {};
    for (const u of n?.fallback_origins ?? []) c[u] = await ai(u, n, t.fetcher);
    const l = this.opts.audio().enabled ? await $e() : "off";
    let h = !1;
    return t.visible && n && !this.active && (h = !0, this.showTest(n, t.seconds)), {
      ok: !!n && !Object.values(i).some((u) => u.startsWith("error")) && o !== "invalid" && !Object.values(c).some((u) => u !== "ok"),
      at: e,
      ms: Math.round(this.opts.now() - e),
      bundle: n?.version ?? null,
      keys: n?.keys.length ?? 0,
      signature: o,
      stages: i,
      audio: l,
      origins: c,
      visible: h
    };
  }
  testStage(t, e) {
    const n = document.createElement("div");
    n.className = "evac-takeover", t.replaceChildren(n);
    let i = "ok";
    if (e.layout) {
      let r = "";
      try {
        const a = this.opts.context();
        dt(n, e.layout, {
          ...a,
          vars: this.vars(e, e.texts[0] ?? ""),
          onError: (o, c) => {
            r = r || `${o}: ${String(c)}`;
          }
        }).destroy();
      } catch (a) {
        r = String(a);
      }
      r && (i = `fallback (${r})`.slice(0, 120));
    }
    try {
      if (n.replaceChildren(this.fallbackLayout(e, e.state, e.texts[0] ?? "")), !n.querySelector("svg")) return "error: no sign";
    } catch (r) {
      return `error: ${String(r)}`.slice(0, 120);
    }
    return i;
  }
  showTest(t, e) {
    const n = {
      ...St(t, "evacuate", !0),
      label: this.t("Self-test"),
      texts: [this.t("This is a test. There is no alarm.")],
      drill_text: this.t("TEST")
    };
    this.stop(), this.layer.replaceChildren(), this.layer.hidden = !1, this.layer.dataset.mode = "test";
    const i = document.createElement("div");
    i.className = "evac-takeover evac-stage-test", i.append(this.fallbackLayout(n, "evacuate", n.texts[0])), this.layer.append(i), this.drawDrill(n), this.expiry = setTimeout(() => this.render(!0), Math.max(2, Math.min(e || 5, 60)) * 1e3);
  }
  /** Whether the screen is taken over (normal content is hidden). */
  get active() {
    const t = this.payload;
    if (!t) return !1;
    const e = wt(t, this.opts.now());
    return t.role === "participant" && t.takeover && e !== "normal";
  }
  /** Draw the current payload. ``force`` redraws even when nothing visible changed (a new message). */
  render(t = !1) {
    const e = this.payload, n = this.opts.now(), i = e ? wt(e, n) : "normal", r = e?.role ?? "participant", o = !!e && r !== "excluded" && i !== "normal" && i !== "staff_alert" ? e.takeover && r === "participant" ? "takeover" : "banner" : "none", c = `${o}|${e?.seq}|${e?.v}|${i}`;
    if (!t && c === this.shownKey || (this.shownKey = c, this.stop(), this.layer.replaceChildren(), this.layer.hidden = o === "none", this.layer.dataset.mode = o, this.layer.dataset.state = i, document.documentElement.classList.toggle("evac-active", o === "takeover"), this.opts.onChange?.(o === "takeover"), !e)) return;
    if (e.state === "all_clear" && e.clear_until) {
      const h = Date.parse(e.clear_until) - n;
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
    const n = document.createElement("div");
    n.className = `evac-takeover evac-stage-${e}`, this.layer.append(n);
    const i = Xt(t), r = () => {
      const o = i[this.frame % i.length];
      if (t.layout) {
        let c = !1;
        try {
          this.rendered?.destroy(), n.replaceChildren();
          const l = this.opts.context();
          this.rendered = dt(n, t.layout, {
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
      return n.replaceChildren(this.fallbackLayout(t, e, o)), !0;
    }, a = r();
    return i.length > 1 && (this.rotation = setInterval(
      () => {
        this.frame += 1, r();
      },
      Math.max(3, t.rotate_seconds || 8) * 1e3
    )), a;
  }
  /** The built-in layout every screen keeps in its code: sign(s), stage, text, direction. */
  fallbackLayout(t, e, n) {
    const i = document.createElement("div");
    i.className = `evac-fb evac-fb-${e}`;
    const r = document.createElement("div");
    r.className = "evac-fb-signs";
    const a = t.guidance.arrow, o = Qt(e, a);
    r.innerHTML = (o === "check" ? Qe() : G(o, "ahead")) + (e === "evacuate" && a ? G("arrow", a) : "");
    const c = document.createElement("h1");
    if (c.className = "evac-fb-label", c.textContent = t.label, i.append(r, c), n) {
      const h = document.createElement("p");
      h.className = "evac-fb-text", h.textContent = n, i.append(h);
    }
    const l = t.direction || this.followStaff(t);
    if (l && e === "evacuate") {
      const h = document.createElement("p");
      h.className = "evac-fb-dir", h.textContent = l, i.append(h);
    }
    return i;
  }
  drawBanner(t, e) {
    const n = document.createElement("div");
    n.className = `evac-banner evac-stage-${e}`, n.setAttribute("role", "alert");
    const i = Xt(t).filter(Boolean), r = document.createElement("span");
    r.className = "evac-banner-icon", r.innerHTML = G(e === "evacuate" ? Qt(e, t.guidance.arrow) : "W001");
    const a = document.createElement("strong");
    a.textContent = t.label;
    const o = document.createElement("span");
    o.className = "evac-banner-text", o.textContent = i[0] ?? "", n.append(r, a, o), this.layer.append(n), i.length > 1 && (this.rotation = setInterval(
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
    const n = (r) => {
      t.sound && t.sound !== "none" && oi(t.sound, e.volume), t.speech && this.opts.speaker.say(`evac:${t.seq}:${t.v}:${r}`, t.speech, {
        volume: e.volume,
        delayMs: t.sound !== "none" ? 2600 : 0
      });
    };
    if ((!t.sound || t.sound === "none") && !t.speech) return;
    let i = 0;
    n(i), this.sound = setInterval(() => n(++i), Math.max(5, t.sound_every || 30) * 1e3);
  }
  stop() {
    this.rotation && clearInterval(this.rotation), this.sound && clearInterval(this.sound), this.expiry && clearTimeout(this.expiry), this.rotation = this.sound = this.expiry = null, this.rendered?.destroy(), this.rendered = null, this.frame = 0;
  }
}
async function $e() {
  if (typeof AudioContext > "u") return "unavailable";
  let s;
  try {
    s = new AudioContext();
  } catch {
    return "unavailable";
  }
  try {
    return s.state === "suspended" && await Promise.race([s.resume(), new Promise((t) => setTimeout(t, 300))]), s.state === "running" ? "running" : "suspended";
  } finally {
    s.close().catch(() => {
    });
  }
}
async function ai(s, t, e = fetch) {
  const n = typeof AbortController < "u" ? new AbortController() : null, i = setTimeout(() => n?.abort(), 3e3);
  try {
    const r = await e(`${s}/evac/${t.event}/state`, { cache: "no-store", signal: n?.signal });
    if (!r.ok) return `http ${r.status}`;
    const a = await r.json();
    return a.sig && Tt(t.keys, a.sig) ? "ok" : "bad signature";
  } catch {
    return "unreachable";
  } finally {
    clearTimeout(i);
  }
}
function oi(s, t = 100) {
  if (s !== "siren") return ye(s, t);
  if (typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const n = e.createGain();
  n.gain.value = Math.max(0, Math.min(1, t / 100)) * 0.35, n.connect(e.destination);
  for (let i = 0; i < 3; i++) {
    const r = e.createOscillator();
    r.type = "sawtooth";
    const a = e.currentTime + i * 0.8;
    r.frequency.setValueAtTime(500, a), r.frequency.linearRampToValueAtTime(1100, a + 0.7), r.connect(n), r.start(a), r.stop(a + 0.75);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, 3e3);
}
const ne = 3e3;
function U(s) {
  document.documentElement.dataset.boot = s;
}
const se = 6e4, ci = 36e5, li = 3e5, ie = 15e3, hi = 6e4, di = 3e3;
class ui {
  constructor(t, e) {
    this.env = t, this.root = e, this.clock = new Pe(), this.speaker = new es(), this.widgetData = new Rn(ns()), this.dataRefresher = null, this.overlays = new ts(this.speaker), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.program = null, this.shown = "", this.timer = null, this.refresher = null, this.housekeeping = null, this.displayState = "on", this.recovered = "", this.lastTick = Date.now(), this.reloadAtNextSlide = "", this.lastDailyReload = "", this.evac = null, this.evacAck = "", this.evacAudio = "", this.evacTimer = null, this.fallbackTimer = null, this.display = new Hn(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    U("boot"), this.recovered = Ns(), E("info", `player ${this.env.version} started (${navigator.userAgent})`), this.recovered && E("warn", this.recovered);
    const t = qs();
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
      e = await Ne(this.env.api, Wt({
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
    const n = async () => {
      try {
        const i = await Ie(this.env.api, e);
        if (i.status === "paired")
          return qt(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        w(String(i));
      }
      setTimeout(() => {
        n();
      }, ne);
    };
    setTimeout(() => {
      n();
    }, ne);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = Us();
    this.evac = this.evac ?? this.makeEvac(t), e && ct(this.evac.layer, e.display ?? {}), this.evac.render(!0), U(e ? "play: cached config" : "play: no cached config"), e && (this.config = e, this.bundle = ut(), this.program = ft(), this.applySettings(), this.bundle && Ft({ ...this.bundle.theme, fonts_css: this.bundle.fonts_css }, t).catch((n) => w(String(n))), this.show(), U("play: shown from cache"));
    try {
      const n = Date.now();
      this.config = await Nt(this.env.api, t), this.clock.add(n, Date.now(), this.config.server_time), this.lastSync = Date.now(), Ut(this.config);
    } catch (n) {
      if (n instanceof $) return this.unpair();
      w(String(n)), this.config = e;
    }
    this.applySettings(), this.bundle = this.bundle ?? ut(), this.program = this.program ?? ft(), await this.loadContent(t), await this.loadProgram(t), this.show(), this.loadEvac(t), $e().then((n) => {
      this.evacAudio = n;
    }), this.evacTimer = setInterval(() => {
      this.loadEvac(t);
    }, hi), this.fallbackTimer = setInterval(() => {
      this.pollFallback();
    }, di), U("play: online"), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, ci), this.loadWidgetData(t), this.dataRefresher = setInterval(() => {
      this.loadWidgetData(t);
    }, li), this.housekeeping = setInterval(() => this.tick(), ie), this.conn = new Oe({
      api: this.env.api,
      ws: ks(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => Wt({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline",
        displayState: this.displayState,
        capture: ke(),
        recovered: this.recovered,
        evacAck: this.evacAck,
        evacBundle: this.evac?.bundle?.version,
        evacAudio: this.evacAudio
      }),
      onMessage: (n) => {
        this.handle(n, t);
      },
      onTransport: (n) => {
        n !== this.transport && (E("info", `connection: ${n}`), (this.transport === "offline" || this.transport === "connecting") && this.loadEvac(t)), this.transport = n;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (n) => {
        this.lastSync = n;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch (E("info", `message: ${t.type}`), t.type) {
      case "config.changed":
        try {
          this.config = await Nt(this.env.api, e), Ut(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), this.applySettings();
          const n = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(e), await this.loadProgram(e), (`${this.bundle?.version}/${this.program?.version}` !== n || this.slide === "idle") && (this.shown = "", this.show());
        } catch (n) {
          n instanceof $ && this.unpair();
        }
        break;
      case "identify": {
        const n = this.config?.screen.name ?? "", i = [this.config?.screen.venue, this.config?.screen.zone, this.config?.screen.room].filter(Boolean).join(" · ");
        this.display.identify(
          n,
          `${i}${i ? " · " : ""}${this.transport}`,
          Number(t.data.seconds) || 10
        );
        break;
      }
      case "program.changed": {
        const n = this.program?.version;
        await this.loadProgram(e), this.program?.version !== n && (this.shown = "", this.show());
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
      case "evac.selftest": {
        if (!this.evac) break;
        await this.loadEvac(e);
        const n = await this.evac.selfTest({ visible: !!t.data.visible, seconds: Number(t.data.seconds) || 5 });
        this.evacAudio = n.audio, E("info", `evacuation self-test: ${n.ok ? "ok" : "problems"}`), await fetch(`${this.env.api}evacuation/selftest/`, {
          method: "POST",
          headers: { Authorization: `Screen ${e}`, "Content-Type": "application/json" },
          body: JSON.stringify(n)
        }).catch((i) => w(`self-test report: ${String(i)}`));
        break;
      }
      case "reload":
        X("requested by staff", { force: !0 });
        break;
      case "clear_cache":
        await Fs(), X("cache cleared by staff", { force: !0 });
        break;
      case "test_pattern": {
        const n = this.config?.screen.name ?? "", i = `${Math.round(innerWidth * devicePixelRatio)}×${Math.round(innerHeight * devicePixelRatio)}`;
        this.display.testPattern(
          n,
          [`${i} · DPR ${devicePixelRatio}`, `${this.env.version} · ${this.transport}`],
          Number(t.data.seconds) || 30
        );
        break;
      }
      case "screenshot":
        try {
          await ot(this.env.api, e, "screenshot", await Os());
        } catch (n) {
          w(`screenshot: ${String(n)}`), await ot(this.env.api, e, "screenshot", { error: String(n).slice(0, 280) }).catch(() => {
          });
        }
        break;
      case "logs":
        await ot(this.env.api, e, "logs", { lines: $s() }).catch((n) => w(String(n)));
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await qn(this.env.api, t) ?? this.bundle;
    } catch (n) {
      if (n instanceof $) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await bs(this.env.api, t);
    e && await Ft(e, t).catch((n) => w(String(n))), this.bundle && Jn(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await Gn(this.env.api, t);
    } catch (n) {
      n instanceof $ && this.unpair();
    }
    const e = [...this.program?.entries ?? [], ...this.program?.overlays ?? []].map((n) => n.speech).filter((n) => !!n);
    e.length && zt(e);
  }
  /** Custom widget rows: "data" elements redraw themselves when the store changes. */
  async loadWidgetData(t) {
    try {
      await ss(this.env.api, t, this.widgetData);
    } catch (e) {
      e instanceof $ && this.unpair();
    }
  }
  // ---------------------------------------------------------------- evacuation (ADR-0033/0034)
  makeEvac(t) {
    return new ri({
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
        nonce: Dt(),
        data: this.widgetData,
        onError: (e, n) => w(`evac ${e}: ${String(n)}`)
      }),
      onRendered: (e, n) => {
        this.evacAck = `${e.seq}:${e.v}`.slice(0, 40), E("info", `evacuation: ${e.state}${e.drill ? " (drill)" : ""} #${e.seq} via ${e.via ?? "cache"}`), fetch(`${this.env.api}evacuation/ack/`, {
          method: "POST",
          headers: { Authorization: `Screen ${t}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            seq: e.seq,
            v: e.v,
            state: e.state,
            drill: e.drill,
            rendered_at: n.rendered_at,
            issued: e.issued ?? null,
            via: e.via ?? "cache",
            fallback: n.fallback
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
      const n = await e.json();
      if (!n.enabled) return;
      this.evac?.setBundle(n.bundle ?? null), this.evac?.offer(n.payload, "fetch");
      const i = Object.values(n.bundle?.stages ?? {}).map((r) => r.speech).filter((r) => !!r);
      i.length && zt(i);
    } catch {
    }
  }
  /** Without a connection, ask the fallback origins (secondary node, bridge) for the signed alarm state. */
  async pollFallback() {
    const t = this.evac?.bundle;
    if (!(this.transport !== "offline" || !t?.fallback_origins.length))
      for (const e of t.fallback_origins)
        try {
          const n = await fetch(`${e}/evac/${t.event}/state`, { cache: "no-store" });
          if (!n.ok) continue;
          const i = await n.json();
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
      groups: e.groups.map((n) => n.name)
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
    let n = null, i, r = "idle", a = null;
    if (this.program && this.bundle) {
      if (a = ps(this.program, this.vars(), e), a?.message)
        n = this.program.messages?.[a.message] ?? null, r = `${a.entry}|message`, this.slide = `${a.entry} message`;
      else if (a?.layout) {
        const p = this.bundle.layouts.find((m) => m.id === a?.layout);
        p && (n = p.data, i = p.variables, r = `${a.entry}|${p.id}|${p.version}|${a.count > 1 ? a.start : ""}`, this.slide = `${p.key} v${p.version} (${a.entry} ${a.index + 1}/${a.count})`);
      }
      const d = [ms(this.program, e, a), Zn(this.program.overlays, e)].filter((p) => p !== null), u = Math.max(5, Math.min(se, (d.length ? Math.min(...d) : e + se) - e));
      this.timer = setTimeout(() => this.show(), u);
    } else {
      const d = Vn(this.bundle);
      d && (n = d.data, i = d.variables, r = `default|${d.id}|${d.version}`, this.slide = `${d.key} v${d.version}`);
    }
    const o = { enabled: t.display?.audio !== !1, volume: t.display?.volume ?? 100 }, c = !!this.evac?.active, l = c || !!a && (a.entry.startsWith("announcement:") || a.entry.startsWith("evacuation"));
    this.overlays.update(this.program?.overlays, e, { hidden: l, audio: o });
    const h = a ? this.program?.entries.find((d) => d.id === a?.entry) : void 0;
    if (h?.speech && o.enabled && !c && this.speaker.say(`${h.id}@${a?.start ?? 0}`, h.speech, {
      volume: o.volume,
      delayMs: ve
    }), r !== this.shown && !(this.reloadAtNextSlide && this.shown && X(this.reloadAtNextSlide))) {
      this.reloadAtNextSlide = "", this.shown = r, E("info", `showing ${this.slide}`);
      try {
        if (!n || !this.bundle) throw new Error("nothing to show");
        this.display.layout(n, {
          vars: this.vars(),
          now: () => this.clock.now(),
          timezone: t.event.timezone,
          assets: this.bundle.assets,
          fonts: this.bundle.fonts,
          reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
          audio: o,
          nonce: Dt(),
          data: this.widgetData,
          onError: (d, u) => w(`${d}: ${String(u)}`),
          onLog: (d, u) => E("info", `${d}: ${u}`)
        }, i);
      } catch (d) {
        n && w(`render failed, showing the idle slide: ${String(d)}`), this.slide = "idle", this.display.idle(t);
      }
      this.overlays.attach(this.root);
    }
  }
  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  applySettings() {
    const t = this.config?.display ?? {};
    ct(this.root, t), this.evac && ct(this.evac.layer, t), this.updateDisplayState();
  }
  updateDisplayState() {
    const t = this.config?.display ?? {}, e = this.evac?.active ? "on" : Ws(t, jt(this.clock.now(), this.config?.event.timezone));
    e !== this.displayState && E("info", `display ${e}`), this.displayState = e, Hs(e, t);
  }
  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  tick() {
    const t = Date.now(), e = t - this.lastTick > ie * 3;
    this.lastTick = t, Is(t), this.updateDisplayState(), e && (E("warn", "timers were stalled; resynchronising"), this.shown = "", this.show());
    const n = this.config?.display?.daily_reload, i = jt(this.clock.now(), this.config?.event.timezone);
    n && i === n && this.lastDailyReload !== i && performance.now() > 36e5 && (this.lastDailyReload = i, this.reloadAtNextSlide = "daily reload"), Ds() && !this.reloadAtNextSlide && (this.reloadAtNextSlide = "memory pressure");
  }
  unpair() {
    this.housekeeping && clearInterval(this.housekeeping), this.housekeeping = null, this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.dataRefresher && clearInterval(this.dataRefresher), this.evacTimer && clearInterval(this.evacTimer), this.fallbackTimer && clearInterval(this.fallbackTimer), this.timer = this.refresher = this.dataRefresher = this.evacTimer = this.fallbackTimer = null, is(), this.widgetData.set({}), Yn(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, qt(null), Un(), this.pair();
  }
}
function fi() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((s) => w(String(s)));
}
if (typeof document < "u" && document.getElementById("player")) {
  As(), Ps(), Cs(() => X("50 errors within a minute")), fi();
  const s = Ss();
  new ui(s, document.getElementById("player")).boot();
}
export {
  ui as Player
};
