// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var Dt = Object.defineProperty;
var _t = (n, t, e) => t in n ? Dt(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var C = (n, t, e) => _t(n, typeof t != "symbol" ? t + "" : t, e);
class S extends Error {
}
async function M(n, t, e = {}) {
  const s = new AbortController(), i = setTimeout(() => s.abort(), e.timeout ?? 1e4), r = new Headers(e.headers);
  r.set("Accept", "application/json"), e.body && r.set("Content-Type", "application/json"), e.token && r.set("Authorization", `Screen ${e.token}`);
  try {
    const o = await fetch(n + t, {
      ...e,
      headers: r,
      signal: s.signal,
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
const Rt = (n, t) => M(n, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), Ft = (n, t) => M(n, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), rt = (n, t) => M(n, "config/", { token: t });
class Bt {
  constructor() {
    this.samples = [], this.offset = 0;
  }
  add(t, e, s) {
    const i = e - t;
    i < 0 || !Number.isFinite(s) || (this.samples.push({ offset: s * 1e3 - (t + e) / 2, rtt: i }), this.samples.length > 8 && this.samples.shift(), this.offset = this.samples.reduce((r, o) => o.rtt < r.rtt ? o : r).offset);
  }
  now() {
    return Date.now() + this.offset;
  }
}
const Lt = 3e4, Wt = 3e5;
class jt {
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
    this.backoff = Math.min(this.backoff * 2, Lt), setTimeout(() => !this.stopped && t(), e);
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > Wt ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        const e = t.body.getReader(), s = new TextDecoder();
        let i = "";
        for (; ; ) {
          const { value: r, done: o } = await e.read();
          if (o) break;
          i += s.decode(r, { stream: !0 });
          let a;
          for (; (a = i.indexOf(`

`)) >= 0; ) {
            const l = i.slice(0, a);
            i = i.slice(a + 2);
            const c = l.split(`
`).filter((h) => h.startsWith("data: ")).map((h) => h.slice(6)).join(`
`);
            if (c)
              try {
                this.deliver(JSON.parse(c));
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
function N(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function Ht(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function Ut(n, t, e) {
  const s = n.style;
  if (!t) return;
  const i = (r, o) => {
    o && s.setProperty(r, o);
  };
  i("color", N(t.color)), i("background", N(t.background)), t.borderWidth && s.setProperty("border", `${t.borderWidth / 10}cqh solid ${N(t.borderColor) || "currentColor"}`), t.radius !== void 0 && s.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && s.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && s.setProperty("opacity", String(t.opacity)), i("font-family", Ht(t.fontFamily, e)), t.fontSize && s.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && s.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && s.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && s.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && s.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && s.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && s.setProperty("box-shadow", "var(--evac-shadow)");
}
function qt(n, t, e) {
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
function Jt(n) {
  const t = [];
  let e = "", s = "";
  for (const i of n)
    s ? (i === s && (s = ""), e += i) : i === '"' || i === "'" ? (s = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function Gt(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function ot(n, t, e) {
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
function b(n) {
  return n == null ? "" : Array.isArray(n) ? n.map(b).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function Vt(n, t, e) {
  const [s, ...i] = t.split(":"), r = Gt(i.join(":")), o = () => n instanceof Date ? n : new Date(String(n));
  switch (s.trim()) {
    case "upper":
      return b(n).toUpperCase();
    case "lower":
      return b(n).toLowerCase();
    case "title":
      return b(n).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, l = b(n);
      return l.length > a ? `${l.slice(0, Math.max(0, a - 1))}…` : l;
    }
    case "default":
      return b(n) === "" ? r : n;
    case "date":
      return isNaN(o().getTime()) ? "" : ot(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : ot(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map(b).join(r || ", ") : b(n);
    default:
      return n;
  }
}
function z(n, t, e = {}) {
  const [s, ...i] = Jt(n);
  let r = qt(t, s, e);
  for (const o of i) r = Vt(r, o, e);
  return r;
}
function Xt(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function L(n, t, e = {}) {
  const s = n.trim();
  if (!s) return !0;
  if (s.startsWith("not ")) return !L(s.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(s);
  if (i) {
    const r = b(z(i[1], t, e)), o = b(z(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return Xt(z(s.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const Yt = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function Kt(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const s = n.split(Yt);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < s.length; ) {
      const l = s[i++], c = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(l);
      if (c) {
        const h = c[1].startsWith("if") ? "if" : c[1];
        if (o.includes(h)) return [a, h];
        if (h === "if") {
          const d = L(c[2], t, e), [u, m] = r(["else", "endif"]);
          let p = "";
          m === "else" && (p = r(["endif"])[0]), a += d ? u : p;
        }
      } else l.startsWith("{{") && l.endsWith("}}") ? a += b(z(l.slice(2, -2), t, e)) : a += l;
    }
    return [a, ""];
  };
  return r([])[0];
}
const Zt = `(() => {
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
function at(n) {
  return n.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function Qt(n, t, e, s = "") {
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
  ].join("; "), a = String(n.css ?? "").replace(/<\/style/gi, "<\\/style"), l = String(n.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${at(o)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${s}</style><style nonce="${i}">${a}</style><script nonce="${i}">${Zt}<\/script></head><body>${String(n.html ?? "")}` + (l.trim() ? `<script nonce="${i}">${l}<\/script>` : "") + "</body></html>";
}
function te(n) {
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
function ee(n = document) {
  const t = n.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
var A = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(A || {});
const ne = [0, 1], bt = [1, 0], St = [2, 3], kt = [3, 2], se = {
  L: ne,
  M: bt,
  Q: St,
  H: kt
}, ie = /^\d*$/, re = /^[A-Z0-9 $%*+./:-]*$/, H = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", tt = 1, et = 40, ct = 3, oe = 3, P = 40, ae = 10, $t = [
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
class ce {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, s, i) {
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
    const o = this.addEccAndInterleave(s);
    if (this.drawCodewords(o), i === -1) {
      let a = 1e9;
      for (let l = 0; l < 8; l++) {
        this.applyMask(l), this.drawFormatBits(l);
        const c = this.getPenaltyScore();
        c < a && (i = l, a = c), this.applyMask(l);
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
      this.setFunctionModule(6, s, s % 2 === 0, A.Timing), this.setFunctionModule(s, 6, s % 2 === 0, A.Timing);
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
    for (let s = 0; s < 12; s++)
      t = t << 1 ^ (t >>> 11) * 7973;
    const e = this.version << 12 | t;
    for (let s = 0; s < 18; s++) {
      const i = $(e, s), r = this.size - 11 + s % 3, o = Math.floor(s / 3);
      this.setFunctionModule(r, o, i), this.setFunctionModule(o, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let s = -4; s <= 4; s++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(s)), o = t + i, a = e + s;
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, A.Position);
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
          A.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, s, i = A.Function) {
    this.modules[e][t] = s, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, s = this.ecc;
    if (t.length !== O(e, s))
      throw new RangeError("Invalid argument");
    const i = Et[s[0]][e], r = $t[s[0]][e], o = Math.floor(G(e) / 8), a = i - o % i, l = Math.floor(o / i), c = [], h = ye(r);
    for (let u = 0, m = 0; u < i; u++) {
      const p = t.slice(m, m + l - r + (u < a ? 0 : 1));
      m += p.length;
      const k = we(p, h);
      u < a && p.push(0), c.push(p.concat(k));
    }
    const d = [];
    for (let u = 0; u < c[0].length; u++)
      c.forEach((m, p) => {
        (u !== l - r || p >= a) && d.push(m[u]);
      });
    return d;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(G(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let s = this.size - 1; s >= 1; s -= 2) {
      s === 6 && (s = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = s - r, l = (s + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[l][o] && e < t.length * 8 && (this.modules[l][o] = $(t[e >>> 3], 7 - (e & 7)), e++);
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
      let o = !1, a = 0;
      const l = [0, 0, 0, 0, 0, 0, 0];
      for (let c = 0; c < this.size; c++)
        this.modules[r][c] === o ? (a++, a === 5 ? t += ct : a > 5 && t++) : (this.finderPenaltyAddHistory(a, l), o || (t += this.finderPenaltyCountPatterns(l) * P), o = this.modules[r][c], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, l) * P;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const l = [0, 0, 0, 0, 0, 0, 0];
      for (let c = 0; c < this.size; c++)
        this.modules[c][r] === o ? (a++, a === 5 ? t += ct : a > 5 && t++) : (this.finderPenaltyAddHistory(a, l), o || (t += this.finderPenaltyCountPatterns(l) * P), o = this.modules[c][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, l) * P;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += oe);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const s = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - s * 10) / s) - 1;
    return t += i * ae, t;
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
function E(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let s = t - 1; s >= 0; s--)
    e.push(n >>> s & 1);
}
function $(n, t) {
  return (n >>> t & 1) !== 0;
}
class nt {
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
const le = [1, 10, 12, 14], he = [2, 9, 11, 13], de = [4, 8, 16, 16];
function xt(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function Mt(n) {
  const t = [];
  for (const e of n)
    E(e, 8, t);
  return new nt(de, n.length, t);
}
function ue(n) {
  if (!At(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const s = Math.min(n.length - e, 3);
    E(Number.parseInt(n.substring(e, e + s), 10), s * 3 + 1, t), e += s;
  }
  return new nt(le, n.length, t);
}
function fe(n) {
  if (!Ct(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let s = H.indexOf(n.charAt(e)) * 45;
    s += H.indexOf(n.charAt(e + 1)), E(s, 11, t);
  }
  return e < n.length && E(H.indexOf(n.charAt(e)), 6, t), new nt(he, n.length, t);
}
function pe(n) {
  return n === "" ? [] : At(n) ? [ue(n)] : Ct(n) ? [fe(n)] : [Mt(ge(n))];
}
function At(n) {
  return ie.test(n);
}
function Ct(n) {
  return re.test(n);
}
function me(n, t) {
  let e = 0;
  for (const s of n) {
    const i = xt(s.mode, t);
    if (s.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + s.bitData.length;
  }
  return e;
}
function ge(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function G(n) {
  if (n < tt || n > et)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function O(n, t) {
  return Math.floor(G(n) / 8) - $t[t[0]][n] * Et[t[0]][n];
}
function ye(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let s = 0; s < n - 1; s++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < t.length; i++)
      t[i] = V(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = V(e, 2);
  }
  return t;
}
function we(n, t) {
  const e = t.map((s) => 0);
  for (const s of n) {
    const i = s ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= V(r, i));
  }
  return e;
}
function V(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let s = 7; s >= 0; s--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> s & 1) * n;
  return e;
}
function ve(n, t, e = 1, s = 40, i = -1, r = !0) {
  if (!(tt <= e && e <= s && s <= et) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const d = O(o, t) * 8, u = me(n, o);
    if (u <= d) {
      a = u;
      break;
    }
    if (o >= s)
      throw new RangeError("Data too long");
  }
  for (const d of [bt, St, kt])
    r && a <= O(o, d) * 8 && (t = d);
  const l = [];
  for (const d of n) {
    E(d.mode[0], 4, l), E(d.numChars, xt(d.mode, o), l);
    for (const u of d.getData())
      l.push(u);
  }
  const c = O(o, t) * 8;
  E(0, Math.min(4, c - l.length), l), E(0, (8 - l.length % 8) % 8, l);
  for (let d = 236; l.length < c; d ^= 253)
    E(d, 8, l);
  const h = Array.from({ length: Math.ceil(l.length / 8) }, () => 0);
  return l.forEach((d, u) => h[u >>> 3] |= d << 7 - (u & 7)), new ce(o, t, h, i);
}
function be(n, t) {
  const {
    ecc: e = "L",
    boostEcc: s = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, l = typeof n == "string" ? pe(n) : Array.isArray(n) ? [Mt(n)] : void 0;
  if (!l)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const c = ve(
    l,
    se[e],
    i,
    r,
    o,
    s
  ), h = Se({
    version: c.version,
    maskPattern: c.mask,
    size: c.size,
    data: c.modules,
    types: c.types
  }, a);
  return t?.invert && (h.data = h.data.map((d) => d.map((u) => !u))), t?.onEncoded?.(h), h;
}
function Se(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, s = e + t * 2;
  n.size = s, n.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    n.data.unshift(Array.from({ length: s }, (o) => !1)), n.data.push(Array.from({ length: s }, (o) => !1));
  const i = A.Border;
  n.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    n.types.unshift(Array.from({ length: s }, (o) => i)), n.types.push(Array.from({ length: s }, (o) => i));
  return n;
}
const U = "http://www.w3.org/2000/svg";
function Tt(n, t = document) {
  const { data: e, size: s } = be(n, { ecc: "M", border: 2 }), i = t.createElementNS(U, "svg");
  i.setAttribute("viewBox", `0 0 ${s} ${s}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(U, "rect");
  r.setAttribute("width", String(s)), r.setAttribute("height", String(s)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((l, c) => l.forEach((h, d) => {
    h && (o += `M${d} ${c}h1v1h-1z`);
  }));
  const a = t.createElementNS(U, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), i.appendChild(a), i;
}
class w extends HTMLElement {
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
    return Kt(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function ke(n, t) {
  t.style.removeProperty("font-size");
  const e = parseFloat(getComputedStyle(t).fontSize) || 16, s = () => t.scrollHeight <= n.clientHeight + 1 && t.scrollWidth <= n.clientWidth + 1;
  if (!n.clientHeight || s()) return;
  let i = Math.max(4, e * 0.1), r = e;
  for (let o = 0; o < 12 && r - i > 0.5; o++) {
    const a = (i + r) / 2;
    t.style.fontSize = `${a}px`, s() ? i = a : r = a;
  }
  t.style.fontSize = `${i}px`;
}
class $e extends w {
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
      const i = () => ke(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Ee extends w {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-richtext";
    for (const e of this.text(this.props.text).split(/\n{2,}/)) {
      const s = document.createElement("p");
      e.split(`
`).forEach((i, r) => {
        r && s.appendChild(document.createElement("br"));
        for (const o of i.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/))
          /^\*\*[^*]+\*\*$/.test(o) ? s.appendChild(Object.assign(
            document.createElement("strong"),
            { textContent: o.slice(2, -2) }
          )) : /^\*[^*]+\*$/.test(o) ? s.appendChild(Object.assign(
            document.createElement("em"),
            { textContent: o.slice(1, -1) }
          )) : o && s.appendChild(document.createTextNode(o));
      }), t.appendChild(s);
    }
    this.replaceChildren(t);
  }
}
function Pt(n, t, e) {
  const s = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = n.urls[r], s.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = n.urls.original, i.alt = e || n.alt || "", i.decoding = "async", i.style.objectFit = t, s.appendChild(i), s;
}
class xe extends w {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(Pt(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class Me extends w {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), s = t.map((o) => {
      const a = Pt(o, e, "");
      return a.className = "evac-slide", a;
    });
    this.replaceChildren(...s);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const o = Math.floor(this.ctx.now() / i) % s.length;
      s.forEach((a, l) => a.classList.toggle("active", l === o));
    };
    r(), this.every(500, r);
  }
}
class Ae extends w {
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
class Ce extends w {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Te extends w {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Pe extends w {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = Tt(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Ie = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Ne extends w {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Ie[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = s.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class ze extends w {
  draw() {
    const t = String(this.props.format ?? "long"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = {
      long: { weekday: "long", day: "numeric", month: "long" },
      short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" },
      iso: { year: "numeric", month: "2-digit", day: "2-digit" }
    }, i = new Intl.DateTimeFormat(t === "iso" ? "sv-SE" : "en-GB", { ...s[t], timeZone: e }), r = document.createElement("time"), o = () => {
      r.textContent = i.format(new Date(this.ctx.now()));
    };
    o(), this.replaceChildren(r), this.every(3e4, o);
  }
}
function Oe(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), s = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (l) => String(l).padStart(2, "0");
  return t === "days" ? `${s} ${s === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || s === 0 ? `${a(i + s * 24)}:${a(r)}:${a(o)}` : `${s}d ${a(i)}:${a(r)}:${a(o)}`;
}
class De extends w {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), s = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : Oe(i, String(this.props.format ?? "auto"));
    };
    s(), this.replaceChildren(e), this.every(250, s);
  }
}
class _e extends w {
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
    s.setAttribute("sandbox", "allow-scripts"), s.setAttribute("referrerpolicy", "no-referrer"), s.setAttribute("allow", "autoplay"), s.setAttribute("title", this.el.name || "Code"), s.setAttribute("tabindex", "-1"), s.className = "evac-code-frame", s.srcdoc = Qt(e, t, location.origin, te(this)), this.frame = s, window.addEventListener("message", this.onMessage), this.replaceChildren(s), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
  }
  /** Only the kinds of data the element asked for (and that the server let it ask for). */
  send() {
    const t = new Set(this.props.data ?? []), e = this.ctx.vars, s = {};
    if (t.has("event") && (s.event = e.event ?? null), t.has("screen") && (s.screen = e.screen ?? null), t.has("time") && (s.now = this.ctx.now(), s.timezone = this.ctx.timezone ?? ""), t.has("assets")) {
      const i = {};
      for (const r of this.props.assets ?? []) {
        const o = this.ctx.assets[r];
        if (!o) continue;
        const a = {};
        for (const [l, c] of Object.entries(o.urls)) a[l] = new URL(c, location.href).href;
        i[r] = { name: o.name, kind: o.kind, alt: o.alt, width: o.width, height: o.height, urls: a };
      }
      s.assets = i;
    }
    this.frame?.contentWindow?.postMessage({ type: "evac:data", data: JSON.parse(JSON.stringify(s)) }, "*");
  }
  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage), this.frame = null, super.disconnectedCallback();
  }
}
const Re = {
  text: $e,
  richtext: Ee,
  image: xe,
  slideshow: Me,
  video: Ae,
  audio: Ce,
  shape: Te,
  qr: Pe,
  clock: Ne,
  countdown: De,
  date: ze,
  code: _e
};
function Fe(n = customElements) {
  for (const [t, e] of Object.entries(Re))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
function Be(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function Le(n, t) {
  const e = !n.visible_if || L(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const s = document.createElement("div");
  s.className = `evac-el evac-el-${n.type}`, s.dataset.id = n.id, (!e || n.hidden) && s.classList.add("evac-dimmed"), Be(s, n), Ut(s, n.style, t);
  const i = n.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (s.classList.add(`evac-enter-${i.enter}`), s.style.animationDuration = `${i.duration ?? 600}ms`, s.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${n.type}`;
  if (!customElements.get(r))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? s : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", s.appendChild(o), o.configure(n, t), s;
}
function We(n, t, e) {
  Fe();
  const s = document.createElement("div");
  s.className = "evac-stage";
  const i = t.background;
  if (i?.color && (s.style.background = N(i.color)), i?.asset && e.assets[i.asset]) {
    const l = e.assets[i.asset], c = l.urls.webp ?? l.urls.original;
    s.style.backgroundImage = `url("${c}")`, s.style.backgroundSize = i.fit ?? "cover", s.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const l of t.elements) {
    const c = Le(l, e);
    c && (r.set(l.id, c), s.appendChild(c));
  }
  n.replaceChildren(s);
  const o = () => {
    const l = n.clientWidth, c = n.clientHeight;
    if (!l || !c) return;
    const h = Math.min(l / t.width, c / t.height);
    s.style.width = `${Math.round(t.width * h)}px`, s.style.height = `${Math.round(t.height * h)}px`;
  };
  o();
  const a = typeof ResizeObserver < "u" ? new ResizeObserver(o) : null;
  return a?.observe(n), {
    stage: s,
    elements: r,
    destroy() {
      a?.disconnect(), s.remove();
    }
  };
}
function f(n, t = "", e = "") {
  const s = document.createElement(n);
  return t && (s.className = t), e && (s.textContent = e), s;
}
class je {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = f("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, s) {
    const i = this.reset();
    i.classList.add("pairing"), i.append(f("h1", "", s.title));
    const r = f("div", "pairing-box"), o = f("p", "code", t);
    o.setAttribute("aria-label", t.split("").join(" "));
    const a = Tt(e);
    a.setAttribute("role", "img"), a.setAttribute("aria-label", e), r.append(o, a);
    const l = f("ol", "steps");
    l.append(f("li", "", s.step1), f("li", "", s.step2)), i.append(r, l, f("p", "url", e), f("p", "waiting", s.waiting));
  }
  message(t, e = "") {
    const s = this.reset();
    s.classList.add("message"), s.append(f("h1", "", t)), e && s.append(f("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const s = f("p", "clock"), i = f("p", "date");
    e.append(f("h1", "event-name", t.event.name), s, i);
    const r = t.event.timezone || void 0, o = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: r }), a = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: r }), l = () => {
      const c = new Date(this.clock.now());
      s.textContent = o.format(c), i.textContent = a.format(c);
    };
    l(), this.clockTimer = setInterval(l, 1e3);
  }
  layout(t, e, s) {
    const i = this.reset();
    i.classList.add("layout");
    for (const [r, o] of Object.entries(s ?? {})) i.style.setProperty(r, o);
    this.rendered = We(i, t, e);
  }
  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(t, e, s = 30) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = f("div", "test-pattern");
    i.setAttribute("role", "img"), i.setAttribute("aria-label", t);
    const r = f("div", "tp-bars");
    for (const l of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"])
      r.appendChild(f("span", `tp-bar tp-${l}`));
    const o = f("div", "tp-ramp"), a = f("div", "tp-info");
    a.append(f("p", "tp-title", t), ...e.map((l) => f("p", "", l))), i.append(r, o, f("div", "tp-grid"), f("div", "tp-circle"), f("div", "tp-corners"), a), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), s * 1e3);
  }
  identify(t, e, s = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = f("div", "identify");
    i.setAttribute("role", "status"), i.append(f("p", "identify-name", t), f("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), s * 1e3);
  }
}
const st = "evac.player.bundle";
async function He(n, t) {
  try {
    const e = await M(n, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(st, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof S) throw e;
    return X();
  }
}
function X() {
  try {
    const n = localStorage.getItem(st);
    return n ? JSON.parse(n) : null;
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
function qe(n) {
  return n?.layouts.length ? n.layouts.find((t) => t.default) ?? n.layouts[0] : null;
}
async function Je(n) {
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
const F = "evac.player.program";
async function Ge(n, t) {
  try {
    const e = await M(n, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(F, JSON.stringify(e.program)) : localStorage.removeItem(F);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof S) throw e;
    return Y();
  }
}
function Y() {
  try {
    const n = localStorage.getItem(F);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function Ve() {
  try {
    localStorage.removeItem(F);
  } catch {
  }
}
function Xe(n, t) {
  const e = [];
  for (const s of n ?? [])
    for (const [i, r] of s.windows)
      if ((i === null || i <= t) && (r === null || t < r)) {
        e.push({ overlay: s, start: i ?? 0, end: r });
        break;
      }
  return e.sort((s, i) => i.overlay.rank - s.overlay.rank || i.start - s.start);
}
function Ye(n, t) {
  let e = null;
  for (const s of n ?? [])
    for (const [i, r] of s.windows)
      for (const o of [i, r])
        o !== null && o > t && (e === null || o < e) && (e = o);
  return e;
}
function Ke(n) {
  return {
    card: n.find((t) => t.overlay.style === "card") ?? null,
    banner: n.find((t) => t.overlay.style === "banner") ?? null,
    ticker: n.filter((t) => t.overlay.style === "ticker")
  };
}
function Ze(n) {
  const t = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(n);
  if (!t) return "#ffffff";
  const [e, s, i] = t.slice(1).map((o) => {
    const a = parseInt(o, 16) / 255;
    return a <= 0.03928 ? a / 12.92 : ((a + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * e + 0.7152 * s + 0.0722 * i > 0.179 ? "#000000" : "#ffffff";
}
function g(n, t, e = "") {
  const s = document.createElement(n);
  return s.className = t, e && (s.textContent = e), s;
}
function q(n, t) {
  n.style.setProperty("--ann-bg", /^#[0-9a-f]{6}$/i.test(t) ? t : "#2563eb"), n.style.setProperty("--ann-fg", Ze(t));
}
function Qe(n, t = 100) {
  if (n === "none" || typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const s = Math.max(0, Math.min(1, t / 100)) * 0.4, i = n === "chime" ? [[660, 0, 0.6], [880, 0.35, 0.9]] : n === "gong" ? [[196, 0, 2.5], [392, 0, 1.5], [294, 0.02, 2]] : [[880, 0, 0.25], [660, 0.3, 0.25], [880, 0.6, 0.25], [660, 0.9, 0.25]];
  let r = 0;
  for (const [o, a, l] of i) {
    const c = e.createOscillator(), h = e.createGain();
    c.type = n === "alert" ? "square" : "sine", c.frequency.value = o;
    const d = e.currentTime + a;
    h.gain.setValueAtTime(1e-4, d), h.gain.exponentialRampToValueAtTime(s, d + 0.02), h.gain.exponentialRampToValueAtTime(1e-4, d + l), c.connect(h).connect(e.destination), c.start(d), c.stop(d + l + 0.05), r = Math.max(r, a + l);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, (r + 0.5) * 1e3);
}
class tn {
  constructor() {
    this.drawn = "", this.heard = /* @__PURE__ */ new Set(), this.node = g("div", "ann-layer"), this.node.setAttribute("aria-live", "polite");
  }
  /** Keep the layer on top of the content (the display replaces its children on every slide). */
  attach(t) {
    (this.node.parentElement !== t || t.lastElementChild !== this.node) && t.appendChild(this.node);
  }
  update(t, e, s = {}) {
    const i = s.hidden ? [] : Xe(t, e), { card: r, banner: o, ticker: a } = Ke(i);
    for (const c of i) {
      const h = `${c.overlay.id}@${c.start}`;
      this.heard.has(h) || (this.heard.add(h), s.audio?.enabled !== !1 && c.overlay.sound && c.overlay.sound !== "none" && Qe(c.overlay.sound, s.audio?.volume ?? 100));
    }
    this.heard.size > 500 && (this.heard = new Set([...this.heard].slice(-100)));
    const l = JSON.stringify([
      r?.overlay.id,
      r?.overlay.title,
      r?.overlay.text,
      o?.overlay.id,
      o?.overlay.text,
      a.map((c) => [c.overlay.id, c.overlay.text])
    ]);
    if (l !== this.drawn) {
      if (this.drawn = l, this.node.replaceChildren(), r) {
        const c = g("section", "ann-card");
        q(c, r.overlay.colour), c.append(g("p", "ann-level", r.overlay.level), g("h2", "ann-title", r.overlay.title)), r.overlay.text && r.overlay.text !== r.overlay.title && c.append(g("p", "ann-text", r.overlay.text)), this.node.append(c);
      }
      if (o) {
        const c = g("div", "ann-banner");
        q(c, o.overlay.colour), c.append(g("span", "ann-level", o.overlay.level), g("span", "ann-text", o.overlay.text)), this.node.append(c);
      }
      if (a.length) {
        const c = g("div", "ann-ticker");
        q(c, a[0].overlay.colour);
        const h = g("div", "ann-track"), d = a.map((m) => m.overlay.text).join("   ◆   "), u = g("span", "", d);
        u.setAttribute("aria-hidden", "true"), h.append(g("span", "", d), u), h.style.setProperty("--ann-duration", `${Math.max(12, Math.round(d.length / 6))}s`), c.append(g("span", "ann-level", a[0].overlay.level), h), this.node.append(c);
      }
      this.node.classList.toggle("has-bottom", !!(o && a.length));
    }
  }
}
const en = 5, nn = 1e4;
function sn(n) {
  let t = 2166136261;
  for (let e = 0; e < n.length; e++)
    t ^= n.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function rn(n, t) {
  let e = t >>> 0 || 1;
  const s = [...n];
  for (let i = s.length - 1; i > 0; i--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (i + 1);
    [s[i], s[r]] = [s[r], s[i]];
  }
  return s;
}
function on(n, t) {
  const e = t.reduce((r, o) => r + o, 0), s = t.map(() => 0), i = [];
  for (let r = 0; r < e; r++) {
    t.forEach((a, l) => {
      s[l] += a;
    });
    let o = 0;
    for (let a = 1; a < n.length; a++) s[a] > s[o] && (o = a);
    s[o] -= e, i.push(n[o]);
  }
  return i;
}
function an(n, t, e) {
  if (n.from !== null && n.from !== void 0 && t < n.from || n.until !== null && n.until !== void 0 && t >= n.until) return !1;
  const s = n.tags ?? [], i = e.screen?.tags ?? [];
  return s.length && !s.some((r) => i.includes(r)) ? !1 : L(n.when ?? "", e);
}
function K(n, t, e, s, i, r = []) {
  const o = n.playlists[t];
  if (!o || r.includes(t) || r.length >= en) return [];
  let a = [];
  const l = [];
  for (const c of o.items ?? []) {
    if (!an(c, s, e)) continue;
    let h = [];
    if (c.playlist) h = K(n, c.playlist, e, s, i, [...r, t]);
    else if (c.layout && c.layout in n.layouts) {
      const d = c.duration || n.layouts[c.layout] || o.default || nn;
      h = [{ layout: c.layout, duration: d, item: c.id }];
    }
    h.length && (a.push(h), l.push(Math.max(1, Math.trunc(c.weight || 1))));
  }
  return o.mode === "weighted" ? a = on(a, l) : o.mode === "shuffle" && (a = rn(a, sn(`${t}:${i}`))), a.flat();
}
function cn(n, t) {
  return (n[0] === null || n[0] <= t) && (n[1] === null || t < n[1]);
}
function ln(n, t) {
  const e = [];
  return n.entries.forEach((s, i) => {
    const r = s.windows.find((o) => cn(o, t));
    r && e.push({ key: [-s.priority, -(r[0] ?? -1), i], entry: s, w: r });
  }), e.sort((s, i) => s.key[0] - i.key[0] || s.key[1] - i.key[1] || s.key[2] - i.key[2]), e.map((s) => [s.entry, s.w]);
}
function hn(n, t, e, s, i) {
  const r = s.content, o = { entry: s.id, index: 0, count: 1, start: i[0], end: i[1] };
  if (r.message !== void 0) return r.message in (n.messages ?? {}) ? { ...o, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in n.layouts ? { ...o, layout: r.layout } : null;
  const a = r.playlist, l = i[0] ?? 0;
  let c = K(n, a, t, e, 0);
  const h = c.reduce((p, k) => p + k.duration, 0);
  if (!h) return null;
  const d = Math.floor((e - l) / h);
  d && (c = K(n, a, t, e, d));
  let u = e - l - d * h, m = l + d * h;
  for (let p = 0; p < c.length; p++) {
    const k = c[p];
    if (u < k.duration) {
      let j = m + k.duration;
      return i[1] !== null && (j = Math.min(j, i[1])), { ...o, layout: k.layout, item: k.item, index: p, count: c.length, start: m, end: j };
    }
    u -= k.duration, m += k.duration;
  }
  return null;
}
function dn(n, t, e) {
  for (const [s, i] of ln(n, e)) {
    const r = hn(n, t, e, s, i);
    if (r) return r;
  }
  return null;
}
function un(n, t, e) {
  const s = e?.end != null ? [e.end] : [];
  for (const i of n.entries)
    for (const [r, o] of i.windows)
      r !== null && r > t && s.push(r), o !== null && o > t && s.push(o);
  return s.length ? Math.min(...s) : null;
}
const fn = "evac-player-content-v1", pn = "content/theme/", mn = /url\("([^"]+)"\)/g;
async function lt(n, t) {
  const e = await caches.open(fn).catch(() => null), s = await e?.match(n).catch(() => {
  });
  if (s) return s;
  const i = new AbortController(), r = setTimeout(() => i.abort(), 1e4);
  try {
    const o = await fetch(n, {
      headers: { Authorization: `Screen ${t}` },
      credentials: "omit",
      signal: i.signal
    });
    if (o.ok)
      return await e?.put(n, o.clone()), o;
  } catch {
  } finally {
    clearTimeout(r);
  }
  return null;
}
async function gn(n, t) {
  try {
    const e = await M(n, pn, { token: t });
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
function yn(n) {
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
const ht = [];
async function dt(n, t, e = document.documentElement) {
  const s = document.fonts;
  await Promise.all(yn(n.fonts_css).map(async (i) => {
    const r = await lt(i.url, t);
    if (r)
      try {
        const o = new FontFace(i.family, await r.arrayBuffer(), {
          weight: i.weight,
          style: i.style,
          unicodeRange: i.unicodeRange
        });
        s.add(await o.load());
      } catch {
      }
  })), ht.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, r] of Object.entries(n.variables)) {
    let o = r;
    for (const a of r.matchAll(mn)) {
      const l = await lt(a[1], t);
      if (l) {
        const c = URL.createObjectURL(await l.blob());
        ht.push(c), o = o.replace(a[1], c);
      }
    }
    e.style.setProperty(i, o);
  }
  e.dataset.theme = n.key || "default";
}
function wn(n = document) {
  const t = n.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, s = new URLSearchParams(n.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: s.get("mode") === "obs" ? "obs" : "screen"
  };
}
function x(n, t, e = {}) {
  let s = n.strings[t] ?? t;
  for (const [i, r] of Object.entries(e)) s = s.replace(`{${i}}`, String(r));
  return s;
}
function vn(n, t = location) {
  return n.ws ? n.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const D = [], _ = [], bn = Date.now(), Sn = 300;
let T = [], Z = null;
function v(n, t) {
  _.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n.toUpperCase()} ${t}`.slice(0, 500)), _.length > Sn && _.shift();
}
function kn() {
  return [..._];
}
function y(n) {
  D.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n}`.slice(0, 300)), D.length > 10 && D.shift(), v("error", n);
  const t = Date.now();
  T = T.filter((e) => t - e < 6e4), T.push(t), T.length >= 50 && Z && (T = [], Z());
}
function $n(n) {
  Z = n;
}
function En(n = window) {
  n.addEventListener("error", (t) => y(t.message || "error")), n.addEventListener("unhandledrejection", (t) => y(String(t.reason)));
  for (const t of ["warn", "info"]) {
    const e = console[t].bind(console);
    console[t] = (...s) => {
      v(t, s.map(String).join(" ")), e(...s);
    };
  }
}
function ut(n) {
  const t = window.innerWidth, e = window.innerHeight, s = performance.memory;
  return {
    version: n.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - bn) / 1e3),
    slide: n.slide,
    errors: [...D],
    memory: s ? Math.round(s.usedJSHeapSize / 1048576) : null,
    last_sync: n.lastSync ? new Date(n.lastSync).toISOString() : null,
    online: n.online,
    user_agent: navigator.userAgent,
    ...n.contentVersion ? { content_version: n.contentVersion } : {},
    ...n.displayState ? { display_state: n.displayState } : {},
    ...n.capture !== void 0 ? { capture: n.capture } : {},
    ...n.recovered ? { recovered: n.recovered } : {}
  };
}
const It = "evac.player.reloads", B = "evac.player.alive", xn = 3, Mn = 10 * 6e4;
function Nt(n) {
  try {
    return localStorage.getItem(n);
  } catch {
    return null;
  }
}
function W(n, t) {
  try {
    t === null ? localStorage.removeItem(n) : localStorage.setItem(n, t);
  } catch {
  }
}
function An(n = Date.now()) {
  try {
    return JSON.parse(Nt(It) ?? "[]").filter((t) => n - t < Mn);
  } catch {
    return [];
  }
}
function R(n, t = {}) {
  const e = Date.now(), s = An(e);
  return !t.force && s.length >= xn ? (y(`reload (${n}) skipped: ${s.length} reloads in the last 10 minutes`), !1) : (W(It, JSON.stringify([...s, e])), v("info", `reload: ${n}`), zt(), (t.win ?? location).reload(), !0);
}
function Cn(n = Date.now()) {
  const t = Nt(B);
  if (W(B, String(n)), !t || t === "clean") return "";
  const e = Number(t);
  return Number.isFinite(e) ? `restarted after an unclean stop (last sign of life ${new Date(e).toISOString()})` : "";
}
function Tn(n = Date.now()) {
  W(B, String(n));
}
function zt() {
  W(B, "clean");
}
function Pn(n = window) {
  n.addEventListener("pagehide", () => zt());
}
function In() {
  const n = performance.memory;
  return !!n && n.jsHeapSizeLimit > 0 && n.usedJSHeapSize / n.jsHeapSizeLimit > 0.85;
}
function Ot() {
  return typeof navigator < "u" && !!navigator.mediaDevices?.getDisplayMedia;
}
function Nn(n, t, e) {
  return new Promise((s, i) => {
    const r = setTimeout(() => i(new Error(`${e} timed out`)), t);
    n.then((o) => {
      clearTimeout(r), s(o);
    }, (o) => {
      clearTimeout(r), i(o);
    });
  });
}
async function zn(n = 1e4) {
  return Nn(On(), n, "screen capture");
}
async function On() {
  if (!Ot()) throw new Error("screen capture is not available in this browser");
  const n = document.createElement("div");
  n.className = "evac-capture-dot", document.body.appendChild(n);
  let t = 0;
  const e = setInterval(() => n.classList.toggle("on", t++ % 2 === 0), 16);
  try {
    return await Dn();
  } finally {
    clearInterval(e), n.remove();
  }
}
async function Dn() {
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
async function J(n, t, e, s) {
  const i = typeof Blob < "u" && s instanceof Blob;
  await fetch(`${n}upload/${e}/`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Screen ${t}`, "Content-Type": i ? s.type : "application/json" },
    body: i ? s : JSON.stringify(s)
  });
}
async function _n() {
  try {
    if (typeof caches < "u") for (const n of await caches.keys()) await caches.delete(n);
  } catch {
  }
  try {
    for (const n of Object.keys(localStorage))
      n.startsWith("evac.player.") && n !== "evac.player.token" && localStorage.removeItem(n);
  } catch {
  }
  try {
    for (const n of await navigator.serviceWorker?.getRegistrations?.() ?? []) await n.unregister();
  } catch {
  }
}
function ft(n, t) {
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
function pt(n, t, e) {
  return !t || !e || t === e ? !1 : t < e ? n >= t && n < e : n >= t || n < e;
}
function Rn(n, t) {
  return pt(t, n.sleep_from, n.sleep_until) ? "sleeping" : pt(t, n.dim_from, n.dim_until) ? "dimmed" : "on";
}
function Fn(n) {
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
function Bn(n, t) {
  const e = Fn(t);
  n.classList.add("evac-root"), n.style.width = e.width, n.style.height = e.height, n.style.transform = e.transform, n.style.setProperty("--evac-overscan", e.overscan);
}
function Ln(n, t, e = document) {
  let s = e.getElementById("evac-dim");
  if (n === "on") {
    s?.remove();
    return;
  }
  s || (s = e.createElement("div"), s.id = "evac-dim", s.setAttribute("aria-hidden", "true"), e.body.appendChild(s));
  const i = n === "sleeping" ? 0 : Math.max(10, Math.min(90, t.dim_level ?? 40));
  s.style.opacity = String(1 - i / 100), s.dataset.state = n;
}
const Q = "evac.player.token", it = "evac.player.config";
function Wn() {
  try {
    return localStorage.getItem(Q);
  } catch {
    return null;
  }
}
function mt(n) {
  try {
    n ? localStorage.setItem(Q, n) : (localStorage.removeItem(Q), localStorage.removeItem(it));
  } catch {
  }
}
function jn() {
  try {
    const n = localStorage.getItem(it);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function gt(n) {
  try {
    localStorage.setItem(it, JSON.stringify(n));
  } catch {
  }
}
const yt = 3e3;
function I(n) {
  document.documentElement.dataset.boot = n;
}
const wt = 6e4, Hn = 36e5, vt = 15e3;
class Un {
  constructor(t, e) {
    this.env = t, this.root = e, this.clock = new Bt(), this.overlays = new tn(), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.program = null, this.shown = "", this.timer = null, this.refresher = null, this.housekeeping = null, this.displayState = "on", this.recovered = "", this.lastTick = Date.now(), this.reloadAtNextSlide = "", this.lastDailyReload = "", this.display = new je(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    I("boot"), this.recovered = Cn(), v("info", `player ${this.env.version} started (${navigator.userAgent})`), this.recovered && v("warn", this.recovered);
    const t = Wn();
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
      e = await Rt(this.env.api, ut({
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
    const s = async () => {
      try {
        const i = await Ft(this.env.api, e);
        if (i.status === "paired")
          return mt(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        y(String(i));
      }
      setTimeout(() => {
        s();
      }, yt);
    };
    setTimeout(() => {
      s();
    }, yt);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = jn();
    I(e ? "play: cached config" : "play: no cached config"), e && (this.config = e, this.bundle = X(), this.program = Y(), this.applySettings(), this.bundle && dt({ ...this.bundle.theme, fonts_css: this.bundle.fonts_css }, t).catch((s) => y(String(s))), this.show(), I("play: shown from cache"));
    try {
      const s = Date.now();
      this.config = await rt(this.env.api, t), this.clock.add(s, Date.now(), this.config.server_time), this.lastSync = Date.now(), gt(this.config);
    } catch (s) {
      if (s instanceof S) return this.unpair();
      y(String(s)), this.config = e;
    }
    this.applySettings(), this.bundle = this.bundle ?? X(), this.program = this.program ?? Y(), await this.loadContent(t), await this.loadProgram(t), this.show(), I("play: online"), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, Hn), this.housekeeping = setInterval(() => this.tick(), vt), this.conn = new jt({
      api: this.env.api,
      ws: vn(this.env),
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
        capture: Ot(),
        recovered: this.recovered
      }),
      onMessage: (s) => {
        this.handle(s, t);
      },
      onTransport: (s) => {
        s !== this.transport && v("info", `connection: ${s}`), this.transport = s;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (s) => {
        this.lastSync = s;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch (v("info", `message: ${t.type}`), t.type) {
      case "config.changed":
        try {
          this.config = await rt(this.env.api, e), gt(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), this.applySettings();
          const s = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(e), await this.loadProgram(e), (`${this.bundle?.version}/${this.program?.version}` !== s || this.slide === "idle") && (this.shown = "", this.show());
        } catch (s) {
          s instanceof S && this.unpair();
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
      case "reload":
        R("requested by staff", { force: !0 });
        break;
      case "clear_cache":
        await _n(), R("cache cleared by staff", { force: !0 });
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
          await J(this.env.api, e, "screenshot", await zn());
        } catch (s) {
          y(`screenshot: ${String(s)}`), await J(this.env.api, e, "screenshot", { error: String(s).slice(0, 280) }).catch(() => {
          });
        }
        break;
      case "logs":
        await J(this.env.api, e, "logs", { lines: kn() }).catch((s) => y(String(s)));
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await He(this.env.api, t) ?? this.bundle;
    } catch (s) {
      if (s instanceof S) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await gn(this.env.api, t);
    e && await dt(e, t).catch((s) => y(String(s))), this.bundle && Je(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await Ge(this.env.api, t);
    } catch (e) {
      e instanceof S && this.unpair();
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
      this.slide = "error", this.display.message(x(this.env, "no_server"), x(this.env, "retrying"));
      return;
    }
    const e = this.clock.now();
    let s = null, i, r = "idle", o = null;
    if (this.program && this.bundle) {
      if (o = dn(this.program, this.vars(), e), o?.message)
        s = this.program.messages?.[o.message] ?? null, r = `${o.entry}|message`, this.slide = `${o.entry} message`;
      else if (o?.layout) {
        const d = this.bundle.layouts.find((u) => u.id === o?.layout);
        d && (s = d.data, i = d.variables, r = `${o.entry}|${d.id}|${d.version}|${o.count > 1 ? o.start : ""}`, this.slide = `${d.key} v${d.version} (${o.entry} ${o.index + 1}/${o.count})`);
      }
      const c = [un(this.program, e, o), Ye(this.program.overlays, e)].filter((d) => d !== null), h = Math.max(5, Math.min(wt, (c.length ? Math.min(...c) : e + wt) - e));
      this.timer = setTimeout(() => this.show(), h);
    } else {
      const c = qe(this.bundle);
      c && (s = c.data, i = c.variables, r = `default|${c.id}|${c.version}`, this.slide = `${c.key} v${c.version}`);
    }
    const a = { enabled: t.display?.audio !== !1, volume: t.display?.volume ?? 100 }, l = !!o && (o.entry.startsWith("announcement:") || o.entry.startsWith("evacuation"));
    if (this.overlays.update(this.program?.overlays, e, { hidden: l, audio: a }), r !== this.shown && !(this.reloadAtNextSlide && this.shown && R(this.reloadAtNextSlide))) {
      this.reloadAtNextSlide = "", this.shown = r, v("info", `showing ${this.slide}`);
      try {
        if (!s || !this.bundle) throw new Error("nothing to show");
        this.display.layout(s, {
          vars: this.vars(),
          now: () => this.clock.now(),
          timezone: t.event.timezone,
          assets: this.bundle.assets,
          fonts: this.bundle.fonts,
          reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
          audio: a,
          nonce: ee(),
          onError: (c, h) => y(`${c}: ${String(h)}`),
          onLog: (c, h) => v("info", `${c}: ${h}`)
        }, i);
      } catch (c) {
        s && y(`render failed, showing the idle slide: ${String(c)}`), this.slide = "idle", this.display.idle(t);
      }
      this.overlays.attach(this.root);
    }
  }
  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  applySettings() {
    const t = this.config?.display ?? {};
    Bn(this.root, t), this.updateDisplayState();
  }
  updateDisplayState() {
    const t = this.config?.display ?? {}, e = Rn(t, ft(this.clock.now(), this.config?.event.timezone));
    e !== this.displayState && v("info", `display ${e}`), this.displayState = e, Ln(e, t);
  }
  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  tick() {
    const t = Date.now(), e = t - this.lastTick > vt * 3;
    this.lastTick = t, Tn(t), this.updateDisplayState(), e && (v("warn", "timers were stalled; resynchronising"), this.shown = "", this.show());
    const s = this.config?.display?.daily_reload, i = ft(this.clock.now(), this.config?.event.timezone);
    s && i === s && this.lastDailyReload !== i && performance.now() > 36e5 && (this.lastDailyReload = i, this.reloadAtNextSlide = "daily reload"), In() && !this.reloadAtNextSlide && (this.reloadAtNextSlide = "memory pressure");
  }
  unpair() {
    this.housekeeping && clearInterval(this.housekeeping), this.housekeeping = null, this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.timer = this.refresher = null, Ve(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, mt(null), Ue(), this.pair();
  }
}
function qn() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((n) => y(String(n)));
}
if (typeof document < "u" && document.getElementById("player")) {
  En(), Pn(), $n(() => R("50 errors within a minute")), qn();
  const n = wn();
  new Un(n, document.getElementById("player")).boot();
}
export {
  Un as Player
};
