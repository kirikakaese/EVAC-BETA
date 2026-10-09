// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from player/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var tt = Object.defineProperty;
var et = (n, t, e) => t in n ? tt(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var E = (n, t, e) => et(n, typeof t != "symbol" ? t + "" : t, e);
class y extends Error {
}
async function S(n, t, e = {}) {
  const s = new AbortController(), i = setTimeout(() => s.abort(), e.timeout ?? 1e4), o = new Headers(e.headers);
  o.set("Accept", "application/json"), e.body && o.set("Content-Type", "application/json"), e.token && o.set("Authorization", `Screen ${e.token}`);
  try {
    const r = await fetch(n + t, {
      ...e,
      headers: o,
      signal: s.signal,
      cache: "no-store",
      credentials: "omit"
    });
    if (r.status === 401) throw new y("token rejected");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(i);
  }
}
const st = (n, t) => S(n, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), nt = (n, t) => S(n, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), O = (n, t) => S(n, "config/", { token: t });
class it {
  constructor() {
    this.samples = [], this.offset = 0;
  }
  add(t, e, s) {
    const i = e - t;
    i < 0 || !Number.isFinite(s) || (this.samples.push({ offset: s * 1e3 - (t + e) / 2, rtt: i }), this.samples.length > 8 && this.samples.shift(), this.offset = this.samples.reduce((o, r) => r.rtt < o.rtt ? r : o).offset);
  }
  now() {
    return Date.now() + this.offset;
  }
}
const ot = 3e4, rt = 3e5;
class at {
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
    this.backoff = Math.min(this.backoff * 2, ot), setTimeout(() => !this.stopped && t(), e);
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > rt ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        const e = t.body.getReader(), s = new TextDecoder();
        let i = "";
        for (; ; ) {
          const { value: o, done: r } = await e.read();
          if (r) break;
          i += s.decode(o, { stream: !0 });
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
        t instanceof y ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
      }
    }
  }
  async poll() {
    if (!(this.stopped || this.maybeBackToWebSocket()))
      try {
        const t = await S(
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
    S(this.o.api, "heartbeat/", {
      method: "POST",
      token: this.o.token,
      body: JSON.stringify({ data: t })
    }).then((e) => this.ack(e.server_time)).catch((e) => {
      e instanceof y ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
var w = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(w || {});
const ct = [0, 1], q = [1, 0], H = [2, 3], J = [3, 2], lt = {
  L: ct,
  M: q,
  Q: H,
  H: J
}, ht = /^\d*$/, ft = /^[A-Z0-9 $%*+./:-]*$/, P = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", R = 1, _ = 40, U = 3, ut = 3, M = 40, dt = 10, V = [
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
], Y = [
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
class pt {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, s, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    E(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    E(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    E(this, "modules", []);
    E(this, "types", []);
    if (this.version = t, this.ecc = e, t < R || t > _)
      throw new RangeError("Version value out of range");
    if (i < -1 || i > 7)
      throw new RangeError("Mask value out of range");
    this.size = t * 4 + 17;
    const o = Array.from({ length: this.size }).fill(!1);
    for (let a = 0; a < this.size; a++)
      this.modules.push(o.slice()), this.types.push(o.map(() => 0));
    this.drawFunctionPatterns();
    const r = this.addEccAndInterleave(s);
    if (this.drawCodewords(r), i === -1) {
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
      this.setFunctionModule(6, s, s % 2 === 0, w.Timing), this.setFunctionModule(s, 6, s % 2 === 0, w.Timing);
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
    for (let o = 0; o < 10; o++)
      s = s << 1 ^ (s >>> 9) * 1335;
    const i = (e << 10 | s) ^ 21522;
    for (let o = 0; o <= 5; o++)
      this.setFunctionModule(8, o, p(i, o));
    this.setFunctionModule(8, 7, p(i, 6)), this.setFunctionModule(8, 8, p(i, 7)), this.setFunctionModule(7, 8, p(i, 8));
    for (let o = 9; o < 15; o++)
      this.setFunctionModule(14 - o, 8, p(i, o));
    for (let o = 0; o < 8; o++)
      this.setFunctionModule(this.size - 1 - o, 8, p(i, o));
    for (let o = 8; o < 15; o++)
      this.setFunctionModule(8, this.size - 15 + o, p(i, o));
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
      const i = p(e, s), o = this.size - 11 + s % 3, r = Math.floor(s / 3);
      this.setFunctionModule(o, r, i), this.setFunctionModule(r, o, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let s = -4; s <= 4; s++)
      for (let i = -4; i <= 4; i++) {
        const o = Math.max(Math.abs(i), Math.abs(s)), r = t + i, a = e + s;
        r >= 0 && r < this.size && a >= 0 && a < this.size && this.setFunctionModule(r, a, o !== 2 && o !== 4, w.Position);
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
          w.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, s, i = w.Function) {
    this.modules[e][t] = s, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, s = this.ecc;
    if (t.length !== A(e, s))
      throw new RangeError("Invalid argument");
    const i = Y[s[0]][e], o = V[s[0]][e], r = Math.floor(C(e) / 8), a = i - r % i, c = Math.floor(r / i), l = [], d = Et(o);
    for (let f = 0, k = 0; f < i; f++) {
      const v = t.slice(k, k + c - o + (f < a ? 0 : 1));
      k += v.length;
      const Q = Mt(v, d);
      f < a && v.push(0), l.push(v.concat(Q));
    }
    const h = [];
    for (let f = 0; f < l[0].length; f++)
      l.forEach((k, v) => {
        (f !== c - o || v >= a) && h.push(k[f]);
      });
    return h;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(C(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let s = this.size - 1; s >= 1; s -= 2) {
      s === 6 && (s = 5);
      for (let i = 0; i < this.size; i++)
        for (let o = 0; o < 2; o++) {
          const r = s - o, c = (s + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][r] && e < t.length * 8 && (this.modules[c][r] = p(t[e >>> 3], 7 - (e & 7)), e++);
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
    for (let o = 0; o < this.size; o++) {
      let r = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[o][l] === r ? (a++, a === 5 ? t += U : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), r || (t += this.finderPenaltyCountPatterns(c) * M), r = this.modules[o][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(r, a, c) * M;
    }
    for (let o = 0; o < this.size; o++) {
      let r = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][o] === r ? (a++, a === 5 ? t += U : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), r || (t += this.finderPenaltyCountPatterns(c) * M), r = this.modules[l][o], a = 1);
      t += this.finderPenaltyTerminateAndCount(r, a, c) * M;
    }
    for (let o = 0; o < this.size - 1; o++)
      for (let r = 0; r < this.size - 1; r++) {
        const a = this.modules[o][r];
        a === this.modules[o][r + 1] && a === this.modules[o + 1][r] && a === this.modules[o + 1][r + 1] && (t += ut);
      }
    let e = 0;
    for (const o of this.modules)
      e = o.reduce((r, a) => r + (a ? 1 : 0), e);
    const s = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - s * 10) / s) - 1;
    return t += i * dt, t;
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
function m(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let s = t - 1; s >= 0; s--)
    e.push(n >>> s & 1);
}
function p(n, t) {
  return (n >>> t & 1) !== 0;
}
class F {
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
const mt = [1, 10, 12, 14], gt = [2, 9, 11, 13], wt = [4, 8, 16, 16];
function G(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function X(n) {
  const t = [];
  for (const e of n)
    m(e, 8, t);
  return new F(wt, n.length, t);
}
function yt(n) {
  if (!K(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const s = Math.min(n.length - e, 3);
    m(Number.parseInt(n.substring(e, e + s), 10), s * 3 + 1, t), e += s;
  }
  return new F(mt, n.length, t);
}
function bt(n) {
  if (!Z(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let s = P.indexOf(n.charAt(e)) * 45;
    s += P.indexOf(n.charAt(e + 1)), m(s, 11, t);
  }
  return e < n.length && m(P.indexOf(n.charAt(e)), 6, t), new F(gt, n.length, t);
}
function vt(n) {
  return n === "" ? [] : K(n) ? [yt(n)] : Z(n) ? [bt(n)] : [X(kt(n))];
}
function K(n) {
  return ht.test(n);
}
function Z(n) {
  return ft.test(n);
}
function St(n, t) {
  let e = 0;
  for (const s of n) {
    const i = G(s.mode, t);
    if (s.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + s.bitData.length;
  }
  return e;
}
function kt(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function C(n) {
  if (n < R || n > _)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function A(n, t) {
  return Math.floor(C(n) / 8) - V[t[0]][n] * Y[t[0]][n];
}
function Et(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let s = 0; s < n - 1; s++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < t.length; i++)
      t[i] = I(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = I(e, 2);
  }
  return t;
}
function Mt(n, t) {
  const e = t.map((s) => 0);
  for (const s of n) {
    const i = s ^ e.shift();
    e.push(0), t.forEach((o, r) => e[r] ^= I(o, i));
  }
  return e;
}
function I(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let s = 7; s >= 0; s--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> s & 1) * n;
  return e;
}
function At(n, t, e = 1, s = 40, i = -1, o = !0) {
  if (!(R <= e && e <= s && s <= _) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let r, a;
  for (r = e; ; r++) {
    const h = A(r, t) * 8, f = St(n, r);
    if (f <= h) {
      a = f;
      break;
    }
    if (r >= s)
      throw new RangeError("Data too long");
  }
  for (const h of [q, H, J])
    o && a <= A(r, h) * 8 && (t = h);
  const c = [];
  for (const h of n) {
    m(h.mode[0], 4, c), m(h.numChars, G(h.mode, r), c);
    for (const f of h.getData())
      c.push(f);
  }
  const l = A(r, t) * 8;
  m(0, Math.min(4, l - c.length), c), m(0, (8 - c.length % 8) % 8, c);
  for (let h = 236; c.length < l; h ^= 253)
    m(h, 8, c);
  const d = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((h, f) => d[f >>> 3] |= h << 7 - (f & 7)), new pt(r, t, d, i);
}
function Tt(n, t) {
  const {
    ecc: e = "L",
    boostEcc: s = !1,
    minVersion: i = 1,
    maxVersion: o = 40,
    maskPattern: r = -1,
    border: a = 1
  } = t || {}, c = typeof n == "string" ? vt(n) : Array.isArray(n) ? [X(n)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const l = At(
    c,
    lt[e],
    i,
    o,
    r,
    s
  ), d = Pt({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (d.data = d.data.map((h) => h.map((f) => !f))), t?.onEncoded?.(d), d;
}
function Pt(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, s = e + t * 2;
  n.size = s, n.data.forEach((o) => {
    for (let r = 0; r < t; r++)
      o.unshift(!1), o.push(!1);
  });
  for (let o = 0; o < t; o++)
    n.data.unshift(Array.from({ length: s }, (r) => !1)), n.data.push(Array.from({ length: s }, (r) => !1));
  const i = w.Border;
  n.types.forEach((o) => {
    for (let r = 0; r < t; r++)
      o.unshift(i), o.push(i);
  });
  for (let o = 0; o < t; o++)
    n.types.unshift(Array.from({ length: s }, (r) => i)), n.types.push(Array.from({ length: s }, (r) => i));
  return n;
}
const z = "http://www.w3.org/2000/svg";
function zt(n, t = document) {
  const { data: e, size: s } = Tt(n, { ecc: "M", border: 2 }), i = t.createElementNS(z, "svg");
  i.setAttribute("viewBox", `0 0 ${s} ${s}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const o = t.createElementNS(z, "rect");
  o.setAttribute("width", String(s)), o.setAttribute("height", String(s)), o.setAttribute("fill", "#fff"), i.appendChild(o);
  let r = "";
  e.forEach((c, l) => c.forEach((d, h) => {
    d && (r += `M${h} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(z, "path");
  return a.setAttribute("d", r), a.setAttribute("fill", "#000"), i.appendChild(a), i;
}
function u(n, t = "", e = "") {
  const s = document.createElement(n);
  return t && (s.className = t), e && (s.textContent = e), s;
}
class Ct {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.root.replaceChildren();
    const t = u("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, s) {
    const i = this.reset();
    i.classList.add("pairing"), i.append(u("h1", "", s.title));
    const o = u("div", "pairing-box"), r = u("p", "code", t);
    r.setAttribute("aria-label", t.split("").join(" "));
    const a = zt(e);
    a.setAttribute("role", "img"), a.setAttribute("aria-label", e), o.append(r, a);
    const c = u("ol", "steps");
    c.append(u("li", "", s.step1), u("li", "", s.step2)), i.append(o, c, u("p", "url", e), u("p", "waiting", s.waiting));
  }
  message(t, e = "") {
    const s = this.reset();
    s.classList.add("message"), s.append(u("h1", "", t)), e && s.append(u("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const s = u("p", "clock"), i = u("p", "date");
    e.append(u("h1", "event-name", t.event.name), s, i);
    const o = t.event.timezone || void 0, r = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: o }), a = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: o }), c = () => {
      const l = new Date(this.clock.now());
      s.textContent = r.format(l), i.textContent = a.format(l);
    };
    c(), this.clockTimer = setInterval(c, 1e3);
  }
  identify(t, e, s = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = u("div", "identify");
    i.setAttribute("role", "status"), i.append(u("p", "identify-name", t), u("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), s * 1e3);
  }
}
const It = "evac-player-content-v1", Nt = "content/theme/", Rt = /url\("([^"]+)"\)/g;
async function L(n, t) {
  const e = await caches.open(It).catch(() => null);
  try {
    const s = await fetch(n, { headers: { Authorization: `Screen ${t}` }, credentials: "omit" });
    if (s.ok)
      return await e?.put(n, s.clone()), s;
  } catch {
  }
  return await e?.match(n) ?? null;
}
async function _t(n, t) {
  try {
    const e = await S(n, Nt, { token: t });
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
function Ft(n) {
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
const $ = [];
async function Bt(n, t, e = document.documentElement) {
  const s = document.fonts;
  await Promise.all(Ft(n.fonts_css).map(async (i) => {
    const o = await L(i.url, t);
    if (o)
      try {
        const r = new FontFace(i.family, await o.arrayBuffer(), {
          weight: i.weight,
          style: i.style,
          unicodeRange: i.unicodeRange
        });
        s.add(await r.load());
      } catch {
      }
  })), $.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, o] of Object.entries(n.variables)) {
    let r = o;
    for (const a of o.matchAll(Rt)) {
      const c = await L(a[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        $.push(l), r = r.replace(a[1], l);
      }
    }
    e.style.setProperty(i, r);
  }
  e.dataset.theme = n.key || "default";
}
function Ot(n = document) {
  const t = n.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, s = new URLSearchParams(n.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: s.get("mode") === "obs" ? "obs" : "screen"
  };
}
function g(n, t, e = {}) {
  let s = n.strings[t] ?? t;
  for (const [i, o] of Object.entries(e)) s = s.replace(`{${i}}`, String(o));
  return s;
}
function Ut(n, t = location) {
  return n.ws ? n.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const T = [], Lt = Date.now();
function b(n) {
  T.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n}`.slice(0, 300)), T.length > 10 && T.shift();
}
function $t(n = window) {
  n.addEventListener("error", (t) => b(t.message || "error")), n.addEventListener("unhandledrejection", (t) => b(String(t.reason)));
}
function D(n) {
  const t = window.innerWidth, e = window.innerHeight, s = performance.memory;
  return {
    version: n.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - Lt) / 1e3),
    slide: n.slide,
    errors: [...T],
    memory: s ? Math.round(s.usedJSHeapSize / 1048576) : null,
    last_sync: n.lastSync ? new Date(n.lastSync).toISOString() : null,
    online: n.online,
    user_agent: navigator.userAgent,
    ...n.contentVersion ? { content_version: n.contentVersion } : {}
  };
}
const N = "evac.player.token", B = "evac.player.config";
function Dt() {
  try {
    return localStorage.getItem(N);
  } catch {
    return null;
  }
}
function x(n) {
  try {
    n ? localStorage.setItem(N, n) : (localStorage.removeItem(N), localStorage.removeItem(B));
  } catch {
  }
}
function xt() {
  try {
    const n = localStorage.getItem(B);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function W(n) {
  try {
    localStorage.setItem(B, JSON.stringify(n));
  } catch {
  }
}
const j = 3e3;
class Wt {
  constructor(t, e) {
    this.env = t, this.clock = new it(), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.display = new Ct(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    const t = Dt();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: g(this.env, "pair_title"),
      step1: g(this.env, "pair_step1"),
      step2: g(this.env, "pair_step2"),
      waiting: g(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await st(this.env.api, D({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (i) {
      b(String(i)), this.display.message(g(this.env, "no_server"), g(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const s = async () => {
      try {
        const i = await nt(this.env.api, e);
        if (i.status === "paired")
          return x(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        b(String(i));
      }
      setTimeout(() => {
        s();
      }, j);
    };
    setTimeout(() => {
      s();
    }, j);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = xt();
    try {
      const s = Date.now();
      this.config = await O(this.env.api, t), this.clock.add(s, Date.now(), this.config.server_time), this.lastSync = Date.now(), W(this.config);
    } catch (s) {
      if (s instanceof y) return this.unpair();
      b(String(s)), this.config = e;
    }
    await this.loadTheme(t), this.config ? this.display.idle(this.config) : this.display.message(g(this.env, "no_server"), g(this.env, "retrying")), this.conn = new at({
      api: this.env.api,
      ws: Ut(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => D({
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
          this.config = await O(this.env.api, e), W(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), await this.loadTheme(e), this.slide === "idle" && this.display.idle(this.config);
        } catch (s) {
          s instanceof y && this.unpair();
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
  async loadTheme(t) {
    const e = await _t(this.env.api, t);
    e && await Bt(e, t).catch((s) => b(String(s)));
  }
  unpair() {
    this.conn?.stop(), this.conn = null, x(null), this.pair();
  }
}
function jt() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((n) => b(String(n)));
}
if (typeof document < "u" && document.getElementById("player")) {
  $t(), jt();
  const n = Ot();
  new Wt(n, document.getElementById("player")).boot();
}
export {
  Wt as Player
};
