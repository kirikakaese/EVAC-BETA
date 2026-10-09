// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var Pt = Object.defineProperty;
var It = (n, t, e) => t in n ? Pt(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var C = (n, t, e) => It(n, typeof t != "symbol" ? t + "" : t, e);
class w extends Error {
}
async function M(n, t, e = {}) {
  const i = new AbortController(), s = setTimeout(() => i.abort(), e.timeout ?? 1e4), r = new Headers(e.headers);
  r.set("Accept", "application/json"), e.body && r.set("Content-Type", "application/json"), e.token && r.set("Authorization", `Screen ${e.token}`);
  try {
    const o = await fetch(n + t, {
      ...e,
      headers: r,
      signal: i.signal,
      cache: "no-store",
      credentials: "omit"
    });
    if (o.status === 401) throw new w("token rejected");
    if (!o.ok) throw new Error(`HTTP ${o.status}`);
    return await o.json();
  } finally {
    clearTimeout(s);
  }
}
const Nt = (n, t) => M(n, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), zt = (n, t) => M(n, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), tt = (n, t) => M(n, "config/", { token: t });
class Dt {
  constructor() {
    this.samples = [], this.offset = 0;
  }
  add(t, e, i) {
    const s = e - t;
    s < 0 || !Number.isFinite(i) || (this.samples.push({ offset: i * 1e3 - (t + e) / 2, rtt: s }), this.samples.length > 8 && this.samples.shift(), this.offset = this.samples.reduce((r, o) => o.rtt < r.rtt ? o : r).offset);
  }
  now() {
    return Date.now() + this.offset;
  }
}
const _t = 3e4, Ot = 3e5;
class Rt {
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
    this.backoff = Math.min(this.backoff * 2, _t), setTimeout(() => !this.stopped && t(), e);
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
    }, e.onmessage = (i) => {
      let s;
      try {
        s = JSON.parse(String(i.data));
      } catch {
        return;
      }
      s.type === "hello" ? (this.wsFailures = 0, this.backoff = 1e3, this.setTransport("websocket"), this.beat()) : s.type === "heartbeat.ack" ? this.ack(s.server_time ?? NaN) : s.type !== "pong" && this.deliver(s);
    }, e.onclose = (i) => {
      if (this.ws = null, !this.stopped) {
        if (i.code === 4401) {
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > Ot ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        if (t.status === 401) throw new w("token rejected");
        if (!t.ok || !t.body) throw new Error(`SSE HTTP ${t.status}`);
        this.setTransport("sse"), this.backoff = 1e3;
        const e = t.body.getReader(), i = new TextDecoder();
        let s = "";
        for (; ; ) {
          const { value: r, done: o } = await e.read();
          if (o) break;
          s += i.decode(r, { stream: !0 });
          let a;
          for (; (a = s.indexOf(`

`)) >= 0; ) {
            const c = s.slice(0, a);
            s = s.slice(a + 2);
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
        t instanceof w ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
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
        if (t instanceof w) {
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
      e instanceof w ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function P(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function Ft(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function Bt(n, t, e) {
  const i = n.style;
  if (!t) return;
  const s = (r, o) => {
    o && i.setProperty(r, o);
  };
  s("color", P(t.color)), s("background", P(t.background)), t.borderWidth && i.setProperty("border", `${t.borderWidth / 10}cqh solid ${P(t.borderColor) || "currentColor"}`), t.radius !== void 0 && i.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && i.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && i.setProperty("opacity", String(t.opacity)), s("font-family", Ft(t.fontFamily, e)), t.fontSize && i.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && i.setProperty("font-weight", String(t.fontWeight)), s("font-style", t.fontStyle ?? ""), s("text-align", t.textAlign ?? ""), t.verticalAlign && i.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && i.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && i.setProperty("letter-spacing", `${t.letterSpacing}em`), s("text-transform", t.textTransform ?? ""), t.tabularNumbers && i.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && i.setProperty("box-shadow", "var(--evac-shadow)");
}
function Lt(n, t, e) {
  const i = t.trim();
  if (i === "now") return new Date(e.now ? e.now() : Date.now());
  if (/^".*"$|^'.*'$/.test(i)) return i.slice(1, -1);
  if (/^-?\d+(\.\d+)?$/.test(i)) return Number(i);
  let s = n;
  for (const r of i.split(".")) {
    if (s == null || typeof s != "object") return;
    s = s[r];
  }
  return s;
}
function Wt(n) {
  const t = [];
  let e = "", i = "";
  for (const s of n)
    i ? (s === i && (i = ""), e += s) : s === '"' || s === "'" ? (i = s, e += s) : s === "|" ? (t.push(e), e = "") : e += s;
  return t.push(e), t.map((s) => s.trim());
}
function jt(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function et(n, t, e) {
  const i = e ? { timeZone: e } : {};
  switch (t) {
    case "short":
      return new Intl.DateTimeFormat("en-GB", { ...i, day: "numeric", month: "short" }).format(n);
    case "weekday":
      return new Intl.DateTimeFormat("en-GB", { ...i, weekday: "long" }).format(n);
    case "iso":
      return n.toISOString().slice(0, 10);
    case "HH:mm":
      return new Intl.DateTimeFormat("en-GB", { ...i, hour: "2-digit", minute: "2-digit" }).format(n);
    case "HH:mm:ss":
      return new Intl.DateTimeFormat("en-GB", { ...i, hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(n);
    case "h:mm a":
      return new Intl.DateTimeFormat("en-US", { ...i, hour: "numeric", minute: "2-digit" }).format(n);
    default:
      return new Intl.DateTimeFormat("en-GB", {
        ...i,
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
      }).format(n);
  }
}
function y(n) {
  return n == null ? "" : Array.isArray(n) ? n.map(y).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function Ht(n, t, e) {
  const [i, ...s] = t.split(":"), r = jt(s.join(":")), o = () => n instanceof Date ? n : new Date(String(n));
  switch (i.trim()) {
    case "upper":
      return y(n).toUpperCase();
    case "lower":
      return y(n).toLowerCase();
    case "title":
      return y(n).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = y(n);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return y(n) === "" ? r : n;
    case "date":
      return isNaN(o().getTime()) ? "" : et(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : et(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map(y).join(r || ", ") : y(n);
    default:
      return n;
  }
}
function I(n, t, e = {}) {
  const [i, ...s] = Wt(n);
  let r = Lt(t, i, e);
  for (const o of s) r = Ht(r, o, e);
  return r;
}
function Ut(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function F(n, t, e = {}) {
  const i = n.trim();
  if (!i) return !0;
  if (i.startsWith("not ")) return !F(i.slice(4), t, e);
  const s = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(i);
  if (s) {
    const r = y(I(s[1], t, e)), o = y(I(s[3], t, e));
    return s[2] === "==" ? r === o : r !== o;
  }
  return Ut(I(i.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const qt = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function Jt(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const i = n.split(qt);
  let s = 0;
  const r = (o) => {
    let a = "";
    for (; s < i.length; ) {
      const c = i[s++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(h)) return [a, h];
        if (h === "if") {
          const d = F(l[2], t, e), [f, g] = r(["else", "endif"]);
          let p = "";
          g === "else" && (p = r(["endif"])[0]), a += d ? f : p;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += y(I(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
var A = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(A || {});
const Gt = [0, 1], ft = [1, 0], pt = [2, 3], mt = [3, 2], Vt = {
  L: Gt,
  M: ft,
  Q: pt,
  H: mt
}, Xt = /^\d*$/, Yt = /^[A-Z0-9 $%*+./:-]*$/, W = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", X = 1, Y = 40, nt = 3, Kt = 3, T = 40, Zt = 10, gt = [
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
], yt = [
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
class Qt {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, i, s) {
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
    if (this.version = t, this.ecc = e, t < X || t > Y)
      throw new RangeError("Version value out of range");
    if (s < -1 || s > 7)
      throw new RangeError("Mask value out of range");
    this.size = t * 4 + 17;
    const r = Array.from({ length: this.size }).fill(!1);
    for (let a = 0; a < this.size; a++)
      this.modules.push(r.slice()), this.types.push(r.map(() => 0));
    this.drawFunctionPatterns();
    const o = this.addEccAndInterleave(i);
    if (this.drawCodewords(o), s === -1) {
      let a = 1e9;
      for (let c = 0; c < 8; c++) {
        this.applyMask(c), this.drawFormatBits(c);
        const l = this.getPenaltyScore();
        l < a && (s = c, a = l), this.applyMask(c);
      }
    }
    this.mask = s, this.applyMask(s), this.drawFormatBits(s);
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
    for (let i = 0; i < this.size; i++)
      this.setFunctionModule(6, i, i % 2 === 0, A.Timing), this.setFunctionModule(i, 6, i % 2 === 0, A.Timing);
    this.drawFinderPattern(3, 3), this.drawFinderPattern(this.size - 4, 3), this.drawFinderPattern(3, this.size - 4);
    const t = this.getAlignmentPatternPositions(), e = t.length;
    for (let i = 0; i < e; i++)
      for (let s = 0; s < e; s++)
        i === 0 && s === 0 || i === 0 && s === e - 1 || i === e - 1 && s === 0 || this.drawAlignmentPattern(t[i], t[s]);
    this.drawFormatBits(0), this.drawVersion();
  }
  // Draws two copies of the format bits (with its own error correction code)
  // based on the given mask and this object's error correction level field.
  drawFormatBits(t) {
    const e = this.ecc[1] << 3 | t;
    let i = e;
    for (let r = 0; r < 10; r++)
      i = i << 1 ^ (i >>> 9) * 1335;
    const s = (e << 10 | i) ^ 21522;
    for (let r = 0; r <= 5; r++)
      this.setFunctionModule(8, r, k(s, r));
    this.setFunctionModule(8, 7, k(s, 6)), this.setFunctionModule(8, 8, k(s, 7)), this.setFunctionModule(7, 8, k(s, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, k(s, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, k(s, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, k(s, r));
    this.setFunctionModule(8, this.size - 8, !0);
  }
  // Draws two copies of the version bits (with its own error correction code),
  // based on this object's version field, iff 7 <= version <= 40.
  drawVersion() {
    if (this.version < 7)
      return;
    let t = this.version;
    for (let i = 0; i < 12; i++)
      t = t << 1 ^ (t >>> 11) * 7973;
    const e = this.version << 12 | t;
    for (let i = 0; i < 18; i++) {
      const s = k(e, i), r = this.size - 11 + i % 3, o = Math.floor(i / 3);
      this.setFunctionModule(r, o, s), this.setFunctionModule(o, r, s);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let i = -4; i <= 4; i++)
      for (let s = -4; s <= 4; s++) {
        const r = Math.max(Math.abs(s), Math.abs(i)), o = t + s, a = e + i;
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, A.Position);
      }
  }
  // Draws a 5*5 alignment pattern, with the center module
  // at (x, y). All modules must be in bounds.
  drawAlignmentPattern(t, e) {
    for (let i = -2; i <= 2; i++)
      for (let s = -2; s <= 2; s++)
        this.setFunctionModule(
          t + s,
          e + i,
          Math.max(Math.abs(s), Math.abs(i)) !== 1,
          A.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, i, s = A.Function) {
    this.modules[e][t] = i, this.types[e][t] = s;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, i = this.ecc;
    if (t.length !== N(e, i))
      throw new RangeError("Invalid argument");
    const s = yt[i[0]][e], r = gt[i[0]][e], o = Math.floor(U(e) / 8), a = s - o % s, c = Math.floor(o / s), l = [], h = ce(r);
    for (let f = 0, g = 0; f < s; f++) {
      const p = t.slice(g, g + c - r + (f < a ? 0 : 1));
      g += p.length;
      const b = le(p, h);
      f < a && p.push(0), l.push(p.concat(b));
    }
    const d = [];
    for (let f = 0; f < l[0].length; f++)
      l.forEach((g, p) => {
        (f !== c - r || p >= a) && d.push(g[f]);
      });
    return d;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(U(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let i = this.size - 1; i >= 1; i -= 2) {
      i === 6 && (i = 5);
      for (let s = 0; s < this.size; s++)
        for (let r = 0; r < 2; r++) {
          const o = i - r, c = (i + 1 & 2) === 0 ? this.size - 1 - s : s;
          !this.types[c][o] && e < t.length * 8 && (this.modules[c][o] = k(t[e >>> 3], 7 - (e & 7)), e++);
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
      for (let i = 0; i < this.size; i++) {
        let s;
        switch (t) {
          case 0:
            s = (i + e) % 2 === 0;
            break;
          case 1:
            s = e % 2 === 0;
            break;
          case 2:
            s = i % 3 === 0;
            break;
          case 3:
            s = (i + e) % 3 === 0;
            break;
          case 4:
            s = (Math.floor(i / 3) + Math.floor(e / 2)) % 2 === 0;
            break;
          case 5:
            s = i * e % 2 + i * e % 3 === 0;
            break;
          case 6:
            s = (i * e % 2 + i * e % 3) % 2 === 0;
            break;
          case 7:
            s = ((i + e) % 2 + i * e % 3) % 2 === 0;
            break;
          default:
            throw new Error("Unreachable");
        }
        !this.types[e][i] && s && (this.modules[e][i] = !this.modules[e][i]);
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
        this.modules[r][l] === o ? (a++, a === 5 ? t += nt : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * T), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * T;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += nt : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * T), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * T;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += Kt);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const i = this.size * this.size, s = Math.ceil(Math.abs(e * 20 - i * 10) / i) - 1;
    return t += s * Zt, t;
  }
  /* -- Private helper functions -- */
  // Returns an ascending list of positions of alignment patterns for this version number.
  // Each position is in the range [0,177), and are used on both the x and y axes.
  // This could be implemented as lookup table of 40 variable-length lists of integers.
  getAlignmentPatternPositions() {
    if (this.version === 1)
      return [];
    {
      const t = Math.floor(this.version / 7) + 2, e = this.version === 32 ? 26 : Math.ceil((this.version * 4 + 4) / (t * 2 - 2)) * 2, i = [6];
      for (let s = this.size - 7; i.length < t; s -= e)
        i.splice(1, 0, s);
      return i;
    }
  }
  // Can only be called immediately after a light run is added, and
  // returns either 0, 1, or 2. A helper function for getPenaltyScore().
  finderPenaltyCountPatterns(t) {
    const e = t[1], i = e > 0 && t[2] === e && t[3] === e * 3 && t[4] === e && t[5] === e;
    return (i && t[0] >= e * 4 && t[6] >= e ? 1 : 0) + (i && t[6] >= e * 4 && t[0] >= e ? 1 : 0);
  }
  // Must be called at the end of a line (row or column) of modules. A helper function for getPenaltyScore().
  finderPenaltyTerminateAndCount(t, e, i) {
    return t && (this.finderPenaltyAddHistory(e, i), e = 0), e += this.size, this.finderPenaltyAddHistory(e, i), this.finderPenaltyCountPatterns(i);
  }
  // Pushes the given value to the front and drops the last value. A helper function for getPenaltyScore().
  finderPenaltyAddHistory(t, e) {
    e[0] === 0 && (t += this.size), e.pop(), e.unshift(t);
  }
}
function E(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let i = t - 1; i >= 0; i--)
    e.push(n >>> i & 1);
}
function k(n, t) {
  return (n >>> t & 1) !== 0;
}
class K {
  // Creates a new QR Code segment with the given attributes and data.
  // The character count (numChars) must agree with the mode and the bit buffer length,
  // but the constraint isn't checked. The given bit buffer is cloned and stored.
  constructor(t, e, i) {
    if (this.mode = t, this.numChars = e, this.bitData = i, e < 0)
      throw new RangeError("Invalid argument");
    this.bitData = i.slice();
  }
  /* -- Methods -- */
  // Returns a new copy of the data bits of this segment.
  getData() {
    return this.bitData.slice();
  }
}
const te = [1, 10, 12, 14], ee = [2, 9, 11, 13], ne = [4, 8, 16, 16];
function wt(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function vt(n) {
  const t = [];
  for (const e of n)
    E(e, 8, t);
  return new K(ne, n.length, t);
}
function ie(n) {
  if (!bt(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const i = Math.min(n.length - e, 3);
    E(Number.parseInt(n.substring(e, e + i), 10), i * 3 + 1, t), e += i;
  }
  return new K(te, n.length, t);
}
function se(n) {
  if (!St(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let i = W.indexOf(n.charAt(e)) * 45;
    i += W.indexOf(n.charAt(e + 1)), E(i, 11, t);
  }
  return e < n.length && E(W.indexOf(n.charAt(e)), 6, t), new K(ee, n.length, t);
}
function re(n) {
  return n === "" ? [] : bt(n) ? [ie(n)] : St(n) ? [se(n)] : [vt(ae(n))];
}
function bt(n) {
  return Xt.test(n);
}
function St(n) {
  return Yt.test(n);
}
function oe(n, t) {
  let e = 0;
  for (const i of n) {
    const s = wt(i.mode, t);
    if (i.numChars >= 1 << s)
      return Number.POSITIVE_INFINITY;
    e += 4 + s + i.bitData.length;
  }
  return e;
}
function ae(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function U(n) {
  if (n < X || n > Y)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function N(n, t) {
  return Math.floor(U(n) / 8) - gt[t[0]][n] * yt[t[0]][n];
}
function ce(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let i = 0; i < n - 1; i++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let i = 0; i < n; i++) {
    for (let s = 0; s < t.length; s++)
      t[s] = q(t[s], e), s + 1 < t.length && (t[s] ^= t[s + 1]);
    e = q(e, 2);
  }
  return t;
}
function le(n, t) {
  const e = t.map((i) => 0);
  for (const i of n) {
    const s = i ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= q(r, s));
  }
  return e;
}
function q(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let i = 7; i >= 0; i--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> i & 1) * n;
  return e;
}
function he(n, t, e = 1, i = 40, s = -1, r = !0) {
  if (!(X <= e && e <= i && i <= Y) || s < -1 || s > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const d = N(o, t) * 8, f = oe(n, o);
    if (f <= d) {
      a = f;
      break;
    }
    if (o >= i)
      throw new RangeError("Data too long");
  }
  for (const d of [ft, pt, mt])
    r && a <= N(o, d) * 8 && (t = d);
  const c = [];
  for (const d of n) {
    E(d.mode[0], 4, c), E(d.numChars, wt(d.mode, o), c);
    for (const f of d.getData())
      c.push(f);
  }
  const l = N(o, t) * 8;
  E(0, Math.min(4, l - c.length), c), E(0, (8 - c.length % 8) % 8, c);
  for (let d = 236; c.length < l; d ^= 253)
    E(d, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((d, f) => h[f >>> 3] |= d << 7 - (f & 7)), new Qt(o, t, h, s);
}
function de(n, t) {
  const {
    ecc: e = "L",
    boostEcc: i = !1,
    minVersion: s = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof n == "string" ? re(n) : Array.isArray(n) ? [vt(n)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const l = he(
    c,
    Vt[e],
    s,
    r,
    o,
    i
  ), h = ue({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (h.data = h.data.map((d) => d.map((f) => !f))), t?.onEncoded?.(h), h;
}
function ue(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, i = e + t * 2;
  n.size = i, n.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    n.data.unshift(Array.from({ length: i }, (o) => !1)), n.data.push(Array.from({ length: i }, (o) => !1));
  const s = A.Border;
  n.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(s), r.push(s);
  });
  for (let r = 0; r < t; r++)
    n.types.unshift(Array.from({ length: i }, (o) => s)), n.types.push(Array.from({ length: i }, (o) => s));
  return n;
}
const j = "http://www.w3.org/2000/svg";
function kt(n, t = document) {
  const { data: e, size: i } = de(n, { ecc: "M", border: 2 }), s = t.createElementNS(j, "svg");
  s.setAttribute("viewBox", `0 0 ${i} ${i}`), s.setAttribute("shape-rendering", "crispEdges"), s.setAttribute("class", "qr");
  const r = t.createElementNS(j, "rect");
  r.setAttribute("width", String(i)), r.setAttribute("height", String(i)), r.setAttribute("fill", "#fff"), s.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((h, d) => {
    h && (o += `M${d} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(j, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), s.appendChild(a), s;
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
    return Jt(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function fe(n, t) {
  t.style.removeProperty("font-size");
  const e = parseFloat(getComputedStyle(t).fontSize) || 16, i = () => t.scrollHeight <= n.clientHeight + 1 && t.scrollWidth <= n.clientWidth + 1;
  if (!n.clientHeight || i()) return;
  let s = Math.max(4, e * 0.1), r = e;
  for (let o = 0; o < 12 && r - s > 0.5; o++) {
    const a = (s + r) / 2;
    t.style.fontSize = `${a}px`, i() ? s = a : r = a;
  }
  t.style.fontSize = `${s}px`;
}
class pe extends v {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-text";
    const e = this.text(this.props.text), i = Number(this.props.clamp) || 0;
    if (this.props.marquee) {
      const s = document.createElement("span");
      s.className = "evac-marquee", s.textContent = e, s.style.animationDuration = `${Math.max(8, e.length / 6)}s`, t.classList.add("evac-marquee-box"), t.appendChild(s);
    } else
      t.textContent = e, i && (t.classList.add("evac-clamp"), t.style.setProperty("-webkit-line-clamp", String(i)));
    if (this.replaceChildren(t), this.props.autofit && !this.props.marquee) {
      const s = () => fe(this, t);
      requestAnimationFrame(s), document.fonts?.ready.then(s).catch(() => {
      }), this.observe(s);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class me extends v {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-richtext";
    for (const e of this.text(this.props.text).split(/\n{2,}/)) {
      const i = document.createElement("p");
      e.split(`
`).forEach((s, r) => {
        r && i.appendChild(document.createElement("br"));
        for (const o of s.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/))
          /^\*\*[^*]+\*\*$/.test(o) ? i.appendChild(Object.assign(
            document.createElement("strong"),
            { textContent: o.slice(2, -2) }
          )) : /^\*[^*]+\*$/.test(o) ? i.appendChild(Object.assign(
            document.createElement("em"),
            { textContent: o.slice(1, -1) }
          )) : o && i.appendChild(document.createTextNode(o));
      }), t.appendChild(i);
    }
    this.replaceChildren(t);
  }
}
function Et(n, t, e) {
  const i = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = n.urls[r], i.appendChild(a);
    }
  const s = document.createElement("img");
  return s.src = n.urls.original, s.alt = e || n.alt || "", s.decoding = "async", s.style.objectFit = t, i.appendChild(s), i;
}
class ge extends v {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(Et(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class ye extends v {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), i = t.map((o) => {
      const a = Et(o, e, "");
      return a.className = "evac-slide", a;
    });
    this.replaceChildren(...i);
    const s = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const o = Math.floor(this.ctx.now() / s) % i.length;
      i.forEach((a, c) => a.classList.toggle("active", c === o));
    };
    r(), this.every(500, r);
  }
}
class we extends v {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Video");
    const e = document.createElement("video");
    e.muted = this.props.muted !== !1 || this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.loop = this.props.loop !== !1, e.playsInline = !0, e.preload = "auto", e.style.objectFit = String(this.props.fit ?? "cover"), t.urls.poster && (e.poster = t.urls.poster);
    for (const i of ["webm", "mp4", "original"]) {
      if (!t.urls[i]) continue;
      const s = document.createElement("source");
      s.src = t.urls[i], s.type = t.mimes[i] || "", e.appendChild(s);
    }
    this.ctx.editing || (e.autoplay = !0, e.play?.()?.catch(() => {
    })), this.replaceChildren(e);
  }
}
class ve extends v {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class be extends v {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Se extends v {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = kt(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const ke = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Ee extends v {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, i = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...ke[t], timeZone: e }), s = document.createElement("time"), r = () => {
      s.textContent = i.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(s), this.every(1e3, r);
  }
}
class $e extends v {
  draw() {
    const t = String(this.props.format ?? "long"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, i = {
      long: { weekday: "long", day: "numeric", month: "long" },
      short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" },
      iso: { year: "numeric", month: "2-digit", day: "2-digit" }
    }, s = new Intl.DateTimeFormat(t === "iso" ? "sv-SE" : "en-GB", { ...i[t], timeZone: e }), r = document.createElement("time"), o = () => {
      r.textContent = s.format(new Date(this.ctx.now()));
    };
    o(), this.replaceChildren(r), this.every(3e4, o);
  }
}
function Me(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), i = Math.floor(e / 86400), s = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${i} ${i === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || i === 0 ? `${a(s + i * 24)}:${a(r)}:${a(o)}` : `${i}d ${a(s)}:${a(r)}:${a(o)}`;
}
class Ae extends v {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), i = () => {
      const s = t - this.ctx.now();
      e.textContent = s <= 0 && this.props.finished ? this.text(this.props.finished) : Me(s, String(this.props.format ?? "auto"));
    };
    i(), this.replaceChildren(e), this.every(250, i);
  }
}
const Ce = {
  text: pe,
  richtext: me,
  image: ge,
  slideshow: ye,
  video: we,
  audio: ve,
  shape: be,
  qr: Se,
  clock: Ee,
  countdown: Ae,
  date: $e
};
function xe(n = customElements) {
  for (const [t, e] of Object.entries(Ce))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
function Te(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function Pe(n, t) {
  const e = !n.visible_if || F(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const i = document.createElement("div");
  i.className = `evac-el evac-el-${n.type}`, i.dataset.id = n.id, (!e || n.hidden) && i.classList.add("evac-dimmed"), Te(i, n), Bt(i, n.style, t);
  const s = n.animation;
  s?.enter && s.enter !== "none" && !t.reducedMotion && !t.editing && (i.classList.add(`evac-enter-${s.enter}`), i.style.animationDuration = `${s.duration ?? 600}ms`, i.style.animationDelay = `${s.delay ?? 0}ms`);
  const r = `evac-${n.type}`;
  if (!customElements.get(r))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? i : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", i.appendChild(o), o.configure(n, t), i;
}
function Ie(n, t, e) {
  xe();
  const i = document.createElement("div");
  i.className = "evac-stage";
  const s = t.background;
  if (s?.color && (i.style.background = P(s.color)), s?.asset && e.assets[s.asset]) {
    const c = e.assets[s.asset], l = c.urls.webp ?? c.urls.original;
    i.style.backgroundImage = `url("${l}")`, i.style.backgroundSize = s.fit ?? "cover", i.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = Pe(c, e);
    l && (r.set(c.id, l), i.appendChild(l));
  }
  n.replaceChildren(i);
  const o = () => {
    const c = n.clientWidth, l = n.clientHeight;
    if (!c || !l) return;
    const h = Math.min(c / t.width, l / t.height);
    i.style.width = `${Math.round(t.width * h)}px`, i.style.height = `${Math.round(t.height * h)}px`;
  };
  o();
  const a = typeof ResizeObserver < "u" ? new ResizeObserver(o) : null;
  return a?.observe(n), {
    stage: i,
    elements: r,
    destroy() {
      a?.disconnect(), i.remove();
    }
  };
}
function u(n, t = "", e = "") {
  const i = document.createElement(n);
  return t && (i.className = t), e && (i.textContent = e), i;
}
class Ne {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = u("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, i) {
    const s = this.reset();
    s.classList.add("pairing"), s.append(u("h1", "", i.title));
    const r = u("div", "pairing-box"), o = u("p", "code", t);
    o.setAttribute("aria-label", t.split("").join(" "));
    const a = kt(e);
    a.setAttribute("role", "img"), a.setAttribute("aria-label", e), r.append(o, a);
    const c = u("ol", "steps");
    c.append(u("li", "", i.step1), u("li", "", i.step2)), s.append(r, c, u("p", "url", e), u("p", "waiting", i.waiting));
  }
  message(t, e = "") {
    const i = this.reset();
    i.classList.add("message"), i.append(u("h1", "", t)), e && i.append(u("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const i = u("p", "clock"), s = u("p", "date");
    e.append(u("h1", "event-name", t.event.name), i, s);
    const r = t.event.timezone || void 0, o = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: r }), a = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: r }), c = () => {
      const l = new Date(this.clock.now());
      i.textContent = o.format(l), s.textContent = a.format(l);
    };
    c(), this.clockTimer = setInterval(c, 1e3);
  }
  layout(t, e, i) {
    const s = this.reset();
    s.classList.add("layout");
    for (const [r, o] of Object.entries(i ?? {})) s.style.setProperty(r, o);
    this.rendered = Ie(s, t, e);
  }
  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(t, e, i = 30) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const s = u("div", "test-pattern");
    s.setAttribute("role", "img"), s.setAttribute("aria-label", t);
    const r = u("div", "tp-bars");
    for (const c of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"])
      r.appendChild(u("span", `tp-bar tp-${c}`));
    const o = u("div", "tp-ramp"), a = u("div", "tp-info");
    a.append(u("p", "tp-title", t), ...e.map((c) => u("p", "", c))), s.append(r, o, u("div", "tp-grid"), u("div", "tp-circle"), u("div", "tp-corners"), a), this.root.appendChild(s), this.overlay = s, this.overlayTimer = setTimeout(() => s.remove(), i * 1e3);
  }
  identify(t, e, i = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const s = u("div", "identify");
    s.setAttribute("role", "status"), s.append(u("p", "identify-name", t), u("p", "identify-detail", e)), this.root.appendChild(s), this.overlay = s, this.overlayTimer = setTimeout(() => s.remove(), i * 1e3);
  }
}
const Z = "evac.player.bundle";
async function ze(n, t) {
  try {
    const e = await M(n, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(Z, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof w) throw e;
    return $t();
  }
}
function $t() {
  try {
    const n = localStorage.getItem(Z);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function De() {
  try {
    localStorage.removeItem(Z);
  } catch {
  }
}
function _e(n) {
  return n?.layouts.length ? n.layouts.find((t) => t.default) ?? n.layouts[0] : null;
}
async function Oe(n) {
  const t = /* @__PURE__ */ new Set();
  for (const i of Object.values(n.assets)) Object.values(i.urls).forEach((s) => t.add(s));
  let e = 0;
  return await Promise.all([...t].map(async (i) => {
    try {
      const s = await fetch(i, { credentials: "omit" });
      s.ok && (e += 1), await s.body?.cancel();
    } catch {
    }
  })), e;
}
const O = "evac.player.program";
async function Re(n, t) {
  try {
    const e = await M(n, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(O, JSON.stringify(e.program)) : localStorage.removeItem(O);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof w) throw e;
    return Mt();
  }
}
function Mt() {
  try {
    const n = localStorage.getItem(O);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function Fe() {
  try {
    localStorage.removeItem(O);
  } catch {
  }
}
const Be = 5, Le = 1e4;
function We(n) {
  let t = 2166136261;
  for (let e = 0; e < n.length; e++)
    t ^= n.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function je(n, t) {
  let e = t >>> 0 || 1;
  const i = [...n];
  for (let s = i.length - 1; s > 0; s--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (s + 1);
    [i[s], i[r]] = [i[r], i[s]];
  }
  return i;
}
function He(n, t) {
  const e = t.reduce((r, o) => r + o, 0), i = t.map(() => 0), s = [];
  for (let r = 0; r < e; r++) {
    t.forEach((a, c) => {
      i[c] += a;
    });
    let o = 0;
    for (let a = 1; a < n.length; a++) i[a] > i[o] && (o = a);
    i[o] -= e, s.push(n[o]);
  }
  return s;
}
function Ue(n, t, e) {
  if (n.from !== null && n.from !== void 0 && t < n.from || n.until !== null && n.until !== void 0 && t >= n.until) return !1;
  const i = n.tags ?? [], s = e.screen?.tags ?? [];
  return i.length && !i.some((r) => s.includes(r)) ? !1 : F(n.when ?? "", e);
}
function J(n, t, e, i, s, r = []) {
  const o = n.playlists[t];
  if (!o || r.includes(t) || r.length >= Be) return [];
  let a = [];
  const c = [];
  for (const l of o.items ?? []) {
    if (!Ue(l, i, e)) continue;
    let h = [];
    if (l.playlist) h = J(n, l.playlist, e, i, s, [...r, t]);
    else if (l.layout && l.layout in n.layouts) {
      const d = l.duration || n.layouts[l.layout] || o.default || Le;
      h = [{ layout: l.layout, duration: d, item: l.id }];
    }
    h.length && (a.push(h), c.push(Math.max(1, Math.trunc(l.weight || 1))));
  }
  return o.mode === "weighted" ? a = He(a, c) : o.mode === "shuffle" && (a = je(a, We(`${t}:${s}`))), a.flat();
}
function qe(n, t) {
  return (n[0] === null || n[0] <= t) && (n[1] === null || t < n[1]);
}
function Je(n, t) {
  const e = [];
  return n.entries.forEach((i, s) => {
    const r = i.windows.find((o) => qe(o, t));
    r && e.push({ key: [-i.priority, -(r[0] ?? -1), s], entry: i, w: r });
  }), e.sort((i, s) => i.key[0] - s.key[0] || i.key[1] - s.key[1] || i.key[2] - s.key[2]), e.map((i) => [i.entry, i.w]);
}
function Ge(n, t, e, i, s) {
  const r = i.content, o = { entry: i.id, index: 0, count: 1, start: s[0], end: s[1] };
  if (r.message !== void 0) return r.message in (n.messages ?? {}) ? { ...o, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in n.layouts ? { ...o, layout: r.layout } : null;
  const a = r.playlist, c = s[0] ?? 0;
  let l = J(n, a, t, e, 0);
  const h = l.reduce((p, b) => p + b.duration, 0);
  if (!h) return null;
  const d = Math.floor((e - c) / h);
  d && (l = J(n, a, t, e, d));
  let f = e - c - d * h, g = c + d * h;
  for (let p = 0; p < l.length; p++) {
    const b = l[p];
    if (f < b.duration) {
      let L = g + b.duration;
      return s[1] !== null && (L = Math.min(L, s[1])), { ...o, layout: b.layout, item: b.item, index: p, count: l.length, start: g, end: L };
    }
    f -= b.duration, g += b.duration;
  }
  return null;
}
function Ve(n, t, e) {
  for (const [i, s] of Je(n, e)) {
    const r = Ge(n, t, e, i, s);
    if (r) return r;
  }
  return null;
}
function Xe(n, t, e) {
  const i = e?.end != null ? [e.end] : [];
  for (const s of n.entries)
    for (const [r, o] of s.windows)
      r !== null && r > t && i.push(r), o !== null && o > t && i.push(o);
  return i.length ? Math.min(...i) : null;
}
const Ye = "evac-player-content-v1", Ke = "content/theme/", Ze = /url\("([^"]+)"\)/g;
async function it(n, t) {
  const e = await caches.open(Ye).catch(() => null);
  try {
    const i = await fetch(n, { headers: { Authorization: `Screen ${t}` }, credentials: "omit" });
    if (i.ok)
      return await e?.put(n, i.clone()), i;
  } catch {
  }
  return await e?.match(n) ?? null;
}
async function Qe(n, t) {
  try {
    const e = await M(n, Ke, { token: t });
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
function tn(n) {
  const t = [];
  for (const e of n.match(/@font-face\{[^}]*\}/g) ?? []) {
    const i = /font-family:"([^"]+)"/.exec(e)?.[1], s = /src:url\("([^"]+)"\)/.exec(e)?.[1];
    !i || !s || t.push({
      family: i,
      url: s,
      weight: /font-weight:([^;]+);/.exec(e)?.[1] ?? "400",
      style: /font-style:([^;]+);/.exec(e)?.[1] ?? "normal",
      unicodeRange: /unicode-range:([^;]+);/.exec(e)?.[1]
    });
  }
  return t;
}
const st = [];
async function en(n, t, e = document.documentElement) {
  const i = document.fonts;
  await Promise.all(tn(n.fonts_css).map(async (s) => {
    const r = await it(s.url, t);
    if (r)
      try {
        const o = new FontFace(s.family, await r.arrayBuffer(), {
          weight: s.weight,
          style: s.style,
          unicodeRange: s.unicodeRange
        });
        i.add(await o.load());
      } catch {
      }
  })), st.splice(0).forEach((s) => URL.revokeObjectURL(s));
  for (const [s, r] of Object.entries(n.variables)) {
    let o = r;
    for (const a of r.matchAll(Ze)) {
      const c = await it(a[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        st.push(l), o = o.replace(a[1], l);
      }
    }
    e.style.setProperty(s, o);
  }
  e.dataset.theme = n.key || "default";
}
function nn(n = document) {
  const t = n.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, i = new URLSearchParams(n.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: i.get("mode") === "obs" ? "obs" : "screen"
  };
}
function $(n, t, e = {}) {
  let i = n.strings[t] ?? t;
  for (const [s, r] of Object.entries(e)) i = i.replace(`{${s}}`, String(r));
  return i;
}
function sn(n, t = location) {
  return n.ws ? n.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const z = [], D = [], rn = Date.now(), on = 300;
let x = [], G = null;
function S(n, t) {
  D.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n.toUpperCase()} ${t}`.slice(0, 500)), D.length > on && D.shift();
}
function an() {
  return [...D];
}
function m(n) {
  z.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n}`.slice(0, 300)), z.length > 10 && z.shift(), S("error", n);
  const t = Date.now();
  x = x.filter((e) => t - e < 6e4), x.push(t), x.length >= 50 && G && (x = [], G());
}
function cn(n) {
  G = n;
}
function ln(n = window) {
  n.addEventListener("error", (t) => m(t.message || "error")), n.addEventListener("unhandledrejection", (t) => m(String(t.reason)));
  for (const t of ["warn", "info"]) {
    const e = console[t].bind(console);
    console[t] = (...i) => {
      S(t, i.map(String).join(" ")), e(...i);
    };
  }
}
function rt(n) {
  const t = window.innerWidth, e = window.innerHeight, i = performance.memory;
  return {
    version: n.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - rn) / 1e3),
    slide: n.slide,
    errors: [...z],
    memory: i ? Math.round(i.usedJSHeapSize / 1048576) : null,
    last_sync: n.lastSync ? new Date(n.lastSync).toISOString() : null,
    online: n.online,
    user_agent: navigator.userAgent,
    ...n.contentVersion ? { content_version: n.contentVersion } : {},
    ...n.displayState ? { display_state: n.displayState } : {},
    ...n.capture !== void 0 ? { capture: n.capture } : {},
    ...n.recovered ? { recovered: n.recovered } : {}
  };
}
const At = "evac.player.reloads", R = "evac.player.alive", hn = 3, dn = 10 * 6e4;
function Ct(n) {
  try {
    return localStorage.getItem(n);
  } catch {
    return null;
  }
}
function B(n, t) {
  try {
    t === null ? localStorage.removeItem(n) : localStorage.setItem(n, t);
  } catch {
  }
}
function un(n = Date.now()) {
  try {
    return JSON.parse(Ct(At) ?? "[]").filter((t) => n - t < dn);
  } catch {
    return [];
  }
}
function _(n, t = {}) {
  const e = Date.now(), i = un(e);
  return !t.force && i.length >= hn ? (m(`reload (${n}) skipped: ${i.length} reloads in the last 10 minutes`), !1) : (B(At, JSON.stringify([...i, e])), S("info", `reload: ${n}`), xt(), (t.win ?? location).reload(), !0);
}
function fn(n = Date.now()) {
  const t = Ct(R);
  if (B(R, String(n)), !t || t === "clean") return "";
  const e = Number(t);
  return Number.isFinite(e) ? `restarted after an unclean stop (last sign of life ${new Date(e).toISOString()})` : "";
}
function pn(n = Date.now()) {
  B(R, String(n));
}
function xt() {
  B(R, "clean");
}
function mn(n = window) {
  n.addEventListener("pagehide", () => xt());
}
function gn() {
  const n = performance.memory;
  return !!n && n.jsHeapSizeLimit > 0 && n.usedJSHeapSize / n.jsHeapSizeLimit > 0.85;
}
function Tt() {
  return typeof navigator < "u" && !!navigator.mediaDevices?.getDisplayMedia;
}
function yn(n, t, e) {
  return new Promise((i, s) => {
    const r = setTimeout(() => s(new Error(`${e} timed out`)), t);
    n.then((o) => {
      clearTimeout(r), i(o);
    }, (o) => {
      clearTimeout(r), s(o);
    });
  });
}
async function wn(n = 1e4) {
  return yn(vn(), n, "screen capture");
}
async function vn() {
  if (!Tt()) throw new Error("screen capture is not available in this browser");
  const n = document.createElement("div");
  n.className = "evac-capture-dot", document.body.appendChild(n);
  let t = 0;
  const e = setInterval(() => n.classList.toggle("on", t++ % 2 === 0), 16);
  try {
    return await bn();
  } finally {
    clearInterval(e), n.remove();
  }
}
async function bn() {
  const n = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "browser" },
    audio: !1,
    preferCurrentTab: !0,
    selfBrowserSurface: "include"
  });
  try {
    const t = document.createElement("video");
    t.muted = !0, t.srcObject = n, await t.play(), t.videoWidth || await new Promise((i) => t.addEventListener("loadeddata", i, { once: !0 }));
    const e = document.createElement("canvas");
    return e.width = t.videoWidth || window.innerWidth, e.height = t.videoHeight || window.innerHeight, e.getContext("2d")?.drawImage(t, 0, 0, e.width, e.height), t.srcObject = null, await new Promise((i, s) => e.toBlob((r) => r ? i(r) : s(new Error("encoding failed")), "image/jpeg", 0.85));
  } finally {
    n.getTracks().forEach((t) => t.stop());
  }
}
async function H(n, t, e, i) {
  const s = typeof Blob < "u" && i instanceof Blob;
  await fetch(`${n}upload/${e}/`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Screen ${t}`, "Content-Type": s ? i.type : "application/json" },
    body: s ? i : JSON.stringify(i)
  });
}
async function Sn() {
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
function ot(n, t) {
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
function at(n, t, e) {
  return !t || !e || t === e ? !1 : t < e ? n >= t && n < e : n >= t || n < e;
}
function kn(n, t) {
  return at(t, n.sleep_from, n.sleep_until) ? "sleeping" : at(t, n.dim_from, n.dim_until) ? "dimmed" : "on";
}
function En(n) {
  const t = Number(n.rotation ?? 0) || 0, e = t === 90 || t === 270, i = ["translate(-50%, -50%)"];
  t && i.push(`rotate(${t}deg)`), (n.keystone_x || n.keystone_y) && (i.push("perspective(1200px)"), n.keystone_y && i.push(`rotateX(${n.keystone_y}deg)`), n.keystone_x && i.push(`rotateY(${n.keystone_x}deg)`));
  const s = (n.scale ?? 100) / 100;
  s !== 1 && i.push(`scale(${s})`);
  const r = Math.max(0, Math.min(15, n.overscan ?? 0));
  return {
    width: e ? "100vh" : "100vw",
    height: e ? "100vw" : "100vh",
    transform: i.join(" "),
    overscan: `${r}%`
  };
}
function $n(n, t) {
  const e = En(t);
  n.classList.add("evac-root"), n.style.width = e.width, n.style.height = e.height, n.style.transform = e.transform, n.style.setProperty("--evac-overscan", e.overscan);
}
function Mn(n, t, e = document) {
  let i = e.getElementById("evac-dim");
  if (n === "on") {
    i?.remove();
    return;
  }
  i || (i = e.createElement("div"), i.id = "evac-dim", i.setAttribute("aria-hidden", "true"), e.body.appendChild(i));
  const s = n === "sleeping" ? 0 : Math.max(10, Math.min(90, t.dim_level ?? 40));
  i.style.opacity = String(1 - s / 100), i.dataset.state = n;
}
const V = "evac.player.token", Q = "evac.player.config";
function An() {
  try {
    return localStorage.getItem(V);
  } catch {
    return null;
  }
}
function ct(n) {
  try {
    n ? localStorage.setItem(V, n) : (localStorage.removeItem(V), localStorage.removeItem(Q));
  } catch {
  }
}
function Cn() {
  try {
    const n = localStorage.getItem(Q);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function lt(n) {
  try {
    localStorage.setItem(Q, JSON.stringify(n));
  } catch {
  }
}
const ht = 3e3, dt = 6e4, xn = 36e5, ut = 15e3;
class Tn {
  constructor(t, e) {
    this.env = t, this.root = e, this.clock = new Dt(), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.program = null, this.shown = "", this.timer = null, this.refresher = null, this.housekeeping = null, this.displayState = "on", this.recovered = "", this.lastTick = Date.now(), this.reloadAtNextSlide = "", this.lastDailyReload = "", this.display = new Ne(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    this.recovered = fn(), S("info", `player ${this.env.version} started (${navigator.userAgent})`), this.recovered && S("warn", this.recovered);
    const t = An();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: $(this.env, "pair_title"),
      step1: $(this.env, "pair_step1"),
      step2: $(this.env, "pair_step2"),
      waiting: $(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await Nt(this.env.api, rt({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (s) {
      m(String(s)), this.display.message($(this.env, "no_server"), $(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const i = async () => {
      try {
        const s = await zt(this.env.api, e);
        if (s.status === "paired")
          return ct(s.token), this.play(s.token);
        if (s.status !== "pending") return this.pair();
      } catch (s) {
        m(String(s));
      }
      setTimeout(() => {
        i();
      }, ht);
    };
    setTimeout(() => {
      i();
    }, ht);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = Cn();
    try {
      const i = Date.now();
      this.config = await tt(this.env.api, t), this.clock.add(i, Date.now(), this.config.server_time), this.lastSync = Date.now(), lt(this.config);
    } catch (i) {
      if (i instanceof w) return this.unpair();
      m(String(i)), this.config = e;
    }
    this.applySettings(), this.bundle = $t(), this.program = Mt(), await this.loadContent(t), await this.loadProgram(t), this.show(), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, xn), this.housekeeping = setInterval(() => this.tick(), ut), this.conn = new Rt({
      api: this.env.api,
      ws: sn(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => rt({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline",
        displayState: this.displayState,
        capture: Tt(),
        recovered: this.recovered
      }),
      onMessage: (i) => {
        this.handle(i, t);
      },
      onTransport: (i) => {
        i !== this.transport && S("info", `connection: ${i}`), this.transport = i;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (i) => {
        this.lastSync = i;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch (S("info", `message: ${t.type}`), t.type) {
      case "config.changed":
        try {
          this.config = await tt(this.env.api, e), lt(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), this.applySettings();
          const i = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(e), await this.loadProgram(e), (`${this.bundle?.version}/${this.program?.version}` !== i || this.slide === "idle") && (this.shown = "", this.show());
        } catch (i) {
          i instanceof w && this.unpair();
        }
        break;
      case "identify": {
        const i = this.config?.screen.name ?? "", s = [this.config?.screen.venue, this.config?.screen.zone, this.config?.screen.room].filter(Boolean).join(" · ");
        this.display.identify(
          i,
          `${s}${s ? " · " : ""}${this.transport}`,
          Number(t.data.seconds) || 10
        );
        break;
      }
      case "program.changed": {
        const i = this.program?.version;
        await this.loadProgram(e), this.program?.version !== i && (this.shown = "", this.show());
        break;
      }
      case "reload":
        _("requested by staff", { force: !0 });
        break;
      case "clear_cache":
        await Sn(), _("cache cleared by staff", { force: !0 });
        break;
      case "test_pattern": {
        const i = this.config?.screen.name ?? "", s = `${Math.round(innerWidth * devicePixelRatio)}×${Math.round(innerHeight * devicePixelRatio)}`;
        this.display.testPattern(
          i,
          [`${s} · DPR ${devicePixelRatio}`, `${this.env.version} · ${this.transport}`],
          Number(t.data.seconds) || 30
        );
        break;
      }
      case "screenshot":
        try {
          await H(this.env.api, e, "screenshot", await wn());
        } catch (i) {
          m(`screenshot: ${String(i)}`), await H(this.env.api, e, "screenshot", { error: String(i).slice(0, 280) }).catch(() => {
          });
        }
        break;
      case "logs":
        await H(this.env.api, e, "logs", { lines: an() }).catch((i) => m(String(i)));
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await ze(this.env.api, t) ?? this.bundle;
    } catch (i) {
      if (i instanceof w) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await Qe(this.env.api, t);
    e && await en(e, t).catch((i) => m(String(i))), this.bundle && Oe(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await Re(this.env.api, t);
    } catch (e) {
      e instanceof w && this.unpair();
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
      groups: e.groups.map((i) => i.name)
    } };
  }
  /** Show what the program says for now (or the default layout without one) and wake up at the next change. */
  show() {
    this.timer && clearTimeout(this.timer), this.timer = null;
    const t = this.config;
    if (!t) {
      this.slide = "error", this.display.message($(this.env, "no_server"), $(this.env, "retrying"));
      return;
    }
    const e = this.clock.now();
    let i = null, s, r = "idle", o = null;
    if (this.program && this.bundle) {
      if (o = Ve(this.program, this.vars(), e), o?.message)
        i = this.program.messages?.[o.message] ?? null, r = `${o.entry}|message`, this.slide = `${o.entry} message`;
      else if (o?.layout) {
        const h = this.bundle.layouts.find((d) => d.id === o?.layout);
        h && (i = h.data, s = h.variables, r = `${o.entry}|${h.id}|${h.version}|${o.count > 1 ? o.start : ""}`, this.slide = `${h.key} v${h.version} (${o.entry} ${o.index + 1}/${o.count})`);
      }
      const c = Xe(this.program, e, o), l = Math.max(5, Math.min(dt, (c ?? e + dt) - e));
      this.timer = setTimeout(() => this.show(), l);
    } else {
      const c = _e(this.bundle);
      c && (i = c.data, s = c.variables, r = `default|${c.id}|${c.version}`, this.slide = `${c.key} v${c.version}`);
    }
    if (r === this.shown || this.reloadAtNextSlide && this.shown && _(this.reloadAtNextSlide)) return;
    this.reloadAtNextSlide = "", this.shown = r, S("info", `showing ${this.slide}`);
    const a = { enabled: t.display?.audio !== !1, volume: t.display?.volume ?? 100 };
    try {
      if (!i || !this.bundle) throw new Error("nothing to show");
      this.display.layout(i, {
        vars: this.vars(),
        now: () => this.clock.now(),
        timezone: t.event.timezone,
        assets: this.bundle.assets,
        fonts: this.bundle.fonts,
        reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
        audio: a,
        onError: (c, l) => m(`${c}: ${String(l)}`)
      }, s);
    } catch (c) {
      i && m(`render failed, showing the idle slide: ${String(c)}`), this.slide = "idle", this.display.idle(t);
    }
  }
  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  applySettings() {
    const t = this.config?.display ?? {};
    $n(this.root, t), this.updateDisplayState();
  }
  updateDisplayState() {
    const t = this.config?.display ?? {}, e = kn(t, ot(this.clock.now(), this.config?.event.timezone));
    e !== this.displayState && S("info", `display ${e}`), this.displayState = e, Mn(e, t);
  }
  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  tick() {
    const t = Date.now(), e = t - this.lastTick > ut * 3;
    this.lastTick = t, pn(t), this.updateDisplayState(), e && (S("warn", "timers were stalled; resynchronising"), this.shown = "", this.show());
    const i = this.config?.display?.daily_reload, s = ot(this.clock.now(), this.config?.event.timezone);
    i && s === i && this.lastDailyReload !== s && performance.now() > 36e5 && (this.lastDailyReload = s, this.reloadAtNextSlide = "daily reload"), gn() && !this.reloadAtNextSlide && (this.reloadAtNextSlide = "memory pressure");
  }
  unpair() {
    this.housekeeping && clearInterval(this.housekeeping), this.housekeeping = null, this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.timer = this.refresher = null, Fe(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, ct(null), De(), this.pair();
  }
}
function Pn() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((n) => m(String(n)));
}
if (typeof document < "u" && document.getElementById("player")) {
  ln(), mn(), cn(() => _("50 errors within a minute")), Pn();
  const n = nn();
  new Tn(n, document.getElementById("player")).boot();
}
export {
  Tn as Player
};
