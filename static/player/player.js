// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC player, built from frontend/src with `npm run build` - do not edit.
// Includes uqr (MIT, https://github.com/unjs/uqr).
// Includes ISO 7010 safety signs from @iso-safety-signs/core (Copyright (c) Karl Norling, MIT,
// https://github.com/karlnorling/iso-safety-signs).
var Oe = Object.defineProperty;
var Le = (s, t, e) => t in s ? Oe(s, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : s[t] = e;
var B = (s, t, e) => Le(s, typeof t != "symbol" ? t + "" : t, e);
class E extends Error {
}
async function _(s, t, e = {}) {
  const n = new AbortController(), i = setTimeout(() => n.abort(), e.timeout ?? 1e4), r = new Headers(e.headers);
  r.set("Accept", "application/json"), e.body && r.set("Content-Type", "application/json"), e.token && r.set("Authorization", `Screen ${e.token}`);
  try {
    const a = await fetch(s + t, {
      ...e,
      headers: r,
      signal: n.signal,
      cache: "no-store",
      credentials: "omit"
    });
    if (a.status === 401) throw new E("token rejected");
    if (!a.ok) throw new Error(`HTTP ${a.status}`);
    return await a.json();
  } finally {
    clearTimeout(i);
  }
}
const Re = (s, t) => _(s, "pair/", { method: "POST", body: JSON.stringify({ info: t }) }), Be = (s, t) => _(s, `pair/${t.id}/`, { method: "POST", headers: { "X-Pairing-Secret": t.secret } }), zt = (s, t) => _(s, "config/", { token: t });
class Fe {
  constructor() {
    this.samples = [], this.offset = 0;
  }
  add(t, e, n) {
    const i = e - t;
    i < 0 || !Number.isFinite(n) || (this.samples.push({ offset: n * 1e3 - (t + e) / 2, rtt: i }), this.samples.length > 8 && this.samples.shift(), this.offset = this.samples.reduce((r, a) => a.rtt < r.rtt ? a : r).offset);
  }
  now() {
    return Date.now() + this.offset;
  }
}
const We = 3e4, je = 3e5;
class He {
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
    this.backoff = Math.min(this.backoff * 2, We), setTimeout(() => !this.stopped && t(), e);
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
    return typeof WebSocket < "u" && Date.now() - this.fallbackSince > je ? (this.wsFailures = 0, this.openWebSocket(), !0) : !1;
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
        if (t.status === 401) throw new E("token rejected");
        if (!t.ok || !t.body) throw new Error(`SSE HTTP ${t.status}`);
        this.setTransport("sse"), this.backoff = 1e3;
        const e = t.body.getReader(), n = new TextDecoder();
        let i = "";
        for (; ; ) {
          const { value: r, done: a } = await e.read();
          if (a) break;
          i += n.decode(r, { stream: !0 });
          let o;
          for (; (o = i.indexOf(`

`)) >= 0; ) {
            const c = i.slice(0, o);
            i = i.slice(o + 2);
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
        t instanceof E ? (this.stop(), this.o.onUnauthorized()) : this.stopped || this.poll();
      }
    }
  }
  async poll() {
    if (!(this.stopped || this.maybeBackToWebSocket()))
      try {
        const t = await _(
          this.o.api,
          `poll/?since=${this.seq}&wait=10`,
          { token: this.o.token, timeout: 2e4 }
        );
        this.setTransport("poll"), this.backoff = 1e3, t.messages.forEach((e) => this.deliver(e)), this.poll();
      } catch (t) {
        if (t instanceof E) {
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
    _(this.o.api, "heartbeat/", {
      method: "POST",
      token: this.o.token,
      body: JSON.stringify({ data: t })
    }).then((e) => this.ack(e.server_time)).catch((e) => {
      e instanceof E ? (this.stop(), this.o.onUnauthorized()) : this.transport !== "websocket" && this.setTransport("offline");
    });
  }
}
function V(s) {
  return s ? s.startsWith("token:") ? `var(--evac-color-${s.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(s) || s === "transparent" ? s : "" : "";
}
function qe(s, t) {
  return s ? s === "token:heading" ? "var(--evac-font-heading)" : s === "token:body" ? "var(--evac-font-body)" : t.fonts[s] ?? "" : "";
}
function Ue(s, t, e) {
  const n = s.style;
  if (!t) return;
  const i = (r, a) => {
    a && n.setProperty(r, a);
  };
  i("color", V(t.color)), i("background", V(t.background)), t.borderWidth && n.setProperty("border", `${t.borderWidth / 10}cqh solid ${V(t.borderColor) || "currentColor"}`), t.radius !== void 0 && n.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && n.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && n.setProperty("opacity", String(t.opacity)), i("font-family", qe(t.fontFamily, e)), t.fontSize && n.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && n.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && n.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && n.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && n.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && n.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && n.setProperty("box-shadow", "var(--evac-shadow)");
}
function Je(s, t, e) {
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
function Ge(s) {
  const t = [];
  let e = "", n = "";
  for (const i of s)
    n ? (i === n && (n = ""), e += i) : i === '"' || i === "'" ? (n = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function Ve(s) {
  if (!s) return "";
  const t = s.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function Dt(s, t, e) {
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
function A(s) {
  return s == null ? "" : Array.isArray(s) ? s.map(A).join(", ") : s instanceof Date ? s.toISOString() : typeof s == "object" ? s.name ?? "" : String(s);
}
function Ke(s, t, e) {
  const [n, ...i] = t.split(":"), r = Ve(i.join(":")), a = () => s instanceof Date ? s : new Date(String(s));
  switch (n.trim()) {
    case "upper":
      return A(s).toUpperCase();
    case "lower":
      return A(s).toLowerCase();
    case "title":
      return A(s).replace(/\b\p{L}/gu, (o) => o.toUpperCase());
    case "truncate": {
      const o = Number(r) || 30, c = A(s);
      return c.length > o ? `${c.slice(0, Math.max(0, o - 1))}…` : c;
    }
    case "default":
      return A(s) === "" ? r : s;
    case "date":
      return isNaN(a().getTime()) ? "" : Dt(a(), r || "long", e.timezone);
    case "time":
      return isNaN(a().getTime()) ? "" : Dt(a(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(s) ? s.map(A).join(r || ", ") : A(s);
    default:
      return s;
  }
}
function K(s, t, e = {}) {
  const [n, ...i] = Ge(s);
  let r = Je(t, n, e);
  for (const a of i) r = Ke(r, a, e);
  return r;
}
function Ye(s) {
  return Array.isArray(s) ? s.length > 0 : !(s == null || s === !1 || s === "" || s === 0);
}
function rt(s, t, e = {}) {
  const n = s.trim();
  if (!n) return !0;
  if (n.startsWith("not ")) return !rt(n.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(n);
  if (i) {
    const r = A(K(i[1], t, e)), a = A(K(i[3], t, e));
    return i[2] === "==" ? r === a : r !== a;
  }
  return Ye(K(n.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const Xe = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function de(s, t, e = {}) {
  if (!s || !s.includes("{{") && !s.includes("{%")) return s ?? "";
  const n = s.split(Xe);
  let i = 0;
  const r = (a) => {
    let o = "";
    for (; i < n.length; ) {
      const c = n[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (a.includes(h)) return [o, h];
        if (h === "if") {
          const d = rt(l[2], t, e), [u, g] = r(["else", "endif"]);
          let m = "";
          g === "else" && (m = r(["endif"])[0]), o += d ? u : m;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? o += A(K(c.slice(2, -2), t, e)) : o += c;
    }
    return [o, ""];
  };
  return r([])[0];
}
const Ze = `(() => {
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
function Pt(s) {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function Qe(s, t, e, n = "") {
  const i = Pt(t), r = e ? ` ${e}` : "", a = [
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
  ].join("; "), o = String(s.css ?? "").replace(/<\/style/gi, "<\\/style"), c = String(s.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${Pt(a)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${n}</style><style nonce="${i}">${o}</style><script nonce="${i}">${Ze}<\/script></head><body>${String(s.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function tn(s) {
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
function Ot(s = document) {
  const t = s.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
const ue = {
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
}, en = "#237f52", nn = ["ahead", "ahead_right", "right", "back_right", "back", "back_left", "left", "ahead_left"], sn = {
  E001: "Emergency exit (left)",
  E002: "Emergency exit (right)",
  E003: "First aid",
  E007: "Assembly point",
  W001: "General warning",
  arrow: "Direction"
};
function rn(s) {
  const t = nn.indexOf(s);
  return t < 0 ? 0 : t * 45;
}
function an(s, t, e, n) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${t}"
 color="${n}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${e}"/>${s}</svg>`;
}
function on(s, t) {
  return ue[s].svg.replace(/^<svg\b/, `<svg role="img" aria-label="${t}"`);
}
function cn() {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="All clear"
 color="#fff"><circle cx="50" cy="50" r="44" fill="none" stroke="currentColor" stroke-width="8"/>
<path d="M28 52 L44 68 L74 34" fill="none" stroke="currentColor" stroke-width="10" stroke-linecap="round"
 stroke-linejoin="round"/></svg>`;
}
function Y(s, t = "ahead") {
  const e = sn[s] ?? "Safety sign";
  if (s in ue) return on(s, e);
  const n = rn(t);
  return an(
    `<g transform="rotate(${n} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
    `${e}: ${String(t).replace("_", " ")}`,
    en,
    "#fff"
  );
}
var O = /* @__PURE__ */ ((s) => (s[s.Border = -1] = "Border", s[s.Data = 0] = "Data", s[s.Function = 1] = "Function", s[s.Position = 2] = "Position", s[s.Timing = 3] = "Timing", s[s.Alignment = 4] = "Alignment", s))(O || {});
const ln = [0, 1], fe = [1, 0], pe = [2, 3], me = [3, 2], hn = {
  L: ln,
  M: fe,
  Q: pe,
  H: me
}, dn = /^\d*$/, un = /^[A-Z0-9 $%*+./:-]*$/, ot = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", Et = 1, Ct = 40, Lt = 3, fn = 3, q = 40, pn = 10, ge = [
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
], ve = [
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
class mn {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, n, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    B(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    B(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    B(this, "modules", []);
    B(this, "types", []);
    if (this.version = t, this.ecc = e, t < Et || t > Ct)
      throw new RangeError("Version value out of range");
    if (i < -1 || i > 7)
      throw new RangeError("Mask value out of range");
    this.size = t * 4 + 17;
    const r = Array.from({ length: this.size }).fill(!1);
    for (let o = 0; o < this.size; o++)
      this.modules.push(r.slice()), this.types.push(r.map(() => 0));
    this.drawFunctionPatterns();
    const a = this.addEccAndInterleave(n);
    if (this.drawCodewords(a), i === -1) {
      let o = 1e9;
      for (let c = 0; c < 8; c++) {
        this.applyMask(c), this.drawFormatBits(c);
        const l = this.getPenaltyScore();
        l < o && (i = c, o = l), this.applyMask(c);
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
      this.setFunctionModule(6, n, n % 2 === 0, O.Timing), this.setFunctionModule(n, 6, n % 2 === 0, O.Timing);
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
      this.setFunctionModule(8, r, N(i, r));
    this.setFunctionModule(8, 7, N(i, 6)), this.setFunctionModule(8, 8, N(i, 7)), this.setFunctionModule(7, 8, N(i, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, N(i, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, N(i, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, N(i, r));
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
      const i = N(e, n), r = this.size - 11 + n % 3, a = Math.floor(n / 3);
      this.setFunctionModule(r, a, i), this.setFunctionModule(a, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let n = -4; n <= 4; n++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(n)), a = t + i, o = e + n;
        a >= 0 && a < this.size && o >= 0 && o < this.size && this.setFunctionModule(a, o, r !== 2 && r !== 4, O.Position);
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
          O.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, n, i = O.Function) {
    this.modules[e][t] = n, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, n = this.ecc;
    if (t.length !== X(e, n))
      throw new RangeError("Invalid argument");
    const i = ve[n[0]][e], r = ge[n[0]][e], a = Math.floor(ft(e) / 8), o = i - a % i, c = Math.floor(a / i), l = [], h = $n(r);
    for (let u = 0, g = 0; u < i; u++) {
      const m = t.slice(g, g + c - r + (u < o ? 0 : 1));
      g += m.length;
      const b = En(m, h);
      u < o && m.push(0), l.push(m.concat(b));
    }
    const d = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((g, m) => {
        (u !== c - r || m >= o) && d.push(g[u]);
      });
    return d;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(ft(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let n = this.size - 1; n >= 1; n -= 2) {
      n === 6 && (n = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const a = n - r, c = (n + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][a] && e < t.length * 8 && (this.modules[c][a] = N(t[e >>> 3], 7 - (e & 7)), e++);
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
      let a = !1, o = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[r][l] === a ? (o++, o === 5 ? t += Lt : o > 5 && t++) : (this.finderPenaltyAddHistory(o, c), a || (t += this.finderPenaltyCountPatterns(c) * q), a = this.modules[r][l], o = 1);
      t += this.finderPenaltyTerminateAndCount(a, o, c) * q;
    }
    for (let r = 0; r < this.size; r++) {
      let a = !1, o = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][r] === a ? (o++, o === 5 ? t += Lt : o > 5 && t++) : (this.finderPenaltyAddHistory(o, c), a || (t += this.finderPenaltyCountPatterns(c) * q), a = this.modules[l][r], o = 1);
      t += this.finderPenaltyTerminateAndCount(a, o, c) * q;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let a = 0; a < this.size - 1; a++) {
        const o = this.modules[r][a];
        o === this.modules[r][a + 1] && o === this.modules[r + 1][a] && o === this.modules[r + 1][a + 1] && (t += fn);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((a, o) => a + (o ? 1 : 0), e);
    const n = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - n * 10) / n) - 1;
    return t += i * pn, t;
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
function I(s, t, e) {
  if (t < 0 || t > 31 || s >>> t)
    throw new RangeError("Value out of range");
  for (let n = t - 1; n >= 0; n--)
    e.push(s >>> n & 1);
}
function N(s, t) {
  return (s >>> t & 1) !== 0;
}
class Mt {
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
const gn = [1, 10, 12, 14], vn = [2, 9, 11, 13], yn = [4, 8, 16, 16];
function ye(s, t) {
  return s[Math.floor((t + 7) / 17) + 1];
}
function we(s) {
  const t = [];
  for (const e of s)
    I(e, 8, t);
  return new Mt(yn, s.length, t);
}
function wn(s) {
  if (!be(s))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < s.length; ) {
    const n = Math.min(s.length - e, 3);
    I(Number.parseInt(s.substring(e, e + n), 10), n * 3 + 1, t), e += n;
  }
  return new Mt(gn, s.length, t);
}
function bn(s) {
  if (!Se(s))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= s.length; e += 2) {
    let n = ot.indexOf(s.charAt(e)) * 45;
    n += ot.indexOf(s.charAt(e + 1)), I(n, 11, t);
  }
  return e < s.length && I(ot.indexOf(s.charAt(e)), 6, t), new Mt(vn, s.length, t);
}
function Sn(s) {
  return s === "" ? [] : be(s) ? [wn(s)] : Se(s) ? [bn(s)] : [we(xn(s))];
}
function be(s) {
  return dn.test(s);
}
function Se(s) {
  return un.test(s);
}
function kn(s, t) {
  let e = 0;
  for (const n of s) {
    const i = ye(n.mode, t);
    if (n.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + n.bitData.length;
  }
  return e;
}
function xn(s) {
  s = encodeURI(s);
  const t = [];
  for (let e = 0; e < s.length; e++)
    s.charAt(e) !== "%" ? t.push(s.charCodeAt(e)) : (t.push(Number.parseInt(s.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function ft(s) {
  if (s < Et || s > Ct)
    throw new RangeError("Version number out of range");
  let t = (16 * s + 128) * s + 64;
  if (s >= 2) {
    const e = Math.floor(s / 7) + 2;
    t -= (25 * e - 10) * e - 55, s >= 7 && (t -= 36);
  }
  return t;
}
function X(s, t) {
  return Math.floor(ft(s) / 8) - ge[t[0]][s] * ve[t[0]][s];
}
function $n(s) {
  if (s < 1 || s > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let n = 0; n < s - 1; n++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let n = 0; n < s; n++) {
    for (let i = 0; i < t.length; i++)
      t[i] = pt(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = pt(e, 2);
  }
  return t;
}
function En(s, t) {
  const e = t.map((n) => 0);
  for (const n of s) {
    const i = n ^ e.shift();
    e.push(0), t.forEach((r, a) => e[a] ^= pt(r, i));
  }
  return e;
}
function pt(s, t) {
  if (s >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let n = 7; n >= 0; n--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> n & 1) * s;
  return e;
}
function Cn(s, t, e = 1, n = 40, i = -1, r = !0) {
  if (!(Et <= e && e <= n && n <= Ct) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let a, o;
  for (a = e; ; a++) {
    const d = X(a, t) * 8, u = kn(s, a);
    if (u <= d) {
      o = u;
      break;
    }
    if (a >= n)
      throw new RangeError("Data too long");
  }
  for (const d of [fe, pe, me])
    r && o <= X(a, d) * 8 && (t = d);
  const c = [];
  for (const d of s) {
    I(d.mode[0], 4, c), I(d.numChars, ye(d.mode, a), c);
    for (const u of d.getData())
      c.push(u);
  }
  const l = X(a, t) * 8;
  I(0, Math.min(4, l - c.length), c), I(0, (8 - c.length % 8) % 8, c);
  for (let d = 236; c.length < l; d ^= 253)
    I(d, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((d, u) => h[u >>> 3] |= d << 7 - (u & 7)), new mn(a, t, h, i);
}
function Mn(s, t) {
  const {
    ecc: e = "L",
    boostEcc: n = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: a = -1,
    border: o = 1
  } = t || {}, c = typeof s == "string" ? Sn(s) : Array.isArray(s) ? [we(s)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof s}`);
  const l = Cn(
    c,
    hn[e],
    i,
    r,
    a,
    n
  ), h = An({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, o);
  return t?.invert && (h.data = h.data.map((d) => d.map((u) => !u))), t?.onEncoded?.(h), h;
}
function An(s, t = 1) {
  if (!t)
    return s;
  const { size: e } = s, n = e + t * 2;
  s.size = n, s.data.forEach((r) => {
    for (let a = 0; a < t; a++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    s.data.unshift(Array.from({ length: n }, (a) => !1)), s.data.push(Array.from({ length: n }, (a) => !1));
  const i = O.Border;
  s.types.forEach((r) => {
    for (let a = 0; a < t; a++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    s.types.unshift(Array.from({ length: n }, (a) => i)), s.types.push(Array.from({ length: n }, (a) => i));
  return s;
}
const ct = "http://www.w3.org/2000/svg";
function ke(s, t = document) {
  const { data: e, size: n } = Mn(s, { ecc: "M", border: 2 }), i = t.createElementNS(ct, "svg");
  i.setAttribute("viewBox", `0 0 ${n} ${n}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(ct, "rect");
  r.setAttribute("width", String(n)), r.setAttribute("height", String(n)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let a = "";
  e.forEach((c, l) => c.forEach((h, d) => {
    h && (a += `M${d} ${l}h1v1h-1z`);
  }));
  const o = t.createElementNS(ct, "path");
  return o.setAttribute("d", a), o.setAttribute("fill", "#000"), i.appendChild(o), i;
}
class x extends HTMLElement {
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
    return de(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function Tn(s, t) {
  t.style.removeProperty("font-size");
  const e = parseFloat(getComputedStyle(t).fontSize) || 16, n = () => t.scrollHeight <= s.clientHeight + 1 && t.scrollWidth <= s.clientWidth + 1;
  if (!s.clientHeight || n()) return;
  let i = Math.max(4, e * 0.1), r = e;
  for (let a = 0; a < 12 && r - i > 0.5; a++) {
    const o = (i + r) / 2;
    t.style.fontSize = `${o}px`, n() ? i = o : r = o;
  }
  t.style.fontSize = `${i}px`;
}
class _n extends x {
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
      const i = () => Tn(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Nn extends x {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-richtext";
    for (const e of this.text(this.props.text).split(/\n{2,}/)) {
      const n = document.createElement("p");
      e.split(`
`).forEach((i, r) => {
        r && n.appendChild(document.createElement("br"));
        for (const a of i.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/))
          /^\*\*[^*]+\*\*$/.test(a) ? n.appendChild(Object.assign(
            document.createElement("strong"),
            { textContent: a.slice(2, -2) }
          )) : /^\*[^*]+\*$/.test(a) ? n.appendChild(Object.assign(
            document.createElement("em"),
            { textContent: a.slice(1, -1) }
          )) : a && n.appendChild(document.createTextNode(a));
      }), t.appendChild(n);
    }
    this.replaceChildren(t);
  }
}
function xe(s, t, e) {
  const n = document.createElement("picture");
  for (const [r, a] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (s.urls[r]) {
      const o = document.createElement("source");
      o.type = a, o.srcset = s.urls[r], n.appendChild(o);
    }
  const i = document.createElement("img");
  return i.src = s.urls.original, i.alt = e || s.alt || "", i.decoding = "async", i.style.objectFit = t, n.appendChild(i), n;
}
class In extends x {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(xe(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class zn extends x {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((a) => this.asset(a)).filter((a) => !!a);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), n = t.map((a) => {
      const o = xe(a, e, "");
      return o.className = "evac-slide", o;
    });
    this.replaceChildren(...n);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const a = Math.floor(this.ctx.now() / i) % n.length;
      n.forEach((o, c) => o.classList.toggle("active", c === a));
    };
    r(), this.every(500, r);
  }
}
class Dn extends x {
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
class Pn extends x {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class On extends x {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Ln extends x {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = ke(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Rn = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Bn extends x {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Rn[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = n.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class Fn extends x {
  draw() {
    const t = String(this.props.format ?? "long"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, n = {
      long: { weekday: "long", day: "numeric", month: "long" },
      short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" },
      iso: { year: "numeric", month: "2-digit", day: "2-digit" }
    }, i = new Intl.DateTimeFormat(t === "iso" ? "sv-SE" : "en-GB", { ...n[t], timeZone: e }), r = document.createElement("time"), a = () => {
      r.textContent = i.format(new Date(this.ctx.now()));
    };
    a(), this.replaceChildren(r), this.every(3e4, a);
  }
}
function Wn(s, t) {
  const e = Math.max(0, Math.floor(s / 1e3)), n = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), a = e % 60, o = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${n} ${n === 1 ? "day" : "days"}` : t === "ms" ? `${o(Math.floor(e / 60))}:${o(a)}` : t === "hms" || n === 0 ? `${o(i + n * 24)}:${o(r)}:${o(a)}` : `${n}d ${o(i)}:${o(r)}:${o(a)}`;
}
class jn extends x {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), n = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : Wn(i, String(this.props.format ?? "auto"));
    };
    n(), this.replaceChildren(e), this.every(250, n);
  }
}
class Hn extends x {
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
    n.setAttribute("sandbox", "allow-scripts"), n.setAttribute("referrerpolicy", "no-referrer"), n.setAttribute("allow", "autoplay"), n.setAttribute("title", this.el.name || "Code"), n.setAttribute("tabindex", "-1"), n.className = "evac-code-frame", n.srcdoc = Qe(e, t, location.origin, tn(this)), this.frame = n, window.addEventListener("message", this.onMessage), this.replaceChildren(n), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
  }
  /** Only the kinds of data the element asked for (and that the server let it ask for). */
  send() {
    const t = new Set(this.props.data ?? []), e = this.ctx.vars, n = {};
    if (t.has("event") && (n.event = e.event ?? null), t.has("screen") && (n.screen = e.screen ?? null), t.has("time") && (n.now = this.ctx.now(), n.timezone = this.ctx.timezone ?? ""), t.has("assets")) {
      const i = {};
      for (const r of this.props.assets ?? []) {
        const a = this.ctx.assets[r];
        if (!a) continue;
        const o = {};
        for (const [c, l] of Object.entries(a.urls)) o[c] = new URL(l, location.href).href;
        i[r] = { name: a.name, kind: a.kind, alt: a.alt, width: a.width, height: a.height, urls: o };
      }
      n.assets = i;
    }
    this.frame?.contentWindow?.postMessage({ type: "evac:data", data: JSON.parse(JSON.stringify(n)) }, "*");
  }
  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage), this.frame = null, super.disconnectedCallback();
  }
}
const R = {
  text: _n,
  richtext: Nn,
  image: In,
  slideshow: zn,
  video: Dn,
  audio: Pn,
  shape: On,
  qr: Ln,
  clock: Bn,
  countdown: jn,
  date: Fn,
  code: Hn
};
function qn(s = customElements) {
  for (const [t, e] of Object.entries(R))
    s.get(`evac-${t}`) || s.define(`evac-${t}`, e);
}
class Un extends x {
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
    this.hidden = !1, this.innerHTML = Y(t, e);
  }
}
R.pictogram = Un;
class Jn {
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
function p(s, t = "", e) {
  const n = document.createElement(s);
  return t && (n.className = t), e != null && e !== "" && (n.textContent = String(e)), n;
}
function L(s) {
  if (typeof s == "number") return Number.isFinite(s) ? s : null;
  if (typeof s == "string" && s.trim() !== "") {
    const t = Number(s.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function U(s, t) {
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
const Gn = ["time", "title", "subtitle", "label", "value"];
class Vn extends x {
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
    const n = p("div", `evac-data evac-data-${e.visual}`), i = String(this.props.title || e.options.heading || "");
    i && n.appendChild(p("div", "evac-data-heading", i));
    const r = p("div", "evac-data-body");
    n.appendChild(r), (Rt[e.visual] ?? Rt.list)(r, e, this), this.ctx.editing && e.stale && n.appendChild(p("span", "evac-data-stale", "stale")), this.replaceChildren(n);
  }
  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(t, e) {
    return de(
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
function F(s, t) {
  return t.rows.length ? !1 : (s.appendChild(p("div", "evac-data-empty", "–")), !0);
}
const Rt = {
  text(s, t, e) {
    s.appendChild(p("div", "evac-data-text", e.tmpl(
      String(t.options.template || "{{ data.first.title }}"),
      t
    )));
  },
  list(s, t, e) {
    if (F(s, t)) return;
    const n = p("ul", "evac-data-list");
    for (const i of t.rows) {
      const r = p("li");
      i.time && r.appendChild(p("span", "evac-data-time", U(i.time, e.tz)));
      const a = p("span", "evac-data-main");
      a.appendChild(p("span", "evac-data-title", i.title ?? i.label ?? i.value)), i.subtitle && a.appendChild(p("span", "evac-data-sub", i.subtitle)), r.appendChild(a), i.value !== void 0 && i.value !== null && i.title && r.appendChild(p("span", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  table(s, t, e) {
    if (F(s, t)) return;
    const n = Gn.filter((a) => t.rows.some((o) => o[a] !== void 0 && o[a] !== null && o[a] !== "")), i = p("table", "evac-data-table"), r = p("tbody");
    for (const a of t.rows) {
      const o = p("tr");
      for (const c of n) o.appendChild(p("td", `evac-data-${c}`, c === "time" ? U(a[c], e.tz) : a[c]));
      r.appendChild(o);
    }
    i.appendChild(r), s.appendChild(i);
  },
  cards(s, t, e) {
    if (F(s, t)) return;
    const n = p("div", "evac-data-cards");
    for (const i of t.rows) {
      const r = p("div", "evac-data-card");
      if (typeof i.image == "string" && i.image.startsWith("/")) {
        const a = p("img");
        a.src = i.image, a.alt = "", r.appendChild(a);
      }
      i.time && r.appendChild(p("div", "evac-data-time", U(i.time, e.tz))), r.appendChild(p("div", "evac-data-title", i.title ?? i.label)), i.subtitle && r.appendChild(p("div", "evac-data-sub", i.subtitle)), i.value !== void 0 && i.value !== null && r.appendChild(p("div", "evac-data-value", i.value)), n.appendChild(r);
    }
    s.appendChild(n);
  },
  counter(s, t) {
    const e = t.rows[0] ?? {}, n = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, i = L(n), r = p("div", "evac-data-number", i === null ? n : i.toLocaleString("en-GB"));
    t.options.unit && r.appendChild(p("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(r), (e.label || e.title) && s.appendChild(p("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(s, t) {
    const e = t.rows[0] ?? {}, n = L(e.value) ?? 0, i = L(t.options.minimum) ?? 0, r = L(t.options.maximum) ?? 100, a = Math.max(0, Math.min(1, (n - i) / (r - i || 1))), o = "http://www.w3.org/2000/svg", c = document.createElementNS(o, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${n}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (d, u) => {
      const g = Math.PI * (1 - d), m = document.createElementNS(o, "path");
      m.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(g)} ${100 - 80 * Math.sin(g)}`), m.setAttribute("class", u), c.appendChild(m);
    };
    l(1, "evac-gauge-track"), a > 0 && l(a, "evac-gauge-fill"), s.appendChild(c);
    const h = p("div", "evac-data-number", n.toLocaleString("en-GB"));
    t.options.unit && h.appendChild(p("span", "evac-data-unit", ` ${t.options.unit}`)), s.appendChild(h), (e.label || e.title) && s.appendChild(p("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(s, t, e) {
    if (F(s, t)) return;
    const n = t.rows.map((a) => [a.time ? U(a.time, e.tz) : "", a.title ?? a.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), i = p("div", "evac-marquee-box"), r = p("span", "evac-marquee", n);
    r.style.animationDuration = `${Math.max(10, n.length / 5)}s`, i.appendChild(r), s.appendChild(i);
  },
  bars(s, t) {
    if (F(s, t)) return;
    const e = t.rows.map((r) => L(r.value) ?? 0), n = L(t.options.maximum) || Math.max(...e, 1), i = p("div", "evac-data-bars");
    t.rows.forEach((r, a) => {
      const o = p("div", "evac-bar");
      o.appendChild(p("span", "evac-bar-label", r.label ?? r.title));
      const c = p("span", "evac-bar-track"), l = p("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[a] / n * 100))}%`, c.appendChild(l), o.appendChild(c), o.appendChild(p("span", "evac-bar-value", `${e[a].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), i.appendChild(o);
    }), s.appendChild(i);
  }
};
R.data = Vn;
class Kn {
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
function y(s, t = "", e) {
  const n = document.createElement(s);
  return t && (n.className = t), e != null && e !== "" && (n.textContent = String(e)), n;
}
function J(s, t) {
  const e = new Date(s);
  if (Number.isNaN(e.getTime())) return "";
  const n = { hour: "2-digit", minute: "2-digit", hour12: !1 };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...n, timeZone: t }).format(e);
  } catch {
    return new Intl.DateTimeFormat("en-GB", n).format(e);
  }
}
function Bt(s, t) {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: t, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(s));
  } catch {
    return new Date(s).toISOString().slice(0, 10);
  }
}
function Yn(s, t, e) {
  const n = s.filter((a) => (t === null || a.stage === t) && a.status !== "cancelled").sort((a, o) => Date.parse(a.start) - Date.parse(o.start)), i = n.find((a) => Date.parse(a.start) <= e && Date.parse(a.end) > e) ?? null, r = n.find((a) => Date.parse(a.start) > e) ?? null;
  return { now: i, next: r };
}
function Xn(s, t) {
  return t || (s.screen_room ? s.stages.find((e) => e.room === s.screen_room)?.id ?? null : null);
}
class Zn extends x {
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
    const n = y("div", `evac-program evac-program-${e}`), i = String(this.props.title ?? "");
    i && n.appendChild(y("div", "evac-program-heading", i));
    const r = this.ctx.now(), a = Xn(t, String(this.props.stage ?? "")), o = Math.max(1, Math.min(20, Number(this.props.count) || 6));
    e === "changes" ? this.changes(n, t, o) : e === "day" ? this.day(n, t, a, r, o) : this.nowNext(n, t, a, r), this.replaceChildren(n);
  }
  badge(t) {
    return t.status === "cancelled" ? y("span", "evac-program-badge evac-program-cancelled", "Cancelled") : t.delay > 0 ? y("span", "evac-program-badge evac-program-late", `+${t.delay} min`) : t.delay < 0 ? y("span", "evac-program-badge evac-program-late", `${t.delay} min`) : t.moved_from ? y("span", "evac-program-badge evac-program-late", "Room changed") : null;
  }
  session(t, e, n) {
    const i = y("div", `evac-program-session${t.status === "cancelled" ? " is-cancelled" : ""}`);
    t.colour && i.style.setProperty("--evac-track", t.colour);
    const r = y("div", "evac-program-when");
    e && r.appendChild(y("span", "evac-program-label", e)), r.appendChild(y("span", "evac-program-time", `${J(t.start, this.tz)}–${J(t.end, this.tz)}`)), t.planned_start && t.delay && r.appendChild(y("s", "evac-program-was", J(t.planned_start, this.tz)));
    const a = this.badge(t);
    a && r.appendChild(a), i.appendChild(r), i.appendChild(y("div", "evac-program-title", t.title));
    const o = [n ? t.stage_name : "", t.speakers.join(", ")].filter(Boolean).join(" · ");
    return o && i.appendChild(y("div", "evac-program-meta", o)), t.note && i.appendChild(y("div", "evac-program-note", t.note)), i;
  }
  nowNext(t, e, n, i) {
    const r = n ? e.stages.filter((c) => c.id === n) : e.stages;
    let a = 0;
    for (const c of r) {
      const { now: l, next: h } = Yn(e.sessions, c.id, i);
      if (!l && !h) continue;
      const d = y("div", "evac-program-stage");
      n || d.appendChild(y("div", "evac-program-stage-name", c.name)), l && d.appendChild(this.session(l, "Now", !1)), h && d.appendChild(this.session(h, "Next", !1)), t.appendChild(d), a++;
    }
    const o = e.sessions.filter((c) => c.status === "cancelled" && (!n || c.stage === n) && Date.parse(c.end) > i && Date.parse(c.start) - 36e5 < i);
    for (const c of o.slice(0, 2)) t.appendChild(this.session(c, "", !n));
    !a && !o.length && t.appendChild(y("div", "evac-program-empty", "Nothing more today"));
  }
  day(t, e, n, i, r) {
    const a = Bt(i, this.tz), o = e.sessions.filter((c) => (!n || c.stage === n) && Date.parse(c.end) > i && Bt(Date.parse(c.start), this.tz) === a).sort((c, l) => Date.parse(c.start) - Date.parse(l.start));
    if (!o.length) {
      t.appendChild(y("div", "evac-program-empty", "Nothing more today"));
      return;
    }
    for (const c of o.slice(0, r)) {
      const l = Date.parse(c.start) <= i && c.status !== "cancelled";
      t.appendChild(this.session(c, l ? "Now" : "", !n));
    }
  }
  changes(t, e, n) {
    if (!e.changes.length) {
      t.appendChild(y("div", "evac-program-empty", "No changes"));
      return;
    }
    const i = y("ul", "evac-program-changes");
    for (const r of e.changes.slice(0, n)) {
      const a = y("li", `evac-program-change evac-program-change-${r.kind}`);
      a.appendChild(y("span", "evac-program-time", J(r.at, this.tz))), a.appendChild(y("span", "evac-program-change-text", r.text)), i.appendChild(a);
    }
    t.appendChild(i);
  }
  disconnectedCallback() {
    this.unsubscribe?.(), this.unsubscribe = null, this.ticking = !1, super.disconnectedCallback();
  }
}
R.program = Zn;
const lt = /* @__PURE__ */ new Map();
function Qn(s) {
  let t = lt.get(s);
  return t || (t = import(
    /* @vite-ignore */
    s
  ), lt.set(s, t), t.catch(() => lt.delete(s))), t;
}
function ts(s, t, e = () => ({}), n = !1) {
  const i = /* @__PURE__ */ new Map(), r = (a) => `evac.plugin-source.${a}`;
  return {
    get widgets() {
      return s();
    },
    async source(a) {
      try {
        const o = await fetch(`${t}${encodeURIComponent(a)}/`, { headers: e(), cache: "no-store" });
        if (!o.ok) throw new Error(`HTTP ${o.status}`);
        const c = await o.json();
        if (i.set(a, c.data), n)
          try {
            localStorage.setItem(r(a), JSON.stringify(c.data));
          } catch {
          }
        return c.data;
      } catch (o) {
        if (i.has(a)) return i.get(a);
        if (n)
          try {
            const c = localStorage.getItem(r(a));
            if (c !== null) return JSON.parse(c);
          } catch {
          }
        throw o;
      }
    }
  };
}
class es extends x {
  constructor() {
    super(...arguments), this.inner = null;
  }
  draw() {
    const t = String(this.props.widget ?? ""), e = t ? this.ctx.plugins?.widgets[t] : void 0;
    if (!e) return this.placeholder(t ? `Plugin widget “${t}” is not installed` : "Plugin widget");
    const n = this.props.settings ?? {};
    Qn(e.script).then(() => {
      if (!this.isConnected && !this.ctx.editing) return;
      if (!customElements.get(e.element)) throw new Error(`${e.script} did not define <${e.element}>`);
      const i = document.createElement(e.element);
      i.className = "evac-plugin-element", i.settings = n, i.vars = this.ctx.vars, i.data = {}, this.replaceChildren(i), this.inner = i, this.refresh(e), e.sources.length && this.every(Math.max(10, e.ttl) * 1e3, () => this.refresh(e));
    }).catch((i) => this.safely(() => {
      throw i;
    }));
  }
  refresh(t) {
    const e = this.ctx.plugins;
    if (e)
      for (const n of t.sources)
        e.source(n).then((i) => {
          this.inner && (this.inner.data = { ...this.inner.data ?? {}, [n]: i });
        }).catch((i) => this.ctx.onError?.(this.el.id, i));
  }
}
R.plugin = es;
function Ft(s, t) {
  if (s.slide === null) return null;
  if (s.slide) {
    const n = s.slide.end - s.slide.start;
    return n > 0 ? { start: s.slide.start, total: n, loop: !1 } : null;
  }
  const e = Math.max(1e3, s.loopMs ?? 1e4);
  return { start: t - (t % e + e) % e, total: e, loop: !0 };
}
function ns(s, t, e) {
  const n = Math.max(0, Math.min(1, (t - s.start) / s.total));
  return e ? n : 1 - n;
}
class ss extends x {
  draw() {
    const t = this.props, e = t.orientation === "vertical", n = t.mode === "grow", i = document.createElement("span");
    i.className = "evac-progress-bar", this.dataset.orientation = e ? "vertical" : "horizontal", this.dataset.mode = n ? "grow" : "shrink", this.toggleAttribute("data-reverse", t.reverse === !0), this.replaceChildren(i);
    const r = this.parentElement, a = this.ctx.now(), o = Ft(this.ctx, a);
    r?.classList.toggle("evac-off", !o && t.untimed === "hide");
    const c = e ? "Y" : "X", l = (d) => {
      i.style.transform = `scale${c}(${d.toFixed(4)})`;
    };
    if (!o) {
      l(1);
      return;
    }
    if (this.ctx.reducedMotion || this.ctx.motion === !1) {
      const d = () => l(ns(
        o.loop ? Ft(this.ctx, this.ctx.now()) ?? o : o,
        this.ctx.now(),
        n
      ));
      d(), this.every(1e3, d);
      return;
    }
    const h = i.style;
    h.animationName = `evac-timer-${n ? "grow" : "shrink"}-${c.toLowerCase()}`, h.animationDuration = `${o.total}ms`, h.animationDelay = `${-Math.round(a - o.start)}ms`, h.animationTimingFunction = "linear", h.animationIterationCount = o.loop ? "infinite" : "1", h.animationFillMode = "both";
  }
}
R.progress = ss;
const is = /* @__PURE__ */ new Set(["fade", "slide-up", "slide-left", "zoom"]), rs = 1e4, as = 6e4, Wt = (s, t, e) => Math.max(t, Math.min(e, Number(s) || 0));
function os(s) {
  return !s.reducedMotion && (s.motion ?? !s.editing);
}
function cs(s, t) {
  const e = t.frame;
  s.style.left = `${e.x}%`, s.style.top = `${e.y}%`, s.style.width = `${e.w}%`, s.style.height = `${e.h}%`, s.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function ls(s, t) {
  const e = !s.visible_if || rt(s.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (s.hidden && !t.editing || !e && !t.editing) return null;
  const n = document.createElement("div");
  n.className = `evac-el evac-el-${s.type}`, n.dataset.id = s.id, (!e || s.hidden) && n.classList.add("evac-dimmed"), cs(n, s), Ue(n, s.style, t);
  const i = s.animation;
  i?.enter && is.has(i.enter) && os(t) && (n.classList.add(`evac-enter-${i.enter}`), n.style.animationDuration = `${Wt(i.duration ?? 600, 0, rs)}ms`, n.style.animationDelay = `${Wt(i.delay ?? 0, 0, as)}ms`);
  const r = `evac-${s.type}`;
  if (!customElements.get(r))
    return t.onError?.(s.id, new Error(`unknown element type ${s.type}`)), t.editing ? n : null;
  const a = document.createElement(r);
  return a.className = "evac-widget", n.appendChild(a), a.configure(s, t), n;
}
function et(s, t, e) {
  qn(), e.loopMs === void 0 && (e = { ...e, loopMs: Math.max(1, t.duration ?? 10) * 1e3 });
  const n = document.createElement("div");
  n.className = "evac-stage";
  const i = t.background;
  if (i?.color && (n.style.background = V(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    n.style.backgroundImage = `url("${l}")`, n.style.backgroundSize = i.fit ?? "cover", n.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = ls(c, e);
    l && (r.set(c.id, l), n.appendChild(l));
  }
  s.replaceChildren(n);
  const a = () => {
    const c = s.clientWidth, l = s.clientHeight;
    if (!c || !l) return;
    const h = Math.min(c / t.width, l / t.height);
    n.style.width = `${Math.round(t.width * h)}px`, n.style.height = `${Math.round(t.height * h)}px`;
  };
  a();
  const o = typeof ResizeObserver < "u" ? new ResizeObserver(a) : null;
  return o?.observe(s), {
    stage: n,
    elements: r,
    destroy() {
      o?.disconnect(), n.remove();
    }
  };
}
const hs = ["evac-tr-fade", "evac-tr-slide-left", "evac-tr-slide-up", "evac-tr-zoom"];
function v(s, t = "", e = "") {
  const n = document.createElement(s);
  return t && (n.className = t), e && (n.textContent = e), n;
}
class ds {
  constructor(t, e) {
    this.root = t, this.clock = e, this.clockTimer = null, this.overlay = null, this.overlayTimer = null, this.rendered = null, this.view = null, this.leaving = null;
  }
  /** Whether a slide transition is running. */
  get transitioning() {
    return this.leaving !== null;
  }
  /** End a running transition at once: the outgoing slide goes, the incoming one stands still. Alarms and
   *  urgent content call this, so nothing waits for an animation. */
  settle() {
    const t = this.leaving;
    t && (this.leaving = null, clearTimeout(t.timer), t.rendered?.destroy(), t.view.remove(), this.view?.classList.remove("evac-tr-in", ...hs));
  }
  reset() {
    this.settle(), this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null, this.rendered?.destroy(), this.rendered = null, this.root.replaceChildren();
    const t = v("main", "view");
    return this.root.appendChild(t), this.view = t, t;
  }
  pairing(t, e, n) {
    const i = this.reset();
    i.classList.add("pairing"), i.append(v("h1", "", n.title));
    const r = v("div", "pairing-box"), a = v("p", "code", t);
    a.setAttribute("aria-label", t.split("").join(" "));
    const o = ke(e);
    o.setAttribute("role", "img"), o.setAttribute("aria-label", e), r.append(a, o);
    const c = v("ol", "steps");
    c.append(v("li", "", n.step1), v("li", "", n.step2)), i.append(r, c, v("p", "url", e), v("p", "waiting", n.waiting));
  }
  message(t, e = "") {
    const n = this.reset();
    n.classList.add("message"), n.append(v("h1", "", t)), e && n.append(v("p", "", e));
  }
  idle(t) {
    const e = this.reset();
    e.classList.add("idle");
    const n = v("p", "clock"), i = v("p", "date");
    e.append(v("h1", "event-name", t.event.name), n, i);
    const r = t.event.timezone || void 0, a = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: r }), o = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: r }), c = () => {
      const l = new Date(this.clock.now());
      n.textContent = a.format(l), i.textContent = o.format(l);
    };
    c(), this.clockTimer = setInterval(c, 1e3);
  }
  /** Show a layout. With a ``transition`` and a layout on screen, the new slide comes in over the old one, which
   *  is removed when the transition ends (or at once by :meth:`settle`). */
  layout(t, e, n, i = null) {
    const r = i && this.view?.classList.contains("layout") && this.view.parentElement === this.root ? this.view : null;
    if (!r || !i) {
      const c = this.reset();
      c.classList.add("layout");
      for (const [l, h] of Object.entries(n ?? {})) c.style.setProperty(l, h);
      this.rendered = et(c, t, e);
      return;
    }
    this.settle();
    const a = this.rendered;
    this.clockTimer && clearInterval(this.clockTimer), this.clockTimer = null;
    for (const c of [...this.root.children]) c !== r && c.remove();
    const o = v("main", "view layout");
    for (const [c, l] of Object.entries(n ?? {})) o.style.setProperty(c, l);
    this.root.appendChild(o), this.view = o, this.rendered = et(o, t, e), r.setAttribute("aria-hidden", "true"), r.inert = !0;
    for (const c of [o, r])
      c.style.setProperty("--evac-tr-ms", `${i.ms}ms`), c.classList.add(`evac-tr-${i.effect}`);
    o.classList.add("evac-tr-in"), r.classList.add("evac-tr-out"), this.leaving = { view: r, rendered: a, timer: setTimeout(() => this.settle(), i.ms + 50) };
  }
  /** Colour bars, a grid and circles to check geometry, overscan and colours (with name and resolution). */
  testPattern(t, e, n = 30) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = v("div", "test-pattern");
    i.setAttribute("role", "img"), i.setAttribute("aria-label", t);
    const r = v("div", "tp-bars");
    for (const c of ["white", "yellow", "cyan", "green", "magenta", "red", "blue", "black"])
      r.appendChild(v("span", `tp-bar tp-${c}`));
    const a = v("div", "tp-ramp"), o = v("div", "tp-info");
    o.append(v("p", "tp-title", t), ...e.map((c) => v("p", "", c))), i.append(r, a, v("div", "tp-grid"), v("div", "tp-circle"), v("div", "tp-corners"), o), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), n * 1e3);
  }
  identify(t, e, n = 10) {
    this.overlay?.remove(), this.overlayTimer && clearTimeout(this.overlayTimer);
    const i = v("div", "identify");
    i.setAttribute("role", "status"), i.append(v("p", "identify-name", t), v("p", "identify-detail", e)), this.root.appendChild(i), this.overlay = i, this.overlayTimer = setTimeout(() => i.remove(), n * 1e3);
  }
}
const At = "evac.player.bundle";
async function us(s, t) {
  try {
    const e = await _(s, "content/bundle/", { token: t, timeout: 2e4 });
    if (e.bundle)
      try {
        localStorage.setItem(At, JSON.stringify(e.bundle));
      } catch {
      }
    return e.bundle;
  } catch (e) {
    if (e instanceof E) throw e;
    return mt();
  }
}
function mt() {
  try {
    const s = localStorage.getItem(At);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function fs() {
  try {
    localStorage.removeItem(At);
  } catch {
  }
}
function ps(s) {
  return s?.layouts.length ? s.layouts.find((t) => t.default) ?? s.layouts[0] : null;
}
async function ms(s) {
  const t = /* @__PURE__ */ new Set();
  for (const n of Object.values(s.assets)) Object.values(n.urls).forEach((i) => t.add(i));
  for (const n of Object.values(s.plugins ?? {})) t.add(n.script);
  let e = 0;
  return await Promise.all([...t].map(async (n) => {
    try {
      const i = await fetch(n, { credentials: "omit" });
      i.ok && (e += 1), await i.body?.cancel();
    } catch {
    }
  })), e;
}
const nt = "evac.player.program";
async function gs(s, t) {
  try {
    const e = await _(s, "playlists/program/", { token: t, timeout: 15e3 });
    try {
      e.program ? localStorage.setItem(nt, JSON.stringify(e.program)) : localStorage.removeItem(nt);
    } catch {
    }
    return e.program;
  } catch (e) {
    if (e instanceof E) throw e;
    return gt();
  }
}
function gt() {
  try {
    const s = localStorage.getItem(nt);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function vs() {
  try {
    localStorage.removeItem(nt);
  } catch {
  }
}
const $e = 1600;
function ys(s, t) {
  const e = [];
  for (const n of s ?? [])
    for (const [i, r] of n.windows)
      if ((i === null || i <= t) && (r === null || t < r)) {
        e.push({ overlay: n, start: i ?? 0, end: r });
        break;
      }
  return e.sort((n, i) => i.overlay.rank - n.overlay.rank || i.start - n.start);
}
function ws(s, t) {
  let e = null;
  for (const n of s ?? [])
    for (const [i, r] of n.windows)
      for (const a of [i, r])
        a !== null && a > t && (e === null || a < e) && (e = a);
  return e;
}
function bs(s) {
  return {
    card: s.find((t) => t.overlay.style === "card") ?? null,
    banner: s.find((t) => t.overlay.style === "banner") ?? null,
    ticker: s.filter((t) => t.overlay.style === "ticker")
  };
}
function Ss(s) {
  const t = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(s);
  if (!t) return "#ffffff";
  const [e, n, i] = t.slice(1).map((a) => {
    const o = parseInt(a, 16) / 255;
    return o <= 0.03928 ? o / 12.92 : ((o + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * e + 0.7152 * n + 0.0722 * i > 0.179 ? "#000000" : "#ffffff";
}
function C(s, t, e = "") {
  const n = document.createElement(s);
  return n.className = t, e && (n.textContent = e), n;
}
function ht(s, t) {
  s.style.setProperty("--ann-bg", /^#[0-9a-f]{6}$/i.test(t) ? t : "#2563eb"), s.style.setProperty("--ann-fg", Ss(t));
}
function Ee(s, t = 100) {
  if (s === "none" || typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const n = Math.max(0, Math.min(1, t / 100)) * 0.4, i = s === "chime" ? [[660, 0, 0.6], [880, 0.35, 0.9]] : s === "gong" ? [[196, 0, 2.5], [392, 0, 1.5], [294, 0.02, 2]] : [[880, 0, 0.25], [660, 0.3, 0.25], [880, 0.6, 0.25], [660, 0.9, 0.25]];
  let r = 0;
  for (const [a, o, c] of i) {
    const l = e.createOscillator(), h = e.createGain();
    l.type = s === "alert" ? "square" : "sine", l.frequency.value = a;
    const d = e.currentTime + o;
    h.gain.setValueAtTime(1e-4, d), h.gain.exponentialRampToValueAtTime(n, d + 0.02), h.gain.exponentialRampToValueAtTime(1e-4, d + c), l.connect(h).connect(e.destination), l.start(d), l.stop(d + c + 0.05), r = Math.max(r, o + c);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, (r + 0.5) * 1e3);
}
class ks {
  constructor(t) {
    this.speaker = t, this.drawn = "", this.heard = /* @__PURE__ */ new Set(), this.node = C("div", "ann-layer"), this.node.setAttribute("aria-live", "polite");
  }
  /** Keep the layer on top of the content (the display replaces its children on every slide). */
  attach(t) {
    (this.node.parentElement !== t || t.lastElementChild !== this.node) && t.appendChild(this.node);
  }
  update(t, e, n = {}) {
    const i = n.hidden ? [] : ys(t, e), { card: r, banner: a, ticker: o } = bs(i), c = n.audio?.enabled !== !1;
    for (const h of i) {
      const d = `${h.overlay.id}@${h.start}`, u = h.overlay.sound && h.overlay.sound !== "none";
      this.heard.has(d) || (this.heard.add(d), c && u && Ee(h.overlay.sound, n.audio?.volume ?? 100)), c && h.overlay.speech && this.speaker?.say(d, h.overlay.speech, { volume: n.audio?.volume, delayMs: u ? $e : 0 });
    }
    this.heard.size > 500 && (this.heard = new Set([...this.heard].slice(-100)));
    const l = JSON.stringify([
      r?.overlay.id,
      r?.overlay.title,
      r?.overlay.text,
      a?.overlay.id,
      a?.overlay.text,
      o.map((h) => [h.overlay.id, h.overlay.text])
    ]);
    if (l !== this.drawn) {
      if (this.drawn = l, this.node.replaceChildren(), r) {
        const h = C("section", "ann-card");
        ht(h, r.overlay.colour), h.append(C("p", "ann-level", r.overlay.level), C("h2", "ann-title", r.overlay.title)), r.overlay.text && r.overlay.text !== r.overlay.title && h.append(C("p", "ann-text", r.overlay.text)), this.node.append(h);
      }
      if (a) {
        const h = C("div", "ann-banner");
        ht(h, a.overlay.colour), h.append(C("span", "ann-level", a.overlay.level), C("span", "ann-text", a.overlay.text)), this.node.append(h);
      }
      if (o.length) {
        const h = C("div", "ann-ticker");
        ht(h, o[0].overlay.colour);
        const d = C("div", "ann-track"), u = o.map((m) => m.overlay.text).join("   ◆   "), g = C("span", "", u);
        g.setAttribute("aria-hidden", "true"), d.append(C("span", "", u), g), d.style.setProperty("--ann-duration", `${Math.max(12, Math.round(u.length / 6))}s`), h.append(C("span", "ann-level", o[0].overlay.level), d), this.node.append(h);
      }
      this.node.classList.toggle("has-bottom", !!(a && o.length));
    }
  }
}
class xs {
  constructor(t = (e) => new Audio(e)) {
    this.make = t, this.spoken = /* @__PURE__ */ new Set(), this.queue = [], this.playing = !1;
  }
  /** Speak ``url`` once for ``key`` (an announcement occurrence); later calls with the same key do nothing. */
  say(t, e, n = {}) {
    if (!e || this.spoken.has(t)) return !1;
    this.spoken.add(t), this.spoken.size > 500 && (this.spoken = new Set([...this.spoken].slice(-100)));
    const i = { url: e, volume: Math.max(0, Math.min(1, (n.volume ?? 100) / 100)) };
    return setTimeout(() => {
      this.queue.push(i), this.next();
    }, n.delayMs ?? 0), !0;
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
    const n = () => {
      this.playing = !1, this.next();
    };
    e.addEventListener("ended", n, { once: !0 }), e.addEventListener("error", n, { once: !0 });
    const i = e.play();
    i && typeof i.catch == "function" && i.catch(n);
  }
}
async function jt(s) {
  let t = 0;
  return await Promise.all([...new Set(s)].map(async (e) => {
    try {
      const n = await fetch(e, { credentials: "omit" });
      n.ok && (t += 1), await n.body?.cancel();
    } catch {
    }
  })), t;
}
const Tt = "evac.player.widgets";
function $s() {
  try {
    const s = localStorage.getItem(Tt);
    return s ? JSON.parse(s) : {};
  } catch {
    return {};
  }
}
async function Es(s, t, e) {
  try {
    const n = await _(s, "widgets/data/", { token: t, timeout: 15e3 });
    e.set(n.widgets ?? {});
    try {
      localStorage.setItem(Tt, JSON.stringify(n.widgets ?? {}));
    } catch {
    }
    return !0;
  } catch (n) {
    if (n instanceof E) throw n;
    return !1;
  }
}
function Cs() {
  try {
    localStorage.removeItem(Tt);
  } catch {
  }
}
const _t = "evac.player.schedule";
function Ms() {
  try {
    const s = localStorage.getItem(_t);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
async function As(s, t, e) {
  try {
    const n = await _(s, "schedule/", { token: t, timeout: 15e3 });
    e.set(n.sessions ? n : null);
    try {
      localStorage.setItem(_t, JSON.stringify(n));
    } catch {
    }
    return !0;
  } catch (n) {
    if (n instanceof E) throw n;
    return !1;
  }
}
function Ts() {
  try {
    localStorage.removeItem(_t);
  } catch {
  }
}
const _s = 5, Ns = 1e4;
function Is(s) {
  let t = 2166136261;
  for (let e = 0; e < s.length; e++)
    t ^= s.charCodeAt(e), t = Math.imul(t, 16777619) >>> 0;
  return t >>> 0;
}
function zs(s, t) {
  let e = t >>> 0 || 1;
  const n = [...s];
  for (let i = n.length - 1; i > 0; i--) {
    e = (e ^ e << 13) >>> 0, e = (e ^ e >>> 17) >>> 0, e = (e ^ e << 5) >>> 0;
    const r = e % (i + 1);
    [n[i], n[r]] = [n[r], n[i]];
  }
  return n;
}
function Ds(s, t) {
  const e = t.reduce((r, a) => r + a, 0), n = t.map(() => 0), i = [];
  for (let r = 0; r < e; r++) {
    t.forEach((o, c) => {
      n[c] += o;
    });
    let a = 0;
    for (let o = 1; o < s.length; o++) n[o] > n[a] && (a = o);
    n[a] -= e, i.push(s[a]);
  }
  return i;
}
function Ps(s, t, e) {
  if (s.from !== null && s.from !== void 0 && t < s.from || s.until !== null && s.until !== void 0 && t >= s.until) return !1;
  const n = s.tags ?? [], i = e.screen?.tags ?? [];
  return n.length && !n.some((r) => i.includes(r)) ? !1 : rt(s.when ?? "", e);
}
function vt(s, t, e, n, i, r = []) {
  const a = s.playlists[t];
  if (!a || r.includes(t) || r.length >= _s) return [];
  let o = [];
  const c = [];
  for (const l of a.items ?? []) {
    if (!Ps(l, n, e)) continue;
    let h = [];
    if (l.playlist) h = vt(s, l.playlist, e, n, i, [...r, t]);
    else if (l.layout && l.layout in s.layouts) {
      const d = l.duration || s.layouts[l.layout] || a.default || Ns;
      h = [{ layout: l.layout, duration: d, item: l.id }];
    }
    h.length && (o.push(h), c.push(Math.max(1, Math.trunc(l.weight || 1))));
  }
  return a.mode === "weighted" ? o = Ds(o, c) : a.mode === "shuffle" && (o = zs(o, Is(`${t}:${i}`))), o.flat();
}
function Os(s, t) {
  return (s[0] === null || s[0] <= t) && (s[1] === null || t < s[1]);
}
function Ls(s, t) {
  const e = [];
  return s.entries.forEach((n, i) => {
    const r = n.windows.find((a) => Os(a, t));
    r && e.push({ key: [-n.priority, -(r[0] ?? -1), i], entry: n, w: r });
  }), e.sort((n, i) => n.key[0] - i.key[0] || n.key[1] - i.key[1] || n.key[2] - i.key[2]), e.map((n) => [n.entry, n.w]);
}
function Rs(s, t, e, n, i) {
  const r = n.content, a = { entry: n.id, index: 0, count: 1, start: i[0], end: i[1] };
  if (r.message !== void 0) return r.message in (s.messages ?? {}) ? { ...a, message: r.message } : null;
  if (r.layout !== void 0) return r.layout in s.layouts ? { ...a, layout: r.layout } : null;
  const o = r.playlist, c = i[0] ?? 0;
  let l = vt(s, o, t, e, 0);
  const h = l.reduce((m, b) => m + b.duration, 0);
  if (!h) return null;
  const d = Math.floor((e - c) / h);
  d && (l = vt(s, o, t, e, d));
  let u = e - c - d * h, g = c + d * h;
  for (let m = 0; m < l.length; m++) {
    const b = l[m];
    if (u < b.duration) {
      let f = g + b.duration;
      return i[1] !== null && (f = Math.min(f, i[1])), { ...a, layout: b.layout, item: b.item, index: m, count: l.length, start: g, end: f };
    }
    u -= b.duration, g += b.duration;
  }
  return null;
}
function Bs(s, t, e) {
  for (const [n, i] of Ls(s, e)) {
    const r = Rs(s, t, e, n, i);
    if (r) return r;
  }
  return null;
}
function Fs(s, t, e) {
  const n = e?.end != null ? [e.end] : [];
  for (const i of s.entries)
    for (const [r, a] of i.windows)
      r !== null && r > t && n.push(r), a !== null && a > t && n.push(a);
  return n.length ? Math.min(...n) : null;
}
const Ws = "evac-player-content-v1", js = "content/theme/", Hs = /url\("([^"]+)"\)/g;
async function Ht(s, t) {
  const e = await caches.open(Ws).catch(() => null), n = await e?.match(s).catch(() => {
  });
  if (n) return n;
  const i = new AbortController(), r = setTimeout(() => i.abort(), 1e4);
  try {
    const a = await fetch(s, {
      headers: { Authorization: `Screen ${t}` },
      credentials: "omit",
      signal: i.signal
    });
    if (a.ok)
      return await e?.put(s, a.clone()), a;
  } catch {
  } finally {
    clearTimeout(r);
  }
  return null;
}
async function qs(s, t) {
  try {
    const e = await _(s, js, { token: t });
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
function Us(s) {
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
const qt = [];
async function Ut(s, t, e = document.documentElement) {
  const n = document.fonts;
  await Promise.all(Us(s.fonts_css).map(async (i) => {
    const r = await Ht(i.url, t);
    if (r)
      try {
        const a = new FontFace(i.family, await r.arrayBuffer(), {
          weight: i.weight,
          style: i.style,
          unicodeRange: i.unicodeRange
        });
        n.add(await a.load());
      } catch {
      }
  })), qt.splice(0).forEach((i) => URL.revokeObjectURL(i));
  for (const [i, r] of Object.entries(s.variables)) {
    let a = r;
    for (const o of r.matchAll(Hs)) {
      const c = await Ht(o[1], t);
      if (c) {
        const l = URL.createObjectURL(await c.blob());
        qt.push(l), a = a.replace(o[1], l);
      }
    }
    e.style.setProperty(i, a);
  }
  e.dataset.theme = s.key || "default";
}
function Js(s = document) {
  const t = s.getElementById("player-env"), e = t?.textContent ? JSON.parse(t.textContent) : {}, n = new URLSearchParams(s.location?.search ?? "");
  return {
    version: e.version ?? "dev",
    api: e.api ?? "/player/api/",
    ws: e.ws ?? "",
    strings: e.strings ?? {},
    mode: n.get("mode") === "obs" ? "obs" : "screen"
  };
}
function z(s, t, e = {}) {
  let n = s.strings[t] ?? t;
  for (const [i, r] of Object.entries(e)) n = n.replace(`{${i}}`, String(r));
  return n;
}
function Gs(s, t = location) {
  return s.ws ? s.ws.replace(/\/$/, "") + "/ws/screen/" : `${t.protocol === "https:" ? "wss" : "ws"}://${t.host}/ws/screen/`;
}
const Z = [], Q = [], Vs = Date.now(), Ks = 300;
let W = [], yt = null;
function M(s, t) {
  Q.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${s.toUpperCase()} ${t}`.slice(0, 500)), Q.length > Ks && Q.shift();
}
function Ys() {
  return [...Q];
}
function $(s) {
  Z.push(`${(/* @__PURE__ */ new Date()).toISOString()} ${s}`.slice(0, 300)), Z.length > 10 && Z.shift(), M("error", s);
  const t = Date.now();
  W = W.filter((e) => t - e < 6e4), W.push(t), W.length >= 50 && yt && (W = [], yt());
}
function Xs(s) {
  yt = s;
}
function Zs(s = window) {
  s.addEventListener("error", (t) => $(t.message || "error")), s.addEventListener("unhandledrejection", (t) => $(String(t.reason)));
  for (const t of ["warn", "info"]) {
    const e = console[t].bind(console);
    console[t] = (...n) => {
      M(t, n.map(String).join(" ")), e(...n);
    };
  }
}
function Jt(s) {
  const t = window.innerWidth, e = window.innerHeight, n = performance.memory;
  return {
    version: s.version,
    resolution: `${Math.round(t * devicePixelRatio)}x${Math.round(e * devicePixelRatio)}`,
    orientation: t >= e ? "landscape" : "portrait",
    uptime: Math.round((Date.now() - Vs) / 1e3),
    slide: s.slide,
    errors: [...Z],
    memory: n ? Math.round(n.usedJSHeapSize / 1048576) : null,
    last_sync: s.lastSync ? new Date(s.lastSync).toISOString() : null,
    online: s.online,
    user_agent: navigator.userAgent,
    ...s.contentVersion ? { content_version: s.contentVersion } : {},
    ...s.displayState ? { display_state: s.displayState } : {},
    ...s.capture !== void 0 ? { capture: s.capture } : {},
    ...s.recovered ? { recovered: s.recovered } : {},
    ...s.evacAck ? { evac_ack: s.evacAck } : {},
    ...s.evacBundle ? { evac_bundle: s.evacBundle } : {},
    ...s.evacAudio ? { evac_audio: s.evacAudio } : {}
  };
}
const Ce = "evac.player.reloads", st = "evac.player.alive", Qs = 3, ti = 10 * 6e4;
function Me(s) {
  try {
    return localStorage.getItem(s);
  } catch {
    return null;
  }
}
function at(s, t) {
  try {
    t === null ? localStorage.removeItem(s) : localStorage.setItem(s, t);
  } catch {
  }
}
function ei(s = Date.now()) {
  try {
    return JSON.parse(Me(Ce) ?? "[]").filter((t) => s - t < ti);
  } catch {
    return [];
  }
}
function tt(s, t = {}) {
  const e = Date.now(), n = ei(e);
  return !t.force && n.length >= Qs ? ($(`reload (${s}) skipped: ${n.length} reloads in the last 10 minutes`), !1) : (at(Ce, JSON.stringify([...n, e])), M("info", `reload: ${s}`), Ae(), (t.win ?? location).reload(), !0);
}
function ni(s = Date.now()) {
  const t = Me(st);
  if (at(st, String(s)), !t || t === "clean") return "";
  const e = Number(t);
  return Number.isFinite(e) ? `restarted after an unclean stop (last sign of life ${new Date(e).toISOString()})` : "";
}
function si(s = Date.now()) {
  at(st, String(s));
}
function Ae() {
  at(st, "clean");
}
function ii(s = window) {
  s.addEventListener("pagehide", () => Ae());
}
function ri() {
  const s = performance.memory;
  return !!s && s.jsHeapSizeLimit > 0 && s.usedJSHeapSize / s.jsHeapSizeLimit > 0.85;
}
function Te() {
  return typeof navigator < "u" && !!navigator.mediaDevices?.getDisplayMedia;
}
function ai(s, t, e) {
  return new Promise((n, i) => {
    const r = setTimeout(() => i(new Error(`${e} timed out`)), t);
    s.then((a) => {
      clearTimeout(r), n(a);
    }, (a) => {
      clearTimeout(r), i(a);
    });
  });
}
async function oi(s = 1e4) {
  return ai(ci(), s, "screen capture");
}
async function ci() {
  if (!Te()) throw new Error("screen capture is not available in this browser");
  const s = document.createElement("div");
  s.className = "evac-capture-dot", document.body.appendChild(s);
  let t = 0;
  const e = setInterval(() => s.classList.toggle("on", t++ % 2 === 0), 16);
  try {
    return await li();
  } finally {
    clearInterval(e), s.remove();
  }
}
async function li() {
  const s = await navigator.mediaDevices.getDisplayMedia({
    video: { displaySurface: "browser" },
    audio: !1,
    preferCurrentTab: !0,
    selfBrowserSurface: "include"
  });
  try {
    const t = document.createElement("video");
    t.muted = !0, t.srcObject = s, await t.play(), t.videoWidth || await new Promise((n) => t.addEventListener("loadeddata", n, { once: !0 }));
    const e = document.createElement("canvas");
    return e.width = t.videoWidth || window.innerWidth, e.height = t.videoHeight || window.innerHeight, e.getContext("2d")?.drawImage(t, 0, 0, e.width, e.height), t.srcObject = null, await new Promise((n, i) => e.toBlob((r) => r ? n(r) : i(new Error("encoding failed")), "image/jpeg", 0.85));
  } finally {
    s.getTracks().forEach((t) => t.stop());
  }
}
async function dt(s, t, e, n) {
  const i = typeof Blob < "u" && n instanceof Blob;
  await fetch(`${s}upload/${e}/`, {
    method: "POST",
    credentials: "omit",
    cache: "no-store",
    headers: { Authorization: `Screen ${t}`, "Content-Type": i ? n.type : "application/json" },
    body: i ? n : JSON.stringify(n)
  });
}
const hi = /* @__PURE__ */ new Set(["evac.player.token", "evac.player.evac", "evac.player.evacbundle", "evac.player.evacseq"]);
async function di() {
  try {
    if (typeof caches < "u") for (const s of await caches.keys()) await caches.delete(s);
  } catch {
  }
  try {
    for (const s of Object.keys(localStorage))
      s.startsWith("evac.player.") && !hi.has(s) && localStorage.removeItem(s);
  } catch {
  }
  try {
    for (const s of await navigator.serviceWorker?.getRegistrations?.() ?? []) await s.unregister();
  } catch {
  }
}
function ui(s) {
  const t = Math.max(1, Math.min(8, Math.round(s.wall_columns ?? 1))), e = Math.max(1, Math.min(8, Math.round(s.wall_rows ?? 1)));
  return t === 1 && e === 1 ? null : {
    cols: t,
    rows: e,
    col: Math.max(1, Math.min(t, Math.round(s.wall_column ?? 1))),
    row: Math.max(1, Math.min(e, Math.round(s.wall_row ?? 1))),
    bezel: Math.max(0, Math.min(10, s.wall_bezel ?? 0))
  };
}
function Gt(s, t) {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: t || void 0
    }).format(new Date(s));
  } catch {
    return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(s));
  }
}
function Vt(s, t, e) {
  return !t || !e || t === e ? !1 : t < e ? s >= t && s < e : s >= t || s < e;
}
function fi(s, t) {
  return Vt(t, s.sleep_from, s.sleep_until) ? "sleeping" : Vt(t, s.dim_from, s.dim_until) ? "dimmed" : "on";
}
function pi(s, t = !0) {
  const e = Number(s.rotation ?? 0) || 0, n = e === 90 || e === 270, i = t ? ui(s) : null;
  if (i) {
    const c = 100 + i.bezel, l = 100 + i.bezel, h = i.cols * 100 + (i.cols - 1) * i.bezel, d = i.rows * 100 + (i.rows - 1) * i.bezel, u = ((i.col - 1) * c + 50) / h * 100, g = ((i.row - 1) * l + 50) / d * 100;
    return {
      width: `${h}vw`,
      height: `${d}vh`,
      overscan: "0%",
      transform: `translate(${-u.toFixed(4)}%, ${-g.toFixed(4)}%)`
    };
  }
  const r = ["translate(-50%, -50%)"];
  e && r.push(`rotate(${e}deg)`), (s.keystone_x || s.keystone_y) && (r.push("perspective(1200px)"), s.keystone_y && r.push(`rotateX(${s.keystone_y}deg)`), s.keystone_x && r.push(`rotateY(${s.keystone_x}deg)`));
  const a = (s.scale ?? 100) / 100;
  a !== 1 && r.push(`scale(${a})`);
  const o = Math.max(0, Math.min(15, s.overscan ?? 0));
  return {
    width: n ? "100vh" : "100vw",
    height: n ? "100vw" : "100vh",
    transform: r.join(" "),
    overscan: `${o}%`
  };
}
function ut(s, t, e = !0) {
  const n = pi(t, e);
  s.classList.add("evac-root"), s.style.width = n.width, s.style.height = n.height, s.style.transform = n.transform, s.style.setProperty("--evac-overscan", n.overscan);
}
function mi(s, t, e = document) {
  let n = e.getElementById("evac-dim");
  if (s === "on") {
    n?.remove();
    return;
  }
  n || (n = e.createElement("div"), n.id = "evac-dim", n.setAttribute("aria-hidden", "true"), e.body.appendChild(n));
  const i = s === "sleeping" ? 0 : Math.max(10, Math.min(90, t.dim_level ?? 40));
  n.style.opacity = String(1 - i / 100), n.dataset.state = s;
}
const wt = "evac.player.token", Nt = "evac.player.config";
function gi() {
  try {
    return localStorage.getItem(wt);
  } catch {
    return null;
  }
}
function Kt(s) {
  try {
    s ? localStorage.setItem(wt, s) : (localStorage.removeItem(wt), localStorage.removeItem(Nt));
  } catch {
  }
}
function vi() {
  try {
    const s = localStorage.getItem(Nt);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}
function Yt(s) {
  try {
    localStorage.setItem(Nt, JSON.stringify(s));
  } catch {
  }
}
const D = (1n << 64n) - 1n, yi = [
  "428a2f98d728ae22",
  "7137449123ef65cd",
  "b5c0fbcfec4d3b2f",
  "e9b5dba58189dbbc",
  "3956c25bf348b538",
  "59f111f1b605d019",
  "923f82a4af194f9b",
  "ab1c5ed5da6d8118",
  "d807aa98a3030242",
  "12835b0145706fbe",
  "243185be4ee4b28c",
  "550c7dc3d5ffb4e2",
  "72be5d74f27b896f",
  "80deb1fe3b1696b1",
  "9bdc06a725c71235",
  "c19bf174cf692694",
  "e49b69c19ef14ad2",
  "efbe4786384f25e3",
  "0fc19dc68b8cd5b5",
  "240ca1cc77ac9c65",
  "2de92c6f592b0275",
  "4a7484aa6ea6e483",
  "5cb0a9dcbd41fbd4",
  "76f988da831153b5",
  "983e5152ee66dfab",
  "a831c66d2db43210",
  "b00327c898fb213f",
  "bf597fc7beef0ee4",
  "c6e00bf33da88fc2",
  "d5a79147930aa725",
  "06ca6351e003826f",
  "142929670a0e6e70",
  "27b70a8546d22ffc",
  "2e1b21385c26c926",
  "4d2c6dfc5ac42aed",
  "53380d139d95b3df",
  "650a73548baf63de",
  "766a0abb3c77b2a8",
  "81c2c92e47edaee6",
  "92722c851482353b",
  "a2bfe8a14cf10364",
  "a81a664bbc423001",
  "c24b8b70d0f89791",
  "c76c51a30654be30",
  "d192e819d6ef5218",
  "d69906245565a910",
  "f40e35855771202a",
  "106aa07032bbd1b8",
  "19a4c116b8d2d0c8",
  "1e376c085141ab53",
  "2748774cdf8eeb99",
  "34b0bcb5e19b48a8",
  "391c0cb3c5c95a63",
  "4ed8aa4ae3418acb",
  "5b9cca4f7763e373",
  "682e6ff3d6b2b8a3",
  "748f82ee5defb2fc",
  "78a5636f43172f60",
  "84c87814a1f0ab72",
  "8cc702081a6439ec",
  "90befffa23631e28",
  "a4506cebde82bde9",
  "bef9a3f7b2c67915",
  "c67178f2e372532b",
  "ca273eceea26619c",
  "d186b8c721c0c207",
  "eada7dd6cde0eb1e",
  "f57d4f7fee6ed178",
  "06f067aa72176fba",
  "0a637dc5a2c898a6",
  "113f9804bef90dae",
  "1b710b35131c471b",
  "28db77f523047d84",
  "32caab7b40c72493",
  "3c9ebe0a15c9bebc",
  "431d67c49c100d4c",
  "4cc5d4becb3e42b6",
  "597f299cfc657e2a",
  "5fcb6fab3ad6faec",
  "6c44198c4a475817"
].map((s) => BigInt(`0x${s}`)), wi = [
  "6a09e667f3bcc908",
  "bb67ae8584caa73b",
  "3c6ef372fe94f82b",
  "a54ff53a5f1d36f1",
  "510e527fade682d1",
  "9b05688c2b3e6c1f",
  "1f83d9abfb41bd6b",
  "5be0cd19137e2179"
].map((s) => BigInt(`0x${s}`)), T = (s, t) => (s >> t | s << 64n - t) & D;
function bi(s) {
  const t = BigInt(s.length) * 8n, e = s.length + 17 + 127 & -128, n = new Uint8Array(e);
  n.set(s), n[s.length] = 128;
  for (let o = 0; o < 16; o++) n[e - 1 - o] = Number(t >> BigInt(8 * o) & 0xffn);
  const i = [...wi], r = new Array(80);
  for (let o = 0; o < e; o += 128) {
    for (let f = 0; f < 16; f++) {
      let S = 0n;
      for (let k = 0; k < 8; k++) S = S << 8n | BigInt(n[o + f * 8 + k]);
      r[f] = S;
    }
    for (let f = 16; f < 80; f++) {
      const S = T(r[f - 15], 1n) ^ T(r[f - 15], 8n) ^ r[f - 15] >> 7n, k = T(r[f - 2], 19n) ^ T(r[f - 2], 61n) ^ r[f - 2] >> 6n;
      r[f] = r[f - 16] + S + r[f - 7] + k & D;
    }
    let [c, l, h, d, u, g, m, b] = i;
    for (let f = 0; f < 80; f++) {
      const S = T(u, 14n) ^ T(u, 18n) ^ T(u, 41n), k = u & g ^ ~u & D & m, H = b + S + k + yi[f] + r[f] & D, ze = T(c, 28n) ^ T(c, 34n) ^ T(c, 39n), De = c & l ^ c & h ^ l & h, Pe = ze + De & D;
      b = m, m = g, g = u, u = d + H & D, d = h, h = l, l = c, c = H + Pe & D;
    }
    [c, l, h, d, u, g, m, b].forEach((f, S) => {
      i[S] = i[S] + f & D;
    });
  }
  const a = new Uint8Array(64);
  return i.forEach((o, c) => {
    for (let l = 0; l < 8; l++) a[c * 8 + l] = Number(o >> BigInt(56 - 8 * l) & 0xffn);
  }), a;
}
const P = (1n << 255n) - 19n, Xt = (1n << 252n) + 27742317777372353535851937790883648493n, w = (s, t = P) => {
  const e = s % t;
  return e >= 0n ? e : e + t;
};
function j(s, t, e = P) {
  let n = 1n;
  for (s = w(s, e); t > 0n; )
    t & 1n && (n = n * s % e), s = s * s % e, t >>= 1n;
  return n;
}
const _e = (s) => j(s, P - 2n), Ne = w(-121665n * _e(121666n)), Si = j(2n, (P - 1n) / 4n), ki = [0n, 1n, 1n, 0n];
function bt(s, t) {
  const [e, n, i, r] = s, [a, o, c, l] = t, h = w((n - e) * (o - a)), d = w((n + e) * (o + a)), u = w(2n * Ne * r * l), g = w(2n * i * c), m = d - h, b = g - u, f = g + u, S = d + h;
  return [w(m * b), w(f * S), w(b * f), w(m * S)];
}
function Zt(s, t) {
  let e = ki, n = s;
  for (; t > 0n; )
    t & 1n && (e = bt(e, n)), n = bt(n, n), t >>= 1n;
  return e;
}
const St = (s) => s.reduceRight((t, e) => t << 8n | BigInt(e), 0n);
function kt(s) {
  if (s.length !== 32) return null;
  const t = (s[31] & 128) !== 0, e = s.slice();
  e[31] &= 127;
  const n = St(e);
  if (n >= P) return null;
  const i = w(n * n), r = w(i - 1n), a = w(Ne * i + 1n);
  let o = w(r * j(a, 3n) * j(r * j(a, 7n), (P - 5n) / 8n));
  const c = w(a * o * o);
  if (c === w(-r)) o = w(o * Si);
  else if (c !== r) return null;
  return o === 0n && t ? null : ((o & 1n) === 1n ? t || (o = P - o) : t && (o = P - o), [o, n, 1n, w(o * n)]);
}
function Qt(s) {
  const t = _e(s[2]), e = w(s[0] * t), n = w(s[1] * t), i = new Uint8Array(32);
  let r = n;
  for (let a = 0; a < 32; a++)
    i[a] = Number(r & 0xffn), r >>= 8n;
  return e & 1n && (i[31] |= 128), i;
}
const xi = kt(Uint8Array.from([88, ...new Array(31).fill(102)]));
function $i(s, t, e) {
  if (e.length !== 64 || s.length !== 32) return !1;
  const n = kt(s), i = kt(e.slice(0, 32)), r = St(e.slice(32));
  if (!n || !i || r >= Xt) return !1;
  const a = bi(Uint8Array.from([...e.slice(0, 32), ...s, ...t])), o = w(St(a), Xt), c = Qt(Zt(xi, r)), l = Qt(bt(i, Zt(n, o)));
  return c.every((h, d) => h === l[d]);
}
function te(s) {
  const t = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4), e = atob(t);
  return Uint8Array.from(e, (n) => n.charCodeAt(0));
}
function It(s, t) {
  if (!t || typeof t.m != "string" || typeof t.s != "string") return null;
  const e = new TextEncoder().encode(t.m);
  for (const n of s)
    try {
      if ($i(te(n), e, te(t.s))) return JSON.parse(t.m);
    } catch {
    }
  return null;
}
const Ei = ["staff_alert", "attention", "shelter_in_place", "evacuate"], Ci = {
  normal: 0,
  all_clear: 1,
  staff_alert: 2,
  attention: 3,
  shelter_in_place: 4,
  evacuate: 5
}, Mi = 10 * 6e4, ee = { motion: !1, reducedMotion: !0, slide: null }, ne = "evac.player.evac", se = "evac.player.evacbundle", it = (s) => Ei.includes(s);
function xt(s, t) {
  return s.state === "all_clear" && s.clear_until && Date.parse(s.clear_until) <= t ? "normal" : s.state;
}
function Ai(s, t, e) {
  if (!s) return !0;
  if (t.seq < s.seq || t.seq === s.seq && t.v === s.v) return !1;
  if (!it(t.state) && it(xt(s, e))) {
    const i = t.issued ?? (t.sig ? Number(JSON.parse(t.sig.m).ia) * 1e3 : e);
    if (e - i > Mi) return !1;
  }
  return !0;
}
function Ti(s, t) {
  const e = s.map((a) => a.st === "all_clear" && a.cu && a.cu <= t ? { st: "normal", d: !1 } : a), n = e.some((a) => it(a.st) && !a.d);
  let i = { st: "normal", d: !1 };
  const r = (a) => [Ci[a.st] ?? 0, a.d ? 0 : 1];
  for (const a of n ? e.filter((o) => !o.d) : e) {
    const [o, c] = r(a), [l, h] = r(i);
    (o > l || o === l && c > h) && (i = a);
  }
  return i;
}
function $t(s, t, e, n = []) {
  const i = s.stages[t], r = s.directions[n.slice().sort().join(",")];
  return {
    event: s.event,
    screen: s.screen,
    seq: 0,
    v: "",
    state: t,
    label: s.labels[t] ?? i?.label ?? t,
    drill: e,
    drill_text: s.drill_text,
    since: null,
    clear_until: null,
    takeover: i?.takeover ?? !1,
    role: s.role,
    model: s.model,
    guidance: r ? { kind: r.kind, arrow: r.arrow, text: r.text, target: r.target } : { kind: s.model === "zones" ? "follow_staff" : "none", arrow: null, text: "", target: "" },
    direction: r?.direction ?? "",
    texts: i?.texts ?? [],
    rotate_seconds: i?.rotate_seconds ?? 8,
    pictograms_only: i?.pictograms_only ?? !1,
    sound: i?.sound ?? "none",
    sound_every: i?.sound_every ?? 30,
    speech: i?.speech ?? "",
    layout: i?.layout ?? null
  };
}
function _i(s, t, e) {
  const n = It(t.keys, s);
  if (!n || n.e !== t.event || typeof n.seq != "number" || !n.ev || typeof n.ev.st != "string")
    return null;
  const i = [n.ev, ...Object.values(n.z ?? {})];
  if (n.is && i.some((o) => !it(o.st) && o.st !== "normal")) return null;
  const r = Ti([n.ev, ...t.zones.map((o) => n.z?.[o]).filter((o) => !!o)], e), a = i.find((o) => o.st === r.st && o.cu);
  return {
    ...$t(t, r.st, r.d, n.b ?? []),
    seq: n.seq,
    v: `fb-${n.seq}-${r.st}-${r.d}`,
    clear_until: a?.cu ? new Date(a.cu).toISOString() : null,
    issued: n.ia * 1e3,
    sig: s,
    via: "fallback"
  };
}
function ie(s) {
  const t = s.texts.length ? [...s.texts] : [""];
  return s.pictograms_only && s.texts.length && t.push(""), t;
}
function re(s, t) {
  return s === "evacuate" ? t && ["left", "back_left", "ahead_left"].includes(t) ? "E001" : "E002" : s === "all_clear" ? "check" : "W001";
}
function ae(s) {
  try {
    const t = localStorage.getItem(s);
    return t ? JSON.parse(t) : null;
  } catch {
    return null;
  }
}
function oe(s, t) {
  try {
    localStorage.setItem(s, JSON.stringify(t));
  } catch {
  }
}
class Ni {
  constructor(t, e = document) {
    this.opts = t, this.payload = ae(ne), this.bundle = ae(se), this.rendered = null, this.rotation = null, this.sound = null, this.expiry = null, this.frame = 0, this.shownKey = "", this.layer = e.createElement("div"), this.layer.id = "evac-layer", this.layer.hidden = !0, e.body.appendChild(this.layer);
  }
  t(t) {
    return this.opts.strings[t] ?? t;
  }
  setBundle(t) {
    t && (this.bundle = t, oe(se, t));
  }
  /** Offer a payload from any path; returns whether it was taken. */
  offer(t, e) {
    return !t || this.bundle && t.event !== this.bundle.event && this.payload && t.event !== this.payload.event || e === "fallback" && !t.sig || !Ai(this.payload, t, this.opts.now()) ? !1 : (this.payload = { ...t, via: e }, oe(ne, this.payload), this.render(!0), !0);
  }
  /** A signed event-wide message from a fallback origin. */
  offerFallback(t) {
    if (!this.bundle) return !1;
    const e = _i(t, this.bundle, this.opts.now());
    return e ? this.offer(e, "fallback") : !1;
  }
  /** Self-test (ADR-0034): render every stage off screen (own layout and built-in), check the signature of the
   *  current message, the audio permission and each fallback origin. ``visible`` also shows a test frame for
   *  ``seconds`` (never over a running alarm). */
  async selfTest(t) {
    const e = this.opts.now(), n = this.bundle, i = {}, r = document.createElement("div");
    r.className = "evac-selftest-host", r.setAttribute("aria-hidden", "true"), document.body.append(r);
    try {
      for (const u of Object.keys(n?.stages ?? {})) i[u] = this.testStage(r, $t(n, u, !1));
    } finally {
      r.remove();
    }
    const a = this.payload?.sig, o = a ? n && It(n.keys, a) ? "ok" : "invalid" : "missing", c = {};
    for (const u of n?.fallback_origins ?? []) c[u] = await Ii(u, n, t.fetcher);
    const l = this.opts.audio().enabled ? await Ie() : "off";
    let h = !1;
    return t.visible && n && !this.active && (h = !0, this.showTest(n, t.seconds)), {
      ok: !!n && !Object.values(i).some((u) => u.startsWith("error")) && o !== "invalid" && !Object.values(c).some((u) => u !== "ok"),
      at: e,
      ms: Math.round(this.opts.now() - e),
      bundle: n?.version ?? null,
      keys: n?.keys.length ?? 0,
      signature: o,
      stages: i,
      audio: l,
      origins: c,
      visible: h
    };
  }
  testStage(t, e) {
    const n = document.createElement("div");
    n.className = "evac-takeover", t.replaceChildren(n);
    let i = "ok";
    if (e.layout) {
      let r = "";
      try {
        const a = this.opts.context();
        et(n, e.layout, {
          ...a,
          ...ee,
          vars: this.vars(e, e.texts[0] ?? ""),
          onError: (o, c) => {
            r = r || `${o}: ${String(c)}`;
          }
        }).destroy();
      } catch (a) {
        r = String(a);
      }
      r && (i = `fallback (${r})`.slice(0, 120));
    }
    try {
      if (n.replaceChildren(this.fallbackLayout(e, e.state, e.texts[0] ?? "")), !n.querySelector("svg")) return "error: no sign";
    } catch (r) {
      return `error: ${String(r)}`.slice(0, 120);
    }
    return i;
  }
  showTest(t, e) {
    const n = {
      ...$t(t, "evacuate", !0),
      label: this.t("Self-test"),
      texts: [this.t("This is a test. There is no alarm.")],
      drill_text: this.t("TEST")
    };
    this.stop(), this.layer.replaceChildren(), this.layer.hidden = !1, this.layer.dataset.mode = "test";
    const i = document.createElement("div");
    i.className = "evac-takeover evac-stage-test", i.append(this.fallbackLayout(n, "evacuate", n.texts[0])), this.layer.append(i), this.drawDrill(n), this.expiry = setTimeout(() => this.render(!0), Math.max(2, Math.min(e || 5, 60)) * 1e3);
  }
  /** Whether the screen is taken over (normal content is hidden). */
  get active() {
    const t = this.payload;
    if (!t) return !1;
    const e = xt(t, this.opts.now());
    return t.role === "participant" && t.takeover && e !== "normal";
  }
  /** Draw the current payload. ``force`` redraws even when nothing visible changed (a new message). */
  render(t = !1) {
    const e = this.payload, n = this.opts.now(), i = e ? xt(e, n) : "normal", r = e?.role ?? "participant", o = !!e && r !== "excluded" && i !== "normal" && i !== "staff_alert" ? e.takeover && r === "participant" ? "takeover" : "banner" : "none", c = `${o}|${e?.seq}|${e?.v}|${i}`;
    if (!t && c === this.shownKey || (this.shownKey = c, this.stop(), this.layer.replaceChildren(), this.layer.hidden = o === "none", this.layer.dataset.mode = o, this.layer.dataset.state = i, document.documentElement.classList.toggle("evac-active", o === "takeover"), this.opts.onChange?.(o === "takeover"), !e)) return;
    if (e.state === "all_clear" && e.clear_until) {
      const h = Date.parse(e.clear_until) - n;
      h > 0 && (this.expiry = setTimeout(() => this.render(!0), Math.min(h + 50, 2147e6)));
    }
    let l = !1;
    o === "takeover" ? l = this.drawTakeover(e, i) : o === "banner" && this.drawBanner(e, i), o !== "none" && e.drill && this.drawDrill(e), o !== "none" && this.startAudio(e), this.opts.onRendered(e, { fallback: l, rendered_at: this.opts.now() });
  }
  vars(t, e) {
    return {
      ...this.opts.context().vars,
      evac: {
        stage: t.label,
        state: t.state,
        text: e,
        direction: t.direction || this.followStaff(t),
        target: t.guidance.target,
        arrow: t.guidance.arrow,
        drill: t.drill ? t.drill_text : ""
      }
    };
  }
  followStaff(t) {
    return t.guidance.kind === "follow_staff" && t.state === "evacuate" ? this.t("Follow the instructions of the staff") : "";
  }
  drawTakeover(t, e) {
    const n = document.createElement("div");
    n.className = `evac-takeover evac-stage-${e}`, this.layer.append(n);
    const i = ie(t), r = () => {
      const o = i[this.frame % i.length];
      if (t.layout) {
        let c = !1;
        try {
          this.rendered?.destroy(), n.replaceChildren();
          const l = this.opts.context();
          this.rendered = et(n, t.layout, {
            ...l,
            ...ee,
            vars: this.vars(t, o),
            onError: (h, d) => {
              c = !0, l.onError?.(h, d);
            }
          });
        } catch {
          c = !0;
        }
        if (!c) return !1;
        this.rendered?.destroy(), this.rendered = null;
      }
      return n.replaceChildren(this.fallbackLayout(t, e, o)), !0;
    }, a = r();
    return i.length > 1 && (this.rotation = setInterval(
      () => {
        this.frame += 1, r();
      },
      Math.max(3, t.rotate_seconds || 8) * 1e3
    )), a;
  }
  /** The built-in layout every screen keeps in its code: sign(s), stage, text, direction. */
  fallbackLayout(t, e, n) {
    const i = document.createElement("div");
    i.className = `evac-fb evac-fb-${e}`;
    const r = document.createElement("div");
    r.className = "evac-fb-signs";
    const a = t.guidance.arrow, o = re(e, a);
    r.innerHTML = (o === "check" ? cn() : Y(o, "ahead")) + (e === "evacuate" && a ? Y("arrow", a) : "");
    const c = document.createElement("h1");
    if (c.className = "evac-fb-label", c.textContent = t.label, i.append(r, c), n) {
      const h = document.createElement("p");
      h.className = "evac-fb-text", h.textContent = n, i.append(h);
    }
    const l = t.direction || this.followStaff(t);
    if (l && e === "evacuate") {
      const h = document.createElement("p");
      h.className = "evac-fb-dir", h.textContent = l, i.append(h);
    }
    return i;
  }
  drawBanner(t, e) {
    const n = document.createElement("div");
    n.className = `evac-banner evac-stage-${e}`, n.setAttribute("role", "alert");
    const i = ie(t).filter(Boolean), r = document.createElement("span");
    r.className = "evac-banner-icon", r.innerHTML = Y(e === "evacuate" ? re(e, t.guidance.arrow) : "W001");
    const a = document.createElement("strong");
    a.textContent = t.label;
    const o = document.createElement("span");
    o.className = "evac-banner-text", o.textContent = i[0] ?? "", n.append(r, a, o), this.layer.append(n), i.length > 1 && (this.rotation = setInterval(
      () => {
        this.frame += 1, o.textContent = i[this.frame % i.length];
      },
      Math.max(3, t.rotate_seconds || 8) * 1e3
    ));
  }
  drawDrill(t) {
    const e = document.createElement("div");
    e.className = "evac-drill", e.textContent = t.drill_text || "DRILL", this.layer.append(e);
  }
  startAudio(t) {
    const e = this.opts.audio();
    if (!e.enabled || t.role !== "participant") return;
    const n = (r) => {
      t.sound && t.sound !== "none" && zi(t.sound, e.volume), t.speech && this.opts.speaker.say(`evac:${t.seq}:${t.v}:${r}`, t.speech, {
        volume: e.volume,
        delayMs: t.sound !== "none" ? 2600 : 0
      });
    };
    if ((!t.sound || t.sound === "none") && !t.speech) return;
    let i = 0;
    n(i), this.sound = setInterval(() => n(++i), Math.max(5, t.sound_every || 30) * 1e3);
  }
  stop() {
    this.rotation && clearInterval(this.rotation), this.sound && clearInterval(this.sound), this.expiry && clearTimeout(this.expiry), this.rotation = this.sound = this.expiry = null, this.rendered?.destroy(), this.rendered = null, this.frame = 0;
  }
}
async function Ie() {
  if (typeof AudioContext > "u") return "unavailable";
  let s;
  try {
    s = new AudioContext();
  } catch {
    return "unavailable";
  }
  try {
    return s.state === "suspended" && await Promise.race([s.resume(), new Promise((t) => setTimeout(t, 300))]), s.state === "running" ? "running" : "suspended";
  } finally {
    s.close().catch(() => {
    });
  }
}
async function Ii(s, t, e = fetch) {
  const n = typeof AbortController < "u" ? new AbortController() : null, i = setTimeout(() => n?.abort(), 3e3);
  try {
    const r = await e(`${s}/evac/${t.event}/state`, { cache: "no-store", signal: n?.signal });
    if (!r.ok) return `http ${r.status}`;
    const a = await r.json();
    return a.sig && It(t.keys, a.sig) ? "ok" : "bad signature";
  } catch {
    return "unreachable";
  } finally {
    clearTimeout(i);
  }
}
function zi(s, t = 100) {
  if (s !== "siren") return Ee(s, t);
  if (typeof AudioContext > "u") return;
  let e;
  try {
    e = new AudioContext();
  } catch {
    return;
  }
  const n = e.createGain();
  n.gain.value = Math.max(0, Math.min(1, t / 100)) * 0.35, n.connect(e.destination);
  for (let i = 0; i < 3; i++) {
    const r = e.createOscillator();
    r.type = "sawtooth";
    const a = e.currentTime + i * 0.8;
    r.frequency.setValueAtTime(500, a), r.frequency.linearRampToValueAtTime(1100, a + 0.7), r.connect(n), r.start(a), r.stop(a + 0.75);
  }
  setTimeout(() => {
    e.close().catch(() => {
    });
  }, 3e3);
}
const Di = ["fade", "slide-left", "slide-up", "zoom"], Pi = 5e3, Oi = 50;
function Li(s) {
  return s ? s.source === "announcement" || s.source === "evacuation" || s.id.startsWith("evacuation") || s.id.startsWith("announcement:") || s.level === "emergency" : !1;
}
function Ri(s, t, e = {}) {
  if (!s || !t?.item || e.reduced || e.urgent) return null;
  let n;
  for (const r of Object.values(s.playlists ?? {})) {
    const a = r.items?.find((o) => o.id === t.item);
    if (a) {
      n = a.transition;
      break;
    }
  }
  if (!n || !Di.includes(n.effect)) return null;
  let i = Math.min(Number(n.ms) || 0, Pi);
  return t.start !== null && t.end !== null && (i = Math.min(i, (t.end - t.start) / 2)), i >= Oi ? { effect: n.effect, ms: Math.round(i) } : null;
}
const ce = 3e3;
function G(s) {
  document.documentElement.dataset.boot = s;
}
const le = 6e4, Bi = 36e5, Fi = 3e5, he = 15e3, Wi = 6e4, ji = 3e3;
class Hi {
  constructor(t, e) {
    this.env = t, this.root = e, this.clock = new Fe(), this.speaker = new xs(), this.widgetData = new Jn($s()), this.schedule = new Kn(Ms()), this.dataRefresher = null, this.overlays = new ks(this.speaker), this.conn = null, this.config = null, this.transport = "connecting", this.lastSync = null, this.slide = "idle", this.bundle = null, this.plugins = null, this.program = null, this.shown = "", this.shownSlide = "", this.timer = null, this.refresher = null, this.housekeeping = null, this.displayState = "on", this.recovered = "", this.lastTick = Date.now(), this.reloadAtNextSlide = "", this.lastDailyReload = "", this.evac = null, this.evacAck = "", this.evacAudio = "", this.evacTimer = null, this.fallbackTimer = null, this.display = new ds(e, this.clock), t.mode === "obs" && document.documentElement.classList.add("obs");
  }
  async boot() {
    G("boot"), this.recovered = ni(), M("info", `player ${this.env.version} started (${navigator.userAgent})`), this.recovered && M("warn", this.recovered);
    const t = gi();
    return t ? this.play(t) : this.pair();
  }
  // ---------------------------------------------------------------- pairing
  async pair() {
    const t = {
      title: z(this.env, "pair_title"),
      step1: z(this.env, "pair_step1"),
      step2: z(this.env, "pair_step2"),
      waiting: z(this.env, "pair_waiting")
    };
    let e;
    try {
      e = await Re(this.env.api, Jt({
        version: this.env.version,
        slide: "pairing",
        lastSync: null,
        online: !0
      }));
    } catch (i) {
      $(String(i)), this.display.message(z(this.env, "no_server"), z(this.env, "retrying")), setTimeout(() => {
        this.pair();
      }, 1e4);
      return;
    }
    this.display.pairing(e.code, e.pair_url, t);
    const n = async () => {
      try {
        const i = await Be(this.env.api, e);
        if (i.status === "paired")
          return Kt(i.token), this.play(i.token);
        if (i.status !== "pending") return this.pair();
      } catch (i) {
        $(String(i));
      }
      setTimeout(() => {
        n();
      }, ce);
    };
    setTimeout(() => {
      n();
    }, ce);
  }
  // ---------------------------------------------------------------- playing
  async play(t) {
    const e = vi();
    this.evac = this.evac ?? this.makeEvac(t), e && ut(this.evac.layer, e.display ?? {}, !1), this.evac.render(!0), G(e ? "play: cached config" : "play: no cached config"), e && (this.config = e, this.bundle = mt(), this.program = gt(), this.applySettings(), this.bundle && Ut({ ...this.bundle.theme, fonts_css: this.bundle.fonts_css }, t).catch((n) => $(String(n))), this.show(), G("play: shown from cache"));
    try {
      const n = Date.now();
      this.config = await zt(this.env.api, t), this.clock.add(n, Date.now(), this.config.server_time), this.lastSync = Date.now(), Yt(this.config);
    } catch (n) {
      if (n instanceof E) return this.unpair();
      $(String(n)), this.config = e;
    }
    this.applySettings(), this.bundle = this.bundle ?? mt(), this.program = this.program ?? gt(), this.plugins = ts(
      () => this.bundle?.plugins ?? {},
      `${this.env.api}content/sources/`,
      () => ({ Authorization: `Screen ${t}` }),
      !0
    ), await this.loadContent(t), await this.loadProgram(t), this.show(), this.loadEvac(t), Ie().then((n) => {
      this.evacAudio = n;
    }), this.evacTimer = setInterval(() => {
      this.loadEvac(t);
    }, Wi), this.fallbackTimer = setInterval(() => {
      this.pollFallback();
    }, ji), G("play: online"), this.refresher = setInterval(() => {
      this.loadProgram(t).then(() => this.show());
    }, Bi), this.loadWidgetData(t), this.loadSchedule(t), this.dataRefresher = setInterval(() => {
      this.loadWidgetData(t), this.loadSchedule(t);
    }, Fi), this.housekeeping = setInterval(() => this.tick(), he), this.conn = new He({
      api: this.env.api,
      ws: Gs(this.env),
      token: t,
      clock: this.clock,
      heartbeatSeconds: this.config?.settings.heartbeat_seconds ?? 10,
      since: this.config?.seq ?? 0,
      report: () => Jt({
        version: this.env.version,
        slide: this.slide,
        lastSync: this.lastSync,
        online: this.transport !== "offline",
        displayState: this.displayState,
        capture: Te(),
        recovered: this.recovered,
        evacAck: this.evacAck,
        evacBundle: this.evac?.bundle?.version,
        evacAudio: this.evacAudio
      }),
      onMessage: (n) => {
        this.handle(n, t);
      },
      onTransport: (n) => {
        n !== this.transport && (M("info", `connection: ${n}`), (this.transport === "offline" || this.transport === "connecting") && this.loadEvac(t)), this.transport = n;
      },
      onUnauthorized: () => this.unpair(),
      onSync: (n) => {
        this.lastSync = n;
      }
    }), this.conn.start();
  }
  async handle(t, e) {
    switch (M("info", `message: ${t.type}`), t.type) {
      case "config.changed":
        try {
          this.config = await zt(this.env.api, e), Yt(this.config), this.lastSync = Date.now(), this.conn?.setHeartbeat(this.config.settings.heartbeat_seconds), this.applySettings();
          const n = `${this.bundle?.version}/${this.program?.version}`;
          await this.loadContent(e), await this.loadProgram(e), (`${this.bundle?.version}/${this.program?.version}` !== n || this.slide === "idle") && (this.shown = "", this.show());
        } catch (n) {
          n instanceof E && this.unpair();
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
        const n = Math.max(0, Math.min(60, Number(t.data?.spread) || 0));
        window.setTimeout(() => {
          const i = this.program?.version;
          this.loadProgram(e).then(() => {
            this.program?.version !== i && (this.shown = "", this.show());
          });
        }, Math.random() * n * 1e3);
        break;
      }
      case "data.changed":
        await this.loadWidgetData(e);
        break;
      case "schedule.changed":
        await this.loadSchedule(e);
        break;
      case "evac.state":
        this.evac?.offer(t.data, this.transport);
        break;
      case "evac.bundle":
        this.loadEvac(e);
        break;
      case "evac.selftest": {
        if (!this.evac) break;
        await this.loadEvac(e);
        const n = await this.evac.selfTest({ visible: !!t.data.visible, seconds: Number(t.data.seconds) || 5 });
        this.evacAudio = n.audio, M("info", `evacuation self-test: ${n.ok ? "ok" : "problems"}`), await fetch(`${this.env.api}evacuation/selftest/`, {
          method: "POST",
          headers: { Authorization: `Screen ${e}`, "Content-Type": "application/json" },
          body: JSON.stringify(n)
        }).catch((i) => $(`self-test report: ${String(i)}`));
        break;
      }
      case "reload":
        tt("requested by staff", { force: !0 });
        break;
      case "clear_cache":
        await di(), tt("cache cleared by staff", { force: !0 });
        break;
      case "test_pattern": {
        const n = this.config?.screen.name ?? "", i = `${Math.round(innerWidth * devicePixelRatio)}×${Math.round(innerHeight * devicePixelRatio)}`;
        this.display.testPattern(
          n,
          [`${i} · DPR ${devicePixelRatio}`, `${this.env.version} · ${this.transport}`],
          Number(t.data.seconds) || 30
        );
        break;
      }
      case "screenshot":
        try {
          await dt(this.env.api, e, "screenshot", await oi());
        } catch (n) {
          $(`screenshot: ${String(n)}`), await dt(this.env.api, e, "screenshot", { error: String(n).slice(0, 280) }).catch(() => {
          });
        }
        break;
      case "logs":
        await dt(this.env.api, e, "logs", { lines: Ys() }).catch((n) => $(String(n)));
        break;
    }
  }
  /** Theme, fonts and layouts (bundle); falls back to the theme alone if the content module is off. */
  async loadContent(t) {
    try {
      this.bundle = await us(this.env.api, t) ?? this.bundle;
    } catch (n) {
      if (n instanceof E) return this.unpair();
    }
    const e = this.bundle ? { ...this.bundle.theme, fonts_css: this.bundle.fonts_css } : await qs(this.env.api, t);
    e && await Ut(e, t).catch((n) => $(String(n))), this.bundle && ms(this.bundle);
  }
  async loadProgram(t) {
    try {
      this.program = await gs(this.env.api, t);
    } catch (n) {
      n instanceof E && this.unpair();
    }
    const e = [...this.program?.entries ?? [], ...this.program?.overlays ?? []].map((n) => n.speech).filter((n) => !!n);
    e.length && jt(e);
  }
  /** The program: "program" elements redraw themselves when the store changes. */
  async loadSchedule(t) {
    try {
      await As(this.env.api, t, this.schedule);
    } catch (e) {
      e instanceof E && this.unpair();
    }
  }
  /** Custom widget rows: "data" elements redraw themselves when the store changes. */
  async loadWidgetData(t) {
    try {
      await Es(this.env.api, t, this.widgetData);
    } catch (e) {
      e instanceof E && this.unpair();
    }
  }
  // ---------------------------------------------------------------- evacuation (ADR-0033/0034)
  makeEvac(t) {
    return new Ni({
      now: () => this.clock.now(),
      speaker: this.speaker,
      audio: () => ({ enabled: this.config?.display?.audio !== !1, volume: this.config?.display?.volume ?? 100 }),
      strings: this.env.strings,
      context: () => ({
        vars: this.config ? this.vars() : {},
        now: () => this.clock.now(),
        timezone: this.config?.event.timezone,
        assets: this.bundle?.assets ?? {},
        fonts: this.bundle?.fonts ?? {},
        nonce: Ot(),
        data: this.widgetData,
        program: this.schedule,
        plugins: this.plugins ?? void 0,
        onError: (e, n) => $(`evac ${e}: ${String(n)}`)
      }),
      onRendered: (e, n) => {
        this.evacAck = `${e.seq}:${e.v}`.slice(0, 40), M("info", `evacuation: ${e.state}${e.drill ? " (drill)" : ""} #${e.seq} via ${e.via ?? "cache"}`), fetch(`${this.env.api}evacuation/ack/`, {
          method: "POST",
          headers: { Authorization: `Screen ${t}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            seq: e.seq,
            v: e.v,
            state: e.state,
            drill: e.drill,
            rendered_at: n.rendered_at,
            issued: e.issued ?? null,
            via: e.via ?? "cache",
            fallback: n.fallback
          })
        }).catch(() => {
        });
      },
      onChange: () => {
        this.display.settle(), this.updateDisplayState(), this.shown = "", this.show();
      }
    });
  }
  async loadEvac(t) {
    try {
      const e = await fetch(`${this.env.api}evacuation/state/`, { headers: { Authorization: `Screen ${t}` } });
      if (e.status === 401) return this.unpair();
      if (!e.ok) return;
      const n = await e.json();
      if (!n.enabled) return;
      this.evac?.setBundle(n.bundle ?? null), this.evac?.offer(n.payload, "fetch");
      const i = Object.values(n.bundle?.stages ?? {}).map((r) => r.speech).filter((r) => !!r);
      i.length && jt(i);
    } catch {
    }
  }
  /** Without a connection, ask the fallback origins (secondary node, bridge) for the signed alarm state. */
  async pollFallback() {
    const t = this.evac?.bundle;
    if (!(["websocket", "sse", "poll"].includes(this.transport) || !t?.fallback_origins.length))
      for (const e of t.fallback_origins)
        try {
          const n = await fetch(`${e}/evac/${t.event}/state`, { cache: "no-store" });
          if (!n.ok) continue;
          const i = await n.json();
          if (i.sig && this.evac?.offerFallback(i.sig)) return;
        } catch {
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
      this.slide = "error", this.display.message(z(this.env, "no_server"), z(this.env, "retrying"));
      return;
    }
    const e = this.clock.now();
    let n = null, i, r = "idle", a = null;
    if (this.program && this.bundle) {
      if (a = Bs(this.program, this.vars(), e), a?.message)
        n = this.program.messages?.[a.message] ?? null, r = `${a.entry}|message`, this.slide = `${a.entry} message`;
      else if (a?.layout) {
        const k = this.bundle.layouts.find((H) => H.id === a?.layout);
        k && (n = k.data, i = k.variables, r = `${a.entry}|${k.id}|${k.version}|${a.count > 1 ? a.start : ""}`, this.slide = `${k.key} v${k.version} (${a.entry} ${a.index + 1}/${a.count})`);
      }
      const f = [Fs(this.program, e, a), ws(this.program.overlays, e)].filter((k) => k !== null), S = Math.max(5, Math.min(le, (f.length ? Math.min(...f) : e + le) - e));
      this.timer = setTimeout(() => this.show(), S);
    } else {
      const f = ps(this.bundle);
      f && (n = f.data, i = f.variables, r = `default|${f.id}|${f.version}`, this.slide = `${f.key} v${f.version}`);
    }
    const o = { enabled: t.display?.audio !== !1, volume: t.display?.volume ?? 100 }, c = !!this.evac?.active, l = c || !!a && (a.entry.startsWith("announcement:") || a.entry.startsWith("evacuation"));
    this.overlays.update(this.program?.overlays, e, { hidden: l, audio: o });
    const h = a ? this.program?.entries.find((f) => f.id === a?.entry) : void 0, d = c || Li(h);
    if (h?.speech && o.enabled && !c && this.speaker.say(`${h.id}@${a?.start ?? 0}`, h.speech, {
      volume: o.volume,
      delayMs: $e
    }), r === this.shown || this.reloadAtNextSlide && this.shown && tt(this.reloadAtNextSlide)) return;
    this.reloadAtNextSlide = "", this.shown = r, M("info", `showing ${this.slide}`);
    const u = this.reducedMotion(), g = a?.item ? `${a.entry}|${a.item}|${a.start ?? ""}` : "", m = g && g !== this.shownSlide ? Ri(this.program, a, { reduced: u, urgent: d }) : null;
    this.shownSlide = g;
    const b = a && a.count > 1 && a.start !== null && a.end !== null ? { start: a.start, end: a.end } : null;
    d && this.display.settle();
    try {
      if (!n || !this.bundle) throw new Error("nothing to show");
      this.display.layout(n, {
        vars: this.vars(),
        now: () => this.clock.now(),
        timezone: t.event.timezone,
        assets: this.bundle.assets,
        fonts: this.bundle.fonts,
        reducedMotion: u,
        motion: !d,
        slide: b,
        audio: o,
        nonce: Ot(),
        data: this.widgetData,
        program: this.schedule,
        plugins: this.plugins ?? void 0,
        onError: (f, S) => $(`${f}: ${String(S)}`),
        onLog: (f, S) => M("info", `${f}: ${S}`)
      }, i, m);
    } catch (f) {
      n && $(`render failed, showing the idle slide: ${String(f)}`), this.slide = "idle", this.display.idle(t);
    }
    this.overlays.attach(this.root);
  }
  /** The device asks for reduced motion, or the screen's display settings do (ADR-0051). */
  reducedMotion() {
    return !!this.config?.display?.reduce_motion || typeof matchMedia == "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  /** Rotation, overscan, scale, keystone and the dim/sleep overlay from the display settings. */
  applySettings() {
    const t = this.config?.display ?? {};
    ut(this.root, t), document.documentElement.classList.toggle("reduce-motion", !!t.reduce_motion), this.evac && ut(this.evac.layer, t, !1), this.updateDisplayState();
  }
  updateDisplayState() {
    const t = this.config?.display ?? {}, e = this.evac?.active ? "on" : fi(t, Gt(this.clock.now(), this.config?.event.timezone));
    e !== this.displayState && M("info", `display ${e}`), this.displayState = e, mi(e, t);
  }
  /** Every 15 s: dim/sleep, daily reload, memory pressure, and catching up after the tab was frozen. */
  tick() {
    const t = Date.now(), e = t - this.lastTick > he * 3;
    this.lastTick = t, si(t), this.updateDisplayState(), e && (M("warn", "timers were stalled; resynchronising"), this.shown = "", this.show());
    const n = this.config?.display?.daily_reload, i = Gt(this.clock.now(), this.config?.event.timezone);
    n && i === n && this.lastDailyReload !== i && performance.now() > 36e5 && (this.lastDailyReload = i, this.reloadAtNextSlide = "daily reload"), ri() && !this.reloadAtNextSlide && (this.reloadAtNextSlide = "memory pressure");
  }
  unpair() {
    this.housekeeping && clearInterval(this.housekeeping), this.housekeeping = null, this.timer && clearTimeout(this.timer), this.refresher && clearInterval(this.refresher), this.dataRefresher && clearInterval(this.dataRefresher), this.evacTimer && clearInterval(this.evacTimer), this.fallbackTimer && clearInterval(this.fallbackTimer), this.timer = this.refresher = this.dataRefresher = this.evacTimer = this.fallbackTimer = null, Cs(), this.widgetData.set({}), Ts(), this.schedule.set(null), vs(), this.program = null, this.shown = "", this.conn?.stop(), this.conn = null, Kt(null), fs(), this.pair();
  }
}
function qi() {
  "serviceWorker" in navigator && location.protocol !== "file:" && navigator.serviceWorker.register("/player/sw.js", { scope: "/player/" }).catch((s) => $(String(s)));
}
if (typeof document < "u" && document.getElementById("player")) {
  Zs(), ii(), Xs(() => tt("50 errors within a minute")), qi();
  const s = Js();
  new Hi(s, document.getElementById("player")).boot();
}
export {
  Hi as Player
};
