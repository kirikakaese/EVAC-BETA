// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var ht = Object.defineProperty;
var dt = (n, t, e) => t in n ? ht(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var M = (n, t, e) => dt(n, typeof t != "symbol" ? t + "" : t, e);
class b extends Error {
}
async function C(n, t, e = {}) {
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
    if (o.status === 401) throw new b("token rejected");
    if (!o.ok) throw new Error(`HTTP ${o.status}`);
    return await o.json();
  } finally {
    clearTimeout(i);
  }
}
const ut = (n, t) => C(n, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), ft = (n, t) => C(n, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), U = (n, t) => C(n, "config/", { token: t });
class pt {
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
const mt = 3e4, gt = 3e5;
class yt {
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
    this.backoff = Math.min(this.backoff * 2, mt), setTimeout(() => !this.stopped && t(), e);
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > gt ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        if (t.status === 401) throw new b("token rejected");
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
            const c = i.slice(0, a);
            i = i.slice(a + 2);
            const l = c.split(`
`).filter((d) => d.startsWith("data: ")).map((d) => d.slice(6)).join(`
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
        t instanceof b ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
      }
    }
  }
  async poll() {
    if (!(this.stopped || this.maybeBackToWebSocket()))
      try {
        const t = await C(
          this.o.api,
          `poll/?since=${this.seq}&wait=10`,
          { token: this.o.token, timeout: 2e4 }
        );
        this.setTransport("poll"), this.backoff = 1e3, t.messages.forEach((e) => this.deliver(e)), this.poll();
      } catch (t) {
        if (t instanceof b) {
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
    C(this.o.api, "heartbeat/", {
      method: "POST",
      token: this.o.token,
      body: JSON.stringify({ data: t })
    }).then((e) => this.ack(e.server_time)).catch((e) => {
      e instanceof b ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function x(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function wt(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function bt(n, t, e) {
  const s = n.style;
  if (!t) return;
  const i = (r, o) => {
    o && s.setProperty(r, o);
  };
  i("color", x(t.color)), i("background", x(t.background)), t.borderWidth && s.setProperty("border", `${t.borderWidth / 10}cqh solid ${x(t.borderColor) || "currentColor"}`), t.radius !== void 0 && s.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && s.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && s.setProperty("opacity", String(t.opacity)), i("font-family", wt(t.fontFamily, e)), t.fontSize && s.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && s.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && s.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && s.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && s.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && s.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && s.setProperty("box-shadow", "var(--evac-shadow)");
}
function vt(n, t, e) {
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
function St(n) {
  const t = [];
  let e = "", s = "";
  for (const i of n)
    s ? (i === s && (s = ""), e += i) : i === '"' || i === "'" ? (s = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function kt(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function j(n, t, e) {
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
function p(n) {
  return n == null ? "" : Array.isArray(n) ? n.map(p).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function Et(n, t, e) {
  const [s, ...i] = t.split(":"), r = kt(i.join(":")), o = () => n instanceof Date ? n : new Date(String(n));
  switch (s.trim()) {
    case "upper":
      return p(n).toUpperCase();
    case "lower":
      return p(n).toLowerCase();
    case "title":
      return p(n).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = p(n);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return p(n) === "" ? r : n;
    case "date":
      return isNaN(o().getTime()) ? "" : j(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : j(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map(p).join(r || ", ") : p(n);
    default:
      return n;
  }
}
function $(n, t, e = {}) {
  const [s, ...i] = St(n);
  let r = vt(t, s, e);
  for (const o of i) r = Et(r, o, e);
  return r;
}
function Ct(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function B(n, t, e = {}) {
  const s = n.trim();
  if (!s) return !0;
  if (s.startsWith("not ")) return !B(s.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(s);
  if (i) {
    const r = p($(i[1], t, e)), o = p($(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return Ct($(s.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const Mt = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function At(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const s = n.split(Mt);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < s.length; ) {
      const c = s[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const d = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(d)) return [a, d];
        if (d === "if") {
          const h = B(l[2], t, e), [u, k] = r(["else", "endif"]);
          let g = "";
          k === "else" && (g = r(["endif"])[0]), a += h ? u : g;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += p($(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
var E = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(E || {});
const xt = [0, 1], X = [1, 0], Z = [2, 3], Q = [3, 2], $t = {
  L: xt,
  M: X,
  Q: Z,
  H: Q
}, Tt = /^\d*$/, Pt = /^[A-Z0-9 $%*+./:-]*$/, z = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", R = 1, _ = 40, H = 3, zt = 3, A = 40, Nt = 10, tt = [
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
], et = [
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
class It {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, s, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    M(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    M(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    M(this, "modules", []);
    M(this, "types", []);
    if (this.version = t, this.ecc = e, t < R || t > _)
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
    for (let s = 0; s < this.size; s++)
      this.setFunctionModule(6, s, s % 2 === 0, E.Timing), this.setFunctionModule(s, 6, s % 2 === 0, E.Timing);
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
      this.setFunctionModule(8, r, y(i, r));
    this.setFunctionModule(8, 7, y(i, 6)), this.setFunctionModule(8, 8, y(i, 7)), this.setFunctionModule(7, 8, y(i, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, y(i, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, y(i, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, y(i, r));
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
      const i = y(e, s), r = this.size - 11 + s % 3, o = Math.floor(s / 3);
      this.setFunctionModule(r, o, i), this.setFunctionModule(o, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let s = -4; s <= 4; s++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(s)), o = t + i, a = e + s;
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, E.Position);
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
          E.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, s, i = E.Function) {
    this.modules[e][t] = s, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, s = this.ecc;
    if (t.length !== T(e, s))
      throw new RangeError("Invalid argument");
    const i = et[s[0]][e], r = tt[s[0]][e], o = Math.floor(I(e) / 8), a = i - o % i, c = Math.floor(o / i), l = [], d = Ut(r);
    for (let u = 0, k = 0; u < i; u++) {
      const g = t.slice(k, k + c - r + (u < a ? 0 : 1));
      k += g.length;
      const lt = jt(g, d);
      u < a && g.push(0), l.push(g.concat(lt));
    }
    const h = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((k, g) => {
        (u !== c - r || g >= a) && h.push(k[u]);
      });
    return h;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(I(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let s = this.size - 1; s >= 1; s -= 2) {
      s === 6 && (s = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = s - r, c = (s + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][o] && e < t.length * 8 && (this.modules[c][o] = y(t[e >>> 3], 7 - (e & 7)), e++);
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
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[r][l] === o ? (a++, a === 5 ? t += H : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * A), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * A;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += H : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * A), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * A;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += zt);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const s = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - s * 10) / s) - 1;
    return t += i * Nt, t;
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
function w(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let s = t - 1; s >= 0; s--)
    e.push(n >>> s & 1);
}
function y(n, t) {
  return (n >>> t & 1) !== 0;
}
class D {
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
const Ft = [1, 10, 12, 14], Ot = [2, 9, 11, 13], Bt = [4, 8, 16, 16];
function st(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function nt(n) {
  const t = [];
  for (const e of n)
    w(e, 8, t);
  return new D(Bt, n.length, t);
}
function Rt(n) {
  if (!it(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const s = Math.min(n.length - e, 3);
    w(Number.parseInt(n.substring(e, e + s), 10), s * 3 + 1, t), e += s;
  }
  return new D(Ft, n.length, t);
}
function _t(n) {
  if (!rt(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let s = z.indexOf(n.charAt(e)) * 45;
    s += z.indexOf(n.charAt(e + 1)), w(s, 11, t);
  }
  return e < n.length && w(z.indexOf(n.charAt(e)), 6, t), new D(Ot, n.length, t);
}
function Dt(n) {
  return n === "" ? [] : it(n) ? [Rt(n)] : rt(n) ? [_t(n)] : [nt(Lt(n))];
}
function it(n) {
  return Tt.test(n);
}
function rt(n) {
  return Pt.test(n);
}
function Wt(n, t) {
  let e = 0;
  for (const s of n) {
    const i = st(s.mode, t);
    if (s.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + s.bitData.length;
  }
  return e;
}
function Lt(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function I(n) {
  if (n < R || n > _)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function T(n, t) {
  return Math.floor(I(n) / 8) - tt[t[0]][n] * et[t[0]][n];
}
function Ut(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let s = 0; s < n - 1; s++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < t.length; i++)
      t[i] = F(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = F(e, 2);
  }
  return t;
}
function jt(n, t) {
  const e = t.map((s) => 0);
  for (const s of n) {
    const i = s ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= F(r, i));
  }
  return e;
}
function F(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let s = 7; s >= 0; s--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> s & 1) * n;
  return e;
}
function Ht(n, t, e = 1, s = 40, i = -1, r = !0) {
  if (!(R <= e && e <= s && s <= _) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const h = T(o, t) * 8, u = Wt(n, o);
    if (u <= h) {
      a = u;
      break;
    }
    if (o >= s)
      throw new RangeError("Data too long");
  }
  for (const h of [X, Z, Q])
    r && a <= T(o, h) * 8 && (t = h);
  const c = [];
  for (const h of n) {
    w(h.mode[0], 4, c), w(h.numChars, st(h.mode, o), c);
    for (const u of h.getData())
      c.push(u);
  }
  const l = T(o, t) * 8;
  w(0, Math.min(4, l - c.length), c), w(0, (8 - c.length % 8) % 8, c);
  for (let h = 236; c.length < l; h ^= 253)
    w(h, 8, c);
  const d = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((h, u) => d[u >>> 3] |= h << 7 - (u & 7)), new It(o, t, d, i);
}
function qt(n, t) {
  const {
    ecc: e = "L",
    boostEcc: s = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof n == "string" ? Dt(n) : Array.isArray(n) ? [nt(n)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const l = Ht(
    c,
    $t[e],
    i,
    r,
    o,
    s
  ), d = Gt({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (d.data = d.data.map((h) => h.map((u) => !u))), t?.onEncoded?.(d), d;
}
function Gt(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, s = e + t * 2;
  n.size = s, n.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    n.data.unshift(Array.from({ length: s }, (o) => !1)), n.data.push(Array.from({ length: s }, (o) => !1));
  const i = E.Border;
  n.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    n.types.unshift(Array.from({ length: s }, (o) => i)), n.types.push(Array.from({ length: s }, (o) => i));
  return n;
}
const N = "http://www.w3.org/2000/svg";
function ot(n, t = document) {
  const { data: e, size: s } = qt(n, { ecc: "M", border: 2 }), i = t.createElementNS(N, "svg");
  i.setAttribute("viewBox", `0 0 ${s} ${s}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(N, "rect");
  r.setAttribute("width", String(s)), r.setAttribute("height", String(s)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((d, h) => {
    d && (o += `M${h} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(N, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), i.appendChild(a), i;
}
class m extends HTMLElement {
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
    return At(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function Jt(n, t) {
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
class Vt extends m {
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
      const i = () => Jt(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Yt extends m {
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
function at(n, t, e) {
  const s = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = n.urls[r], s.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = n.urls.original, i.alt = e || n.alt || "", i.decoding = "async", i.style.objectFit = t, s.appendChild(i), s;
}
class Kt extends m {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(at(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class Xt extends m {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), s = t.map((o) => {
      const a = at(o, e, "");
      return a.className = "evac-slide", a;
    });
    this.replaceChildren(...s);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const o = Math.floor(this.ctx.now() / i) % s.length;
      s.forEach((a, c) => a.classList.toggle("active", c === o));
    };
    r(), this.every(500, r);
  }
}
class Zt extends m {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Video");
    const e = document.createElement("video");
    e.muted = this.props.muted !== !1, e.loop = this.props.loop !== !1, e.playsInline = !0, e.preload = "auto", e.style.objectFit = String(this.props.fit ?? "cover"), t.urls.poster && (e.poster = t.urls.poster);
    for (const s of ["webm", "mp4", "original"]) {
      if (!t.urls[s]) continue;
      const i = document.createElement("source");
      i.src = t.urls[s], i.type = t.mimes[s] || "", e.appendChild(i);
    }
    this.ctx.editing || (e.autoplay = !0, e.play?.()?.catch(() => {
    })), this.replaceChildren(e);
  }
}
class Qt extends m {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.autoplay = !0, this.replaceChildren(e);
  }
}
class te extends m {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class ee extends m {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = ot(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const se = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class ne extends m {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...se[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = s.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class ie extends m {
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
function re(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), s = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${s} ${s === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || s === 0 ? `${a(i + s * 24)}:${a(r)}:${a(o)}` : `${s}d ${a(i)}:${a(r)}:${a(o)}`;
}
class oe extends m {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), s = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : re(i, String(this.props.format ?? "auto"));
    };
    s(), this.replaceChildren(e), this.every(250, s);
  }
}
const ae = {
  text: Vt,
  richtext: Yt,
  image: Kt,
  slideshow: Xt,
  video: Zt,
  audio: Qt,
  shape: te,
  qr: ee,
  clock: ne,
  countdown: oe,
  date: ie
};
function ce(n = customElements) {
  for (const [t, e] of Object.entries(ae))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
function le(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function he(n, t) {
  const e = !n.visible_if || B(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const s = document.createElement("div");
  s.className = `evac-el evac-el-${n.type}`, s.dataset.id = n.id, (!e || n.hidden) && s.classList.add("evac-dimmed"), le(s, n), bt(s, n.style, t);
  const i = n.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (s.classList.add(`evac-enter-${i.enter}`), s.style.animationDuration = `${i.duration ?? 600}ms`, s.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${n.type}`;
  if (!customElements.get(r))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? s : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", s.appendChild(o), o.configure(n, t), s;
}
function de(n, t, e) {
  ce();
  const s = document.createElement("div");
  s.className = "evac-stage";
  const i = t.background;
  if (i?.color && (s.style.background = x(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    s.style.backgroundImage = `url("${l}")`, s.style.backgroundSize = i.fit ?? "cover", s.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = he(c, e);
    l && (r.set(c.id, l), s.appendChild(l));
  }
  n.replaceChildren(s);
  const o = () => {
    const c = n.clientWidth, l = n.clientHeight;
    if (!c || !l) return;
    const d = Math.min(c / t.width, l / t.height);
    s.style.width = `${Math.round(t.width * d)}px`, s.style.height = `${Math.round(t.height * d)}px`;
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
class ue {
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
    const a = ot(e);
    a.setAttribute("role", "img"), a.setAttribute("aria-label", e), r.append(o, a);
    const c = f("ol", "steps");
    c.append(f("li", "", s.step1), f("li", "", s.step2)), i.append(r, c, f("p", "url", e), f("p", "waiting", s.waiting));
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
    const r = t.event.timezone || void 0, o = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: r }), a = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: r }), c = () => {
      const l = new Date(this.clock.now());
      s.textContent = o.format(l), i.textContent = a.format(l);
    };
    c(), this.clockTimer = setInterval(c, 1e3);
  }
  layout(t, e, s) {
    const i = this.reset();
    i.classList.add("layout");
    for (const [r, o] of Object.entries(s ?? {})) i.style.setProperty(r, o);
    this.rendered = de(i, t, e);
  }
  identify(t, e, s = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = f("div", "identify");
    i.setAttribute("role", "status"), i.append(f("p", "identify-name", t), f("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), s * 1e3);
  }
}
const W = "evac.player.bundle";
async function fe(n, t) {
  try {
    const e = await C(n, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(W, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof b) throw e;
    return ct();
  }
}
function ct() {
  try {
    const n = localStorage.getItem(W);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function pe() {
  try {
    localStorage.removeItem(W);
  } catch {
  }
}
function me(n) {
  return n?.layouts.length ? n.layouts.find((t) => t.default) ?? n.layouts[0] : null;
}
async function ge(n) {
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
const ye = "evac-player-content-v1", we = "content/theme/", be = /url\("([^"]+)"\)/g;
async function q(n, t) {
  const e = await caches.open(ye).catch(() => null);
  try {
    const s = await fetch(n, { headers: { Authorization: `Screen ${t}` }, credentials: "omit" });
    if (s.ok)
      return await e?.put(n, s.clone()), s;
  } catch {
  }
  return await e?.match(n) ?? null;
}
async function ve(n, t) {
  try {
    const e = await C(n, we, { token: t });
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
function Se(n) {
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
const G = [];
async function ke(n, t, e = document.documentElement) {
  const s = document.fonts;
  await Promise.all(Se(n.fonts_css).map(async (i) => {
    const r = await q(i.url, t);
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
  })), G.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, r] of Object.entries(n.variables)) {
    let o = r;
    for (const a of r.matchAll(be)) {
      const c = await q(a[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        G.push(l), o = o.replace(a[1], l);
      }
    }
    e.style.setProperty(i, o);
  }
  e.dataset.theme = n.key || "default";
}
function Ee(n = document) {
  const t = n.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, s = new URLSearchParams(n.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: s.get("mode") === "obs" ? "obs" : "screen"
  };
}
function v(n, t, e = {}) {
  let s = n.strings[t] ?? t;
  for (const [i, r] of Object.entries(e)) s = s.replace(`{${i}}`, String(r));
  return s;
}
function Ce(n, t = location) {
  return n.ws ? n.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const P = [], Me = Date.now();
function S(n) {
  P.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n}`.slice(0, 300)), P.length > 10 && P.shift();
}
function Ae(n = window) {
  n.addEventListener("error", (t) => S(t.message || "error")), n.addEventListener("unhandledrejection", (t) => S(String(t.reason)));
}
function J(n) {
  const t = window.innerWidth, e = window.innerHeight, s = performance.memory;
  return {
    version: n.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - Me) / 1e3),
    slide: n.slide,
    errors: [...P],
    memory: s ? Math.round(s.usedJSHeapSize / 1048576) : null,
    last_sync: n.lastSync ? new Date(n.lastSync).toISOString() : null,
    online: n.online,
    user_agent: navigator.userAgent,
    ...n.contentVersion ? { content_version: n.contentVersion } : {}
  };
}
const O = "evac.player.token", L = "evac.player.config";
function xe() {
  try {
    return localStorage.getItem(O);
  } catch {
    return null;
  }
}
function V(n) {
  try {
    n ? localStorage.setItem(O, n) : (localStorage.removeItem(O), localStorage.removeItem(L));
  } catch {
  }
}
function $e() {
  try {
    const n = localStorage.getItem(L);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function Y(n) {
  try {
    localStorage.setItem(L, JSON.stringify(n));
  } catch {
  }
}
const K = 3e3;
class Te {
  constructor(t, e) {
    this.env = t, this.clock = new pt(), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.display = new ue(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    const t = xe();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: v(this.env, "pair_title"),
      step1: v(this.env, "pair_step1"),
      step2: v(this.env, "pair_step2"),
      waiting: v(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await ut(this.env.api, J({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (i) {
      S(String(i)), this.display.message(v(this.env, "no_server"), v(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const s = async () => {
      try {
        const i = await ft(this.env.api, e);
        if (i.status === "paired")
          return V(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        S(String(i));
      }
      setTimeout(() => {
        s();
      }, K);
    };
    setTimeout(() => {
      s();
    }, K);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = $e();
    try {
      const s = Date.now();
      this.config = await U(this.env.api, t), this.clock.add(s, Date.now(), this.config.server_time), this.lastSync = Date.now(), Y(this.config);
    } catch (s) {
      if (s instanceof b) return this.unpair();
      S(String(s)), this.config = e;
    }
    this.bundle = ct(), await this.loadContent(t), this.show(), this.conn = new yt({
      api: this.env.api,
      ws: Ce(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => J({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline"
      }),
      onMessage: (s) => {
        this.handle(s, t);
      },
      onTransport: (s) => {
        this.transport = s;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (s) => {
        this.lastSync = s;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch (t.type) {
      case "config.changed":
        try {
          this.config = await U(this.env.api, e), Y(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds);
          const s = this.bundle?.version;
          await this.loadContent(e), (this.bundle?.version !== s || this.slide === "idle") && this.show();
        } catch (s) {
          s instanceof b && this.unpair();
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
      case "reload":
        location.reload();
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await fe(this.env.api, t) ?? this.bundle;
    } catch (s) {
      if (s instanceof b) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await ve(this.env.api, t);
    e && await ke(e, t).catch((s) => S(String(s))), this.bundle && ge(this.bundle);
  }
  show() {
    const t = me(this.bundle), e = this.config;
    if (t && e && this.bundle) {
      const s = e.screen;
      this.slide = `${t.key} v${t.version}`, this.display.layout(t.data, {
        vars: { event: e.event, screen: {
          name: s.name,
          zone: s.zone ?? "",
          room: s.room ?? "",
          venue: s.venue ?? "",
          tags: s.tags,
          groups: s.groups.map((i) => i.name)
        } },
        now: () => this.clock.now(),
        timezone: e.event.timezone,
        assets: this.bundle.assets,
        fonts: this.bundle.fonts,
        reducedMotion: matchMedia?.("(prefers-reduced-motion: reduce)").matches,
        onError: (i, r) => S(`${i}: ${String(r)}`)
      }, t.variables);
    } else e ? (this.slide = "idle", this.display.idle(e)) : this.display.message(v(this.env, "no_server"), v(this.env, "retrying"));
  }
  unpair() {
    this.conn?.stop(), this.conn = null, V(null), pe(), this.pair();
  }
}
function Pe() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((n) => S(String(n)));
}
if (typeof document < "u" && document.getElementById("player")) {
  Ae(), Pe();
  const n = Ee();
  new Te(n, document.getElementById("player")).boot();
}
export {
  Te as Player
};
