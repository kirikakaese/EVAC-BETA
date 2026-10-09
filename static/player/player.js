// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var pt = Object.defineProperty;
var gt = (s, t, e) => t in s ? pt(s, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : s[t] = e;
var $ = (s, t, e) => gt(s, typeof t != "symbol" ? t + "" : t, e);
class y extends Error {
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
    if (o.status === 401) throw new y("token rejected");
    if (!o.ok) throw new Error(`HTTP ${o.status}`);
    return await o.json();
  } finally {
    clearTimeout(i);
  }
}
const yt = (s, t) => M(s, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), wt = (s, t) => M(s, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), G = (s, t) => M(s, "config/", { token: t });
class bt {
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
const vt = 3e4, St = 3e5;
class kt {
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
    this.backoff = Math.min(this.backoff * 2, vt), setTimeout(() => !this.stopped && t(), e);
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > St ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        if (t.status === 401) throw new y("token rejected");
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
        t instanceof y ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
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
        if (t instanceof y) {
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
      e instanceof y ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function x(s) {
  return s ? s.startsWith("token:") ? `var(--evac-color-${s.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(s) || s === "transparent" ? s : "" : "";
}
function Et(s, t) {
  return s ? s === "token:heading" ? "var(--evac-font-heading)" : s === "token:body" ? "var(--evac-font-body)" : t.fonts[s] ?? "" : "";
}
function Mt(s, t, e) {
  const n = s.style;
  if (!t) return;
  const i = (r, o) => {
    o && n.setProperty(r, o);
  };
  i("color", x(t.color)), i("background", x(t.background)), t.borderWidth && n.setProperty("border", `${t.borderWidth / 10}cqh solid ${x(t.borderColor) || "currentColor"}`), t.radius !== void 0 && n.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && n.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && n.setProperty("opacity", String(t.opacity)), i("font-family", Et(t.fontFamily, e)), t.fontSize && n.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && n.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && n.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && n.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && n.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && n.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && n.setProperty("box-shadow", "var(--evac-shadow)");
}
function Ct(s, t, e) {
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
function $t(s) {
  const t = [];
  let e = "", n = "";
  for (const i of s)
    n ? (i === n && (n = ""), e += i) : i === '"' || i === "'" ? (n = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function At(s) {
  if (!s) return "";
  const t = s.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function J(s, t, e) {
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
function g(s) {
  return s == null ? "" : Array.isArray(s) ? s.map(g).join(", ") : s instanceof Date ? s.toISOString() : typeof s == "object" ? s.name ?? "" : String(s);
}
function xt(s, t, e) {
  const [n, ...i] = t.split(":"), r = At(i.join(":")), o = () => s instanceof Date ? s : new Date(String(s));
  switch (n.trim()) {
    case "upper":
      return g(s).toUpperCase();
    case "lower":
      return g(s).toLowerCase();
    case "title":
      return g(s).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = g(s);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return g(s) === "" ? r : s;
    case "date":
      return isNaN(o().getTime()) ? "" : J(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : J(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(s) ? s.map(g).join(r || ", ") : g(s);
    default:
      return s;
  }
}
function P(s, t, e = {}) {
  const [n, ...i] = $t(s);
  let r = Ct(t, n, e);
  for (const o of i) r = xt(r, o, e);
  return r;
}
function Pt(s) {
  return Array.isArray(s) ? s.length > 0 : !(s == null || s === !1 || s === "" || s === 0);
}
function N(s, t, e = {}) {
  const n = s.trim();
  if (!n) return !0;
  if (n.startsWith("not ")) return !N(n.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(n);
  if (i) {
    const r = g(P(i[1], t, e)), o = g(P(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return Pt(P(n.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const Tt = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function zt(s, t, e = {}) {
  if (!s || !s.includes("{{") && !s.includes("{%")) return s ?? "";
  const n = s.split(Tt);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < n.length; ) {
      const c = n[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(h)) return [a, h];
        if (h === "if") {
          const u = N(l[2], t, e), [f, p] = r(["else", "endif"]);
          let m = "";
          p === "else" && (m = r(["endif"])[0]), a += u ? f : m;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += g(P(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
var C = /* @__PURE__ */ ((s) => (s[s.Border = -1] = "Border", s[s.Data = 0] = "Data", s[s.Function = 1] = "Function", s[s.Position = 2] = "Position", s[s.Timing = 3] = "Timing", s[s.Alignment = 4] = "Alignment", s))(C || {});
const It = [0, 1], nt = [1, 0], st = [2, 3], it = [3, 2], Nt = {
  L: It,
  M: nt,
  Q: st,
  H: it
}, Ft = /^\d*$/, Ot = /^[A-Z0-9 $%*+./:-]*$/, O = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", L = 1, j = 40, V = 3, Rt = 3, A = 40, _t = 10, rt = [
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
], ot = [
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
class Bt {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, n, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    $(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    $(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    $(this, "modules", []);
    $(this, "types", []);
    if (this.version = t, this.ecc = e, t < L || t > j)
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
      this.setFunctionModule(6, n, n % 2 === 0, C.Timing), this.setFunctionModule(n, 6, n % 2 === 0, C.Timing);
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
      this.setFunctionModule(8, r, v(i, r));
    this.setFunctionModule(8, 7, v(i, 6)), this.setFunctionModule(8, 8, v(i, 7)), this.setFunctionModule(7, 8, v(i, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, v(i, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, v(i, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, v(i, r));
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
      const i = v(e, n), r = this.size - 11 + n % 3, o = Math.floor(n / 3);
      this.setFunctionModule(r, o, i), this.setFunctionModule(o, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let n = -4; n <= 4; n++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(n)), o = t + i, a = e + n;
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, C.Position);
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
          C.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, n, i = C.Function) {
    this.modules[e][t] = n, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, n = this.ecc;
    if (t.length !== T(e, n))
      throw new RangeError("Invalid argument");
    const i = ot[n[0]][e], r = rt[n[0]][e], o = Math.floor(_(e) / 8), a = i - o % i, c = Math.floor(o / i), l = [], h = Jt(r);
    for (let f = 0, p = 0; f < i; f++) {
      const m = t.slice(p, p + c - r + (f < a ? 0 : 1));
      p += m.length;
      const b = Vt(m, h);
      f < a && m.push(0), l.push(m.concat(b));
    }
    const u = [];
    for (let f = 0; f < l[0].length; f++)
      l.forEach((p, m) => {
        (f !== c - r || m >= a) && u.push(p[f]);
      });
    return u;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(_(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let n = this.size - 1; n >= 1; n -= 2) {
      n === 6 && (n = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = n - r, c = (n + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][o] && e < t.length * 8 && (this.modules[c][o] = v(t[e >>> 3], 7 - (e & 7)), e++);
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
        this.modules[r][l] === o ? (a++, a === 5 ? t += V : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * A), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * A;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += V : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * A), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * A;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += Rt);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const n = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - n * 10) / n) - 1;
    return t += i * _t, t;
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
function S(s, t, e) {
  if (t < 0 || t > 31 || s >>> t)
    throw new RangeError("Value out of range");
  for (let n = t - 1; n >= 0; n--)
    e.push(s >>> n & 1);
}
function v(s, t) {
  return (s >>> t & 1) !== 0;
}
class H {
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
const Dt = [1, 10, 12, 14], Wt = [2, 9, 11, 13], Lt = [4, 8, 16, 16];
function at(s, t) {
  return s[Math.floor((t + 7) / 17) + 1];
}
function ct(s) {
  const t = [];
  for (const e of s)
    S(e, 8, t);
  return new H(Lt, s.length, t);
}
function jt(s) {
  if (!lt(s))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < s.length; ) {
    const n = Math.min(s.length - e, 3);
    S(Number.parseInt(s.substring(e, e + n), 10), n * 3 + 1, t), e += n;
  }
  return new H(Dt, s.length, t);
}
function Ht(s) {
  if (!ht(s))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= s.length; e += 2) {
    let n = O.indexOf(s.charAt(e)) * 45;
    n += O.indexOf(s.charAt(e + 1)), S(n, 11, t);
  }
  return e < s.length && S(O.indexOf(s.charAt(e)), 6, t), new H(Wt, s.length, t);
}
function Ut(s) {
  return s === "" ? [] : lt(s) ? [jt(s)] : ht(s) ? [Ht(s)] : [ct(Gt(s))];
}
function lt(s) {
  return Ft.test(s);
}
function ht(s) {
  return Ot.test(s);
}
function qt(s, t) {
  let e = 0;
  for (const n of s) {
    const i = at(n.mode, t);
    if (n.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + n.bitData.length;
  }
  return e;
}
function Gt(s) {
  s = encodeURI(s);
  const t = [];
  for (let e = 0; e < s.length; e++)
    s.charAt(e) !== "%" ? t.push(s.charCodeAt(e)) : (t.push(Number.parseInt(s.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function _(s) {
  if (s < L || s > j)
    throw new RangeError("Version number out of range");
  let t = (16 * s + 128) * s + 64;
  if (s >= 2) {
    const e = Math.floor(s / 7) + 2;
    t -= (25 * e - 10) * e - 55, s >= 7 && (t -= 36);
  }
  return t;
}
function T(s, t) {
  return Math.floor(_(s) / 8) - rt[t[0]][s] * ot[t[0]][s];
}
function Jt(s) {
  if (s < 1 || s > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let n = 0; n < s - 1; n++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let n = 0; n < s; n++) {
    for (let i = 0; i < t.length; i++)
      t[i] = B(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = B(e, 2);
  }
  return t;
}
function Vt(s, t) {
  const e = t.map((n) => 0);
  for (const n of s) {
    const i = n ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= B(r, i));
  }
  return e;
}
function B(s, t) {
  if (s >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let n = 7; n >= 0; n--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> n & 1) * s;
  return e;
}
function Yt(s, t, e = 1, n = 40, i = -1, r = !0) {
  if (!(L <= e && e <= n && n <= j) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const u = T(o, t) * 8, f = qt(s, o);
    if (f <= u) {
      a = f;
      break;
    }
    if (o >= n)
      throw new RangeError("Data too long");
  }
  for (const u of [nt, st, it])
    r && a <= T(o, u) * 8 && (t = u);
  const c = [];
  for (const u of s) {
    S(u.mode[0], 4, c), S(u.numChars, at(u.mode, o), c);
    for (const f of u.getData())
      c.push(f);
  }
  const l = T(o, t) * 8;
  S(0, Math.min(4, l - c.length), c), S(0, (8 - c.length % 8) % 8, c);
  for (let u = 236; c.length < l; u ^= 253)
    S(u, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((u, f) => h[f >>> 3] |= u << 7 - (f & 7)), new Bt(o, t, h, i);
}
function Kt(s, t) {
  const {
    ecc: e = "L",
    boostEcc: n = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof s == "string" ? Ut(s) : Array.isArray(s) ? [ct(s)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof s}`);
  const l = Yt(
    c,
    Nt[e],
    i,
    r,
    o,
    n
  ), h = Xt({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (h.data = h.data.map((u) => u.map((f) => !f))), t?.onEncoded?.(h), h;
}
function Xt(s, t = 1) {
  if (!t)
    return s;
  const { size: e } = s, n = e + t * 2;
  s.size = n, s.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    s.data.unshift(Array.from({ length: n }, (o) => !1)), s.data.push(Array.from({ length: n }, (o) => !1));
  const i = C.Border;
  s.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    s.types.unshift(Array.from({ length: n }, (o) => i)), s.types.push(Array.from({ length: n }, (o) => i));
  return s;
}
const R = "http://www.w3.org/2000/svg";
function ut(s, t = document) {
  const { data: e, size: n } = Kt(s, { ecc: "M", border: 2 }), i = t.createElementNS(R, "svg");
  i.setAttribute("viewBox", `0 0 ${n} ${n}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(R, "rect");
  r.setAttribute("width", String(n)), r.setAttribute("height", String(n)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((h, u) => {
    h && (o += `M${u} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(R, "path");
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
    return zt(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function Zt(s, t) {
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
class Qt extends w {
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
      const i = () => Zt(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class te extends w {
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
function ft(s, t, e) {
  const n = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (s.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = s.urls[r], n.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = s.urls.original, i.alt = e || s.alt || "", i.decoding = "async", i.style.objectFit = t, n.appendChild(i), n;
}
class ee extends w {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(ft(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class ne extends w {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), n = t.map((o) => {
      const a = ft(o, e, "");
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
class se extends w {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Video");
    const e = document.createElement("video");
    e.muted = this.props.muted !== !1, e.loop = this.props.loop !== !1, e.playsInline = !0, e.preload = "auto", e.style.objectFit = String(this.props.fit ?? "cover"), t.urls.poster && (e.poster = t.urls.poster);
    for (const n of ["webm", "mp4", "original"]) {
      if (!t.urls[n]) continue;
      const i = document.createElement("source");
      i.src = t.urls[n], i.type = t.mimes[n] || "", e.appendChild(i);
    }
    this.ctx.editing || (e.autoplay = !0, e.play?.()?.catch(() => {
    })), this.replaceChildren(e);
  }
}
class ie extends w {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.autoplay = !0, this.replaceChildren(e);
  }
}
class re extends w {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class oe extends w {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = ut(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const ae = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class ce extends w {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...ae[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = n.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class le extends w {
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
function he(s, t) {
  const e = Math.max(0, Math.floor(s / 1e3)), n = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${n} ${n === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || n === 0 ? `${a(i + n * 24)}:${a(r)}:${a(o)}` : `${n}d ${a(i)}:${a(r)}:${a(o)}`;
}
class ue extends w {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), n = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : he(i, String(this.props.format ?? "auto"));
    };
    n(), this.replaceChildren(e), this.every(250, n);
  }
}
const fe = {
  text: Qt,
  richtext: te,
  image: ee,
  slideshow: ne,
  video: se,
  audio: ie,
  shape: re,
  qr: oe,
  clock: ce,
  countdown: ue,
  date: le
};
function de(s = customElements) {
  for (const [t, e] of Object.entries(fe))
    s.get(`evac-${t}`) || s.define(`evac-${t}`, e);
}
function me(s, t) {
  const e = t.frame;
  s.style.left = `${e.x}%`, s.style.top = `${e.y}%`, s.style.width = `${e.w}%`, s.style.height = `${e.h}%`, s.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function pe(s, t) {
  const e = !s.visible_if || N(s.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (s.hidden && !t.editing || !e && !t.editing) return null;
  const n = document.createElement("div");
  n.className = `evac-el evac-el-${s.type}`, n.dataset.id = s.id, (!e || s.hidden) && n.classList.add("evac-dimmed"), me(n, s), Mt(n, s.style, t);
  const i = s.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (n.classList.add(`evac-enter-${i.enter}`), n.style.animationDuration = `${i.duration ?? 600}ms`, n.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${s.type}`;
  if (!customElements.get(r))
    return t.onError?.(s.id, new Error(`unknown element type ${s.type}`)), t.editing ? n : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", n.appendChild(o), o.configure(s, t), n;
}
function ge(s, t, e) {
  de();
  const n = document.createElement("div");
  n.className = "evac-stage";
  const i = t.background;
  if (i?.color && (n.style.background = x(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    n.style.backgroundImage = `url("${l}")`, n.style.backgroundSize = i.fit ?? "cover", n.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = pe(c, e);
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
function d(s, t = "", e = "") {
  const n = document.createElement(s);
  return t && (n.className = t), e && (n.textContent = e), n;
}
class ye {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = d("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, n) {
    const i = this.reset();
    i.classList.add("pairing"), i.append(d("h1", "", n.title));
    const r = d("div", "pairing-box"), o = d("p", "code", t);
    o.setAttribute("aria-label", t.split("").join(" "));
    const a = ut(e);
    a.setAttribute("role", "img"), a.setAttribute("aria-label", e), r.append(o, a);
    const c = d("ol", "steps");
    c.append(d("li", "", n.step1), d("li", "", n.step2)), i.append(r, c, d("p", "url", e), d("p", "waiting", n.waiting));
  }
  message(t, e = "") {
    const n = this.reset();
    n.classList.add("message"), n.append(d("h1", "", t)), e && n.append(d("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const n = d("p", "clock"), i = d("p", "date");
    e.append(d("h1", "event-name", t.event.name), n, i);
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
    this.rendered = ge(i, t, e);
  }
  identify(t, e, n = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = d("div", "identify");
    i.setAttribute("role", "status"), i.append(d("p", "identify-name", t), d("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), n * 1e3);
  }
}
const U = "evac.player.bundle";
async function we(s, t) {
  try {
    const e = await M(s, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(U, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof y) throw e;
    return dt();
  }
}
function dt() {
  try {
    const s = localStorage.getItem(U);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function be() {
  try {
    localStorage.removeItem(U);
  } catch {
  }
}
function ve(s) {
  return s?.layouts.length ? s.layouts.find((t) => t.default) ?? s.layouts[0] : null;
}
async function Se(s) {
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
const I = "evac.player.program";
async function ke(s, t) {
  try {
    const e = await M(s, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(I, JSON.stringify(e.program)) : localStorage.removeItem(I);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof y) throw e;
    return mt();
  }
}
function mt() {
  try {
    const s = localStorage.getItem(I);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Ee() {
  try {
    localStorage.removeItem(I);
  } catch {
  }
}
const Me = 5, Ce = 1e4;
function $e(s) {
  let t = 2166136261;
  for (let e = 0; e < s.length; e++)
    t ^= s.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function Ae(s, t) {
  let e = t >>> 0 || 1;
  const n = [...s];
  for (let i = n.length - 1; i > 0; i--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (i + 1);
    [n[i], n[r]] = [n[r], n[i]];
  }
  return n;
}
function xe(s, t) {
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
function Pe(s, t, e) {
  if (s.from !== null && s.from !== void 0 && t < s.from || s.until !== null && s.until !== void 0 && t >= s.until) return !1;
  const n = s.tags ?? [], i = e.screen?.tags ?? [];
  return n.length && !n.some((r) => i.includes(r)) ? !1 : N(s.when ?? "", e);
}
function D(s, t, e, n, i, r = []) {
  const o = s.playlists[t];
  if (!o || r.includes(t) || r.length >= Me) return [];
  let a = [];
  const c = [];
  for (const l of o.items ?? []) {
    if (!Pe(l, n, e)) continue;
    let h = [];
    if (l.playlist) h = D(s, l.playlist, e, n, i, [...r, t]);
    else if (l.layout && l.layout in s.layouts) {
      const u = l.duration || s.layouts[l.layout] || o.default || Ce;
      h = [{ layout: l.layout, duration: u, item: l.id }];
    }
    h.length && (a.push(h), c.push(Math.max(1, Math.trunc(l.weight || 1))));
  }
  return o.mode === "weighted" ? a = xe(a, c) : o.mode === "shuffle" && (a = Ae(a, $e(`${t}:${i}`))), a.flat();
}
function Te(s, t) {
  return (s[0] === null || s[0] <= t) && (s[1] === null || t < s[1]);
}
function ze(s, t) {
  const e = [];
  return s.entries.forEach((n, i) => {
    const r = n.windows.find((o) => Te(o, t));
    r && e.push({ key: [-n.priority, -(r[0] ?? -1), i], entry: n, w: r });
  }), e.sort((n, i) => n.key[0] - i.key[0] || n.key[1] - i.key[1] || n.key[2] - i.key[2]), e.map((n) => [n.entry, n.w]);
}
function Ie(s, t, e, n, i) {
  const r = n.content, o = { entry: n.id, index: 0, count: 1, start: i[0], end: i[1] };
  if (r.message !== void 0) return r.message in (s.messages ?? {}) ? { ...o, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in s.layouts ? { ...o, layout: r.layout } : null;
  const a = r.playlist, c = i[0] ?? 0;
  let l = D(s, a, t, e, 0);
  const h = l.reduce((m, b) => m + b.duration, 0);
  if (!h) return null;
  const u = Math.floor((e - c) / h);
  u && (l = D(s, a, t, e, u));
  let f = e - c - u * h, p = c + u * h;
  for (let m = 0; m < l.length; m++) {
    const b = l[m];
    if (f < b.duration) {
      let F = p + b.duration;
      return i[1] !== null && (F = Math.min(F, i[1])), { ...o, layout: b.layout, item: b.item, index: m, count: l.length, start: p, end: F };
    }
    f -= b.duration, p += b.duration;
  }
  return null;
}
function Ne(s, t, e) {
  for (const [n, i] of ze(s, e)) {
    const r = Ie(s, t, e, n, i);
    if (r) return r;
  }
  return null;
}
function Fe(s, t, e) {
  const n = e?.end != null ? [e.end] : [];
  for (const i of s.entries)
    for (const [r, o] of i.windows)
      r !== null && r > t && n.push(r), o !== null && o > t && n.push(o);
  return n.length ? Math.min(...n) : null;
}
const Oe = "evac-player-content-v1", Re = "content/theme/", _e = /url\("([^"]+)"\)/g;
async function Y(s, t) {
  const e = await caches.open(Oe).catch(() => null);
  try {
    const n = await fetch(s, { headers: { Authorization: `Screen ${t}` }, credentials: "omit" });
    if (n.ok)
      return await e?.put(s, n.clone()), n;
  } catch {
  }
  return await e?.match(s) ?? null;
}
async function Be(s, t) {
  try {
    const e = await M(s, Re, { token: t });
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
function De(s) {
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
const K = [];
async function We(s, t, e = document.documentElement) {
  const n = document.fonts;
  await Promise.all(De(s.fonts_css).map(async (i) => {
    const r = await Y(i.url, t);
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
  })), K.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, r] of Object.entries(s.variables)) {
    let o = r;
    for (const a of r.matchAll(_e)) {
      const c = await Y(a[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        K.push(l), o = o.replace(a[1], l);
      }
    }
    e.style.setProperty(i, o);
  }
  e.dataset.theme = s.key || "default";
}
function Le(s = document) {
  const t = s.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, n = new URLSearchParams(s.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: n.get("mode") === "obs" ? "obs" : "screen"
  };
}
function k(s, t, e = {}) {
  let n = s.strings[t] ?? t;
  for (const [i, r] of Object.entries(e)) n = n.replace(`{${i}}`, String(r));
  return n;
}
function je(s, t = location) {
  return s.ws ? s.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const z = [], He = Date.now();
function E(s) {
  z.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${s}`.slice(0, 300)), z.length > 10 && z.shift();
}
function Ue(s = window) {
  s.addEventListener("error", (t) => E(t.message || "error")), s.addEventListener("unhandledrejection", (t) => E(String(t.reason)));
}
function X(s) {
  const t = window.innerWidth, e = window.innerHeight, n = performance.memory;
  return {
    version: s.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - He) / 1e3),
    slide: s.slide,
    errors: [...z],
    memory: n ? Math.round(n.usedJSHeapSize / 1048576) : null,
    last_sync: s.lastSync ? new Date(s.lastSync).toISOString() : null,
    online: s.online,
    user_agent: navigator.userAgent,
    ...s.contentVersion ? { content_version: s.contentVersion } : {}
  };
}
const W = "evac.player.token", q = "evac.player.config";
function qe() {
  try {
    return localStorage.getItem(W);
  } catch {
    return null;
  }
}
function Z(s) {
  try {
    s ? localStorage.setItem(W, s) : (localStorage.removeItem(W), localStorage.removeItem(q));
  } catch {
  }
}
function Ge() {
  try {
    const s = localStorage.getItem(q);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Q(s) {
  try {
    localStorage.setItem(q, JSON.stringify(s));
  } catch {
  }
}
const tt = 3e3, et = 6e4, Je = 36e5;
class Ve {
  constructor(t, e) {
    this.env = t, this.clock = new bt(), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.program = null, this.shown = "", this.timer = null, this.refresher = null, this.display = new ye(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    const t = qe();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: k(this.env, "pair_title"),
      step1: k(this.env, "pair_step1"),
      step2: k(this.env, "pair_step2"),
      waiting: k(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await yt(this.env.api, X({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (i) {
      E(String(i)), this.display.message(k(this.env, "no_server"), k(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const n = async () => {
      try {
        const i = await wt(this.env.api, e);
        if (i.status === "paired")
          return Z(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        E(String(i));
      }
      setTimeout(() => {
        n();
      }, tt);
    };
    setTimeout(() => {
      n();
    }, tt);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = Ge();
    try {
      const n = Date.now();
      this.config = await G(this.env.api, t), this.clock.add(n, Date.now(), this.config.server_time), this.lastSync = Date.now(), Q(this.config);
    } catch (n) {
      if (n instanceof y) return this.unpair();
      E(String(n)), this.config = e;
    }
    this.bundle = dt(), this.program = mt(), await this.loadContent(t), await this.loadProgram(t), this.show(), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, Je), this.conn = new kt({
      api: this.env.api,
      ws: je(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => X({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline"
      }),
      onMessage: (n) => {
        this.handle(n, t);
      },
      onTransport: (n) => {
        this.transport = n;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (n) => {
        this.lastSync = n;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch (t.type) {
      case "config.changed":
        try {
          this.config = await G(this.env.api, e), Q(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds);
          const n = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(e), await this.loadProgram(e), (`${this.bundle?.version}/${this.program?.version}` !== n || this.slide === "idle") && (this.shown = "", this.show());
        } catch (n) {
          n instanceof y && this.unpair();
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
        location.reload();
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await we(this.env.api, t) ?? this.bundle;
    } catch (n) {
      if (n instanceof y) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await Be(this.env.api, t);
    e && await We(e, t).catch((n) => E(String(n))), this.bundle && Se(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await ke(this.env.api, t);
    } catch (e) {
      e instanceof y && this.unpair();
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
      this.slide = "error", this.display.message(k(this.env, "no_server"), k(this.env, "retrying"));
      return;
    }
    const e = this.clock.now();
    let n = null, i, r = "idle", o = null;
    if (this.program && this.bundle) {
      if (o = Ne(this.program, this.vars(), e), o?.message)
        n = this.program.messages?.[o.message] ?? null, r = `${o.entry}|message`, this.slide = `${o.entry} message`;
      else if (o?.layout) {
        const l = this.bundle.layouts.find((h) => h.id === o?.layout);
        l && (n = l.data, i = l.variables, r = `${o.entry}|${l.id}|${l.version}|${o.count > 1 ? o.start : ""}`, this.slide = `${l.key} v${l.version} (${o.entry} ${o.index + 1}/${o.count})`);
      }
      const a = Fe(this.program, e, o), c = Math.max(5, Math.min(et, (a ?? e + et) - e));
      this.timer = setTimeout(() => this.show(), c);
    } else {
      const a = ve(this.bundle);
      a && (n = a.data, i = a.variables, r = `default|${a.id}|${a.version}`, this.slide = `${a.key} v${a.version}`);
    }
    r !== this.shown && (this.shown = r, n && this.bundle ? this.display.layout(n, {
      vars: this.vars(),
      now: () => this.clock.now(),
      timezone: t.event.timezone,
      assets: this.bundle.assets,
      fonts: this.bundle.fonts,
      reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
      onError: (a, c) => E(`${a}: ${String(c)}`)
    }, i) : (this.slide = "idle", this.display.idle(t)));
  }
  unpair() {
    this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.timer = this.refresher = null, Ee(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, Z(null), be(), this.pair();
  }
}
function Ye() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((s) => E(String(s)));
}
if (typeof document < "u" && document.getElementById("player")) {
  Ue(), Ye();
  const s = Le();
  new Ve(s, document.getElementById("player")).boot();
}
export {
  Ve as Player
};
