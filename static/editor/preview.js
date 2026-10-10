// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC slide preview, built from frontend/src with `npm run build` - do not edit.
var nt = Object.defineProperty;
var st = (s, t, e) => t in s ? nt(s, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : s[t] = e;
var E = (s, t, e) => st(s, typeof t != "symbol" ? t + "" : t, e);
const it = `(() => {
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
function T(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function rt(s, t, e, n = "") {
  const i = T(t), r = e ? ` ${e}` : "", o = [
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
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${T(o)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${n}</style><style nonce="${i}">${a}</style><script nonce="${i}">${it}<\/script></head><body>${String(s.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function ot(s) {
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
function at(s = document) {
  const t = s.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
function ct(s, t, e) {
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
function lt(s) {
  const t = [];
  let e = "", n = "";
  for (const i of s)
    n ? (i === n && (n = ""), e += i) : i === '"' || i === "'" ? (n = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function dt(s) {
  if (!s) return "";
  const t = s.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function W(s, t, e) {
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
function ht(s, t, e) {
  const [n, ...i] = t.split(":"), r = dt(i.join(":")), o = () => s instanceof Date ? s : new Date(String(s));
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
      return isNaN(o().getTime()) ? "" : W(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : W(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(s) ? s.map(g).join(r || ", ") : g(s);
    default:
      return s;
  }
}
function k(s, t, e = {}) {
  const [n, ...i] = lt(s);
  let r = ct(t, n, e);
  for (const o of i) r = ht(r, o, e);
  return r;
}
function ut(s) {
  return Array.isArray(s) ? s.length > 0 : !(s == null || s === !1 || s === "" || s === 0);
}
function B(s, t, e = {}) {
  const n = s.trim();
  if (!n) return !0;
  if (n.startsWith("not ")) return !B(n.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(n);
  if (i) {
    const r = g(k(i[1], t, e)), o = g(k(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return ut(k(n.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const ft = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function V(s, t, e = {}) {
  if (!s || !s.includes("{{") && !s.includes("{%")) return s ?? "";
  const n = s.split(ft);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < n.length; ) {
      const c = n[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const f = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(f)) return [a, f];
        if (f === "if") {
          const h = B(l[2], t, e), [u, w] = r(["else", "endif"]);
          let m = "";
          w === "else" && (m = r(["endif"])[0]), a += h ? u : m;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += g(k(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
const M = "#00843d", pt = "#f9a800", mt = ["ahead", "ahead_right", "right", "back_right", "back", "back_left", "left", "ahead_left"], gt = {
  E001: "Emergency exit (left)",
  E002: "Emergency exit (right)",
  E003: "First aid",
  E007: "Assembly point",
  W001: "General warning",
  arrow: "Direction"
};
function wt(s) {
  const t = mt.indexOf(s);
  return t < 0 ? 0 : t * 45;
}
const vt = `<circle cx="57" cy="20" r="8"/>
<path d="M52 32 L44 56 L30 62 M48 44 L64 50 L74 42 M44 56 L56 70 L52 86 M44 56 L34 74 L20 78" fill="none"
 stroke="currentColor" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M50 30 L58 32 L62 36 L50 58 L42 54 Z"/>`;
function $(s, t, e, n) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${t}"
 color="${n}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${e}"/>${s}</svg>`;
}
function yt(s, t = "ahead") {
  const e = gt[s] ?? "Safety sign";
  switch (s) {
    case "E001":
    case "E002": {
      const n = `<path d="M66 10 H92 V90 H66 Z" fill="none" stroke="currentColor" stroke-width="5"/>
<path d="M72 18 H86 V82 H72 Z" opacity=".35"/>`, i = `<g transform="translate(0 8) scale(.84)">${vt}</g>`, r = `${n}${i}`;
      return $(
        s === "E001" ? `<g transform="translate(100 0) scale(-1 1)">${r}</g>` : r,
        e,
        M,
        "#fff"
      );
    }
    case "E003":
      return $('<path d="M40 18 H60 V40 H82 V60 H60 V82 H40 V60 H18 V40 H40 Z"/>', e, M, "#fff");
    case "E007": {
      const n = [30, 50, 70].map((r) => `<circle cx="${r}" cy="44" r="6"/><path d="M${r - 6} 74 V56 a6 6 0 0 1 12 0 V74 Z"/>`).join(""), i = (r) => `<g transform="rotate(${r} 50 50)"><path d="M50 24 L58 14 H53 V5 H47 V14 H42 Z"/></g>`;
      return $(`${n}${[45, 135, 225, 315].map((r) => i(r)).join("")}`, e, M, "#fff");
    }
    case "W001":
      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${e}">
<path d="M50 6 L96 90 H4 Z" fill="${pt}" stroke="#000" stroke-width="6" stroke-linejoin="round"/>
<rect x="45" y="32" width="10" height="34" rx="3"/><circle cx="50" cy="77" r="6"/></svg>`;
    default: {
      const n = wt(t);
      return $(
        `<g transform="rotate(${n} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
        `${e}: ${String(t).replace("_", " ")}`,
        M,
        "#fff"
      );
    }
  }
}
var b = /* @__PURE__ */ ((s) => (s[s.Border = -1] = "Border", s[s.Data = 0] = "Data", s[s.Function = 1] = "Function", s[s.Position = 2] = "Position", s[s.Timing = 3] = "Timing", s[s.Alignment = 4] = "Alignment", s))(b || {});
const bt = [0, 1], q = [1, 0], U = [2, 3], G = [3, 2], Ct = {
  L: bt,
  M: q,
  Q: U,
  H: G
}, Et = /^\d*$/, xt = /^[A-Z0-9 $%*+./:-]*$/, P = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", R = 1, D = 40, _ = 3, Mt = 3, S = 40, $t = 10, Z = [
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
class St {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, n, i) {
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
    if (this.version = t, this.ecc = e, t < R || t > D)
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
      this.setFunctionModule(6, n, n % 2 === 0, b.Timing), this.setFunctionModule(n, 6, n % 2 === 0, b.Timing);
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
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, b.Position);
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
          b.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, n, i = b.Function) {
    this.modules[e][t] = n, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, n = this.ecc;
    if (t.length !== z(e, n))
      throw new RangeError("Invalid argument");
    const i = Y[n[0]][e], r = Z[n[0]][e], o = Math.floor(F(e) / 8), a = i - o % i, c = Math.floor(o / i), l = [], f = Bt(r);
    for (let u = 0, w = 0; u < i; u++) {
      const m = t.slice(w, w + c - r + (u < a ? 0 : 1));
      w += m.length;
      const et = Rt(m, f);
      u < a && m.push(0), l.push(m.concat(et));
    }
    const h = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((w, m) => {
        (u !== c - r || m >= a) && h.push(w[u]);
      });
    return h;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(F(this.version) / 8))
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
        this.modules[r][l] === o ? (a++, a === 5 ? t += _ : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * S), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * S;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += _ : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * S), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * S;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += Mt);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const n = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - n * 10) / n) - 1;
    return t += i * $t, t;
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
function y(s, t, e) {
  if (t < 0 || t > 31 || s >>> t)
    throw new RangeError("Value out of range");
  for (let n = t - 1; n >= 0; n--)
    e.push(s >>> n & 1);
}
function v(s, t) {
  return (s >>> t & 1) !== 0;
}
class O {
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
const At = [1, 10, 12, 14], kt = [2, 9, 11, 13], zt = [4, 8, 16, 16];
function X(s, t) {
  return s[Math.floor((t + 7) / 17) + 1];
}
function J(s) {
  const t = [];
  for (const e of s)
    y(e, 8, t);
  return new O(zt, s.length, t);
}
function Nt(s) {
  if (!K(s))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < s.length; ) {
    const n = Math.min(s.length - e, 3);
    y(Number.parseInt(s.substring(e, e + n), 10), n * 3 + 1, t), e += n;
  }
  return new O(At, s.length, t);
}
function Pt(s) {
  if (!Q(s))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= s.length; e += 2) {
    let n = P.indexOf(s.charAt(e)) * 45;
    n += P.indexOf(s.charAt(e + 1)), y(n, 11, t);
  }
  return e < s.length && y(P.indexOf(s.charAt(e)), 6, t), new O(kt, s.length, t);
}
function Lt(s) {
  return s === "" ? [] : K(s) ? [Nt(s)] : Q(s) ? [Pt(s)] : [J(It(s))];
}
function K(s) {
  return Et.test(s);
}
function Q(s) {
  return xt.test(s);
}
function Ft(s, t) {
  let e = 0;
  for (const n of s) {
    const i = X(n.mode, t);
    if (n.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + n.bitData.length;
  }
  return e;
}
function It(s) {
  s = encodeURI(s);
  const t = [];
  for (let e = 0; e < s.length; e++)
    s.charAt(e) !== "%" ? t.push(s.charCodeAt(e)) : (t.push(Number.parseInt(s.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function F(s) {
  if (s < R || s > D)
    throw new RangeError("Version number out of range");
  let t = (16 * s + 128) * s + 64;
  if (s >= 2) {
    const e = Math.floor(s / 7) + 2;
    t -= (25 * e - 10) * e - 55, s >= 7 && (t -= 36);
  }
  return t;
}
function z(s, t) {
  return Math.floor(F(s) / 8) - Z[t[0]][s] * Y[t[0]][s];
}
function Bt(s) {
  if (s < 1 || s > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let n = 0; n < s - 1; n++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let n = 0; n < s; n++) {
    for (let i = 0; i < t.length; i++)
      t[i] = I(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = I(e, 2);
  }
  return t;
}
function Rt(s, t) {
  const e = t.map((n) => 0);
  for (const n of s) {
    const i = n ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= I(r, i));
  }
  return e;
}
function I(s, t) {
  if (s >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let n = 7; n >= 0; n--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> n & 1) * s;
  return e;
}
function Dt(s, t, e = 1, n = 40, i = -1, r = !0) {
  if (!(R <= e && e <= n && n <= D) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const h = z(o, t) * 8, u = Ft(s, o);
    if (u <= h) {
      a = u;
      break;
    }
    if (o >= n)
      throw new RangeError("Data too long");
  }
  for (const h of [q, U, G])
    r && a <= z(o, h) * 8 && (t = h);
  const c = [];
  for (const h of s) {
    y(h.mode[0], 4, c), y(h.numChars, X(h.mode, o), c);
    for (const u of h.getData())
      c.push(u);
  }
  const l = z(o, t) * 8;
  y(0, Math.min(4, l - c.length), c), y(0, (8 - c.length % 8) % 8, c);
  for (let h = 236; c.length < l; h ^= 253)
    y(h, 8, c);
  const f = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((h, u) => f[u >>> 3] |= h << 7 - (u & 7)), new St(o, t, f, i);
}
function Ot(s, t) {
  const {
    ecc: e = "L",
    boostEcc: n = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof s == "string" ? Lt(s) : Array.isArray(s) ? [J(s)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof s}`);
  const l = Dt(
    c,
    Ct[e],
    i,
    r,
    o,
    n
  ), f = Ht({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (f.data = f.data.map((h) => h.map((u) => !u))), t?.onEncoded?.(f), f;
}
function Ht(s, t = 1) {
  if (!t)
    return s;
  const { size: e } = s, n = e + t * 2;
  s.size = n, s.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    s.data.unshift(Array.from({ length: n }, (o) => !1)), s.data.push(Array.from({ length: n }, (o) => !1));
  const i = b.Border;
  s.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    s.types.unshift(Array.from({ length: n }, (o) => i)), s.types.push(Array.from({ length: n }, (o) => i));
  return s;
}
const L = "http://www.w3.org/2000/svg";
function Tt(s, t = document) {
  const { data: e, size: n } = Ot(s, { ecc: "M", border: 2 }), i = t.createElementNS(L, "svg");
  i.setAttribute("viewBox", `0 0 ${n} ${n}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(L, "rect");
  r.setAttribute("width", String(n)), r.setAttribute("height", String(n)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((f, h) => {
    f && (o += `M${h} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(L, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), i.appendChild(a), i;
}
class p extends HTMLElement {
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
    return V(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function Wt(s, t) {
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
class _t extends p {
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
      const i = () => Wt(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class jt extends p {
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
function tt(s, t, e) {
  const n = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (s.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = s.urls[r], n.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = s.urls.original, i.alt = e || s.alt || "", i.decoding = "async", i.style.objectFit = t, n.appendChild(i), n;
}
class Vt extends p {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(tt(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class qt extends p {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), n = t.map((o) => {
      const a = tt(o, e, "");
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
class Ut extends p {
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
class Gt extends p {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Zt extends p {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Yt extends p {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = Tt(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Xt = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Jt extends p {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Xt[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = n.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class Kt extends p {
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
function Qt(s, t) {
  const e = Math.max(0, Math.floor(s / 1e3)), n = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${n} ${n === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || n === 0 ? `${a(i + n * 24)}:${a(r)}:${a(o)}` : `${n}d ${a(i)}:${a(r)}:${a(o)}`;
}
class te extends p {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), n = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : Qt(i, String(this.props.format ?? "auto"));
    };
    n(), this.replaceChildren(e), this.every(250, n);
  }
}
class ee extends p {
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
    n.setAttribute("sandbox", "allow-scripts"), n.setAttribute("referrerpolicy", "no-referrer"), n.setAttribute("allow", "autoplay"), n.setAttribute("title", this.el.name || "Code"), n.setAttribute("tabindex", "-1"), n.className = "evac-code-frame", n.srcdoc = rt(e, t, location.origin, ot(this)), this.frame = n, window.addEventListener("message", this.onMessage), this.replaceChildren(n), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
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
const H = {
  text: _t,
  richtext: jt,
  image: Vt,
  slideshow: qt,
  video: Ut,
  audio: Gt,
  shape: Zt,
  qr: Yt,
  clock: Jt,
  countdown: te,
  date: Kt,
  code: ee
};
function ne(s = customElements) {
  for (const [t, e] of Object.entries(H))
    s.get(`evac-${t}`) || s.define(`evac-${t}`, e);
}
class se extends p {
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
    this.hidden = !1, this.innerHTML = yt(t, e);
  }
}
H.pictogram = se;
class ie {
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
function d(s, t = "", e) {
  const n = document.createElement(s);
  return t && (n.className = t), e != null && e !== "" && (n.textContent = String(e)), n;
}
function C(s) {
  if (typeof s == "number") return Number.isFinite(s) ? s : null;
  if (typeof s == "string" && s.trim() !== "") {
    const t = Number(s.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function A(s, t) {
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
const re = ["time", "title", "subtitle", "label", "value"];
class oe extends p {
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
    const n = d("div", `evac-data evac-data-${e.visual}`), i = String(this.props.title || e.options.heading || "");
    i && n.appendChild(d("div", "evac-data-heading", i));
    const r = d("div", "evac-data-body");
    n.appendChild(r), (j[e.visual] ?? j.list)(r, e, this), this.ctx.editing && e.stale && n.appendChild(d("span", "evac-data-stale", "stale")), this.replaceChildren(n);
  }
  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(t, e) {
    return V(
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
function x(s, t) {
  return t.rows.length ? !1 : (s.appendChild(d("div", "evac-data-empty", "–")), !0);
}
const j = {
  text(s, t, e) {
    s.appendChild(d("div", "evac-data-text", e.tmpl(
      String(t.options.template || "{{ data.first.title }}"),
      t
    )));
  },
  list(s, t, e) {
    if (x(s, t)) return;
    const n = d("ul", "evac-data-list");
    for (const i of t.rows) {
      const r = d("li");
      i.time && r.appendChild(d("span", "evac-data-time", A(i.time, e.tz)));
      const o = d("span", "evac-data-main");
      o.appendChild(d("span", "evac-data-title", i.title ?? i.label ?? i.value)), i.subtitle && o.appendChild(d("span", "evac-data-sub", i.subtitle)), r.appendChild(o), i.value !== void 0 && i.value !== null && i.title && r.appendChild(d("span", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  table(s, t, e) {
    if (x(s, t)) return;
    const n = re.filter((o) => t.rows.some((a) => a[o] !== void 0 && a[o] !== null && a[o] !== "")), i = d("table", "evac-data-table"), r = d("tbody");
    for (const o of t.rows) {
      const a = d("tr");
      for (const c of n) a.appendChild(d("td", `evac-data-${c}`, c === "time" ? A(o[c], e.tz) : o[c]));
      r.appendChild(a);
    }
    i.appendChild(r), s.appendChild(i);
  },
  cards(s, t, e) {
    if (x(s, t)) return;
    const n = d("div", "evac-data-cards");
    for (const i of t.rows) {
      const r = d("div", "evac-data-card");
      if (typeof i.image == "string" && i.image.startsWith("/")) {
        const o = d("img");
        o.src = i.image, o.alt = "", r.appendChild(o);
      }
      i.time && r.appendChild(d("div", "evac-data-time", A(i.time, e.tz))), r.appendChild(d("div", "evac-data-title", i.title ?? i.label)), i.subtitle && r.appendChild(d("div", "evac-data-sub", i.subtitle)), i.value !== void 0 && i.value !== null && r.appendChild(d("div", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  counter(s, t) {
    const e = t.rows[0] ?? {}, n = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, i = C(n), r = d("div", "evac-data-number", i === null ? n : i.toLocaleString("en-GB"));
    t.options.unit && r.appendChild(d("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(r), (e.label || e.title) && s.appendChild(d("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(s, t) {
    const e = t.rows[0] ?? {}, n = C(e.value) ?? 0, i = C(t.options.minimum) ?? 0, r = C(t.options.maximum) ?? 100, o = Math.max(0, Math.min(1, (n - i) / (r - i || 1))), a = "http://www.w3.org/2000/svg", c = document.createElementNS(a, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${n}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (h, u) => {
      const w = Math.PI * (1 - h), m = document.createElementNS(a, "path");
      m.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(w)} ${100 - 80 * Math.sin(w)}`), m.setAttribute("class", u), c.appendChild(m);
    };
    l(1, "evac-gauge-track"), o > 0 && l(o, "evac-gauge-fill"), s.appendChild(c);
    const f = d("div", "evac-data-number", n.toLocaleString("en-GB"));
    t.options.unit && f.appendChild(d("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(f), (e.label || e.title) && s.appendChild(d("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(s, t, e) {
    if (x(s, t)) return;
    const n = t.rows.map((o) => [o.time ? A(o.time, e.tz) : "", o.title ?? o.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), i = d("div", "evac-marquee-box"), r = d("span", "evac-marquee", n);
    r.style.animationDuration = `${Math.max(10, n.length / 5)}s`, i.appendChild(r), s.appendChild(i);
  },
  bars(s, t) {
    if (x(s, t)) return;
    const e = t.rows.map((r) => C(r.value) ?? 0), n = C(t.options.maximum) || Math.max(...e, 1), i = d("div", "evac-data-bars");
    t.rows.forEach((r, o) => {
      const a = d("div", "evac-bar");
      a.appendChild(d("span", "evac-bar-label", r.label ?? r.title));
      const c = d("span", "evac-bar-track"), l = d("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[o] / n * 100))}%`, c.appendChild(l), a.appendChild(c), a.appendChild(d("span", "evac-bar-value", `${e[o].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), i.appendChild(a);
    }), s.appendChild(i);
  }
};
H.data = oe;
function N(s) {
  return s ? s.startsWith("token:") ? `var(--evac-color-${s.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(s) || s === "transparent" ? s : "" : "";
}
function ae(s, t) {
  return s ? s === "token:heading" ? "var(--evac-font-heading)" : s === "token:body" ? "var(--evac-font-body)" : t.fonts[s] ?? "" : "";
}
function ce(s, t, e) {
  const n = s.style;
  if (!t) return;
  const i = (r, o) => {
    o && n.setProperty(r, o);
  };
  i("color", N(t.color)), i("background", N(t.background)), t.borderWidth && n.setProperty("border", `${t.borderWidth / 10}cqh solid ${N(t.borderColor) || "currentColor"}`), t.radius !== void 0 && n.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && n.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && n.setProperty("opacity", String(t.opacity)), i("font-family", ae(t.fontFamily, e)), t.fontSize && n.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && n.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && n.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && n.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && n.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && n.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && n.setProperty("box-shadow", "var(--evac-shadow)");
}
function le(s, t) {
  const e = t.frame;
  s.style.left = `${e.x}%`, s.style.top = `${e.y}%`, s.style.width = `${e.w}%`, s.style.height = `${e.h}%`, s.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function de(s, t) {
  const e = !s.visible_if || B(s.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (s.hidden && !t.editing || !e && !t.editing) return null;
  const n = document.createElement("div");
  n.className = `evac-el evac-el-${s.type}`, n.dataset.id = s.id, (!e || s.hidden) && n.classList.add("evac-dimmed"), le(n, s), ce(n, s.style, t);
  const i = s.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (n.classList.add(`evac-enter-${i.enter}`), n.style.animationDuration = `${i.duration ?? 600}ms`, n.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${s.type}`;
  if (!customElements.get(r))
    return t.onError?.(s.id, new Error(`unknown element type ${s.type}`)), t.editing ? n : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", n.appendChild(o), o.configure(s, t), n;
}
function he(s, t, e) {
  ne();
  const n = document.createElement("div");
  n.className = "evac-stage";
  const i = t.background;
  if (i?.color && (n.style.background = N(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    n.style.backgroundImage = `url("${l}")`, n.style.backgroundSize = i.fit ?? "cover", n.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = de(c, e);
    l && (r.set(c.id, l), n.appendChild(l));
  }
  s.replaceChildren(n);
  const o = () => {
    const c = s.clientWidth, l = s.clientHeight;
    if (!c || !l) return;
    const f = Math.min(c / t.width, l / t.height);
    n.style.width = `${Math.round(t.width * f)}px`, n.style.height = `${Math.round(t.height * f)}px`;
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
function ue(s, t) {
  const e = Date.now();
  s.replaceChildren(), s.style.aspectRatio = `${t.layout.width} / ${t.layout.height}`;
  for (const [n, i] of Object.entries(t.themeVariables ?? {})) s.style.setProperty(n, i);
  s.classList.add("evac-preview-host"), he(s, t.layout, {
    vars: t.vars,
    now: () => t.at + (Date.now() - e),
    timezone: t.timezone,
    assets: t.assets,
    fonts: t.fonts,
    reducedMotion: !0,
    nonce: at(),
    data: new ie(t.data ?? {})
  });
}
if (typeof document < "u") {
  const s = document.getElementById("preview-config"), t = document.querySelector("[data-preview]");
  s && t && ue(t, JSON.parse(s.textContent || "{}"));
}
export {
  ue as mountPreview
};
