// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC slide preview, built from frontend/src with `npm run build` - do not edit.
var V = Object.defineProperty;
var Y = (s, t, e) => t in s ? V(s, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : s[t] = e;
var v = (s, t, e) => Y(s, typeof t != "symbol" ? t + "" : t, e);
const X = `(() => {
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
function I(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function Z(s, t, e, n = "") {
  const i = I(t), r = e ? ` ${e}` : "", o = [
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
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${I(o)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${n}</style><style nonce="${i}">${a}</style><script nonce="${i}">${X}<\/script></head><body>${String(s.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function J(s) {
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
function K(s = document) {
  const t = s.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
function M(s) {
  return s ? s.startsWith("token:") ? `var(--evac-color-${s.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(s) || s === "transparent" ? s : "" : "";
}
function Q(s, t) {
  return s ? s === "token:heading" ? "var(--evac-font-heading)" : s === "token:body" ? "var(--evac-font-body)" : t.fonts[s] ?? "" : "";
}
function tt(s, t, e) {
  const n = s.style;
  if (!t) return;
  const i = (r, o) => {
    o && n.setProperty(r, o);
  };
  i("color", M(t.color)), i("background", M(t.background)), t.borderWidth && n.setProperty("border", `${t.borderWidth / 10}cqh solid ${M(t.borderColor) || "currentColor"}`), t.radius !== void 0 && n.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && n.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && n.setProperty("opacity", String(t.opacity)), i("font-family", Q(t.fontFamily, e)), t.fontSize && n.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && n.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && n.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && n.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && n.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && n.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && n.setProperty("box-shadow", "var(--evac-shadow)");
}
function et(s, t, e) {
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
function nt(s) {
  const t = [];
  let e = "", n = "";
  for (const i of s)
    n ? (i === n && (n = ""), e += i) : i === '"' || i === "'" ? (n = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function st(s) {
  if (!s) return "";
  const t = s.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function R(s, t, e) {
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
function m(s) {
  return s == null ? "" : Array.isArray(s) ? s.map(m).join(", ") : s instanceof Date ? s.toISOString() : typeof s == "object" ? s.name ?? "" : String(s);
}
function it(s, t, e) {
  const [n, ...i] = t.split(":"), r = st(i.join(":")), o = () => s instanceof Date ? s : new Date(String(s));
  switch (n.trim()) {
    case "upper":
      return m(s).toUpperCase();
    case "lower":
      return m(s).toLowerCase();
    case "title":
      return m(s).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = m(s);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return m(s) === "" ? r : s;
    case "date":
      return isNaN(o().getTime()) ? "" : R(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : R(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(s) ? s.map(m).join(r || ", ") : m(s);
    default:
      return s;
  }
}
function S(s, t, e = {}) {
  const [n, ...i] = nt(s);
  let r = et(t, n, e);
  for (const o of i) r = it(r, o, e);
  return r;
}
function rt(s) {
  return Array.isArray(s) ? s.length > 0 : !(s == null || s === !1 || s === "" || s === 0);
}
function z(s, t, e = {}) {
  const n = s.trim();
  if (!n) return !0;
  if (n.startsWith("not ")) return !z(n.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(n);
  if (i) {
    const r = m(S(i[1], t, e)), o = m(S(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return rt(S(n.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const ot = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function at(s, t, e = {}) {
  if (!s || !s.includes("{{") && !s.includes("{%")) return s ?? "";
  const n = s.split(ot);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < n.length; ) {
      const c = n[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const u = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(u)) return [a, u];
        if (u === "if") {
          const h = z(l[2], t, e), [d, w] = r(["else", "endif"]);
          let p = "";
          w === "else" && (p = r(["endif"])[0]), a += h ? d : p;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += m(S(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
var b = /* @__PURE__ */ ((s) => (s[s.Border = -1] = "Border", s[s.Data = 0] = "Data", s[s.Function = 1] = "Function", s[s.Position = 2] = "Position", s[s.Timing = 3] = "Timing", s[s.Alignment = 4] = "Alignment", s))(b || {});
const ct = [0, 1], B = [1, 0], O = [2, 3], W = [3, 2], lt = {
  L: ct,
  M: B,
  Q: O,
  H: W
}, ht = /^\d*$/, dt = /^[A-Z0-9 $%*+./:-]*$/, x = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", k = 1, N = 40, D = 3, ut = 3, E = 40, ft = 10, L = [
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
], T = [
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
class mt {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, n, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    v(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    v(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    v(this, "modules", []);
    v(this, "types", []);
    if (this.version = t, this.ecc = e, t < k || t > N)
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
      this.setFunctionModule(8, r, g(i, r));
    this.setFunctionModule(8, 7, g(i, 6)), this.setFunctionModule(8, 8, g(i, 7)), this.setFunctionModule(7, 8, g(i, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, g(i, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, g(i, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, g(i, r));
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
      const i = g(e, n), r = this.size - 11 + n % 3, o = Math.floor(n / 3);
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
    if (t.length !== C(e, n))
      throw new RangeError("Invalid argument");
    const i = T[n[0]][e], r = L[n[0]][e], o = Math.floor($(e) / 8), a = i - o % i, c = Math.floor(o / i), l = [], u = St(r);
    for (let d = 0, w = 0; d < i; d++) {
      const p = t.slice(w, w + c - r + (d < a ? 0 : 1));
      w += p.length;
      const G = Ct(p, u);
      d < a && p.push(0), l.push(p.concat(G));
    }
    const h = [];
    for (let d = 0; d < l[0].length; d++)
      l.forEach((w, p) => {
        (d !== c - r || p >= a) && h.push(w[d]);
      });
    return h;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor($(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let n = this.size - 1; n >= 1; n -= 2) {
      n === 6 && (n = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = n - r, c = (n + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][o] && e < t.length * 8 && (this.modules[c][o] = g(t[e >>> 3], 7 - (e & 7)), e++);
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
        this.modules[r][l] === o ? (a++, a === 5 ? t += D : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * E), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * E;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += D : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * E), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * E;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += ut);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const n = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - n * 10) / n) - 1;
    return t += i * ft, t;
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
function g(s, t) {
  return (s >>> t & 1) !== 0;
}
class F {
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
const pt = [1, 10, 12, 14], gt = [2, 9, 11, 13], yt = [4, 8, 16, 16];
function _(s, t) {
  return s[Math.floor((t + 7) / 17) + 1];
}
function j(s) {
  const t = [];
  for (const e of s)
    y(e, 8, t);
  return new F(yt, s.length, t);
}
function wt(s) {
  if (!H(s))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < s.length; ) {
    const n = Math.min(s.length - e, 3);
    y(Number.parseInt(s.substring(e, e + n), 10), n * 3 + 1, t), e += n;
  }
  return new F(pt, s.length, t);
}
function bt(s) {
  if (!q(s))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= s.length; e += 2) {
    let n = x.indexOf(s.charAt(e)) * 45;
    n += x.indexOf(s.charAt(e + 1)), y(n, 11, t);
  }
  return e < s.length && y(x.indexOf(s.charAt(e)), 6, t), new F(gt, s.length, t);
}
function vt(s) {
  return s === "" ? [] : H(s) ? [wt(s)] : q(s) ? [bt(s)] : [j(Mt(s))];
}
function H(s) {
  return ht.test(s);
}
function q(s) {
  return dt.test(s);
}
function Et(s, t) {
  let e = 0;
  for (const n of s) {
    const i = _(n.mode, t);
    if (n.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + n.bitData.length;
  }
  return e;
}
function Mt(s) {
  s = encodeURI(s);
  const t = [];
  for (let e = 0; e < s.length; e++)
    s.charAt(e) !== "%" ? t.push(s.charCodeAt(e)) : (t.push(Number.parseInt(s.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function $(s) {
  if (s < k || s > N)
    throw new RangeError("Version number out of range");
  let t = (16 * s + 128) * s + 64;
  if (s >= 2) {
    const e = Math.floor(s / 7) + 2;
    t -= (25 * e - 10) * e - 55, s >= 7 && (t -= 36);
  }
  return t;
}
function C(s, t) {
  return Math.floor($(s) / 8) - L[t[0]][s] * T[t[0]][s];
}
function St(s) {
  if (s < 1 || s > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let n = 0; n < s - 1; n++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let n = 0; n < s; n++) {
    for (let i = 0; i < t.length; i++)
      t[i] = P(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = P(e, 2);
  }
  return t;
}
function Ct(s, t) {
  const e = t.map((n) => 0);
  for (const n of s) {
    const i = n ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= P(r, i));
  }
  return e;
}
function P(s, t) {
  if (s >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let n = 7; n >= 0; n--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> n & 1) * s;
  return e;
}
function xt(s, t, e = 1, n = 40, i = -1, r = !0) {
  if (!(k <= e && e <= n && n <= N) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const h = C(o, t) * 8, d = Et(s, o);
    if (d <= h) {
      a = d;
      break;
    }
    if (o >= n)
      throw new RangeError("Data too long");
  }
  for (const h of [B, O, W])
    r && a <= C(o, h) * 8 && (t = h);
  const c = [];
  for (const h of s) {
    y(h.mode[0], 4, c), y(h.numChars, _(h.mode, o), c);
    for (const d of h.getData())
      c.push(d);
  }
  const l = C(o, t) * 8;
  y(0, Math.min(4, l - c.length), c), y(0, (8 - c.length % 8) % 8, c);
  for (let h = 236; c.length < l; h ^= 253)
    y(h, 8, c);
  const u = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((h, d) => u[d >>> 3] |= h << 7 - (d & 7)), new mt(o, t, u, i);
}
function At(s, t) {
  const {
    ecc: e = "L",
    boostEcc: n = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof s == "string" ? vt(s) : Array.isArray(s) ? [j(s)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof s}`);
  const l = xt(
    c,
    lt[e],
    i,
    r,
    o,
    n
  ), u = $t({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (u.data = u.data.map((h) => h.map((d) => !d))), t?.onEncoded?.(u), u;
}
function $t(s, t = 1) {
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
const A = "http://www.w3.org/2000/svg";
function Pt(s, t = document) {
  const { data: e, size: n } = At(s, { ecc: "M", border: 2 }), i = t.createElementNS(A, "svg");
  i.setAttribute("viewBox", `0 0 ${n} ${n}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(A, "rect");
  r.setAttribute("width", String(n)), r.setAttribute("height", String(n)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((u, h) => {
    u && (o += `M${h} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(A, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), i.appendChild(a), i;
}
class f extends HTMLElement {
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
    return at(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function zt(s, t) {
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
class kt extends f {
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
      const i = () => zt(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Nt extends f {
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
function U(s, t, e) {
  const n = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (s.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = s.urls[r], n.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = s.urls.original, i.alt = e || s.alt || "", i.decoding = "async", i.style.objectFit = t, n.appendChild(i), n;
}
class Ft extends f {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(U(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class It extends f {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), n = t.map((o) => {
      const a = U(o, e, "");
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
class Rt extends f {
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
class Dt extends f {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Bt extends f {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Ot extends f {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = Pt(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Wt = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Lt extends f {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Wt[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = n.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class Tt extends f {
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
function _t(s, t) {
  const e = Math.max(0, Math.floor(s / 1e3)), n = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${n} ${n === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || n === 0 ? `${a(i + n * 24)}:${a(r)}:${a(o)}` : `${n}d ${a(i)}:${a(r)}:${a(o)}`;
}
class jt extends f {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), n = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : _t(i, String(this.props.format ?? "auto"));
    };
    n(), this.replaceChildren(e), this.every(250, n);
  }
}
class Ht extends f {
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
    n.setAttribute("sandbox", "allow-scripts"), n.setAttribute("referrerpolicy", "no-referrer"), n.setAttribute("allow", "autoplay"), n.setAttribute("title", this.el.name || "Code"), n.setAttribute("tabindex", "-1"), n.className = "evac-code-frame", n.srcdoc = Z(e, t, location.origin, J(this)), this.frame = n, window.addEventListener("message", this.onMessage), this.replaceChildren(n), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
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
const qt = {
  text: kt,
  richtext: Nt,
  image: Ft,
  slideshow: It,
  video: Rt,
  audio: Dt,
  shape: Bt,
  qr: Ot,
  clock: Lt,
  countdown: jt,
  date: Tt,
  code: Ht
};
function Ut(s = customElements) {
  for (const [t, e] of Object.entries(qt))
    s.get(`evac-${t}`) || s.define(`evac-${t}`, e);
}
function Gt(s, t) {
  const e = t.frame;
  s.style.left = `${e.x}%`, s.style.top = `${e.y}%`, s.style.width = `${e.w}%`, s.style.height = `${e.h}%`, s.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function Vt(s, t) {
  const e = !s.visible_if || z(s.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (s.hidden && !t.editing || !e && !t.editing) return null;
  const n = document.createElement("div");
  n.className = `evac-el evac-el-${s.type}`, n.dataset.id = s.id, (!e || s.hidden) && n.classList.add("evac-dimmed"), Gt(n, s), tt(n, s.style, t);
  const i = s.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (n.classList.add(`evac-enter-${i.enter}`), n.style.animationDuration = `${i.duration ?? 600}ms`, n.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${s.type}`;
  if (!customElements.get(r))
    return t.onError?.(s.id, new Error(`unknown element type ${s.type}`)), t.editing ? n : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", n.appendChild(o), o.configure(s, t), n;
}
function Yt(s, t, e) {
  Ut();
  const n = document.createElement("div");
  n.className = "evac-stage";
  const i = t.background;
  if (i?.color && (n.style.background = M(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    n.style.backgroundImage = `url("${l}")`, n.style.backgroundSize = i.fit ?? "cover", n.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = Vt(c, e);
    l && (r.set(c.id, l), n.appendChild(l));
  }
  s.replaceChildren(n);
  const o = () => {
    const c = s.clientWidth, l = s.clientHeight;
    if (!c || !l) return;
    const u = Math.min(c / t.width, l / t.height);
    n.style.width = `${Math.round(t.width * u)}px`, n.style.height = `${Math.round(t.height * u)}px`;
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
function Xt(s, t) {
  const e = Date.now();
  s.replaceChildren(), s.style.aspectRatio = `${t.layout.width} / ${t.layout.height}`;
  for (const [n, i] of Object.entries(t.themeVariables ?? {})) s.style.setProperty(n, i);
  s.classList.add("evac-preview-host"), Yt(s, t.layout, {
    vars: t.vars,
    now: () => t.at + (Date.now() - e),
    timezone: t.timezone,
    assets: t.assets,
    fonts: t.fonts,
    reducedMotion: !0,
    nonce: K()
  });
}
if (typeof document < "u") {
  const s = document.getElementById("preview-config"), t = document.querySelector("[data-preview]");
  s && t && Xt(t, JSON.parse(s.textContent || "{}"));
}
export {
  Xt as mountPreview
};
