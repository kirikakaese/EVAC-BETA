// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC slide preview, built from frontend/src with `npm run build` - do not edit.
// Includes ISO 7010 safety signs from @iso-safety-signs/core (Copyright (c) Karl Norling, MIT,
// https://github.com/karlnorling/iso-safety-signs).
var it = Object.defineProperty;
var rt = (s, t, e) => t in s ? it(s, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : s[t] = e;
var E = (s, t, e) => rt(s, typeof t != "symbol" ? t + "" : t, e);
const ot = `(() => {
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
function H(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function at(s, t, e, n = "") {
  const i = H(t), r = e ? ` ${e}` : "", o = [
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
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${H(o)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${n}</style><style nonce="${i}">${a}</style><script nonce="${i}">${ot}<\/script></head><body>${String(s.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function ct(s) {
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
function lt(s = document) {
  const t = s.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
function dt(s, t, e) {
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
function ht(s) {
  const t = [];
  let e = "", n = "";
  for (const i of s)
    n ? (i === n && (n = ""), e += i) : i === '"' || i === "'" ? (n = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function ut(s) {
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
function v(s) {
  return s == null ? "" : Array.isArray(s) ? s.map(v).join(", ") : s instanceof Date ? s.toISOString() : typeof s == "object" ? s.name ?? "" : String(s);
}
function ft(s, t, e) {
  const [n, ...i] = t.split(":"), r = ut(i.join(":")), o = () => s instanceof Date ? s : new Date(String(s));
  switch (n.trim()) {
    case "upper":
      return v(s).toUpperCase();
    case "lower":
      return v(s).toLowerCase();
    case "title":
      return v(s).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, c = v(s);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return v(s) === "" ? r : s;
    case "date":
      return isNaN(o().getTime()) ? "" : W(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : W(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(s) ? s.map(v).join(r || ", ") : v(s);
    default:
      return s;
  }
}
function A(s, t, e = {}) {
  const [n, ...i] = ht(s);
  let r = dt(t, n, e);
  for (const o of i) r = ft(r, o, e);
  return r;
}
function pt(s) {
  return Array.isArray(s) ? s.length > 0 : !(s == null || s === !1 || s === "" || s === 0);
}
function R(s, t, e = {}) {
  const n = s.trim();
  if (!n) return !0;
  if (n.startsWith("not ")) return !R(n.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(n);
  if (i) {
    const r = v(A(i[1], t, e)), o = v(A(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return pt(A(n.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const mt = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function G(s, t, e = {}) {
  if (!s || !s.includes("{{") && !s.includes("{%")) return s ?? "";
  const n = s.split(mt);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < n.length; ) {
      const c = n[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const u = l[1].startsWith("if") ? "if" : l[1];
        if (o.includes(u)) return [a, u];
        if (u === "if") {
          const h = R(l[2], t, e), [f, w] = r(["else", "endif"]);
          let g = "";
          w === "else" && (g = r(["endif"])[0]), a += h ? f : g;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += v(A(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return r([])[0];
}
const V = {
  E001: {
    name: "Emergency exit (left hand)",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 105.833 105.833"><path fill="#fff" d="M105.833 0H0v105.833h105.833z"/><path fill="#237f52" d="M103.187 2.646H2.646v100.541h100.541z"/><path d="M148.169 80.71v60.715c6.316.483 10.53 5.636 10.53 10.315v2.47l-2.468-.007-8.062-.018v12.739l6.082 5.985h-40.129l-7.432-7.12h-9.24l7.433 7.12H93.428l-6.082-5.985v-41.75H98.01c.084 0 .163.004.246.004.056 0 .083-.007.136-.008q.052 0 .103-.004c1.439-.028 1.75-.282 2.779-1.31l6.241-7.378c1.731 3.785 3.362 7.004 5.085 10.66.195.374.655 1.213.31 1.867l-17.153 34.636 6.292-.021c3.29.072 4.662-2.198 5.819-4.23 4.64-9.353 9.301-18.697 13.949-28.05l.877 16.643c.23 2.88 2.176 3.612 4.726 3.691l28.817.066c0-3.312-3.282-7.687-8.627-7.895 0 0-10.292.116-15.673.137-.682 0-.869-.38-.948-.948-.25-4.282-.488-8.591-.754-12.872-.166-2.126-.352-3.598-.969-5.207-2.01-4.31-4.022-8.6-6.035-12.895l7.364-.085c.193-.007.344.035.444.208l5.33 9.337c2.199 4.01 8.139 1.086 6.149-3.166l-6.537-10.933c-1.15-1.71-1.674-2.299-4.661-2.392 0 0-13.956-.022-20.945-.022-2.27-.05-2.53.661-3.614 1.817a649 649 0 0 1-8.95 10.79c-.395.473-.617.675-1.558.667a62 62 0 0 0-4.619.081h-4.288V80.71Zm-38.65 8.337c-4 0-7.067 3.075-7.067 7.097 0 4.03 3.067 7.104 7.068 7.104s7.075-3.075 7.075-7.104c0-4.022-3.075-7.097-7.075-7.097" display="inline" fill="#fff" fill-opacity="1" stroke-width=".264583" transform="translate(-65.617 -71.967)"/></svg>'
  },
  E002: {
    name: "Emergency exit (right hand)",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 105.833 105.833"><path fill="#fff" d="M0 0h105.833v105.833H0z"/><path fill="#237f52" d="M2.646 2.646h100.541v100.541H2.646z"/><path d="M88.898 80.71v60.715c-6.317.483-10.531 5.636-10.531 10.315v2.47l2.469-.007 8.062-.018v12.739l-6.082 5.985h40.129l7.432-7.12h9.239l-7.433 7.12h11.456l6.082-5.985v-41.75h-10.665c-.083 0-.162.004-.246.004-.055 0-.083-.007-.136-.008q-.051 0-.102-.004c-1.439-.028-1.75-.282-2.78-1.31l-6.24-7.378c-1.731 3.785-3.362 7.004-5.085 10.66-.195.374-.655 1.213-.31 1.867l17.153 34.636-6.293-.021c-3.29.072-4.661-2.198-5.818-4.23-4.64-9.353-9.302-18.697-13.949-28.05l-.877 16.643c-.23 2.88-2.176 3.612-4.726 3.691l-28.817.066c0-3.312 3.282-7.687 8.626-7.895 0 0 10.292.116 15.673.137.683 0 .87-.38.949-.948.25-4.282.488-8.591.753-12.872.167-2.126.353-3.598.97-5.207 2.01-4.31 4.022-8.6 6.035-12.895l-7.364-.085c-.194-.007-.344.035-.445.208l-5.33 9.337c-2.198 4.01-8.138 1.086-6.148-3.166l6.536-10.933c1.15-1.71 1.675-2.299 4.662-2.392 0 0 13.956-.022 20.945-.022 2.27-.05 2.529.661 3.614 1.817a649 649 0 0 0 8.95 10.79c.395.473.617.675 1.558.667a62 62 0 0 1 4.619.081h4.288V80.71Zm38.649 8.337c4 0 7.067 3.075 7.067 7.097 0 4.03-3.066 7.104-7.067 7.104-4 0-7.075-3.075-7.075-7.104 0-4.022 3.074-7.097 7.075-7.097" display="inline" fill="#fff" fill-opacity="1" stroke-width=".264583" transform="translate(-65.617 -71.967)"/></svg>'
  },
  E003: {
    name: "First aid",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><g stroke="none" fill-rule="nonzero"><path d="M0 0h200v200H0z" fill="#fff"/><path d="M5 5h190v190H5z" fill="#237f52"/><path d="M75 25h50v150H75z" fill="#fff"/><path d="M25 75h150v50H25z" fill="#fff"/></g></svg>'
  },
  E007: {
    name: "Evacuation assembly point",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><path d="M0 0h200v200H0z" fill="#fff"/><path d="M5 5h190v190H5z" fill="#237f52"/><path d="m29.772 21.893-7.594 7.59 22.09 22.095h-22.08l10.066 10.065h29.682v-29.69l-10.081-10.06v22.09zM22.178 169.95l7.59 7.595 22.095-22.091v22.08l10.066-10.065v-29.682h-29.69l-10.061 10.08h22.09zM177.73 29.488l-7.59-7.594-22.095 22.09v-22.08L137.98 31.97v29.682h29.69l10.06-10.08h-22.09zm-7.6 148.052 7.595-7.59-22.092-22.096h22.08l-10.066-10.065h-29.682v29.69l10.081 10.061v-22.09zm-46.99-96.105h-12.701c-5.4-.159-8.488 3.05-9.195 7.41l-.074 19.594c.01 1.56.895 2.983 2.809 2.975 1.9-.009 2.772-1.426 2.786-2.975V90.46c.004-.261.73-.477 1.056-.481.329-.003.98.212.983.48v51.712c.01 1.78 1.62 3.42 3.804 3.413 2.18-.003 3.73-1.637 3.739-3.413l.013-29.91c.121-.26.698-.402.962-.398.26-.005.867.134.978.398l.017 29.91c.004 1.78 1.467 3.42 3.651 3.413 2.18-.003 3.872-1.637 3.876-3.413V90.458c.004-.26.67-.476.991-.48.33-.003 1.005.212 1.009.48v17.981c.01 1.56.768 2.983 2.682 2.975 1.9-.009 2.897-1.426 2.906-2.975l-.075-19.594c-.706-4.36-3.795-7.569-9.19-7.41m.113-8.735a6.932 6.932 0 1 0-6.933 6.934 6.936 6.936 0 0 0 6.933-6.934m-17.25-11.195a6.932 6.932 0 1 0-6.933 6.934 6.936 6.936 0 0 0 6.933-6.934m-18.398 19.93H75.931c-5.4-.159-8.488 3.05-9.195 7.41l-.074 19.594c.01 1.56.895 2.983 2.809 2.975 1.9-.009 2.772-1.426 2.786-2.975V90.46c.003-.261.73-.477 1.056-.481.329-.003.98.212.983.48v51.712c.01 1.78 1.62 3.42 3.804 3.413 2.18-.003 3.73-1.637 3.739-3.413l.013-29.91c.121-.26.698-.402.962-.398.26-.005.867.134.978.398l.017 29.91c.004 1.78 1.467 3.42 3.651 3.413 2.18-.003 3.872-1.637 3.876-3.413V90.458c.004-.26.67-.476.991-.48.33-.003 1.005.212 1.009.48v17.981c.01 1.56.768 2.983 2.682 2.975 1.9-.009 2.897-1.426 2.906-2.975l-.075-19.594c-.706-4.36-3.795-7.569-9.19-7.41m.122-8.735a6.932 6.932 0 1 0-6.933 6.934 6.936 6.936 0 0 0 6.933-6.934" fill="#fff" stroke="none"/></svg>'
  },
  W001: {
    name: "General warning sign",
    svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 524"><path fill="#f9a800" stroke="#000" stroke-linejoin="round" stroke-width="32" d="m300 16 284 492H16z"/><path d="M337 192a37 37 0 0 0-74 0l11 143a26 26 0 0 0 52 0m12 85a38 38 0 1 1 0-1"/></svg>'
  }
}, gt = "#237f52", vt = ["ahead", "ahead_right", "right", "back_right", "back", "back_left", "left", "ahead_left"], wt = {
  E001: "Emergency exit (left)",
  E002: "Emergency exit (right)",
  E003: "First aid",
  E007: "Assembly point",
  W001: "General warning",
  arrow: "Direction"
};
function yt(s) {
  const t = vt.indexOf(s);
  return t < 0 ? 0 : t * 45;
}
function bt(s, t, e, n) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${t}"
 color="${n}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${e}"/>${s}</svg>`;
}
function Ct(s, t) {
  return V[s].svg.replace(/^<svg\b/, `<svg role="img" aria-label="${t}"`);
}
function xt(s, t = "ahead") {
  const e = wt[s] ?? "Safety sign";
  if (s in V) return Ct(s, e);
  const n = yt(t);
  return bt(
    `<g transform="rotate(${n} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
    `${e}: ${String(t).replace("_", " ")}`,
    gt,
    "#fff"
  );
}
var C = /* @__PURE__ */ ((s) => (s[s.Border = -1] = "Border", s[s.Data = 0] = "Data", s[s.Function = 1] = "Function", s[s.Position = 2] = "Position", s[s.Timing = 3] = "Timing", s[s.Alignment = 4] = "Alignment", s))(C || {});
const Et = [0, 1], U = [1, 0], Z = [2, 3], Y = [3, 2], Mt = {
  L: Et,
  M: U,
  Q: Z,
  H: Y
}, St = /^\d*$/, $t = /^[A-Z0-9 $%*+./:-]*$/, D = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", L = 1, O = 40, _ = 3, zt = 3, S = 40, At = 10, K = [
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
], X = [
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
class kt {
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
    if (this.version = t, this.ecc = e, t < L || t > O)
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
    for (let n = 0; n < 12; n++)
      t = t << 1 ^ (t >>> 11) * 7973;
    const e = this.version << 12 | t;
    for (let n = 0; n < 18; n++) {
      const i = y(e, n), r = this.size - 11 + n % 3, o = Math.floor(n / 3);
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
    if (t.length !== k(e, n))
      throw new RangeError("Invalid argument");
    const i = X[n[0]][e], r = K[n[0]][e], o = Math.floor(B(e) / 8), a = i - o % i, c = Math.floor(o / i), l = [], u = Ot(r);
    for (let f = 0, w = 0; f < i; f++) {
      const g = t.slice(w, w + c - r + (f < a ? 0 : 1));
      w += g.length;
      const st = Tt(g, u);
      f < a && g.push(0), l.push(g.concat(st));
    }
    const h = [];
    for (let f = 0; f < l[0].length; f++)
      l.forEach((w, g) => {
        (f !== c - r || g >= a) && h.push(w[f]);
      });
    return h;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(B(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let n = this.size - 1; n >= 1; n -= 2) {
      n === 6 && (n = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = n - r, c = (n + 1 & 2) === 0 ? this.size - 1 - i : i;
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
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += zt);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const n = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - n * 10) / n) - 1;
    return t += i * At, t;
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
function b(s, t, e) {
  if (t < 0 || t > 31 || s >>> t)
    throw new RangeError("Value out of range");
  for (let n = t - 1; n >= 0; n--)
    e.push(s >>> n & 1);
}
function y(s, t) {
  return (s >>> t & 1) !== 0;
}
class T {
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
const Nt = [1, 10, 12, 14], Pt = [2, 9, 11, 13], Dt = [4, 8, 16, 16];
function J(s, t) {
  return s[Math.floor((t + 7) / 17) + 1];
}
function Q(s) {
  const t = [];
  for (const e of s)
    b(e, 8, t);
  return new T(Dt, s.length, t);
}
function Ft(s) {
  if (!tt(s))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < s.length; ) {
    const n = Math.min(s.length - e, 3);
    b(Number.parseInt(s.substring(e, e + n), 10), n * 3 + 1, t), e += n;
  }
  return new T(Nt, s.length, t);
}
function Bt(s) {
  if (!et(s))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= s.length; e += 2) {
    let n = D.indexOf(s.charAt(e)) * 45;
    n += D.indexOf(s.charAt(e + 1)), b(n, 11, t);
  }
  return e < s.length && b(D.indexOf(s.charAt(e)), 6, t), new T(Pt, s.length, t);
}
function It(s) {
  return s === "" ? [] : tt(s) ? [Ft(s)] : et(s) ? [Bt(s)] : [Q(Lt(s))];
}
function tt(s) {
  return St.test(s);
}
function et(s) {
  return $t.test(s);
}
function Rt(s, t) {
  let e = 0;
  for (const n of s) {
    const i = J(n.mode, t);
    if (n.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + n.bitData.length;
  }
  return e;
}
function Lt(s) {
  s = encodeURI(s);
  const t = [];
  for (let e = 0; e < s.length; e++)
    s.charAt(e) !== "%" ? t.push(s.charCodeAt(e)) : (t.push(Number.parseInt(s.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function B(s) {
  if (s < L || s > O)
    throw new RangeError("Version number out of range");
  let t = (16 * s + 128) * s + 64;
  if (s >= 2) {
    const e = Math.floor(s / 7) + 2;
    t -= (25 * e - 10) * e - 55, s >= 7 && (t -= 36);
  }
  return t;
}
function k(s, t) {
  return Math.floor(B(s) / 8) - K[t[0]][s] * X[t[0]][s];
}
function Ot(s) {
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
function Tt(s, t) {
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
function Ht(s, t, e = 1, n = 40, i = -1, r = !0) {
  if (!(L <= e && e <= n && n <= O) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const h = k(o, t) * 8, f = Rt(s, o);
    if (f <= h) {
      a = f;
      break;
    }
    if (o >= n)
      throw new RangeError("Data too long");
  }
  for (const h of [U, Z, Y])
    r && a <= k(o, h) * 8 && (t = h);
  const c = [];
  for (const h of s) {
    b(h.mode[0], 4, c), b(h.numChars, J(h.mode, o), c);
    for (const f of h.getData())
      c.push(f);
  }
  const l = k(o, t) * 8;
  b(0, Math.min(4, l - c.length), c), b(0, (8 - c.length % 8) % 8, c);
  for (let h = 236; c.length < l; h ^= 253)
    b(h, 8, c);
  const u = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((h, f) => u[f >>> 3] |= h << 7 - (f & 7)), new kt(o, t, u, i);
}
function Wt(s, t) {
  const {
    ecc: e = "L",
    boostEcc: n = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, c = typeof s == "string" ? It(s) : Array.isArray(s) ? [Q(s)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof s}`);
  const l = Ht(
    c,
    Mt[e],
    i,
    r,
    o,
    n
  ), u = _t({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (u.data = u.data.map((h) => h.map((f) => !f))), t?.onEncoded?.(u), u;
}
function _t(s, t = 1) {
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
const F = "http://www.w3.org/2000/svg";
function jt(s, t = document) {
  const { data: e, size: n } = Wt(s, { ecc: "M", border: 2 }), i = t.createElementNS(F, "svg");
  i.setAttribute("viewBox", `0 0 ${n} ${n}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(F, "rect");
  r.setAttribute("width", String(n)), r.setAttribute("height", String(n)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((c, l) => c.forEach((u, h) => {
    u && (o += `M${h} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(F, "path");
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
    return G(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function qt(s, t) {
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
class Gt extends m {
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
      const i = () => qt(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Vt extends m {
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
function nt(s, t, e) {
  const n = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (s.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = s.urls[r], n.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = s.urls.original, i.alt = e || s.alt || "", i.decoding = "async", i.style.objectFit = t, n.appendChild(i), n;
}
class Ut extends m {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(nt(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class Zt extends m {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), n = t.map((o) => {
      const a = nt(o, e, "");
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
class Yt extends m {
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
class Kt extends m {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Xt extends m {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Jt extends m {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = jt(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Qt = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class te extends m {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Qt[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = n.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class ee extends m {
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
function ne(s, t) {
  const e = Math.max(0, Math.floor(s / 1e3)), n = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${n} ${n === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || n === 0 ? `${a(i + n * 24)}:${a(r)}:${a(o)}` : `${n}d ${a(i)}:${a(r)}:${a(o)}`;
}
class se extends m {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), n = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : ne(i, String(this.props.format ?? "auto"));
    };
    n(), this.replaceChildren(e), this.every(250, n);
  }
}
class ie extends m {
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
    n.setAttribute("sandbox", "allow-scripts"), n.setAttribute("referrerpolicy", "no-referrer"), n.setAttribute("allow", "autoplay"), n.setAttribute("title", this.el.name || "Code"), n.setAttribute("tabindex", "-1"), n.className = "evac-code-frame", n.srcdoc = at(e, t, location.origin, ct(this)), this.frame = n, window.addEventListener("message", this.onMessage), this.replaceChildren(n), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
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
const P = {
  text: Gt,
  richtext: Vt,
  image: Ut,
  slideshow: Zt,
  video: Yt,
  audio: Kt,
  shape: Xt,
  qr: Jt,
  clock: te,
  countdown: se,
  date: ee,
  code: ie
};
function re(s = customElements) {
  for (const [t, e] of Object.entries(P))
    s.get(`evac-${t}`) || s.define(`evac-${t}`, e);
}
class oe extends m {
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
    this.hidden = !1, this.innerHTML = xt(t, e);
  }
}
P.pictogram = oe;
class ae {
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
function x(s) {
  if (typeof s == "number") return Number.isFinite(s) ? s : null;
  if (typeof s == "string" && s.trim() !== "") {
    const t = Number(s.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function $(s, t) {
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
const ce = ["time", "title", "subtitle", "label", "value"];
class le extends m {
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
    return G(
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
function M(s, t) {
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
    if (M(s, t)) return;
    const n = d("ul", "evac-data-list");
    for (const i of t.rows) {
      const r = d("li");
      i.time && r.appendChild(d("span", "evac-data-time", $(i.time, e.tz)));
      const o = d("span", "evac-data-main");
      o.appendChild(d("span", "evac-data-title", i.title ?? i.label ?? i.value)), i.subtitle && o.appendChild(d("span", "evac-data-sub", i.subtitle)), r.appendChild(o), i.value !== void 0 && i.value !== null && i.title && r.appendChild(d("span", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  table(s, t, e) {
    if (M(s, t)) return;
    const n = ce.filter((o) => t.rows.some((a) => a[o] !== void 0 && a[o] !== null && a[o] !== "")), i = d("table", "evac-data-table"), r = d("tbody");
    for (const o of t.rows) {
      const a = d("tr");
      for (const c of n) a.appendChild(d("td", `evac-data-${c}`, c === "time" ? $(o[c], e.tz) : o[c]));
      r.appendChild(a);
    }
    i.appendChild(r), s.appendChild(i);
  },
  cards(s, t, e) {
    if (M(s, t)) return;
    const n = d("div", "evac-data-cards");
    for (const i of t.rows) {
      const r = d("div", "evac-data-card");
      if (typeof i.image == "string" && i.image.startsWith("/")) {
        const o = d("img");
        o.src = i.image, o.alt = "", r.appendChild(o);
      }
      i.time && r.appendChild(d("div", "evac-data-time", $(i.time, e.tz))), r.appendChild(d("div", "evac-data-title", i.title ?? i.label)), i.subtitle && r.appendChild(d("div", "evac-data-sub", i.subtitle)), i.value !== void 0 && i.value !== null && r.appendChild(d("div", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  counter(s, t) {
    const e = t.rows[0] ?? {}, n = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, i = x(n), r = d("div", "evac-data-number", i === null ? n : i.toLocaleString("en-GB"));
    t.options.unit && r.appendChild(d("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(r), (e.label || e.title) && s.appendChild(d("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(s, t) {
    const e = t.rows[0] ?? {}, n = x(e.value) ?? 0, i = x(t.options.minimum) ?? 0, r = x(t.options.maximum) ?? 100, o = Math.max(0, Math.min(1, (n - i) / (r - i || 1))), a = "http://www.w3.org/2000/svg", c = document.createElementNS(a, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${n}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (h, f) => {
      const w = Math.PI * (1 - h), g = document.createElementNS(a, "path");
      g.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(w)} ${100 - 80 * Math.sin(w)}`), g.setAttribute("class", f), c.appendChild(g);
    };
    l(1, "evac-gauge-track"), o > 0 && l(o, "evac-gauge-fill"), s.appendChild(c);
    const u = d("div", "evac-data-number", n.toLocaleString("en-GB"));
    t.options.unit && u.appendChild(d("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(u), (e.label || e.title) && s.appendChild(d("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(s, t, e) {
    if (M(s, t)) return;
    const n = t.rows.map((o) => [o.time ? $(o.time, e.tz) : "", o.title ?? o.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), i = d("div", "evac-marquee-box"), r = d("span", "evac-marquee", n);
    r.style.animationDuration = `${Math.max(10, n.length / 5)}s`, i.appendChild(r), s.appendChild(i);
  },
  bars(s, t) {
    if (M(s, t)) return;
    const e = t.rows.map((r) => x(r.value) ?? 0), n = x(t.options.maximum) || Math.max(...e, 1), i = d("div", "evac-data-bars");
    t.rows.forEach((r, o) => {
      const a = d("div", "evac-bar");
      a.appendChild(d("span", "evac-bar-label", r.label ?? r.title));
      const c = d("span", "evac-bar-track"), l = d("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[o] / n * 100))}%`, c.appendChild(l), a.appendChild(c), a.appendChild(d("span", "evac-bar-value", `${e[o].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), i.appendChild(a);
    }), s.appendChild(i);
  }
};
P.data = le;
class de {
  constructor(t = null) {
    this.data = t, this.listeners = /* @__PURE__ */ new Set();
  }
  get() {
    return this.data;
  }
  set(t) {
    this.data = t, this.listeners.forEach((e) => e());
  }
  subscribe(t) {
    return this.listeners.add(t), () => this.listeners.delete(t);
  }
}
function p(s, t = "", e) {
  const n = document.createElement(s);
  return t && (n.className = t), e != null && e !== "" && (n.textContent = String(e)), n;
}
function z(s, t) {
  const e = new Date(s);
  if (Number.isNaN(e.getTime())) return "";
  const n = { hour: "2-digit", minute: "2-digit", hour12: !1 };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...n, timeZone: t }).format(e);
  } catch {
    return new Intl.DateTimeFormat("en-GB", n).format(e);
  }
}
function q(s, t) {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: t, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(s));
  } catch {
    return new Date(s).toISOString().slice(0, 10);
  }
}
function he(s, t, e) {
  const n = s.filter((o) => (t === null || o.stage === t) && o.status !== "cancelled").sort((o, a) => Date.parse(o.start) - Date.parse(a.start)), i = n.find((o) => Date.parse(o.start) <= e && Date.parse(o.end) > e) ?? null, r = n.find((o) => Date.parse(o.start) > e) ?? null;
  return { now: i, next: r };
}
function ue(s, t) {
  return t || (s.screen_room ? s.stages.find((e) => e.room === s.screen_room)?.id ?? null : null);
}
class fe extends m {
  constructor() {
    super(...arguments), this.unsubscribe = null, this.ticking = !1;
  }
  draw() {
    !this.unsubscribe && this.ctx.program && (this.unsubscribe = this.ctx.program.subscribe(() => this.safely(() => this.paint()))), this.paint(), this.ticking || (this.ticking = !0, this.every(15e3, () => this.paint()));
  }
  get tz() {
    return this.ctx.program?.get()?.timezone || this.ctx.timezone;
  }
  paint() {
    const t = this.ctx.program?.get(), e = String(this.props.view ?? "now_next");
    if (!t) {
      this.replaceChildren(), this.placeholder("Program (no sessions yet)");
      return;
    }
    this.classList.remove("evac-placeholder");
    const n = p("div", `evac-program evac-program-${e}`), i = String(this.props.title ?? "");
    i && n.appendChild(p("div", "evac-program-heading", i));
    const r = this.ctx.now(), o = ue(t, String(this.props.stage ?? "")), a = Math.max(1, Math.min(20, Number(this.props.count) || 6));
    e === "changes" ? this.changes(n, t, a) : e === "day" ? this.day(n, t, o, r, a) : this.nowNext(n, t, o, r), this.replaceChildren(n);
  }
  badge(t) {
    return t.status === "cancelled" ? p("span", "evac-program-badge evac-program-cancelled", "Cancelled") : t.delay > 0 ? p("span", "evac-program-badge evac-program-late", `+${t.delay} min`) : t.delay < 0 ? p("span", "evac-program-badge evac-program-late", `${t.delay} min`) : t.moved_from ? p("span", "evac-program-badge evac-program-late", "Room changed") : null;
  }
  session(t, e, n) {
    const i = p("div", `evac-program-session${t.status === "cancelled" ? " is-cancelled" : ""}`);
    t.colour && i.style.setProperty("--evac-track", t.colour);
    const r = p("div", "evac-program-when");
    e && r.appendChild(p("span", "evac-program-label", e)), r.appendChild(p("span", "evac-program-time", `${z(t.start, this.tz)}–${z(t.end, this.tz)}`)), t.planned_start && t.delay && r.appendChild(p("s", "evac-program-was", z(t.planned_start, this.tz)));
    const o = this.badge(t);
    o && r.appendChild(o), i.appendChild(r), i.appendChild(p("div", "evac-program-title", t.title));
    const a = [n ? t.stage_name : "", t.speakers.join(", ")].filter(Boolean).join(" · ");
    return a && i.appendChild(p("div", "evac-program-meta", a)), t.note && i.appendChild(p("div", "evac-program-note", t.note)), i;
  }
  nowNext(t, e, n, i) {
    const r = n ? e.stages.filter((c) => c.id === n) : e.stages;
    let o = 0;
    for (const c of r) {
      const { now: l, next: u } = he(e.sessions, c.id, i);
      if (!l && !u) continue;
      const h = p("div", "evac-program-stage");
      n || h.appendChild(p("div", "evac-program-stage-name", c.name)), l && h.appendChild(this.session(l, "Now", !1)), u && h.appendChild(this.session(u, "Next", !1)), t.appendChild(h), o++;
    }
    const a = e.sessions.filter((c) => c.status === "cancelled" && (!n || c.stage === n) && Date.parse(c.end) > i && Date.parse(c.start) - 36e5 < i);
    for (const c of a.slice(0, 2)) t.appendChild(this.session(c, "", !n));
    !o && !a.length && t.appendChild(p("div", "evac-program-empty", "Nothing more today"));
  }
  day(t, e, n, i, r) {
    const o = q(i, this.tz), a = e.sessions.filter((c) => (!n || c.stage === n) && Date.parse(c.end) > i && q(Date.parse(c.start), this.tz) === o).sort((c, l) => Date.parse(c.start) - Date.parse(l.start));
    if (!a.length) {
      t.appendChild(p("div", "evac-program-empty", "Nothing more today"));
      return;
    }
    for (const c of a.slice(0, r)) {
      const l = Date.parse(c.start) <= i && c.status !== "cancelled";
      t.appendChild(this.session(c, l ? "Now" : "", !n));
    }
  }
  changes(t, e, n) {
    if (!e.changes.length) {
      t.appendChild(p("div", "evac-program-empty", "No changes"));
      return;
    }
    const i = p("ul", "evac-program-changes");
    for (const r of e.changes.slice(0, n)) {
      const o = p("li", `evac-program-change evac-program-change-${r.kind}`);
      o.appendChild(p("span", "evac-program-time", z(r.at, this.tz))), o.appendChild(p("span", "evac-program-change-text", r.text)), i.appendChild(o);
    }
    t.appendChild(i);
  }
  disconnectedCallback() {
    this.unsubscribe?.(), this.unsubscribe = null, this.ticking = !1, super.disconnectedCallback();
  }
}
P.program = fe;
function N(s) {
  return s ? s.startsWith("token:") ? `var(--evac-color-${s.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(s) || s === "transparent" ? s : "" : "";
}
function pe(s, t) {
  return s ? s === "token:heading" ? "var(--evac-font-heading)" : s === "token:body" ? "var(--evac-font-body)" : t.fonts[s] ?? "" : "";
}
function me(s, t, e) {
  const n = s.style;
  if (!t) return;
  const i = (r, o) => {
    o && n.setProperty(r, o);
  };
  i("color", N(t.color)), i("background", N(t.background)), t.borderWidth && n.setProperty("border", `${t.borderWidth / 10}cqh solid ${N(t.borderColor) || "currentColor"}`), t.radius !== void 0 && n.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && n.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && n.setProperty("opacity", String(t.opacity)), i("font-family", pe(t.fontFamily, e)), t.fontSize && n.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && n.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && n.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && n.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && n.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && n.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && n.setProperty("box-shadow", "var(--evac-shadow)");
}
function ge(s, t) {
  const e = t.frame;
  s.style.left = `${e.x}%`, s.style.top = `${e.y}%`, s.style.width = `${e.w}%`, s.style.height = `${e.h}%`, s.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function ve(s, t) {
  const e = !s.visible_if || R(s.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (s.hidden && !t.editing || !e && !t.editing) return null;
  const n = document.createElement("div");
  n.className = `evac-el evac-el-${s.type}`, n.dataset.id = s.id, (!e || s.hidden) && n.classList.add("evac-dimmed"), ge(n, s), me(n, s.style, t);
  const i = s.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (n.classList.add(`evac-enter-${i.enter}`), n.style.animationDuration = `${i.duration ?? 600}ms`, n.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${s.type}`;
  if (!customElements.get(r))
    return t.onError?.(s.id, new Error(`unknown element type ${s.type}`)), t.editing ? n : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", n.appendChild(o), o.configure(s, t), n;
}
function we(s, t, e) {
  re();
  const n = document.createElement("div");
  n.className = "evac-stage";
  const i = t.background;
  if (i?.color && (n.style.background = N(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    n.style.backgroundImage = `url("${l}")`, n.style.backgroundSize = i.fit ?? "cover", n.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = ve(c, e);
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
function ye(s, t) {
  const e = Date.now();
  s.replaceChildren(), s.style.aspectRatio = `${t.layout.width} / ${t.layout.height}`;
  for (const [n, i] of Object.entries(t.themeVariables ?? {})) s.style.setProperty(n, i);
  s.classList.add("evac-preview-host"), we(s, t.layout, {
    vars: t.vars,
    now: () => t.at + (Date.now() - e),
    timezone: t.timezone,
    assets: t.assets,
    fonts: t.fonts,
    reducedMotion: !0,
    nonce: lt(),
    data: new ae(t.data ?? {}),
    program: new de(t.program ?? null)
  });
}
if (typeof document < "u") {
  const s = document.getElementById("preview-config"), t = document.querySelector("[data-preview]");
  s && t && ye(t, JSON.parse(s.textContent || "{}"));
}
export {
  ye as mountPreview
};
