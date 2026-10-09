// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var _t = Object.defineProperty;
var Rt = (s, t, e) => t in s ? _t(s, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : s[t] = e;
var C = (s, t, e) => Rt(s, typeof t != "symbol" ? t + "" : t, e);
class S extends Error {
}
async function M(s, t, e = {}) {
  const n = new AbortController(), i = setTimeout(() => n.abort(), e.timeout ?? 1e4), r = new Headers(e.headers);
  r.set("Accept", "application/json"), e.body && r.set("Content-Type", "application/json"), e.token && r.set("Authorization", `Screen ${e.token}`);
  try {
    const o = await fetch(s + t, {
      ...e,
      headers: r,
      signal: n.signal,
      cache: "no-store",
      credentials: "omit"
    });
    if (o.status === 401) throw new S("token rejected");
    if (!o.ok) throw new Error(`HTTP ${o.status}`);
    return await o.json();
  } finally {
    clearTimeout(i);
  }
}
const Ft = (s, t) => M(s, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), Lt = (s, t) => M(s, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), rt = (s, t) => M(s, "config/", { token: t });
class Bt {
  constructor() {
    this.samples = [], this.offset = 0;
  }
  add(t, e, n) {
    const i = e - t;
    i < 0 || !Number.isFinite(n) || (this.samples.push({ offset: n * 1e3 - (t + e) / 2, rtt: i }), this.samples.length > 8 && this.samples.shift(), this.offset = this.samples.reduce((r, o) => o.rtt < r.rtt ? o : r).offset);
  }
  now() {
    return Date.now() + this.offset;
  }
}
const Wt = 3e4, jt = 3e5;
class Ht {
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
    this.backoff = Math.min(this.backoff * 2, Wt), setTimeout(() => !this.stopped && t(), e);
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > jt ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        if (t.status === 401) throw new S("token rejected");
        if (!t.ok || !t.body) throw new Error(`SSE HTTP ${t.status}`);
        this.setTransport("sse"), this.backoff = 1e3;
        const e = t.body.getReader(), n = new TextDecoder();
        let i = "";
        for (; ; ) {
          const { value: r, done: o } = await e.read();
          if (o) break;
          i += n.decode(r, { stream: !0 });
          let a;
          for (; (a = i.indexOf(`

`)) >= 0; ) {
            const c = i.slice(0, a);
            i = i.slice(a + 2);
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
        t instanceof S ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
      }
    }
  }
  async poll() {
    if (!(this.stopped || this.maybeBackToWebSocket()))
      try {
        const t = await M(
          this.o.api,
          `poll/?since=${this.seq}&wait=10`,
          { token: this.o.token, timeout: 2e4 }
        );
        this.setTransport("poll"), this.backoff = 1e3, t.messages.forEach((e) => this.deliver(e)), this.poll();
      } catch (t) {
        if (t instanceof S) {
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
    M(this.o.api, "heartbeat/", {
      method: "POST",
      token: this.o.token,
      body: JSON.stringify({ data: t })
    }).then((e) => this.ack(e.server_time)).catch((e) => {
      e instanceof S ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function N(s) {
  return s ? s.startsWith("token:") ? `var(--evac-color-${s.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(s) || s === "transparent" ? s : "" : "";
}
function qt(s, t) {
  return s ? s === "token:heading" ? "var(--evac-font-heading)" : s === "token:body" ? "var(--evac-font-body)" : t.fonts[s] ?? "" : "";
}
function Ut(s, t, e) {
  const n = s.style;
  if (!t) return;
  const i = (r, o) => {
    o && n.setProperty(r, o);
  };
  i("color", N(t.color)), i("background", N(t.background)), t.borderWidth && n.setProperty("border", `${t.borderWidth / 10}cqh solid ${N(t.borderColor) || "currentColor"}`), t.radius !== void 0 && n.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && n.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && n.setProperty("opacity", String(t.opacity)), i("font-family", qt(t.fontFamily, e)), t.fontSize && n.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && n.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && n.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && n.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && n.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && n.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && n.setProperty("box-shadow", "var(--evac-shadow)");
}
function Jt(s, t, e) {
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
function Gt(s) {
  const t = [];
  let e = "", n = "";
  for (const i of s)
    n ? (i === n && (n = ""), e += i) : i === '"' || i === "'" ? (n = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function Vt(s) {
  if (!s) return "";
  const t = s.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function ot(s, t, e) {
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
function b(s) {
  return s == null ? "" : Array.isArray(s) ? s.map(b).join(", ") : s instanceof Date ? s.toISOString() : typeof s == "object" ? s.name ?? "" : String(s);
}
function Yt(s, t, e) {
  const [n, ...i] = t.split(":"), r = Vt(i.join(":")), o = () => s instanceof Date ? s : new Date(String(s));
  switch (n.trim()) {
    case "upper":
      return b(s).toUpperCase();
    case "lower":
      return b(s).toLowerCase();
    case "title":
      return b(s).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = b(s);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return b(s) === "" ? r : s;
    case "date":
      return isNaN(o().getTime()) ? "" : ot(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : ot(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(s) ? s.map(b).join(r || ", ") : b(s);
    default:
      return s;
  }
}
function z(s, t, e = {}) {
  const [n, ...i] = Gt(s);
  let r = Jt(t, n, e);
  for (const o of i) r = Yt(r, o, e);
  return r;
}
function Xt(s) {
  return Array.isArray(s) ? s.length > 0 : !(s == null || s === !1 || s === "" || s === 0);
}
function B(s, t, e = {}) {
  const n = s.trim();
  if (!n) return !0;
  if (n.startsWith("not ")) return !B(n.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(n);
  if (i) {
    const r = b(z(i[1], t, e)), o = b(z(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return Xt(z(n.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const Kt = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function Zt(s, t, e = {}) {
  if (!s || !s.includes("{{") && !s.includes("{%")) return s ?? "";
  const n = s.split(Kt);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < n.length; ) {
      const c = n[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(h)) return [a, h];
        if (h === "if") {
          const d = B(l[2], t, e), [u, m] = r(["else", "endif"]);
          let p = "";
          m === "else" && (p = r(["endif"])[0]), a += d ? u : p;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += b(z(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
const Qt = `(() => {
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
function at(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function te(s, t, e, n = "") {
  const i = at(t), r = e ? ` ${e}` : "", o = [
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
  ].join("; "), a = String(s.css ?? "").replace(/<\/style/gi, "<\\/style"), c = String(s.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${at(o)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${n}</style><style nonce="${i}">${a}</style><script nonce="${i}">${Qt}<\/script></head><body>${String(s.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function ee(s) {
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
function ne(s = document) {
  const t = s.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
var A = /* @__PURE__ */ ((s) => (s[s.Border = -1] = "Border", s[s.Data = 0] = "Data", s[s.Function = 1] = "Function", s[s.Position = 2] = "Position", s[s.Timing = 3] = "Timing", s[s.Alignment = 4] = "Alignment", s))(A || {});
const se = [0, 1], bt = [1, 0], St = [2, 3], kt = [3, 2], ie = {
  L: se,
  M: bt,
  Q: St,
  H: kt
}, re = /^\d*$/, oe = /^[A-Z0-9 $%*+./:-]*$/, H = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", tt = 1, et = 40, ct = 3, ae = 3, P = 40, ce = 10, $t = [
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
], Et = [
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
class le {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, n, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    C(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    C(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    C(this, "modules", []);
    C(this, "types", []);
    if (this.version = t, this.ecc = e, t < tt || t > et)
      throw new RangeError("Version value out of range");
    if (i < -1 || i > 7)
      throw new RangeError("Mask value out of range");
    this.size = t * 4 + 17;
    const r = Array.from({ length: this.size }).fill(!1);
    for (let a = 0; a < this.size; a++)
      this.modules.push(r.slice()), this.types.push(r.map(() => 0));
    this.drawFunctionPatterns();
    const o = this.addEccAndInterleave(n);
    if (this.drawCodewords(o), i === -1) {
      let a = 1e9;
      for (let c = 0; c < 8; c++) {
        this.applyMask(c), this.drawFormatBits(c);
        const l = this.getPenaltyScore();
        l < a && (i = c, a = l), this.applyMask(c);
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
      this.setFunctionModule(6, n, n % 2 === 0, A.Timing), this.setFunctionModule(n, 6, n % 2 === 0, A.Timing);
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
      this.setFunctionModule(8, r, $(i, r));
    this.setFunctionModule(8, 7, $(i, 6)), this.setFunctionModule(8, 8, $(i, 7)), this.setFunctionModule(7, 8, $(i, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, $(i, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, $(i, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, $(i, r));
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
      const i = $(e, n), r = this.size - 11 + n % 3, o = Math.floor(n / 3);
      this.setFunctionModule(r, o, i), this.setFunctionModule(o, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let n = -4; n <= 4; n++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(n)), o = t + i, a = e + n;
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, A.Position);
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
          A.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, n, i = A.Function) {
    this.modules[e][t] = n, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, n = this.ecc;
    if (t.length !== O(e, n))
      throw new RangeError("Invalid argument");
    const i = Et[n[0]][e], r = $t[n[0]][e], o = Math.floor(G(e) / 8), a = i - o % i, c = Math.floor(o / i), l = [], h = ve(r);
    for (let u = 0, m = 0; u < i; u++) {
      const p = t.slice(m, m + c - r + (u < a ? 0 : 1));
      m += p.length;
      const k = we(p, h);
      u < a && p.push(0), l.push(p.concat(k));
    }
    const d = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((m, p) => {
        (u !== c - r || p >= a) && d.push(m[u]);
      });
    return d;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(G(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let n = this.size - 1; n >= 1; n -= 2) {
      n === 6 && (n = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = n - r, c = (n + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][o] && e < t.length * 8 && (this.modules[c][o] = $(t[e >>> 3], 7 - (e & 7)), e++);
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
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[r][l] === o ? (a++, a === 5 ? t += ct : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * P), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * P;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += ct : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * P), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * P;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += ae);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const n = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - n * 10) / n) - 1;
    return t += i * ce, t;
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
function E(s, t, e) {
  if (t < 0 || t > 31 || s >>> t)
    throw new RangeError("Value out of range");
  for (let n = t - 1; n >= 0; n--)
    e.push(s >>> n & 1);
}
function $(s, t) {
  return (s >>> t & 1) !== 0;
}
class nt {
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
const he = [1, 10, 12, 14], de = [2, 9, 11, 13], ue = [4, 8, 16, 16];
function xt(s, t) {
  return s[Math.floor((t + 7) / 17) + 1];
}
function Mt(s) {
  const t = [];
  for (const e of s)
    E(e, 8, t);
  return new nt(ue, s.length, t);
}
function fe(s) {
  if (!At(s))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < s.length; ) {
    const n = Math.min(s.length - e, 3);
    E(Number.parseInt(s.substring(e, e + n), 10), n * 3 + 1, t), e += n;
  }
  return new nt(he, s.length, t);
}
function pe(s) {
  if (!Ct(s))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= s.length; e += 2) {
    let n = H.indexOf(s.charAt(e)) * 45;
    n += H.indexOf(s.charAt(e + 1)), E(n, 11, t);
  }
  return e < s.length && E(H.indexOf(s.charAt(e)), 6, t), new nt(de, s.length, t);
}
function me(s) {
  return s === "" ? [] : At(s) ? [fe(s)] : Ct(s) ? [pe(s)] : [Mt(ye(s))];
}
function At(s) {
  return re.test(s);
}
function Ct(s) {
  return oe.test(s);
}
function ge(s, t) {
  let e = 0;
  for (const n of s) {
    const i = xt(n.mode, t);
    if (n.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + n.bitData.length;
  }
  return e;
}
function ye(s) {
  s = encodeURI(s);
  const t = [];
  for (let e = 0; e < s.length; e++)
    s.charAt(e) !== "%" ? t.push(s.charCodeAt(e)) : (t.push(Number.parseInt(s.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function G(s) {
  if (s < tt || s > et)
    throw new RangeError("Version number out of range");
  let t = (16 * s + 128) * s + 64;
  if (s >= 2) {
    const e = Math.floor(s / 7) + 2;
    t -= (25 * e - 10) * e - 55, s >= 7 && (t -= 36);
  }
  return t;
}
function O(s, t) {
  return Math.floor(G(s) / 8) - $t[t[0]][s] * Et[t[0]][s];
}
function ve(s) {
  if (s < 1 || s > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let n = 0; n < s - 1; n++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let n = 0; n < s; n++) {
    for (let i = 0; i < t.length; i++)
      t[i] = V(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = V(e, 2);
  }
  return t;
}
function we(s, t) {
  const e = t.map((n) => 0);
  for (const n of s) {
    const i = n ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= V(r, i));
  }
  return e;
}
function V(s, t) {
  if (s >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let n = 7; n >= 0; n--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> n & 1) * s;
  return e;
}
function be(s, t, e = 1, n = 40, i = -1, r = !0) {
  if (!(tt <= e && e <= n && n <= et) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const d = O(o, t) * 8, u = ge(s, o);
    if (u <= d) {
      a = u;
      break;
    }
    if (o >= n)
      throw new RangeError("Data too long");
  }
  for (const d of [bt, St, kt])
    r && a <= O(o, d) * 8 && (t = d);
  const c = [];
  for (const d of s) {
    E(d.mode[0], 4, c), E(d.numChars, xt(d.mode, o), c);
    for (const u of d.getData())
      c.push(u);
  }
  const l = O(o, t) * 8;
  E(0, Math.min(4, l - c.length), c), E(0, (8 - c.length % 8) % 8, c);
  for (let d = 236; c.length < l; d ^= 253)
    E(d, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((d, u) => h[u >>> 3] |= d << 7 - (u & 7)), new le(o, t, h, i);
}
function Se(s, t) {
  const {
    ecc: e = "L",
    boostEcc: n = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof s == "string" ? me(s) : Array.isArray(s) ? [Mt(s)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof s}`);
  const l = be(
    c,
    ie[e],
    i,
    r,
    o,
    n
  ), h = ke({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (h.data = h.data.map((d) => d.map((u) => !u))), t?.onEncoded?.(h), h;
}
function ke(s, t = 1) {
  if (!t)
    return s;
  const { size: e } = s, n = e + t * 2;
  s.size = n, s.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    s.data.unshift(Array.from({ length: n }, (o) => !1)), s.data.push(Array.from({ length: n }, (o) => !1));
  const i = A.Border;
  s.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    s.types.unshift(Array.from({ length: n }, (o) => i)), s.types.push(Array.from({ length: n }, (o) => i));
  return s;
}
const q = "http://www.w3.org/2000/svg";
function Tt(s, t = document) {
  const { data: e, size: n } = Se(s, { ecc: "M", border: 2 }), i = t.createElementNS(q, "svg");
  i.setAttribute("viewBox", `0 0 ${n} ${n}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(q, "rect");
  r.setAttribute("width", String(n)), r.setAttribute("height", String(n)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((h, d) => {
    h && (o += `M${d} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(q, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), i.appendChild(a), i;
}
class v extends HTMLElement {
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
    return Zt(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function $e(s, t) {
  t.style.removeProperty("font-size");
  const e = parseFloat(getComputedStyle(t).fontSize) || 16, n = () => t.scrollHeight <= s.clientHeight + 1 && t.scrollWidth <= s.clientWidth + 1;
  if (!s.clientHeight || n()) return;
  let i = Math.max(4, e * 0.1), r = e;
  for (let o = 0; o < 12 && r - i > 0.5; o++) {
    const a = (i + r) / 2;
    t.style.fontSize = `${a}px`, n() ? i = a : r = a;
  }
  t.style.fontSize = `${i}px`;
}
class Ee extends v {
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
      const i = () => $e(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class xe extends v {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-richtext";
    for (const e of this.text(this.props.text).split(/\n{2,}/)) {
      const n = document.createElement("p");
      e.split(`
`).forEach((i, r) => {
        r && n.appendChild(document.createElement("br"));
        for (const o of i.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/))
          /^\*\*[^*]+\*\*$/.test(o) ? n.appendChild(Object.assign(
            document.createElement("strong"),
            { textContent: o.slice(2, -2) }
          )) : /^\*[^*]+\*$/.test(o) ? n.appendChild(Object.assign(
            document.createElement("em"),
            { textContent: o.slice(1, -1) }
          )) : o && n.appendChild(document.createTextNode(o));
      }), t.appendChild(n);
    }
    this.replaceChildren(t);
  }
}
function Pt(s, t, e) {
  const n = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (s.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = s.urls[r], n.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = s.urls.original, i.alt = e || s.alt || "", i.decoding = "async", i.style.objectFit = t, n.appendChild(i), n;
}
class Me extends v {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(Pt(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class Ae extends v {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), n = t.map((o) => {
      const a = Pt(o, e, "");
      return a.className = "evac-slide", a;
    });
    this.replaceChildren(...n);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const o = Math.floor(this.ctx.now() / i) % n.length;
      n.forEach((a, c) => a.classList.toggle("active", c === o));
    };
    r(), this.every(500, r);
  }
}
class Ce extends v {
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
class Te extends v {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Pe extends v {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Ie extends v {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = Tt(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Ne = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class ze extends v {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Ne[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = n.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class Oe extends v {
  draw() {
    const t = String(this.props.format ?? "long"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = {
      long: { weekday: "long", day: "numeric", month: "long" },
      short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" },
      iso: { year: "numeric", month: "2-digit", day: "2-digit" }
    }, i = new Intl.DateTimeFormat(t === "iso" ? "sv-SE" : "en-GB", { ...n[t], timeZone: e }), r = document.createElement("time"), o = () => {
      r.textContent = i.format(new Date(this.ctx.now()));
    };
    o(), this.replaceChildren(r), this.every(3e4, o);
  }
}
function De(s, t) {
  const e = Math.max(0, Math.floor(s / 1e3)), n = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${n} ${n === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || n === 0 ? `${a(i + n * 24)}:${a(r)}:${a(o)}` : `${n}d ${a(i)}:${a(r)}:${a(o)}`;
}
class _e extends v {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), n = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : De(i, String(this.props.format ?? "auto"));
    };
    n(), this.replaceChildren(e), this.every(250, n);
  }
}
class Re extends v {
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
    n.setAttribute("sandbox", "allow-scripts"), n.setAttribute("referrerpolicy", "no-referrer"), n.setAttribute("allow", "autoplay"), n.setAttribute("title", this.el.name || "Code"), n.setAttribute("tabindex", "-1"), n.className = "evac-code-frame", n.srcdoc = te(e, t, location.origin, ee(this)), this.frame = n, window.addEventListener("message", this.onMessage), this.replaceChildren(n), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
  }
  /** Only the kinds of data the element asked for (and that the server let it ask for). */
  send() {
    const t = new Set(this.props.data ?? []), e = this.ctx.vars, n = {};
    if (t.has("event") && (n.event = e.event ?? null), t.has("screen") && (n.screen = e.screen ?? null), t.has("time") && (n.now = this.ctx.now(), n.timezone = this.ctx.timezone ?? ""), t.has("assets")) {
      const i = {};
      for (const r of this.props.assets ?? []) {
        const o = this.ctx.assets[r];
        if (!o) continue;
        const a = {};
        for (const [c, l] of Object.entries(o.urls)) a[c] = new URL(l, location.href).href;
        i[r] = { name: o.name, kind: o.kind, alt: o.alt, width: o.width, height: o.height, urls: a };
      }
      n.assets = i;
    }
    this.frame?.contentWindow?.postMessage({ type: "evac:data", data: JSON.parse(JSON.stringify(n)) }, "*");
  }
  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage), this.frame = null, super.disconnectedCallback();
  }
}
const Fe = {
  text: Ee,
  richtext: xe,
  image: Me,
  slideshow: Ae,
  video: Ce,
  audio: Te,
  shape: Pe,
  qr: Ie,
  clock: ze,
  countdown: _e,
  date: Oe,
  code: Re
};
function Le(s = customElements) {
  for (const [t, e] of Object.entries(Fe))
    s.get(`evac-${t}`) || s.define(`evac-${t}`, e);
}
function Be(s, t) {
  const e = t.frame;
  s.style.left = `${e.x}%`, s.style.top = `${e.y}%`, s.style.width = `${e.w}%`, s.style.height = `${e.h}%`, s.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function We(s, t) {
  const e = !s.visible_if || B(s.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (s.hidden && !t.editing || !e && !t.editing) return null;
  const n = document.createElement("div");
  n.className = `evac-el evac-el-${s.type}`, n.dataset.id = s.id, (!e || s.hidden) && n.classList.add("evac-dimmed"), Be(n, s), Ut(n, s.style, t);
  const i = s.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (n.classList.add(`evac-enter-${i.enter}`), n.style.animationDuration = `${i.duration ?? 600}ms`, n.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${s.type}`;
  if (!customElements.get(r))
    return t.onError?.(s.id, new Error(`unknown element type ${s.type}`)), t.editing ? n : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", n.appendChild(o), o.configure(s, t), n;
}
function je(s, t, e) {
  Le();
  const n = document.createElement("div");
  n.className = "evac-stage";
  const i = t.background;
  if (i?.color && (n.style.background = N(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    n.style.backgroundImage = `url("${l}")`, n.style.backgroundSize = i.fit ?? "cover", n.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = We(c, e);
    l && (r.set(c.id, l), n.appendChild(l));
  }
  s.replaceChildren(n);
  const o = () => {
    const c = s.clientWidth, l = s.clientHeight;
    if (!c || !l) return;
    const h = Math.min(c / t.width, l / t.height);
    n.style.width = `${Math.round(t.width * h)}px`, n.style.height = `${Math.round(t.height * h)}px`;
  };
  o();
  const a = typeof ResizeObserver < "u" ? new ResizeObserver(o) : null;
  return a?.observe(s), {
    stage: n,
    elements: r,
    destroy() {
      a?.disconnect(), n.remove();
    }
  };
}
function f(s, t = "", e = "") {
  const n = document.createElement(s);
  return t && (n.className = t), e && (n.textContent = e), n;
}
class He {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = f("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, n) {
    const i = this.reset();
    i.classList.add("pairing"), i.append(f("h1", "", n.title));
    const r = f("div", "pairing-box"), o = f("p", "code", t);
    o.setAttribute("aria-label", t.split("").join(" "));
    const a = Tt(e);
    a.setAttribute("role", "img"), a.setAttribute("aria-label", e), r.append(o, a);
    const c = f("ol", "steps");
    c.append(f("li", "", n.step1), f("li", "", n.step2)), i.append(r, c, f("p", "url", e), f("p", "waiting", n.waiting));
  }
  message(t, e = "") {
    const n = this.reset();
    n.classList.add("message"), n.append(f("h1", "", t)), e && n.append(f("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const n = f("p", "clock"), i = f("p", "date");
    e.append(f("h1", "event-name", t.event.name), n, i);
    const r = t.event.timezone || void 0, o = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: r }), a = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: r }), c = () => {
      const l = new Date(this.clock.now());
      n.textContent = o.format(l), i.textContent = a.format(l);
    };
    c(), this.clockTimer = setInterval(c, 1e3);
  }
  layout(t, e, n) {
    const i = this.reset();
    i.classList.add("layout");
    for (const [r, o] of Object.entries(n ?? {})) i.style.setProperty(r, o);
    this.rendered = je(i, t, e);
  }
  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(t, e, n = 30) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = f("div", "test-pattern");
    i.setAttribute("role", "img"), i.setAttribute("aria-label", t);
    const r = f("div", "tp-bars");
    for (const c of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"])
      r.appendChild(f("span", `tp-bar tp-${c}`));
    const o = f("div", "tp-ramp"), a = f("div", "tp-info");
    a.append(f("p", "tp-title", t), ...e.map((c) => f("p", "", c))), i.append(r, o, f("div", "tp-grid"), f("div", "tp-circle"), f("div", "tp-corners"), a), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), n * 1e3);
  }
  identify(t, e, n = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = f("div", "identify");
    i.setAttribute("role", "status"), i.append(f("p", "identify-name", t), f("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), n * 1e3);
  }
}
const st = "evac.player.bundle";
async function qe(s, t) {
  try {
    const e = await M(s, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(st, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof S) throw e;
    return Y();
  }
}
function Y() {
  try {
    const s = localStorage.getItem(st);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Ue() {
  try {
    localStorage.removeItem(st);
  } catch {
  }
}
function Je(s) {
  return s?.layouts.length ? s.layouts.find((t) => t.default) ?? s.layouts[0] : null;
}
async function Ge(s) {
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
const F = "evac.player.program";
async function Ve(s, t) {
  try {
    const e = await M(s, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(F, JSON.stringify(e.program)) : localStorage.removeItem(F);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof S) throw e;
    return X();
  }
}
function X() {
  try {
    const s = localStorage.getItem(F);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Ye() {
  try {
    localStorage.removeItem(F);
  } catch {
  }
}
const It = 1600;
function Xe(s, t) {
  const e = [];
  for (const n of s ?? [])
    for (const [i, r] of n.windows)
      if ((i === null || i <= t) && (r === null || t < r)) {
        e.push({ overlay: n, start: i ?? 0, end: r });
        break;
      }
  return e.sort((n, i) => i.overlay.rank - n.overlay.rank || i.start - n.start);
}
function Ke(s, t) {
  let e = null;
  for (const n of s ?? [])
    for (const [i, r] of n.windows)
      for (const o of [i, r])
        o !== null && o > t && (e === null || o < e) && (e = o);
  return e;
}
function Ze(s) {
  return {
    card: s.find((t) => t.overlay.style === "card") ?? null,
    banner: s.find((t) => t.overlay.style === "banner") ?? null,
    ticker: s.filter((t) => t.overlay.style === "ticker")
  };
}
function Qe(s) {
  const t = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(s);
  if (!t) return "#ffffff";
  const [e, n, i] = t.slice(1).map((o) => {
    const a = parseInt(o, 16) / 255;
    return a <= 0.03928 ? a / 12.92 : ((a + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * e + 0.7152 * n + 0.0722 * i > 0.179 ? "#000000" : "#ffffff";
}
function g(s, t, e = "") {
  const n = document.createElement(s);
  return n.className = t, e && (n.textContent = e), n;
}
function U(s, t) {
  s.style.setProperty("--ann-bg", /^#[0-9a-f]{6}$/i.test(t) ? t : "#2563eb"), s.style.setProperty("--ann-fg", Qe(t));
}
function tn(s, t = 100) {
  if (s === "none" || typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const n = Math.max(0, Math.min(1, t / 100)) * 0.4, i = s === "chime" ? [[660, 0, 0.6], [880, 0.35, 0.9]] : s === "gong" ? [[196, 0, 2.5], [392, 0, 1.5], [294, 0.02, 2]] : [[880, 0, 0.25], [660, 0.3, 0.25], [880, 0.6, 0.25], [660, 0.9, 0.25]];
  let r = 0;
  for (const [o, a, c] of i) {
    const l = e.createOscillator(), h = e.createGain();
    l.type = s === "alert" ? "square" : "sine", l.frequency.value = o;
    const d = e.currentTime + a;
    h.gain.setValueAtTime(1e-4, d), h.gain.exponentialRampToValueAtTime(n, d + 0.02), h.gain.exponentialRampToValueAtTime(1e-4, d + c), l.connect(h).connect(e.destination), l.start(d), l.stop(d + c + 0.05), r = Math.max(r, a + c);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, (r + 0.5) * 1e3);
}
class en {
  constructor(t) {
    this.speaker = t, this.drawn = "", this.heard = /* @__PURE__ */ new Set(), this.node = g("div", "ann-layer"), this.node.setAttribute("aria-live", "polite");
  }
  /** Keep the layer on top of the content (the display replaces its children on every slide). */
  attach(t) {
    (this.node.parentElement !== t || t.lastElementChild !== this.node) && t.appendChild(this.node);
  }
  update(t, e, n = {}) {
    const i = n.hidden ? [] : Xe(t, e), { card: r, banner: o, ticker: a } = Ze(i), c = n.audio?.enabled !== !1;
    for (const h of i) {
      const d = `${h.overlay.id}@${h.start}`, u = h.overlay.sound && h.overlay.sound !== "none";
      this.heard.has(d) || (this.heard.add(d), c && u && tn(h.overlay.sound, n.audio?.volume ?? 100)), c && h.overlay.speech && this.speaker?.say(d, h.overlay.speech, { volume: n.audio?.volume, delayMs: u ? It : 0 });
    }
    this.heard.size > 500 && (this.heard = new Set([...this.heard].slice(-100)));
    const l = JSON.stringify([
      r?.overlay.id,
      r?.overlay.title,
      r?.overlay.text,
      o?.overlay.id,
      o?.overlay.text,
      a.map((h) => [h.overlay.id, h.overlay.text])
    ]);
    if (l !== this.drawn) {
      if (this.drawn = l, this.node.replaceChildren(), r) {
        const h = g("section", "ann-card");
        U(h, r.overlay.colour), h.append(g("p", "ann-level", r.overlay.level), g("h2", "ann-title", r.overlay.title)), r.overlay.text && r.overlay.text !== r.overlay.title && h.append(g("p", "ann-text", r.overlay.text)), this.node.append(h);
      }
      if (o) {
        const h = g("div", "ann-banner");
        U(h, o.overlay.colour), h.append(g("span", "ann-level", o.overlay.level), g("span", "ann-text", o.overlay.text)), this.node.append(h);
      }
      if (a.length) {
        const h = g("div", "ann-ticker");
        U(h, a[0].overlay.colour);
        const d = g("div", "ann-track"), u = a.map((p) => p.overlay.text).join("   ◆   "), m = g("span", "", u);
        m.setAttribute("aria-hidden", "true"), d.append(g("span", "", u), m), d.style.setProperty("--ann-duration", `${Math.max(12, Math.round(u.length / 6))}s`), h.append(g("span", "ann-level", a[0].overlay.level), d), this.node.append(h);
      }
      this.node.classList.toggle("has-bottom", !!(o && a.length));
    }
  }
}
class nn {
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
async function sn(s) {
  let t = 0;
  return await Promise.all([...new Set(s)].map(async (e) => {
    try {
      const n = await fetch(e, { credentials: "omit" });
      n.ok && (t += 1), await n.body?.cancel();
    } catch {
    }
  })), t;
}
const rn = 5, on = 1e4;
function an(s) {
  let t = 2166136261;
  for (let e = 0; e < s.length; e++)
    t ^= s.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function cn(s, t) {
  let e = t >>> 0 || 1;
  const n = [...s];
  for (let i = n.length - 1; i > 0; i--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (i + 1);
    [n[i], n[r]] = [n[r], n[i]];
  }
  return n;
}
function ln(s, t) {
  const e = t.reduce((r, o) => r + o, 0), n = t.map(() => 0), i = [];
  for (let r = 0; r < e; r++) {
    t.forEach((a, c) => {
      n[c] += a;
    });
    let o = 0;
    for (let a = 1; a < s.length; a++) n[a] > n[o] && (o = a);
    n[o] -= e, i.push(s[o]);
  }
  return i;
}
function hn(s, t, e) {
  if (s.from !== null && s.from !== void 0 && t < s.from || s.until !== null && s.until !== void 0 && t >= s.until) return !1;
  const n = s.tags ?? [], i = e.screen?.tags ?? [];
  return n.length && !n.some((r) => i.includes(r)) ? !1 : B(s.when ?? "", e);
}
function K(s, t, e, n, i, r = []) {
  const o = s.playlists[t];
  if (!o || r.includes(t) || r.length >= rn) return [];
  let a = [];
  const c = [];
  for (const l of o.items ?? []) {
    if (!hn(l, n, e)) continue;
    let h = [];
    if (l.playlist) h = K(s, l.playlist, e, n, i, [...r, t]);
    else if (l.layout && l.layout in s.layouts) {
      const d = l.duration || s.layouts[l.layout] || o.default || on;
      h = [{ layout: l.layout, duration: d, item: l.id }];
    }
    h.length && (a.push(h), c.push(Math.max(1, Math.trunc(l.weight || 1))));
  }
  return o.mode === "weighted" ? a = ln(a, c) : o.mode === "shuffle" && (a = cn(a, an(`${t}:${i}`))), a.flat();
}
function dn(s, t) {
  return (s[0] === null || s[0] <= t) && (s[1] === null || t < s[1]);
}
function un(s, t) {
  const e = [];
  return s.entries.forEach((n, i) => {
    const r = n.windows.find((o) => dn(o, t));
    r && e.push({ key: [-n.priority, -(r[0] ?? -1), i], entry: n, w: r });
  }), e.sort((n, i) => n.key[0] - i.key[0] || n.key[1] - i.key[1] || n.key[2] - i.key[2]), e.map((n) => [n.entry, n.w]);
}
function fn(s, t, e, n, i) {
  const r = n.content, o = { entry: n.id, index: 0, count: 1, start: i[0], end: i[1] };
  if (r.message !== void 0) return r.message in (s.messages ?? {}) ? { ...o, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in s.layouts ? { ...o, layout: r.layout } : null;
  const a = r.playlist, c = i[0] ?? 0;
  let l = K(s, a, t, e, 0);
  const h = l.reduce((p, k) => p + k.duration, 0);
  if (!h) return null;
  const d = Math.floor((e - c) / h);
  d && (l = K(s, a, t, e, d));
  let u = e - c - d * h, m = c + d * h;
  for (let p = 0; p < l.length; p++) {
    const k = l[p];
    if (u < k.duration) {
      let j = m + k.duration;
      return i[1] !== null && (j = Math.min(j, i[1])), { ...o, layout: k.layout, item: k.item, index: p, count: l.length, start: m, end: j };
    }
    u -= k.duration, m += k.duration;
  }
  return null;
}
function pn(s, t, e) {
  for (const [n, i] of un(s, e)) {
    const r = fn(s, t, e, n, i);
    if (r) return r;
  }
  return null;
}
function mn(s, t, e) {
  const n = e?.end != null ? [e.end] : [];
  for (const i of s.entries)
    for (const [r, o] of i.windows)
      r !== null && r > t && n.push(r), o !== null && o > t && n.push(o);
  return n.length ? Math.min(...n) : null;
}
const gn = "evac-player-content-v1", yn = "content/theme/", vn = /url\("([^"]+)"\)/g;
async function lt(s, t) {
  const e = await caches.open(gn).catch(() => null), n = await e?.match(s).catch(() => {
  });
  if (n) return n;
  const i = new AbortController(), r = setTimeout(() => i.abort(), 1e4);
  try {
    const o = await fetch(s, {
      headers: { Authorization: `Screen ${t}` },
      credentials: "omit",
      signal: i.signal
    });
    if (o.ok)
      return await e?.put(s, o.clone()), o;
  } catch {
  } finally {
    clearTimeout(r);
  }
  return null;
}
async function wn(s, t) {
  try {
    const e = await M(s, yn, { token: t });
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
function bn(s) {
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
const ht = [];
async function dt(s, t, e = document.documentElement) {
  const n = document.fonts;
  await Promise.all(bn(s.fonts_css).map(async (i) => {
    const r = await lt(i.url, t);
    if (r)
      try {
        const o = new FontFace(i.family, await r.arrayBuffer(), {
          weight: i.weight,
          style: i.style,
          unicodeRange: i.unicodeRange
        });
        n.add(await o.load());
      } catch {
      }
  })), ht.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, r] of Object.entries(s.variables)) {
    let o = r;
    for (const a of r.matchAll(vn)) {
      const c = await lt(a[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        ht.push(l), o = o.replace(a[1], l);
      }
    }
    e.style.setProperty(i, o);
  }
  e.dataset.theme = s.key || "default";
}
function Sn(s = document) {
  const t = s.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, n = new URLSearchParams(s.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: n.get("mode") === "obs" ? "obs" : "screen"
  };
}
function x(s, t, e = {}) {
  let n = s.strings[t] ?? t;
  for (const [i, r] of Object.entries(e)) n = n.replace(`{${i}}`, String(r));
  return n;
}
function kn(s, t = location) {
  return s.ws ? s.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const D = [], _ = [], $n = Date.now(), En = 300;
let T = [], Z = null;
function w(s, t) {
  _.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${s.toUpperCase()} ${t}`.slice(0, 500)), _.length > En && _.shift();
}
function xn() {
  return [..._];
}
function y(s) {
  D.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${s}`.slice(0, 300)), D.length > 10 && D.shift(), w("error", s);
  const t = Date.now();
  T = T.filter((e) => t - e < 6e4), T.push(t), T.length >= 50 && Z && (T = [], Z());
}
function Mn(s) {
  Z = s;
}
function An(s = window) {
  s.addEventListener("error", (t) => y(t.message || "error")), s.addEventListener("unhandledrejection", (t) => y(String(t.reason)));
  for (const t of ["warn", "info"]) {
    const e = console[t].bind(console);
    console[t] = (...n) => {
      w(t, n.map(String).join(" ")), e(...n);
    };
  }
}
function ut(s) {
  const t = window.innerWidth, e = window.innerHeight, n = performance.memory;
  return {
    version: s.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - $n) / 1e3),
    slide: s.slide,
    errors: [...D],
    memory: n ? Math.round(n.usedJSHeapSize / 1048576) : null,
    last_sync: s.lastSync ? new Date(s.lastSync).toISOString() : null,
    online: s.online,
    user_agent: navigator.userAgent,
    ...s.contentVersion ? { content_version: s.contentVersion } : {},
    ...s.displayState ? { display_state: s.displayState } : {},
    ...s.capture !== void 0 ? { capture: s.capture } : {},
    ...s.recovered ? { recovered: s.recovered } : {}
  };
}
const Nt = "evac.player.reloads", L = "evac.player.alive", Cn = 3, Tn = 10 * 6e4;
function zt(s) {
  try {
    return localStorage.getItem(s);
  } catch {
    return null;
  }
}
function W(s, t) {
  try {
    t === null ? localStorage.removeItem(s) : localStorage.setItem(s, t);
  } catch {
  }
}
function Pn(s = Date.now()) {
  try {
    return JSON.parse(zt(Nt) ?? "[]").filter((t) => s - t < Tn);
  } catch {
    return [];
  }
}
function R(s, t = {}) {
  const e = Date.now(), n = Pn(e);
  return !t.force && n.length >= Cn ? (y(`reload (${s}) skipped: ${n.length} reloads in the last 10 minutes`), !1) : (W(Nt, JSON.stringify([...n, e])), w("info", `reload: ${s}`), Ot(), (t.win ?? location).reload(), !0);
}
function In(s = Date.now()) {
  const t = zt(L);
  if (W(L, String(s)), !t || t === "clean") return "";
  const e = Number(t);
  return Number.isFinite(e) ? `restarted after an unclean stop (last sign of life ${new Date(e).toISOString()})` : "";
}
function Nn(s = Date.now()) {
  W(L, String(s));
}
function Ot() {
  W(L, "clean");
}
function zn(s = window) {
  s.addEventListener("pagehide", () => Ot());
}
function On() {
  const s = performance.memory;
  return !!s && s.jsHeapSizeLimit > 0 && s.usedJSHeapSize / s.jsHeapSizeLimit > 0.85;
}
function Dt() {
  return typeof navigator < "u" && !!navigator.mediaDevices?.getDisplayMedia;
}
function Dn(s, t, e) {
  return new Promise((n, i) => {
    const r = setTimeout(() => i(new Error(`${e} timed out`)), t);
    s.then((o) => {
      clearTimeout(r), n(o);
    }, (o) => {
      clearTimeout(r), i(o);
    });
  });
}
async function _n(s = 1e4) {
  return Dn(Rn(), s, "screen capture");
}
async function Rn() {
  if (!Dt()) throw new Error("screen capture is not available in this browser");
  const s = document.createElement("div");
  s.className = "evac-capture-dot", document.body.appendChild(s);
  let t = 0;
  const e = setInterval(() => s.classList.toggle("on", t++ % 2 === 0), 16);
  try {
    return await Fn();
  } finally {
    clearInterval(e), s.remove();
  }
}
async function Fn() {
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
async function J(s, t, e, n) {
  const i = typeof Blob < "u" && n instanceof Blob;
  await fetch(`${s}upload/${e}/`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Screen ${t}`, "Content-Type": i ? n.type : "application/json" },
    body: i ? n : JSON.stringify(n)
  });
}
async function Ln() {
  try {
    if (typeof caches < "u") for (const s of await caches.keys()) await caches.delete(s);
  } catch {
  }
  try {
    for (const s of Object.keys(localStorage))
      s.startsWith("evac.player.") && s !== "evac.player.token" && localStorage.removeItem(s);
  } catch {
  }
  try {
    for (const s of await navigator.serviceWorker?.getRegistrations?.() ?? []) await s.unregister();
  } catch {
  }
}
function ft(s, t) {
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
function pt(s, t, e) {
  return !t || !e || t === e ? !1 : t < e ? s >= t && s < e : s >= t || s < e;
}
function Bn(s, t) {
  return pt(t, s.sleep_from, s.sleep_until) ? "sleeping" : pt(t, s.dim_from, s.dim_until) ? "dimmed" : "on";
}
function Wn(s) {
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
function jn(s, t) {
  const e = Wn(t);
  s.classList.add("evac-root"), s.style.width = e.width, s.style.height = e.height, s.style.transform = e.transform, s.style.setProperty("--evac-overscan", e.overscan);
}
function Hn(s, t, e = document) {
  let n = e.getElementById("evac-dim");
  if (s === "on") {
    n?.remove();
    return;
  }
  n || (n = e.createElement("div"), n.id = "evac-dim", n.setAttribute("aria-hidden", "true"), e.body.appendChild(n));
  const i = s === "sleeping" ? 0 : Math.max(10, Math.min(90, t.dim_level ?? 40));
  n.style.opacity = String(1 - i / 100), n.dataset.state = s;
}
const Q = "evac.player.token", it = "evac.player.config";
function qn() {
  try {
    return localStorage.getItem(Q);
  } catch {
    return null;
  }
}
function mt(s) {
  try {
    s ? localStorage.setItem(Q, s) : (localStorage.removeItem(Q), localStorage.removeItem(it));
  } catch {
  }
}
function Un() {
  try {
    const s = localStorage.getItem(it);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function gt(s) {
  try {
    localStorage.setItem(it, JSON.stringify(s));
  } catch {
  }
}
const yt = 3e3;
function I(s) {
  document.documentElement.dataset.boot = s;
}
const vt = 6e4, Jn = 36e5, wt = 15e3;
class Gn {
  constructor(t, e) {
    this.env = t, this.root = e, this.clock = new Bt(), this.speaker = new nn(), this.overlays = new en(this.speaker), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.program = null, this.shown = "", this.timer = null, this.refresher = null, this.housekeeping = null, this.displayState = "on", this.recovered = "", this.lastTick = Date.now(), this.reloadAtNextSlide = "", this.lastDailyReload = "", this.display = new He(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    I("boot"), this.recovered = In(), w("info", `player ${this.env.version} started (${navigator.userAgent})`), this.recovered && w("warn", this.recovered);
    const t = qn();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: x(this.env, "pair_title"),
      step1: x(this.env, "pair_step1"),
      step2: x(this.env, "pair_step2"),
      waiting: x(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await Ft(this.env.api, ut({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (i) {
      y(String(i)), this.display.message(x(this.env, "no_server"), x(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const n = async () => {
      try {
        const i = await Lt(this.env.api, e);
        if (i.status === "paired")
          return mt(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        y(String(i));
      }
      setTimeout(() => {
        n();
      }, yt);
    };
    setTimeout(() => {
      n();
    }, yt);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = Un();
    I(e ? "play: cached config" : "play: no cached config"), e && (this.config = e, this.bundle = Y(), this.program = X(), this.applySettings(), this.bundle && dt({ ...this.bundle.theme, fonts_css: this.bundle.fonts_css }, t).catch((n) => y(String(n))), this.show(), I("play: shown from cache"));
    try {
      const n = Date.now();
      this.config = await rt(this.env.api, t), this.clock.add(n, Date.now(), this.config.server_time), this.lastSync = Date.now(), gt(this.config);
    } catch (n) {
      if (n instanceof S) return this.unpair();
      y(String(n)), this.config = e;
    }
    this.applySettings(), this.bundle = this.bundle ?? Y(), this.program = this.program ?? X(), await this.loadContent(t), await this.loadProgram(t), this.show(), I("play: online"), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, Jn), this.housekeeping = setInterval(() => this.tick(), wt), this.conn = new Ht({
      api: this.env.api,
      ws: kn(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => ut({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline",
        displayState: this.displayState,
        capture: Dt(),
        recovered: this.recovered
      }),
      onMessage: (n) => {
        this.handle(n, t);
      },
      onTransport: (n) => {
        n !== this.transport && w("info", `connection: ${n}`), this.transport = n;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (n) => {
        this.lastSync = n;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch (w("info", `message: ${t.type}`), t.type) {
      case "config.changed":
        try {
          this.config = await rt(this.env.api, e), gt(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), this.applySettings();
          const n = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(e), await this.loadProgram(e), (`${this.bundle?.version}/${this.program?.version}` !== n || this.slide === "idle") && (this.shown = "", this.show());
        } catch (n) {
          n instanceof S && this.unpair();
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
      case "reload":
        R("requested by staff", { force: !0 });
        break;
      case "clear_cache":
        await Ln(), R("cache cleared by staff", { force: !0 });
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
          await J(this.env.api, e, "screenshot", await _n());
        } catch (n) {
          y(`screenshot: ${String(n)}`), await J(this.env.api, e, "screenshot", { error: String(n).slice(0, 280) }).catch(() => {
          });
        }
        break;
      case "logs":
        await J(this.env.api, e, "logs", { lines: xn() }).catch((n) => y(String(n)));
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await qe(this.env.api, t) ?? this.bundle;
    } catch (n) {
      if (n instanceof S) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await wn(this.env.api, t);
    e && await dt(e, t).catch((n) => y(String(n))), this.bundle && Ge(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await Ve(this.env.api, t);
    } catch (n) {
      n instanceof S && this.unpair();
    }
    const e = [...this.program?.entries ?? [], ...this.program?.overlays ?? []].map((n) => n.speech).filter((n) => !!n);
    e.length && sn(e);
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
      this.slide = "error", this.display.message(x(this.env, "no_server"), x(this.env, "retrying"));
      return;
    }
    const e = this.clock.now();
    let n = null, i, r = "idle", o = null;
    if (this.program && this.bundle) {
      if (o = pn(this.program, this.vars(), e), o?.message)
        n = this.program.messages?.[o.message] ?? null, r = `${o.entry}|message`, this.slide = `${o.entry} message`;
      else if (o?.layout) {
        const u = this.bundle.layouts.find((m) => m.id === o?.layout);
        u && (n = u.data, i = u.variables, r = `${o.entry}|${u.id}|${u.version}|${o.count > 1 ? o.start : ""}`, this.slide = `${u.key} v${u.version} (${o.entry} ${o.index + 1}/${o.count})`);
      }
      const h = [mn(this.program, e, o), Ke(this.program.overlays, e)].filter((u) => u !== null), d = Math.max(5, Math.min(vt, (h.length ? Math.min(...h) : e + vt) - e));
      this.timer = setTimeout(() => this.show(), d);
    } else {
      const h = Je(this.bundle);
      h && (n = h.data, i = h.variables, r = `default|${h.id}|${h.version}`, this.slide = `${h.key} v${h.version}`);
    }
    const a = { enabled: t.display?.audio !== !1, volume: t.display?.volume ?? 100 }, c = !!o && (o.entry.startsWith("announcement:") || o.entry.startsWith("evacuation"));
    this.overlays.update(this.program?.overlays, e, { hidden: c, audio: a });
    const l = o ? this.program?.entries.find((h) => h.id === o?.entry) : void 0;
    if (l?.speech && a.enabled && this.speaker.say(`${l.id}@${o?.start ?? 0}`, l.speech, {
      volume: a.volume,
      delayMs: It
    }), r !== this.shown && !(this.reloadAtNextSlide && this.shown && R(this.reloadAtNextSlide))) {
      this.reloadAtNextSlide = "", this.shown = r, w("info", `showing ${this.slide}`);
      try {
        if (!n || !this.bundle) throw new Error("nothing to show");
        this.display.layout(n, {
          vars: this.vars(),
          now: () => this.clock.now(),
          timezone: t.event.timezone,
          assets: this.bundle.assets,
          fonts: this.bundle.fonts,
          reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
          audio: a,
          nonce: ne(),
          onError: (h, d) => y(`${h}: ${String(d)}`),
          onLog: (h, d) => w("info", `${h}: ${d}`)
        }, i);
      } catch (h) {
        n && y(`render failed, showing the idle slide: ${String(h)}`), this.slide = "idle", this.display.idle(t);
      }
      this.overlays.attach(this.root);
    }
  }
  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  applySettings() {
    const t = this.config?.display ?? {};
    jn(this.root, t), this.updateDisplayState();
  }
  updateDisplayState() {
    const t = this.config?.display ?? {}, e = Bn(t, ft(this.clock.now(), this.config?.event.timezone));
    e !== this.displayState && w("info", `display ${e}`), this.displayState = e, Hn(e, t);
  }
  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  tick() {
    const t = Date.now(), e = t - this.lastTick > wt * 3;
    this.lastTick = t, Nn(t), this.updateDisplayState(), e && (w("warn", "timers were stalled; resynchronising"), this.shown = "", this.show());
    const n = this.config?.display?.daily_reload, i = ft(this.clock.now(), this.config?.event.timezone);
    n && i === n && this.lastDailyReload !== i && performance.now() > 36e5 && (this.lastDailyReload = i, this.reloadAtNextSlide = "daily reload"), On() && !this.reloadAtNextSlide && (this.reloadAtNextSlide = "memory pressure");
  }
  unpair() {
    this.housekeeping && clearInterval(this.housekeeping), this.housekeeping = null, this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.timer = this.refresher = null, Ye(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, mt(null), Ue(), this.pair();
  }
}
function Vn() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((s) => y(String(s)));
}
if (typeof document < "u" && document.getElementById("player")) {
  An(), zn(), Mn(() => R("50 errors within a minute")), Vn();
  const s = Sn();
  new Gn(s, document.getElementById("player")).boot();
}
export {
  Gn as Player
};
