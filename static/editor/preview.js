// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC slide preview, built from frontend/src with `npm run build` - do not edit.
var tt = Object.defineProperty;
var et = (n, t, e) => t in n ? tt(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var E = (n, t, e) => et(n, typeof t != "symbol" ? t + "" : t, e);
const nt = `(() => {
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
function O(n) {
  return n.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function st(n, t, e, s = "") {
  const i = O(t), r = e ? ` ${e}` : "", o = [
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
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${O(o)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${s}</style><style nonce="${i}">${a}</style><script nonce="${i}">${nt}<\/script></head><body>${String(n.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function it(n) {
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
function rt(n = document) {
  const t = n.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
function ot(n, t, e) {
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
function at(n) {
  const t = [];
  let e = "", s = "";
  for (const i of n)
    s ? (i === s && (s = ""), e += i) : i === '"' || i === "'" ? (s = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function ct(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function L(n, t, e) {
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
function g(n) {
  return n == null ? "" : Array.isArray(n) ? n.map(g).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function lt(n, t, e) {
  const [s, ...i] = t.split(":"), r = ct(i.join(":")), o = () => n instanceof Date ? n : new Date(String(n));
  switch (s.trim()) {
    case "upper":
      return g(n).toUpperCase();
    case "lower":
      return g(n).toLowerCase();
    case "title":
      return g(n).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = g(n);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return g(n) === "" ? r : n;
    case "date":
      return isNaN(o().getTime()) ? "" : L(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : L(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map(g).join(r || ", ") : g(n);
    default:
      return n;
  }
}
function $(n, t, e = {}) {
  const [s, ...i] = at(n);
  let r = ot(t, s, e);
  for (const o of i) r = lt(r, o, e);
  return r;
}
function dt(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function I(n, t, e = {}) {
  const s = n.trim();
  if (!s) return !0;
  if (s.startsWith("not ")) return !I(s.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(s);
  if (i) {
    const r = g($(i[1], t, e)), o = g($(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return dt($(s.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const ht = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function j(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const s = n.split(ht);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < s.length; ) {
      const c = s[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const f = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(f)) return [a, f];
        if (f === "if") {
          const h = I(l[2], t, e), [u, w] = r(["else", "endif"]);
          let p = "";
          w === "else" && (p = r(["endif"])[0]), a += h ? u : p;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += g($(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
var b = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(b || {});
const ut = [0, 1], _ = [1, 0], q = [2, 3], H = [3, 2], ft = {
  L: ut,
  M: _,
  Q: q,
  H
}, pt = /^\d*$/, mt = /^[A-Z0-9 $%*+./:-]*$/, P = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", D = 1, B = 40, T = 3, gt = 3, M = 40, wt = 10, U = [
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
], G = [
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
class vt {
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
    if (this.version = t, this.ecc = e, t < D || t > B)
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
      this.setFunctionModule(6, s, s % 2 === 0, b.Timing), this.setFunctionModule(s, 6, s % 2 === 0, b.Timing);
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
    for (let s = 0; s < 12; s++)
      t = t << 1 ^ (t >>> 11) * 7973;
    const e = this.version << 12 | t;
    for (let s = 0; s < 18; s++) {
      const i = v(e, s), r = this.size - 11 + s % 3, o = Math.floor(s / 3);
      this.setFunctionModule(r, o, i), this.setFunctionModule(o, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let s = -4; s <= 4; s++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(s)), o = t + i, a = e + s;
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, b.Position);
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
          b.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, s, i = b.Function) {
    this.modules[e][t] = s, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, s = this.ecc;
    if (t.length !== A(e, s))
      throw new RangeError("Invalid argument");
    const i = G[s[0]][e], r = U[s[0]][e], o = Math.floor(k(e) / 8), a = i - o % i, c = Math.floor(o / i), l = [], f = At(r);
    for (let u = 0, w = 0; u < i; u++) {
      const p = t.slice(w, w + c - r + (u < a ? 0 : 1));
      w += p.length;
      const Q = zt(p, f);
      u < a && p.push(0), l.push(p.concat(Q));
    }
    const h = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((w, p) => {
        (u !== c - r || p >= a) && h.push(w[u]);
      });
    return h;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(k(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let s = this.size - 1; s >= 1; s -= 2) {
      s === 6 && (s = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = s - r, c = (s + 1 & 2) === 0 ? this.size - 1 - i : i;
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
        this.modules[r][l] === o ? (a++, a === 5 ? t += T : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * M), o = this.modules[r][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * M;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === o ? (a++, a === 5 ? t += T : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), o || (t += this.finderPenaltyCountPatterns(c) * M), o = this.modules[l][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, c) * M;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += gt);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const s = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - s * 10) / s) - 1;
    return t += i * wt, t;
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
function y(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let s = t - 1; s >= 0; s--)
    e.push(n >>> s & 1);
}
function v(n, t) {
  return (n >>> t & 1) !== 0;
}
class R {
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
const yt = [1, 10, 12, 14], bt = [2, 9, 11, 13], Ct = [4, 8, 16, 16];
function V(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function Y(n) {
  const t = [];
  for (const e of n)
    y(e, 8, t);
  return new R(Ct, n.length, t);
}
function Et(n) {
  if (!Z(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const s = Math.min(n.length - e, 3);
    y(Number.parseInt(n.substring(e, e + s), 10), s * 3 + 1, t), e += s;
  }
  return new R(yt, n.length, t);
}
function xt(n) {
  if (!X(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let s = P.indexOf(n.charAt(e)) * 45;
    s += P.indexOf(n.charAt(e + 1)), y(s, 11, t);
  }
  return e < n.length && y(P.indexOf(n.charAt(e)), 6, t), new R(bt, n.length, t);
}
function Mt(n) {
  return n === "" ? [] : Z(n) ? [Et(n)] : X(n) ? [xt(n)] : [Y($t(n))];
}
function Z(n) {
  return pt.test(n);
}
function X(n) {
  return mt.test(n);
}
function St(n, t) {
  let e = 0;
  for (const s of n) {
    const i = V(s.mode, t);
    if (s.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + s.bitData.length;
  }
  return e;
}
function $t(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function k(n) {
  if (n < D || n > B)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function A(n, t) {
  return Math.floor(k(n) / 8) - U[t[0]][n] * G[t[0]][n];
}
function At(n) {
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
function zt(n, t) {
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
function Pt(n, t, e = 1, s = 40, i = -1, r = !0) {
  if (!(D <= e && e <= s && s <= B) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const h = A(o, t) * 8, u = St(n, o);
    if (u <= h) {
      a = u;
      break;
    }
    if (o >= s)
      throw new RangeError("Data too long");
  }
  for (const h of [_, q, H])
    r && a <= A(o, h) * 8 && (t = h);
  const c = [];
  for (const h of n) {
    y(h.mode[0], 4, c), y(h.numChars, V(h.mode, o), c);
    for (const u of h.getData())
      c.push(u);
  }
  const l = A(o, t) * 8;
  y(0, Math.min(4, l - c.length), c), y(0, (8 - c.length % 8) % 8, c);
  for (let h = 236; c.length < l; h ^= 253)
    y(h, 8, c);
  const f = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((h, u) => f[u >>> 3] |= h << 7 - (u & 7)), new vt(o, t, f, i);
}
function Nt(n, t) {
  const {
    ecc: e = "L",
    boostEcc: s = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof n == "string" ? Mt(n) : Array.isArray(n) ? [Y(n)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const l = Pt(
    c,
    ft[e],
    i,
    r,
    o,
    s
  ), f = kt({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (f.data = f.data.map((h) => h.map((u) => !u))), t?.onEncoded?.(f), f;
}
function kt(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, s = e + t * 2;
  n.size = s, n.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    n.data.unshift(Array.from({ length: s }, (o) => !1)), n.data.push(Array.from({ length: s }, (o) => !1));
  const i = b.Border;
  n.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    n.types.unshift(Array.from({ length: s }, (o) => i)), n.types.push(Array.from({ length: s }, (o) => i));
  return n;
}
const N = "http://www.w3.org/2000/svg";
function Ft(n, t = document) {
  const { data: e, size: s } = Nt(n, { ecc: "M", border: 2 }), i = t.createElementNS(N, "svg");
  i.setAttribute("viewBox", `0 0 ${s} ${s}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(N, "rect");
  r.setAttribute("width", String(s)), r.setAttribute("height", String(s)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((f, h) => {
    f && (o += `M${h} ${l}h1v1h-1z`);
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
    return j(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function It(n, t) {
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
class Dt extends m {
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
      const i = () => It(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Bt extends m {
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
function J(n, t, e) {
  const s = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = n.urls[r], s.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = n.urls.original, i.alt = e || n.alt || "", i.decoding = "async", i.style.objectFit = t, s.appendChild(i), s;
}
class Rt extends m {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(J(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class Ot extends m {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), s = t.map((o) => {
      const a = J(o, e, "");
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
class Lt extends m {
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
class Tt extends m {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Wt extends m {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class jt extends m {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = Ft(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const _t = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class qt extends m {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ..._t[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = s.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class Ht extends m {
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
function Ut(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), s = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${s} ${s === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || s === 0 ? `${a(i + s * 24)}:${a(r)}:${a(o)}` : `${s}d ${a(i)}:${a(r)}:${a(o)}`;
}
class Gt extends m {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), s = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : Ut(i, String(this.props.format ?? "auto"));
    };
    s(), this.replaceChildren(e), this.every(250, s);
  }
}
class Vt extends m {
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
    s.setAttribute("sandbox", "allow-scripts"), s.setAttribute("referrerpolicy", "no-referrer"), s.setAttribute("allow", "autoplay"), s.setAttribute("title", this.el.name || "Code"), s.setAttribute("tabindex", "-1"), s.className = "evac-code-frame", s.srcdoc = st(e, t, location.origin, it(this)), this.frame = s, window.addEventListener("message", this.onMessage), this.replaceChildren(s), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
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
        for (const [c, l] of Object.entries(o.urls)) a[c] = new URL(l, location.href).href;
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
const K = {
  text: Dt,
  richtext: Bt,
  image: Rt,
  slideshow: Ot,
  video: Lt,
  audio: Tt,
  shape: Wt,
  qr: jt,
  clock: qt,
  countdown: Gt,
  date: Ht,
  code: Vt
};
function Yt(n = customElements) {
  for (const [t, e] of Object.entries(K))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
class Zt {
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
function d(n, t = "", e) {
  const s = document.createElement(n);
  return t && (s.className = t), e != null && e !== "" && (s.textContent = String(e)), s;
}
function C(n) {
  if (typeof n == "number") return Number.isFinite(n) ? n : null;
  if (typeof n == "string" && n.trim() !== "") {
    const t = Number(n.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function S(n, t) {
  if (typeof n != "string" || !n) return "";
  const e = /^\d{4}-\d{2}-\d{2}$/.test(n), s = new Date(e ? `${n}T12:00:00Z` : n);
  if (Number.isNaN(s.getTime())) return n;
  const i = e ? { weekday: "short", day: "numeric", month: "short" } : { hour: "2-digit", minute: "2-digit", hour12: !1 };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...i, timeZone: e ? "UTC" : t }).format(s);
  } catch {
    return new Intl.DateTimeFormat("en-GB", i).format(s);
  }
}
const Xt = ["time", "title", "subtitle", "label", "value"];
class Jt extends m {
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
    const s = d("div", `evac-data evac-data-${e.visual}`), i = String(this.props.title || e.options.heading || "");
    i && s.appendChild(d("div", "evac-data-heading", i));
    const r = d("div", "evac-data-body");
    s.appendChild(r), (W[e.visual] ?? W.list)(r, e, this), this.ctx.editing && e.stale && s.appendChild(d("span", "evac-data-stale", "stale")), this.replaceChildren(s);
  }
  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(t, e) {
    return j(
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
function x(n, t) {
  return t.rows.length ? !1 : (n.appendChild(d("div", "evac-data-empty", "–")), !0);
}
const W = {
  text(n, t, e) {
    n.appendChild(d("div", "evac-data-text", e.tmpl(
      String(t.options.template || "{{ data.first.title }}"),
      t
    )));
  },
  list(n, t, e) {
    if (x(n, t)) return;
    const s = d("ul", "evac-data-list");
    for (const i of t.rows) {
      const r = d("li");
      i.time && r.appendChild(d("span", "evac-data-time", S(i.time, e.tz)));
      const o = d("span", "evac-data-main");
      o.appendChild(d("span", "evac-data-title", i.title ?? i.label ?? i.value)), i.subtitle && o.appendChild(d("span", "evac-data-sub", i.subtitle)), r.appendChild(o), i.value !== void 0 && i.value !== null && i.title && r.appendChild(d("span", "evac-data-value", i.value)), s.appendChild(r);
    }
    n.appendChild(s);
  },
  table(n, t, e) {
    if (x(n, t)) return;
    const s = Xt.filter((o) => t.rows.some((a) => a[o] !== void 0 && a[o] !== null && a[o] !== "")), i = d("table", "evac-data-table"), r = d("tbody");
    for (const o of t.rows) {
      const a = d("tr");
      for (const c of s) a.appendChild(d("td", `evac-data-${c}`, c === "time" ? S(o[c], e.tz) : o[c]));
      r.appendChild(a);
    }
    i.appendChild(r), n.appendChild(i);
  },
  cards(n, t, e) {
    if (x(n, t)) return;
    const s = d("div", "evac-data-cards");
    for (const i of t.rows) {
      const r = d("div", "evac-data-card");
      if (typeof i.image == "string" && i.image.startsWith("/")) {
        const o = d("img");
        o.src = i.image, o.alt = "", r.appendChild(o);
      }
      i.time && r.appendChild(d("div", "evac-data-time", S(i.time, e.tz))), r.appendChild(d("div", "evac-data-title", i.title ?? i.label)), i.subtitle && r.appendChild(d("div", "evac-data-sub", i.subtitle)), i.value !== void 0 && i.value !== null && r.appendChild(d("div", "evac-data-value", i.value)), s.appendChild(r);
    }
    n.appendChild(s);
  },
  counter(n, t) {
    const e = t.rows[0] ?? {}, s = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, i = C(s), r = d("div", "evac-data-number", i === null ? s : i.toLocaleString("en-GB"));
    t.options.unit && r.appendChild(d("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(r), (e.label || e.title) && n.appendChild(d("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(n, t) {
    const e = t.rows[0] ?? {}, s = C(e.value) ?? 0, i = C(t.options.minimum) ?? 0, r = C(t.options.maximum) ?? 100, o = Math.max(0, Math.min(1, (s - i) / (r - i || 1))), a = "http://www.w3.org/2000/svg", c = document.createElementNS(a, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${s}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (h, u) => {
      const w = Math.PI * (1 - h), p = document.createElementNS(a, "path");
      p.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(w)} ${100 - 80 * Math.sin(w)}`), p.setAttribute("class", u), c.appendChild(p);
    };
    l(1, "evac-gauge-track"), o > 0 && l(o, "evac-gauge-fill"), n.appendChild(c);
    const f = d("div", "evac-data-number", s.toLocaleString("en-GB"));
    t.options.unit && f.appendChild(d("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(f), (e.label || e.title) && n.appendChild(d("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(n, t, e) {
    if (x(n, t)) return;
    const s = t.rows.map((o) => [o.time ? S(o.time, e.tz) : "", o.title ?? o.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), i = d("div", "evac-marquee-box"), r = d("span", "evac-marquee", s);
    r.style.animationDuration = `${Math.max(10, s.length / 5)}s`, i.appendChild(r), n.appendChild(i);
  },
  bars(n, t) {
    if (x(n, t)) return;
    const e = t.rows.map((r) => C(r.value) ?? 0), s = C(t.options.maximum) || Math.max(...e, 1), i = d("div", "evac-data-bars");
    t.rows.forEach((r, o) => {
      const a = d("div", "evac-bar");
      a.appendChild(d("span", "evac-bar-label", r.label ?? r.title));
      const c = d("span", "evac-bar-track"), l = d("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[o] / s * 100))}%`, c.appendChild(l), a.appendChild(c), a.appendChild(d("span", "evac-bar-value", `${e[o].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), i.appendChild(a);
    }), n.appendChild(i);
  }
};
K.data = Jt;
function z(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function Kt(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function Qt(n, t, e) {
  const s = n.style;
  if (!t) return;
  const i = (r, o) => {
    o && s.setProperty(r, o);
  };
  i("color", z(t.color)), i("background", z(t.background)), t.borderWidth && s.setProperty("border", `${t.borderWidth / 10}cqh solid ${z(t.borderColor) || "currentColor"}`), t.radius !== void 0 && s.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && s.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && s.setProperty("opacity", String(t.opacity)), i("font-family", Kt(t.fontFamily, e)), t.fontSize && s.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && s.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && s.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && s.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && s.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && s.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && s.setProperty("box-shadow", "var(--evac-shadow)");
}
function te(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function ee(n, t) {
  const e = !n.visible_if || I(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const s = document.createElement("div");
  s.className = `evac-el evac-el-${n.type}`, s.dataset.id = n.id, (!e || n.hidden) && s.classList.add("evac-dimmed"), te(s, n), Qt(s, n.style, t);
  const i = n.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (s.classList.add(`evac-enter-${i.enter}`), s.style.animationDuration = `${i.duration ?? 600}ms`, s.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${n.type}`;
  if (!customElements.get(r))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? s : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", s.appendChild(o), o.configure(n, t), s;
}
function ne(n, t, e) {
  Yt();
  const s = document.createElement("div");
  s.className = "evac-stage";
  const i = t.background;
  if (i?.color && (s.style.background = z(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    s.style.backgroundImage = `url("${l}")`, s.style.backgroundSize = i.fit ?? "cover", s.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = ee(c, e);
    l && (r.set(c.id, l), s.appendChild(l));
  }
  n.replaceChildren(s);
  const o = () => {
    const c = n.clientWidth, l = n.clientHeight;
    if (!c || !l) return;
    const f = Math.min(c / t.width, l / t.height);
    s.style.width = `${Math.round(t.width * f)}px`, s.style.height = `${Math.round(t.height * f)}px`;
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
function se(n, t) {
  const e = Date.now();
  n.replaceChildren(), n.style.aspectRatio = `${t.layout.width} / ${t.layout.height}`;
  for (const [s, i] of Object.entries(t.themeVariables ?? {})) n.style.setProperty(s, i);
  n.classList.add("evac-preview-host"), ne(n, t.layout, {
    vars: t.vars,
    now: () => t.at + (Date.now() - e),
    timezone: t.timezone,
    assets: t.assets,
    fonts: t.fonts,
    reducedMotion: !0,
    nonce: rt(),
    data: new Zt(t.data ?? {})
  });
}
if (typeof document < "u") {
  const n = document.getElementById("preview-config"), t = document.querySelector("[data-preview]");
  n && t && se(t, JSON.parse(n.textContent || "{}"));
}
export {
  se as mountPreview
};
