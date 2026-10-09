// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
var qt = Object.defineProperty;
var Ut = (n, t, e) => t in n ? qt(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var P = (n, t, e) => Ut(n, typeof t != "symbol" ? t + "" : t, e);
class w extends Error {
}
async function E(n, t, e = {}) {
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
const Gt = (n, t) => E(n, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), Jt = (n, t) => E(n, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), ht = (n, t) => E(n, "config/", { token: t });
class Vt {
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
const Yt = 3e4, Kt = 3e5;
class Xt {
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
    this.backoff = Math.min(this.backoff * 2, Yt), setTimeout(() => !this.stopped && t(), e);
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > Kt ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        const t = await E(
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
    E(this.o.api, "heartbeat/", {
      method: "POST",
      token: this.o.token,
      body: JSON.stringify({ data: t })
    }).then((e) => this.ack(e.server_time)).catch((e) => {
      e instanceof w ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function R(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function Zt(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function Qt(n, t, e) {
  const i = n.style;
  if (!t) return;
  const s = (r, o) => {
    o && i.setProperty(r, o);
  };
  s("color", R(t.color)), s("background", R(t.background)), t.borderWidth && i.setProperty("border", `${t.borderWidth / 10}cqh solid ${R(t.borderColor) || "currentColor"}`), t.radius !== void 0 && i.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && i.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && i.setProperty("opacity", String(t.opacity)), s("font-family", Zt(t.fontFamily, e)), t.fontSize && i.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && i.setProperty("font-weight", String(t.fontWeight)), s("font-style", t.fontStyle ?? ""), s("text-align", t.textAlign ?? ""), t.verticalAlign && i.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && i.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && i.setProperty("letter-spacing", `${t.letterSpacing}em`), s("text-transform", t.textTransform ?? ""), t.tabularNumbers && i.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && i.setProperty("box-shadow", "var(--evac-shadow)");
}
function te(n, t, e) {
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
function ee(n) {
  const t = [];
  let e = "", i = "";
  for (const s of n)
    i ? (s === i && (i = ""), e += s) : s === '"' || s === "'" ? (i = s, e += s) : s === "|" ? (t.push(e), e = "") : e += s;
  return t.push(e), t.map((s) => s.trim());
}
function ne(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function dt(n, t, e) {
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
function k(n) {
  return n == null ? "" : Array.isArray(n) ? n.map(k).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function ie(n, t, e) {
  const [i, ...s] = t.split(":"), r = ne(s.join(":")), o = () => n instanceof Date ? n : new Date(String(n));
  switch (i.trim()) {
    case "upper":
      return k(n).toUpperCase();
    case "lower":
      return k(n).toLowerCase();
    case "title":
      return k(n).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = k(n);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return k(n) === "" ? r : n;
    case "date":
      return isNaN(o().getTime()) ? "" : dt(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : dt(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map(k).join(r || ", ") : k(n);
    default:
      return n;
  }
}
function _(n, t, e = {}) {
  const [i, ...s] = ee(n);
  let r = te(t, i, e);
  for (const o of s) r = ie(r, o, e);
  return r;
}
function se(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function q(n, t, e = {}) {
  const i = n.trim();
  if (!i) return !0;
  if (i.startsWith("not ")) return !q(i.slice(4), t, e);
  const s = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(i);
  if (s) {
    const r = k(_(s[1], t, e)), o = k(_(s[3], t, e));
    return s[2] === "==" ? r === o : r !== o;
  }
  return se(_(i.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const re = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function Et(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const i = n.split(re);
  let s = 0;
  const r = (o) => {
    let a = "";
    for (; s < i.length; ) {
      const c = i[s++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(h)) return [a, h];
        if (h === "if") {
          const d = q(l[2], t, e), [u, g] = r(["else", "endif"]);
          let m = "";
          g === "else" && (m = r(["endif"])[0]), a += d ? u : m;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += k(_(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
const oe = `(() => {
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
function ut(n) {
  return n.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function ae(n, t, e, i = "") {
  const s = ut(t), r = e ? ` ${e}` : "", o = [
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
  ].join("; "), a = String(n.css ?? "").replace(/<\/style/gi, "<\\/style"), c = String(n.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${ut(o)}"><style nonce="${s}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${i}</style><style nonce="${s}">${a}</style><script nonce="${s}">${oe}<\/script></head><body>${String(n.html ?? "")}` + (c.trim() ? `<script nonce="${s}">${c}<\/script>` : "") + "</body></html>";
}
function ce(n) {
  const t = [];
  try {
    const e = getComputedStyle(n);
    for (let i = 0; i < e.length; i++) {
      const s = e[i];
      if (s.startsWith("--evac-")) {
        const r = e.getPropertyValue(s).trim().replace(/[<>{};]/g, "");
        r && t.push(`${s}:${r}`);
      }
    }
  } catch {
  }
  return t.length ? `:root{${t.join(";")}}` : "";
}
function le(n = document) {
  const t = n.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
var A = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(A || {});
const he = [0, 1], Mt = [1, 0], At = [2, 3], Tt = [3, 2], de = {
  L: he,
  M: Mt,
  Q: At,
  H: Tt
}, ue = /^\d*$/, fe = /^[A-Z0-9 $%*+./:-]*$/, J = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", st = 1, rt = 40, ft = 3, pe = 3, D = 40, me = 10, Pt = [
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
], Nt = [
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
class ge {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, i, s) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    P(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    P(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    P(this, "modules", []);
    P(this, "types", []);
    if (this.version = t, this.ecc = e, t < st || t > rt)
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
      this.setFunctionModule(8, r, $(s, r));
    this.setFunctionModule(8, 7, $(s, 6)), this.setFunctionModule(8, 8, $(s, 7)), this.setFunctionModule(7, 8, $(s, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, $(s, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, $(s, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, $(s, r));
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
      const s = $(e, i), r = this.size - 11 + i % 3, o = Math.floor(i / 3);
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
    if (t.length !== L(e, i))
      throw new RangeError("Invalid argument");
    const s = Nt[i[0]][e], r = Pt[i[0]][e], o = Math.floor(X(e) / 8), a = s - o % s, c = Math.floor(o / s), l = [], h = xe(r);
    for (let u = 0, g = 0; u < s; u++) {
      const m = t.slice(g, g + c - r + (u < a ? 0 : 1));
      g += m.length;
      const C = Ee(m, h);
      u < a && m.push(0), l.push(m.concat(C));
    }
    const d = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((g, m) => {
        (u !== c - r || m >= a) && d.push(g[u]);
      });
    return d;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(X(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let i = this.size - 1; i >= 1; i -= 2) {
      i === 6 && (i = 5);
      for (let s = 0; s < this.size; s++)
        for (let r = 0; r < 2; r++) {
          const o = i - r, c = (i + 1 & 2) === 0 ? this.size - 1 - s : s;
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
        this.modules[r][l] === o ? (a++, a === 5 ? t += ft : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * D), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * D;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += ft : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * D), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * D;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += pe);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const i = this.size * this.size, s = Math.ceil(Math.abs(e * 20 - i * 10) / i) - 1;
    return t += s * me, t;
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
function x(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let i = t - 1; i >= 0; i--)
    e.push(n >>> i & 1);
}
function $(n, t) {
  return (n >>> t & 1) !== 0;
}
class ot {
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
const ye = [1, 10, 12, 14], ve = [2, 9, 11, 13], we = [4, 8, 16, 16];
function It(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function Dt(n) {
  const t = [];
  for (const e of n)
    x(e, 8, t);
  return new ot(we, n.length, t);
}
function be(n) {
  if (!zt(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const i = Math.min(n.length - e, 3);
    x(Number.parseInt(n.substring(e, e + i), 10), i * 3 + 1, t), e += i;
  }
  return new ot(ye, n.length, t);
}
function Se(n) {
  if (!Ot(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let i = J.indexOf(n.charAt(e)) * 45;
    i += J.indexOf(n.charAt(e + 1)), x(i, 11, t);
  }
  return e < n.length && x(J.indexOf(n.charAt(e)), 6, t), new ot(ve, n.length, t);
}
function ke(n) {
  return n === "" ? [] : zt(n) ? [be(n)] : Ot(n) ? [Se(n)] : [Dt($e(n))];
}
function zt(n) {
  return ue.test(n);
}
function Ot(n) {
  return fe.test(n);
}
function Ce(n, t) {
  let e = 0;
  for (const i of n) {
    const s = It(i.mode, t);
    if (i.numChars >= 1 << s)
      return Number.POSITIVE_INFINITY;
    e += 4 + s + i.bitData.length;
  }
  return e;
}
function $e(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function X(n) {
  if (n < st || n > rt)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function L(n, t) {
  return Math.floor(X(n) / 8) - Pt[t[0]][n] * Nt[t[0]][n];
}
function xe(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let i = 0; i < n - 1; i++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let i = 0; i < n; i++) {
    for (let s = 0; s < t.length; s++)
      t[s] = Z(t[s], e), s + 1 < t.length && (t[s] ^= t[s + 1]);
    e = Z(e, 2);
  }
  return t;
}
function Ee(n, t) {
  const e = t.map((i) => 0);
  for (const i of n) {
    const s = i ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= Z(r, s));
  }
  return e;
}
function Z(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let i = 7; i >= 0; i--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> i & 1) * n;
  return e;
}
function Me(n, t, e = 1, i = 40, s = -1, r = !0) {
  if (!(st <= e && e <= i && i <= rt) || s < -1 || s > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const d = L(o, t) * 8, u = Ce(n, o);
    if (u <= d) {
      a = u;
      break;
    }
    if (o >= i)
      throw new RangeError("Data too long");
  }
  for (const d of [Mt, At, Tt])
    r && a <= L(o, d) * 8 && (t = d);
  const c = [];
  for (const d of n) {
    x(d.mode[0], 4, c), x(d.numChars, It(d.mode, o), c);
    for (const u of d.getData())
      c.push(u);
  }
  const l = L(o, t) * 8;
  x(0, Math.min(4, l - c.length), c), x(0, (8 - c.length % 8) % 8, c);
  for (let d = 236; c.length < l; d ^= 253)
    x(d, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((d, u) => h[u >>> 3] |= d << 7 - (u & 7)), new ge(o, t, h, s);
}
function Ae(n, t) {
  const {
    ecc: e = "L",
    boostEcc: i = !1,
    minVersion: s = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof n == "string" ? ke(n) : Array.isArray(n) ? [Dt(n)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const l = Me(
    c,
    de[e],
    s,
    r,
    o,
    i
  ), h = Te({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (h.data = h.data.map((d) => d.map((u) => !u))), t?.onEncoded?.(h), h;
}
function Te(n, t = 1) {
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
const V = "http://www.w3.org/2000/svg";
function Rt(n, t = document) {
  const { data: e, size: i } = Ae(n, { ecc: "M", border: 2 }), s = t.createElementNS(V, "svg");
  s.setAttribute("viewBox", `0 0 ${i} ${i}`), s.setAttribute("shape-rendering", "crispEdges"), s.setAttribute("class", "qr");
  const r = t.createElementNS(V, "rect");
  r.setAttribute("width", String(i)), r.setAttribute("height", String(i)), r.setAttribute("fill", "#fff"), s.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((h, d) => {
    h && (o += `M${d} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(V, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), s.appendChild(a), s;
}
class b extends HTMLElement {
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
    return Et(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function Pe(n, t) {
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
class Ne extends b {
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
      const s = () => Pe(this, t);
      requestAnimationFrame(s), document.fonts?.ready.then(s).catch(() => {
      }), this.observe(s);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Ie extends b {
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
function _t(n, t, e) {
  const i = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = n.urls[r], i.appendChild(a);
    }
  const s = document.createElement("img");
  return s.src = n.urls.original, s.alt = e || n.alt || "", s.decoding = "async", s.style.objectFit = t, i.appendChild(s), i;
}
class De extends b {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(_t(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class ze extends b {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), i = t.map((o) => {
      const a = _t(o, e, "");
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
class Oe extends b {
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
class Re extends b {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class _e extends b {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Le extends b {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = Rt(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Be = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Fe extends b {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, i = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Be[t], timeZone: e }), s = document.createElement("time"), r = () => {
      s.textContent = i.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(s), this.every(1e3, r);
  }
}
class We extends b {
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
function je(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), i = Math.floor(e / 86400), s = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${i} ${i === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || i === 0 ? `${a(s + i * 24)}:${a(r)}:${a(o)}` : `${i}d ${a(s)}:${a(r)}:${a(o)}`;
}
class He extends b {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), i = () => {
      const s = t - this.ctx.now();
      e.textContent = s <= 0 && this.props.finished ? this.text(this.props.finished) : je(s, String(this.props.format ?? "auto"));
    };
    i(), this.replaceChildren(e), this.every(250, i);
  }
}
class qe extends b {
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
    const e = this.props, i = document.createElement("iframe");
    i.setAttribute("sandbox", "allow-scripts"), i.setAttribute("referrerpolicy", "no-referrer"), i.setAttribute("allow", "autoplay"), i.setAttribute("title", this.el.name || "Code"), i.setAttribute("tabindex", "-1"), i.className = "evac-code-frame", i.srcdoc = ae(e, t, location.origin, ce(this)), this.frame = i, window.addEventListener("message", this.onMessage), this.replaceChildren(i), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
  }
  /** Only the kinds of data the element asked for (and that the server let it ask for). */
  send() {
    const t = new Set(this.props.data ?? []), e = this.ctx.vars, i = {};
    if (t.has("event") && (i.event = e.event ?? null), t.has("screen") && (i.screen = e.screen ?? null), t.has("time") && (i.now = this.ctx.now(), i.timezone = this.ctx.timezone ?? ""), t.has("assets")) {
      const s = {};
      for (const r of this.props.assets ?? []) {
        const o = this.ctx.assets[r];
        if (!o) continue;
        const a = {};
        for (const [c, l] of Object.entries(o.urls)) a[c] = new URL(l, location.href).href;
        s[r] = { name: o.name, kind: o.kind, alt: o.alt, width: o.width, height: o.height, urls: a };
      }
      i.assets = s;
    }
    this.frame?.contentWindow?.postMessage({ type: "evac:data", data: JSON.parse(JSON.stringify(i)) }, "*");
  }
  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage), this.frame = null, super.disconnectedCallback();
  }
}
const Lt = {
  text: Ne,
  richtext: Ie,
  image: De,
  slideshow: ze,
  video: Oe,
  audio: Re,
  shape: _e,
  qr: Le,
  clock: Fe,
  countdown: He,
  date: We,
  code: qe
};
function Ue(n = customElements) {
  for (const [t, e] of Object.entries(Lt))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
class Ge {
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
  const i = document.createElement(n);
  return t && (i.className = t), e != null && e !== "" && (i.textContent = String(e)), i;
}
function T(n) {
  if (typeof n == "number") return Number.isFinite(n) ? n : null;
  if (typeof n == "string" && n.trim() !== "") {
    const t = Number(n.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function z(n, t) {
  if (typeof n != "string" || !n) return "";
  const e = /^\d{4}-\d{2}-\d{2}$/.test(n), i = new Date(e ? `${n}T12:00:00Z` : n);
  if (Number.isNaN(i.getTime())) return n;
  const s = e ? { weekday: "short", day: "numeric", month: "short" } : { hour: "2-digit", minute: "2-digit", hour12: !1 };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...s, timeZone: e ? "UTC" : t }).format(i);
  } catch {
    return new Intl.DateTimeFormat("en-GB", s).format(i);
  }
}
const Je = ["time", "title", "subtitle", "label", "value"];
class Ve extends b {
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
    const i = f("div", `evac-data evac-data-${e.visual}`), s = String(this.props.title || e.options.heading || "");
    s && i.appendChild(f("div", "evac-data-heading", s));
    const r = f("div", "evac-data-body");
    i.appendChild(r), (pt[e.visual] ?? pt.list)(r, e, this), this.ctx.editing && e.stale && i.appendChild(f("span", "evac-data-stale", "stale")), this.replaceChildren(i);
  }
  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(t, e) {
    return Et(
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
function N(n, t) {
  return t.rows.length ? !1 : (n.appendChild(f("div", "evac-data-empty", "–")), !0);
}
const pt = {
  text(n, t, e) {
    n.appendChild(f("div", "evac-data-text", e.tmpl(
      String(t.options.template || "{{ data.first.title }}"),
      t
    )));
  },
  list(n, t, e) {
    if (N(n, t)) return;
    const i = f("ul", "evac-data-list");
    for (const s of t.rows) {
      const r = f("li");
      s.time && r.appendChild(f("span", "evac-data-time", z(s.time, e.tz)));
      const o = f("span", "evac-data-main");
      o.appendChild(f("span", "evac-data-title", s.title ?? s.label ?? s.value)), s.subtitle && o.appendChild(f("span", "evac-data-sub", s.subtitle)), r.appendChild(o), s.value !== void 0 && s.value !== null && s.title && r.appendChild(f("span", "evac-data-value", s.value)), i.appendChild(r);
    }
    n.appendChild(i);
  },
  table(n, t, e) {
    if (N(n, t)) return;
    const i = Je.filter((o) => t.rows.some((a) => a[o] !== void 0 && a[o] !== null && a[o] !== "")), s = f("table", "evac-data-table"), r = f("tbody");
    for (const o of t.rows) {
      const a = f("tr");
      for (const c of i) a.appendChild(f("td", `evac-data-${c}`, c === "time" ? z(o[c], e.tz) : o[c]));
      r.appendChild(a);
    }
    s.appendChild(r), n.appendChild(s);
  },
  cards(n, t, e) {
    if (N(n, t)) return;
    const i = f("div", "evac-data-cards");
    for (const s of t.rows) {
      const r = f("div", "evac-data-card");
      if (typeof s.image == "string" && s.image.startsWith("/")) {
        const o = f("img");
        o.src = s.image, o.alt = "", r.appendChild(o);
      }
      s.time && r.appendChild(f("div", "evac-data-time", z(s.time, e.tz))), r.appendChild(f("div", "evac-data-title", s.title ?? s.label)), s.subtitle && r.appendChild(f("div", "evac-data-sub", s.subtitle)), s.value !== void 0 && s.value !== null && r.appendChild(f("div", "evac-data-value", s.value)), i.appendChild(r);
    }
    n.appendChild(i);
  },
  counter(n, t) {
    const e = t.rows[0] ?? {}, i = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, s = T(i), r = f("div", "evac-data-number", s === null ? i : s.toLocaleString("en-GB"));
    t.options.unit && r.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(r), (e.label || e.title) && n.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(n, t) {
    const e = t.rows[0] ?? {}, i = T(e.value) ?? 0, s = T(t.options.minimum) ?? 0, r = T(t.options.maximum) ?? 100, o = Math.max(0, Math.min(1, (i - s) / (r - s || 1))), a = "http://www.w3.org/2000/svg", c = document.createElementNS(a, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${i}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (d, u) => {
      const g = Math.PI * (1 - d), m = document.createElementNS(a, "path");
      m.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(g)} ${100 - 80 * Math.sin(g)}`), m.setAttribute("class", u), c.appendChild(m);
    };
    l(1, "evac-gauge-track"), o > 0 && l(o, "evac-gauge-fill"), n.appendChild(c);
    const h = f("div", "evac-data-number", i.toLocaleString("en-GB"));
    t.options.unit && h.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(h), (e.label || e.title) && n.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(n, t, e) {
    if (N(n, t)) return;
    const i = t.rows.map((o) => [o.time ? z(o.time, e.tz) : "", o.title ?? o.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), s = f("div", "evac-marquee-box"), r = f("span", "evac-marquee", i);
    r.style.animationDuration = `${Math.max(10, i.length / 5)}s`, s.appendChild(r), n.appendChild(s);
  },
  bars(n, t) {
    if (N(n, t)) return;
    const e = t.rows.map((r) => T(r.value) ?? 0), i = T(t.options.maximum) || Math.max(...e, 1), s = f("div", "evac-data-bars");
    t.rows.forEach((r, o) => {
      const a = f("div", "evac-bar");
      a.appendChild(f("span", "evac-bar-label", r.label ?? r.title));
      const c = f("span", "evac-bar-track"), l = f("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[o] / i * 100))}%`, c.appendChild(l), a.appendChild(c), a.appendChild(f("span", "evac-bar-value", `${e[o].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), s.appendChild(a);
    }), n.appendChild(s);
  }
};
Lt.data = Ve;
function Ye(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function Ke(n, t) {
  const e = !n.visible_if || q(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const i = document.createElement("div");
  i.className = `evac-el evac-el-${n.type}`, i.dataset.id = n.id, (!e || n.hidden) && i.classList.add("evac-dimmed"), Ye(i, n), Qt(i, n.style, t);
  const s = n.animation;
  s?.enter && s.enter !== "none" && !t.reducedMotion && !t.editing && (i.classList.add(`evac-enter-${s.enter}`), i.style.animationDuration = `${s.duration ?? 600}ms`, i.style.animationDelay = `${s.delay ?? 0}ms`);
  const r = `evac-${n.type}`;
  if (!customElements.get(r))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? i : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", i.appendChild(o), o.configure(n, t), i;
}
function Xe(n, t, e) {
  Ue();
  const i = document.createElement("div");
  i.className = "evac-stage";
  const s = t.background;
  if (s?.color && (i.style.background = R(s.color)), s?.asset && e.assets[s.asset]) {
    const c = e.assets[s.asset], l = c.urls.webp ?? c.urls.original;
    i.style.backgroundImage = `url("${l}")`, i.style.backgroundSize = s.fit ?? "cover", i.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = Ke(c, e);
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
function p(n, t = "", e = "") {
  const i = document.createElement(n);
  return t && (i.className = t), e && (i.textContent = e), i;
}
class Ze {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null;
  }
  reset() {
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = p("main", "view");
    return this.root.appendChild(t), t;
  }
  pairing(t, e, i) {
    const s = this.reset();
    s.classList.add("pairing"), s.append(p("h1", "", i.title));
    const r = p("div", "pairing-box"), o = p("p", "code", t);
    o.setAttribute("aria-label", t.split("").join(" "));
    const a = Rt(e);
    a.setAttribute("role", "img"), a.setAttribute("aria-label", e), r.append(o, a);
    const c = p("ol", "steps");
    c.append(p("li", "", i.step1), p("li", "", i.step2)), s.append(r, c, p("p", "url", e), p("p", "waiting", i.waiting));
  }
  message(t, e = "") {
    const i = this.reset();
    i.classList.add("message"), i.append(p("h1", "", t)), e && i.append(p("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const i = p("p", "clock"), s = p("p", "date");
    e.append(p("h1", "event-name", t.event.name), i, s);
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
    this.rendered = Xe(s, t, e);
  }
  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(t, e, i = 30) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const s = p("div", "test-pattern");
    s.setAttribute("role", "img"), s.setAttribute("aria-label", t);
    const r = p("div", "tp-bars");
    for (const c of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"])
      r.appendChild(p("span", `tp-bar tp-${c}`));
    const o = p("div", "tp-ramp"), a = p("div", "tp-info");
    a.append(p("p", "tp-title", t), ...e.map((c) => p("p", "", c))), s.append(r, o, p("div", "tp-grid"), p("div", "tp-circle"), p("div", "tp-corners"), a), this.root.appendChild(s), this.overlay = s, this.overlayTimer = setTimeout(() => s.remove(), i * 1e3);
  }
  identify(t, e, i = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const s = p("div", "identify");
    s.setAttribute("role", "status"), s.append(p("p", "identify-name", t), p("p", "identify-detail", e)), this.root.appendChild(s), this.overlay = s, this.overlayTimer = setTimeout(() => s.remove(), i * 1e3);
  }
}
const at = "evac.player.bundle";
async function Qe(n, t) {
  try {
    const e = await E(n, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(at, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof w) throw e;
    return Q();
  }
}
function Q() {
  try {
    const n = localStorage.getItem(at);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function tn() {
  try {
    localStorage.removeItem(at);
  } catch {
  }
}
function en(n) {
  return n?.layouts.length ? n.layouts.find((t) => t.default) ?? n.layouts[0] : null;
}
async function nn(n) {
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
const j = "evac.player.program";
async function sn(n, t) {
  try {
    const e = await E(n, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(j, JSON.stringify(e.program)) : localStorage.removeItem(j);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof w) throw e;
    return tt();
  }
}
function tt() {
  try {
    const n = localStorage.getItem(j);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function rn() {
  try {
    localStorage.removeItem(j);
  } catch {
  }
}
const Bt = 1600;
function on(n, t) {
  const e = [];
  for (const i of n ?? [])
    for (const [s, r] of i.windows)
      if ((s === null || s <= t) && (r === null || t < r)) {
        e.push({ overlay: i, start: s ?? 0, end: r });
        break;
      }
  return e.sort((i, s) => s.overlay.rank - i.overlay.rank || s.start - i.start);
}
function an(n, t) {
  let e = null;
  for (const i of n ?? [])
    for (const [s, r] of i.windows)
      for (const o of [s, r])
        o !== null && o > t && (e === null || o < e) && (e = o);
  return e;
}
function cn(n) {
  return {
    card: n.find((t) => t.overlay.style === "card") ?? null,
    banner: n.find((t) => t.overlay.style === "banner") ?? null,
    ticker: n.filter((t) => t.overlay.style === "ticker")
  };
}
function ln(n) {
  const t = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(n);
  if (!t) return "#ffffff";
  const [e, i, s] = t.slice(1).map((o) => {
    const a = parseInt(o, 16) / 255;
    return a <= 0.03928 ? a / 12.92 : ((a + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * e + 0.7152 * i + 0.0722 * s > 0.179 ? "#000000" : "#ffffff";
}
function y(n, t, e = "") {
  const i = document.createElement(n);
  return i.className = t, e && (i.textContent = e), i;
}
function Y(n, t) {
  n.style.setProperty("--ann-bg", /^#[0-9a-f]{6}$/i.test(t) ? t : "#2563eb"), n.style.setProperty("--ann-fg", ln(t));
}
function hn(n, t = 100) {
  if (n === "none" || typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const i = Math.max(0, Math.min(1, t / 100)) * 0.4, s = n === "chime" ? [[660, 0, 0.6], [880, 0.35, 0.9]] : n === "gong" ? [[196, 0, 2.5], [392, 0, 1.5], [294, 0.02, 2]] : [[880, 0, 0.25], [660, 0.3, 0.25], [880, 0.6, 0.25], [660, 0.9, 0.25]];
  let r = 0;
  for (const [o, a, c] of s) {
    const l = e.createOscillator(), h = e.createGain();
    l.type = n === "alert" ? "square" : "sine", l.frequency.value = o;
    const d = e.currentTime + a;
    h.gain.setValueAtTime(1e-4, d), h.gain.exponentialRampToValueAtTime(i, d + 0.02), h.gain.exponentialRampToValueAtTime(1e-4, d + c), l.connect(h).connect(e.destination), l.start(d), l.stop(d + c + 0.05), r = Math.max(r, a + c);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, (r + 0.5) * 1e3);
}
class dn {
  constructor(t) {
    this.speaker = t, this.drawn = "", this.heard = /* @__PURE__ */ new Set(), this.node = y("div", "ann-layer"), this.node.setAttribute("aria-live", "polite");
  }
  /** Keep the layer on top of the content (the display replaces its children on every slide). */
  attach(t) {
    (this.node.parentElement !== t || t.lastElementChild !== this.node) && t.appendChild(this.node);
  }
  update(t, e, i = {}) {
    const s = i.hidden ? [] : on(t, e), { card: r, banner: o, ticker: a } = cn(s), c = i.audio?.enabled !== !1;
    for (const h of s) {
      const d = `${h.overlay.id}@${h.start}`, u = h.overlay.sound && h.overlay.sound !== "none";
      this.heard.has(d) || (this.heard.add(d), c && u && hn(h.overlay.sound, i.audio?.volume ?? 100)), c && h.overlay.speech && this.speaker?.say(d, h.overlay.speech, { volume: i.audio?.volume, delayMs: u ? Bt : 0 });
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
        const h = y("section", "ann-card");
        Y(h, r.overlay.colour), h.append(y("p", "ann-level", r.overlay.level), y("h2", "ann-title", r.overlay.title)), r.overlay.text && r.overlay.text !== r.overlay.title && h.append(y("p", "ann-text", r.overlay.text)), this.node.append(h);
      }
      if (o) {
        const h = y("div", "ann-banner");
        Y(h, o.overlay.colour), h.append(y("span", "ann-level", o.overlay.level), y("span", "ann-text", o.overlay.text)), this.node.append(h);
      }
      if (a.length) {
        const h = y("div", "ann-ticker");
        Y(h, a[0].overlay.colour);
        const d = y("div", "ann-track"), u = a.map((m) => m.overlay.text).join("   ◆   "), g = y("span", "", u);
        g.setAttribute("aria-hidden", "true"), d.append(y("span", "", u), g), d.style.setProperty("--ann-duration", `${Math.max(12, Math.round(u.length / 6))}s`), h.append(y("span", "ann-level", a[0].overlay.level), d), this.node.append(h);
      }
      this.node.classList.toggle("has-bottom", !!(o && a.length));
    }
  }
}
class un {
  constructor(t = (e) => new Audio(e)) {
    this.make = t, this.spoken = /* @__PURE__ */ new Set(), this.queue = [], this.playing = !1;
  }
  /** Speak ``url`` once for ``key`` (an announcement occurrence); later calls with the same key do nothing. */
  say(t, e, i = {}) {
    if (!e || this.spoken.has(t)) return !1;
    this.spoken.add(t), this.spoken.size > 500 && (this.spoken = new Set([...this.spoken].slice(-100)));
    const s = { url: e, volume: Math.max(0, Math.min(1, (i.volume ?? 100) / 100)) };
    return setTimeout(() => {
      this.queue.push(s), this.next();
    }, i.delayMs ?? 0), !0;
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
    const i = () => {
      this.playing = !1, this.next();
    };
    e.addEventListener("ended", i, { once: !0 }), e.addEventListener("error", i, { once: !0 });
    const s = e.play();
    s && typeof s.catch == "function" && s.catch(i);
  }
}
async function fn(n) {
  let t = 0;
  return await Promise.all([...new Set(n)].map(async (e) => {
    try {
      const i = await fetch(e, { credentials: "omit" });
      i.ok && (t += 1), await i.body?.cancel();
    } catch {
    }
  })), t;
}
const ct = "evac.player.widgets";
function pn() {
  try {
    const n = localStorage.getItem(ct);
    return n ? JSON.parse(n) : {};
  } catch {
    return {};
  }
}
async function mn(n, t, e) {
  try {
    const i = await E(n, "widgets/data/", { token: t, timeout: 15e3 });
    e.set(i.widgets ?? {});
    try {
      localStorage.setItem(ct, JSON.stringify(i.widgets ?? {}));
    } catch {
    }
    return !0;
  } catch (i) {
    if (i instanceof w) throw i;
    return !1;
  }
}
function gn() {
  try {
    localStorage.removeItem(ct);
  } catch {
  }
}
const yn = 5, vn = 1e4;
function wn(n) {
  let t = 2166136261;
  for (let e = 0; e < n.length; e++)
    t ^= n.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function bn(n, t) {
  let e = t >>> 0 || 1;
  const i = [...n];
  for (let s = i.length - 1; s > 0; s--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (s + 1);
    [i[s], i[r]] = [i[r], i[s]];
  }
  return i;
}
function Sn(n, t) {
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
function kn(n, t, e) {
  if (n.from !== null && n.from !== void 0 && t < n.from || n.until !== null && n.until !== void 0 && t >= n.until) return !1;
  const i = n.tags ?? [], s = e.screen?.tags ?? [];
  return i.length && !i.some((r) => s.includes(r)) ? !1 : q(n.when ?? "", e);
}
function et(n, t, e, i, s, r = []) {
  const o = n.playlists[t];
  if (!o || r.includes(t) || r.length >= yn) return [];
  let a = [];
  const c = [];
  for (const l of o.items ?? []) {
    if (!kn(l, i, e)) continue;
    let h = [];
    if (l.playlist) h = et(n, l.playlist, e, i, s, [...r, t]);
    else if (l.layout && l.layout in n.layouts) {
      const d = l.duration || n.layouts[l.layout] || o.default || vn;
      h = [{ layout: l.layout, duration: d, item: l.id }];
    }
    h.length && (a.push(h), c.push(Math.max(1, Math.trunc(l.weight || 1))));
  }
  return o.mode === "weighted" ? a = Sn(a, c) : o.mode === "shuffle" && (a = bn(a, wn(`${t}:${s}`))), a.flat();
}
function Cn(n, t) {
  return (n[0] === null || n[0] <= t) && (n[1] === null || t < n[1]);
}
function $n(n, t) {
  const e = [];
  return n.entries.forEach((i, s) => {
    const r = i.windows.find((o) => Cn(o, t));
    r && e.push({ key: [-i.priority, -(r[0] ?? -1), s], entry: i, w: r });
  }), e.sort((i, s) => i.key[0] - s.key[0] || i.key[1] - s.key[1] || i.key[2] - s.key[2]), e.map((i) => [i.entry, i.w]);
}
function xn(n, t, e, i, s) {
  const r = i.content, o = { entry: i.id, index: 0, count: 1, start: s[0], end: s[1] };
  if (r.message !== void 0) return r.message in (n.messages ?? {}) ? { ...o, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in n.layouts ? { ...o, layout: r.layout } : null;
  const a = r.playlist, c = s[0] ?? 0;
  let l = et(n, a, t, e, 0);
  const h = l.reduce((m, C) => m + C.duration, 0);
  if (!h) return null;
  const d = Math.floor((e - c) / h);
  d && (l = et(n, a, t, e, d));
  let u = e - c - d * h, g = c + d * h;
  for (let m = 0; m < l.length; m++) {
    const C = l[m];
    if (u < C.duration) {
      let G = g + C.duration;
      return s[1] !== null && (G = Math.min(G, s[1])), { ...o, layout: C.layout, item: C.item, index: m, count: l.length, start: g, end: G };
    }
    u -= C.duration, g += C.duration;
  }
  return null;
}
function En(n, t, e) {
  for (const [i, s] of $n(n, e)) {
    const r = xn(n, t, e, i, s);
    if (r) return r;
  }
  return null;
}
function Mn(n, t, e) {
  const i = e?.end != null ? [e.end] : [];
  for (const s of n.entries)
    for (const [r, o] of s.windows)
      r !== null && r > t && i.push(r), o !== null && o > t && i.push(o);
  return i.length ? Math.min(...i) : null;
}
const An = "evac-player-content-v1", Tn = "content/theme/", Pn = /url\("([^"]+)"\)/g;
async function mt(n, t) {
  const e = await caches.open(An).catch(() => null), i = await e?.match(n).catch(() => {
  });
  if (i) return i;
  const s = new AbortController(), r = setTimeout(() => s.abort(), 1e4);
  try {
    const o = await fetch(n, {
      headers: { Authorization: `Screen ${t}` },
      credentials: "omit",
      signal: s.signal
    });
    if (o.ok)
      return await e?.put(n, o.clone()), o;
  } catch {
  } finally {
    clearTimeout(r);
  }
  return null;
}
async function Nn(n, t) {
  try {
    const e = await E(n, Tn, { token: t });
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
function In(n) {
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
const gt = [];
async function yt(n, t, e = document.documentElement) {
  const i = document.fonts;
  await Promise.all(In(n.fonts_css).map(async (s) => {
    const r = await mt(s.url, t);
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
  })), gt.splice(0).forEach((s) => URL.revokeObjectURL(s));
  for (const [s, r] of Object.entries(n.variables)) {
    let o = r;
    for (const a of r.matchAll(Pn)) {
      const c = await mt(a[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        gt.push(l), o = o.replace(a[1], l);
      }
    }
    e.style.setProperty(s, o);
  }
  e.dataset.theme = n.key || "default";
}
function Dn(n = document) {
  const t = n.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, i = new URLSearchParams(n.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: i.get("mode") === "obs" ? "obs" : "screen"
  };
}
function M(n, t, e = {}) {
  let i = n.strings[t] ?? t;
  for (const [s, r] of Object.entries(e)) i = i.replace(`{${s}}`, String(r));
  return i;
}
function zn(n, t = location) {
  return n.ws ? n.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const B = [], F = [], On = Date.now(), Rn = 300;
let I = [], nt = null;
function S(n, t) {
  F.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n.toUpperCase()} ${t}`.slice(0, 500)), F.length > Rn && F.shift();
}
function _n() {
  return [...F];
}
function v(n) {
  B.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${n}`.slice(0, 300)), B.length > 10 && B.shift(), S("error", n);
  const t = Date.now();
  I = I.filter((e) => t - e < 6e4), I.push(t), I.length >= 50 && nt && (I = [], nt());
}
function Ln(n) {
  nt = n;
}
function Bn(n = window) {
  n.addEventListener("error", (t) => v(t.message || "error")), n.addEventListener("unhandledrejection", (t) => v(String(t.reason)));
  for (const t of ["warn", "info"]) {
    const e = console[t].bind(console);
    console[t] = (...i) => {
      S(t, i.map(String).join(" ")), e(...i);
    };
  }
}
function vt(n) {
  const t = window.innerWidth, e = window.innerHeight, i = performance.memory;
  return {
    version: n.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - On) / 1e3),
    slide: n.slide,
    errors: [...B],
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
const Ft = "evac.player.reloads", H = "evac.player.alive", Fn = 3, Wn = 10 * 6e4;
function Wt(n) {
  try {
    return localStorage.getItem(n);
  } catch {
    return null;
  }
}
function U(n, t) {
  try {
    t === null ? localStorage.removeItem(n) : localStorage.setItem(n, t);
  } catch {
  }
}
function jn(n = Date.now()) {
  try {
    return JSON.parse(Wt(Ft) ?? "[]").filter((t) => n - t < Wn);
  } catch {
    return [];
  }
}
function W(n, t = {}) {
  const e = Date.now(), i = jn(e);
  return !t.force && i.length >= Fn ? (v(`reload (${n}) skipped: ${i.length} reloads in the last 10 minutes`), !1) : (U(Ft, JSON.stringify([...i, e])), S("info", `reload: ${n}`), jt(), (t.win ?? location).reload(), !0);
}
function Hn(n = Date.now()) {
  const t = Wt(H);
  if (U(H, String(n)), !t || t === "clean") return "";
  const e = Number(t);
  return Number.isFinite(e) ? `restarted after an unclean stop (last sign of life ${new Date(e).toISOString()})` : "";
}
function qn(n = Date.now()) {
  U(H, String(n));
}
function jt() {
  U(H, "clean");
}
function Un(n = window) {
  n.addEventListener("pagehide", () => jt());
}
function Gn() {
  const n = performance.memory;
  return !!n && n.jsHeapSizeLimit > 0 && n.usedJSHeapSize / n.jsHeapSizeLimit > 0.85;
}
function Ht() {
  return typeof navigator < "u" && !!navigator.mediaDevices?.getDisplayMedia;
}
function Jn(n, t, e) {
  return new Promise((i, s) => {
    const r = setTimeout(() => s(new Error(`${e} timed out`)), t);
    n.then((o) => {
      clearTimeout(r), i(o);
    }, (o) => {
      clearTimeout(r), s(o);
    });
  });
}
async function Vn(n = 1e4) {
  return Jn(Yn(), n, "screen capture");
}
async function Yn() {
  if (!Ht()) throw new Error("screen capture is not available in this browser");
  const n = document.createElement("div");
  n.className = "evac-capture-dot", document.body.appendChild(n);
  let t = 0;
  const e = setInterval(() => n.classList.toggle("on", t++ % 2 === 0), 16);
  try {
    return await Kn();
  } finally {
    clearInterval(e), n.remove();
  }
}
async function Kn() {
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
async function K(n, t, e, i) {
  const s = typeof Blob < "u" && i instanceof Blob;
  await fetch(`${n}upload/${e}/`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Screen ${t}`, "Content-Type": s ? i.type : "application/json" },
    body: s ? i : JSON.stringify(i)
  });
}
async function Xn() {
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
function wt(n, t) {
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
function bt(n, t, e) {
  return !t || !e || t === e ? !1 : t < e ? n >= t && n < e : n >= t || n < e;
}
function Zn(n, t) {
  return bt(t, n.sleep_from, n.sleep_until) ? "sleeping" : bt(t, n.dim_from, n.dim_until) ? "dimmed" : "on";
}
function Qn(n) {
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
function ti(n, t) {
  const e = Qn(t);
  n.classList.add("evac-root"), n.style.width = e.width, n.style.height = e.height, n.style.transform = e.transform, n.style.setProperty("--evac-overscan", e.overscan);
}
function ei(n, t, e = document) {
  let i = e.getElementById("evac-dim");
  if (n === "on") {
    i?.remove();
    return;
  }
  i || (i = e.createElement("div"), i.id = "evac-dim", i.setAttribute("aria-hidden", "true"), e.body.appendChild(i));
  const s = n === "sleeping" ? 0 : Math.max(10, Math.min(90, t.dim_level ?? 40));
  i.style.opacity = String(1 - s / 100), i.dataset.state = n;
}
const it = "evac.player.token", lt = "evac.player.config";
function ni() {
  try {
    return localStorage.getItem(it);
  } catch {
    return null;
  }
}
function St(n) {
  try {
    n ? localStorage.setItem(it, n) : (localStorage.removeItem(it), localStorage.removeItem(lt));
  } catch {
  }
}
function ii() {
  try {
    const n = localStorage.getItem(lt);
    return n ? JSON.parse(n) : null;
  } catch {
    return null;
  }
}
function kt(n) {
  try {
    localStorage.setItem(lt, JSON.stringify(n));
  } catch {
  }
}
const Ct = 3e3;
function O(n) {
  document.documentElement.dataset.boot = n;
}
const $t = 6e4, si = 36e5, ri = 3e5, xt = 15e3;
class oi {
  constructor(t, e) {
    this.env = t, this.root = e, this.clock = new Vt(), this.speaker = new un(), this.widgetData = new Ge(pn()), this.dataRefresher = null, this.overlays = new dn(this.speaker), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.program = null, this.shown = "", this.timer = null, this.refresher = null, this.housekeeping = null, this.displayState = "on", this.recovered = "", this.lastTick = Date.now(), this.reloadAtNextSlide = "", this.lastDailyReload = "", this.display = new Ze(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    O("boot"), this.recovered = Hn(), S("info", `player ${this.env.version} started (${navigator.userAgent})`), this.recovered && S("warn", this.recovered);
    const t = ni();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: M(this.env, "pair_title"),
      step1: M(this.env, "pair_step1"),
      step2: M(this.env, "pair_step2"),
      waiting: M(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await Gt(this.env.api, vt({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (s) {
      v(String(s)), this.display.message(M(this.env, "no_server"), M(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const i = async () => {
      try {
        const s = await Jt(this.env.api, e);
        if (s.status === "paired")
          return St(s.token), this.play(s.token);
        if (s.status !== "pending") return this.pair();
      } catch (s) {
        v(String(s));
      }
      setTimeout(() => {
        i();
      }, Ct);
    };
    setTimeout(() => {
      i();
    }, Ct);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = ii();
    O(e ? "play: cached config" : "play: no cached config"), e && (this.config = e, this.bundle = Q(), this.program = tt(), this.applySettings(), this.bundle && yt({ ...this.bundle.theme, fonts_css: this.bundle.fonts_css }, t).catch((i) => v(String(i))), this.show(), O("play: shown from cache"));
    try {
      const i = Date.now();
      this.config = await ht(this.env.api, t), this.clock.add(i, Date.now(), this.config.server_time), this.lastSync = Date.now(), kt(this.config);
    } catch (i) {
      if (i instanceof w) return this.unpair();
      v(String(i)), this.config = e;
    }
    this.applySettings(), this.bundle = this.bundle ?? Q(), this.program = this.program ?? tt(), await this.loadContent(t), await this.loadProgram(t), this.show(), O("play: online"), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, si), this.loadWidgetData(t), this.dataRefresher = setInterval(() => {
      this.loadWidgetData(t);
    }, ri), this.housekeeping = setInterval(() => this.tick(), xt), this.conn = new Xt({
      api: this.env.api,
      ws: zn(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => vt({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline",
        displayState: this.displayState,
        capture: Ht(),
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
          this.config = await ht(this.env.api, e), kt(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), this.applySettings();
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
      case "data.changed":
        await this.loadWidgetData(e);
        break;
      case "reload":
        W("requested by staff", { force: !0 });
        break;
      case "clear_cache":
        await Xn(), W("cache cleared by staff", { force: !0 });
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
          await K(this.env.api, e, "screenshot", await Vn());
        } catch (i) {
          v(`screenshot: ${String(i)}`), await K(this.env.api, e, "screenshot", { error: String(i).slice(0, 280) }).catch(() => {
          });
        }
        break;
      case "logs":
        await K(this.env.api, e, "logs", { lines: _n() }).catch((i) => v(String(i)));
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await Qe(this.env.api, t) ?? this.bundle;
    } catch (i) {
      if (i instanceof w) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await Nn(this.env.api, t);
    e && await yt(e, t).catch((i) => v(String(i))), this.bundle && nn(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await sn(this.env.api, t);
    } catch (i) {
      i instanceof w && this.unpair();
    }
    const e = [...this.program?.entries ?? [], ...this.program?.overlays ?? []].map((i) => i.speech).filter((i) => !!i);
    e.length && fn(e);
  }
  /** Custom widget rows: "data" elements redraw themselves when the store changes. */
  async loadWidgetData(t) {
    try {
      await mn(this.env.api, t, this.widgetData);
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
      this.slide = "error", this.display.message(M(this.env, "no_server"), M(this.env, "retrying"));
      return;
    }
    const e = this.clock.now();
    let i = null, s, r = "idle", o = null;
    if (this.program && this.bundle) {
      if (o = En(this.program, this.vars(), e), o?.message)
        i = this.program.messages?.[o.message] ?? null, r = `${o.entry}|message`, this.slide = `${o.entry} message`;
      else if (o?.layout) {
        const u = this.bundle.layouts.find((g) => g.id === o?.layout);
        u && (i = u.data, s = u.variables, r = `${o.entry}|${u.id}|${u.version}|${o.count > 1 ? o.start : ""}`, this.slide = `${u.key} v${u.version} (${o.entry} ${o.index + 1}/${o.count})`);
      }
      const h = [Mn(this.program, e, o), an(this.program.overlays, e)].filter((u) => u !== null), d = Math.max(5, Math.min($t, (h.length ? Math.min(...h) : e + $t) - e));
      this.timer = setTimeout(() => this.show(), d);
    } else {
      const h = en(this.bundle);
      h && (i = h.data, s = h.variables, r = `default|${h.id}|${h.version}`, this.slide = `${h.key} v${h.version}`);
    }
    const a = { enabled: t.display?.audio !== !1, volume: t.display?.volume ?? 100 }, c = !!o && (o.entry.startsWith("announcement:") || o.entry.startsWith("evacuation"));
    this.overlays.update(this.program?.overlays, e, { hidden: c, audio: a });
    const l = o ? this.program?.entries.find((h) => h.id === o?.entry) : void 0;
    if (l?.speech && a.enabled && this.speaker.say(`${l.id}@${o?.start ?? 0}`, l.speech, {
      volume: a.volume,
      delayMs: Bt
    }), r !== this.shown && !(this.reloadAtNextSlide && this.shown && W(this.reloadAtNextSlide))) {
      this.reloadAtNextSlide = "", this.shown = r, S("info", `showing ${this.slide}`);
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
          nonce: le(),
          data: this.widgetData,
          onError: (h, d) => v(`${h}: ${String(d)}`),
          onLog: (h, d) => S("info", `${h}: ${d}`)
        }, s);
      } catch (h) {
        i && v(`render failed, showing the idle slide: ${String(h)}`), this.slide = "idle", this.display.idle(t);
      }
      this.overlays.attach(this.root);
    }
  }
  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  applySettings() {
    const t = this.config?.display ?? {};
    ti(this.root, t), this.updateDisplayState();
  }
  updateDisplayState() {
    const t = this.config?.display ?? {}, e = Zn(t, wt(this.clock.now(), this.config?.event.timezone));
    e !== this.displayState && S("info", `display ${e}`), this.displayState = e, ei(e, t);
  }
  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  tick() {
    const t = Date.now(), e = t - this.lastTick > xt * 3;
    this.lastTick = t, qn(t), this.updateDisplayState(), e && (S("warn", "timers were stalled; resynchronising"), this.shown = "", this.show());
    const i = this.config?.display?.daily_reload, s = wt(this.clock.now(), this.config?.event.timezone);
    i && s === i && this.lastDailyReload !== s && performance.now() > 36e5 && (this.lastDailyReload = s, this.reloadAtNextSlide = "daily reload"), Gn() && !this.reloadAtNextSlide && (this.reloadAtNextSlide = "memory pressure");
  }
  unpair() {
    this.housekeeping && clearInterval(this.housekeeping), this.housekeeping = null, this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.dataRefresher && clearInterval(this.dataRefresher), this.timer = this.refresher = this.dataRefresher = null, gn(), this.widgetData.set({}), rn(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, St(null), tn(), this.pair();
  }
}
function ai() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((n) => v(String(n)));
}
if (typeof document < "u" && document.getElementById("player")) {
  Bn(), Un(), Ln(() => W("50 errors within a minute")), ai();
  const n = Dn();
  new oi(n, document.getElementById("player")).boot();
}
export {
  oi as Player
};
