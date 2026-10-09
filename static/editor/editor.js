// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC layout editor, built from frontend/src with `npm run build` - do not edit.
// Includes Lit (BSD-3-Clause, https://lit.dev) and uqr (MIT).
var se = Object.defineProperty;
var ie = (n, t, e) => t in n ? se(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var z = (n, t, e) => ie(n, typeof t != "symbol" ? t + "" : t, e);
const q = globalThis, ot = q.ShadowRoot && (q.ShadyCSS === void 0 || q.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, Ht = /* @__PURE__ */ Symbol(), gt = /* @__PURE__ */ new WeakMap();
let ne = class {
  constructor(t, e, s) {
    if (this._$cssResult$ = !0, s !== Ht) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (ot && t === void 0) {
      const s = e !== void 0 && e.length === 1;
      s && (t = gt.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), s && gt.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const re = (n) => new ne(typeof n == "string" ? n : n + "", void 0, Ht), oe = (n, t) => {
  if (ot) n.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const s = document.createElement("style"), i = q.litNonce;
    i !== void 0 && s.setAttribute("nonce", i), s.textContent = e.cssText, n.appendChild(s);
  }
}, $t = ot ? (n) => n : (n) => n instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const s of t.cssRules) e += s.cssText;
  return re(e);
})(n) : n;
const { is: ae, defineProperty: he, getOwnPropertyDescriptor: ce, getOwnPropertyNames: le, getOwnPropertySymbols: de, getPrototypeOf: ue } = Object, x = globalThis, yt = x.trustedTypes, fe = yt ? yt.emptyScript : "", pe = x.reactiveElementPolyfillSupport, O = (n, t) => n, et = { toAttribute(n, t) {
  switch (t) {
    case Boolean:
      n = n ? fe : null;
      break;
    case Object:
    case Array:
      n = n == null ? n : JSON.stringify(n);
  }
  return n;
}, fromAttribute(n, t) {
  let e = n;
  switch (t) {
    case Boolean:
      e = n !== null;
      break;
    case Number:
      e = n === null ? null : Number(n);
      break;
    case Object:
    case Array:
      try {
        e = JSON.parse(n);
      } catch {
        e = null;
      }
  }
  return e;
} }, Dt = (n, t) => !ae(n, t), bt = { attribute: !0, type: String, converter: et, reflect: !1, useDefault: !1, hasChanged: Dt };
Symbol.metadata ?? (Symbol.metadata = /* @__PURE__ */ Symbol("metadata")), x.litPropertyMetadata ?? (x.litPropertyMetadata = /* @__PURE__ */ new WeakMap());
let M = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ?? (this.l = [])).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = bt) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const s = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(t, s, e);
      i !== void 0 && he(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, s) {
    const { get: i, set: r } = ce(this.prototype, t) ?? { get() {
      return this[e];
    }, set(o) {
      this[e] = o;
    } };
    return { get: i, set(o) {
      const a = i?.call(this);
      r?.call(this, o), this.requestUpdate(t, a, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? bt;
  }
  static _$Ei() {
    if (this.hasOwnProperty(O("elementProperties"))) return;
    const t = ue(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(O("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(O("properties"))) {
      const e = this.properties, s = [...le(e), ...de(e)];
      for (const i of s) this.createProperty(i, e[i]);
    }
    const t = this[Symbol.metadata];
    if (t !== null) {
      const e = litPropertyMetadata.get(t);
      if (e !== void 0) for (const [s, i] of e) this.elementProperties.set(s, i);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [e, s] of this.elementProperties) {
      const i = this._$Eu(e, s);
      i !== void 0 && this._$Eh.set(i, e);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(t) {
    const e = [];
    if (Array.isArray(t)) {
      const s = new Set(t.flat(1 / 0).reverse());
      for (const i of s) e.unshift($t(i));
    } else t !== void 0 && e.push($t(t));
    return e;
  }
  static _$Eu(t, e) {
    const s = e.attribute;
    return s === !1 ? void 0 : typeof s == "string" ? s : typeof t == "string" ? t.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((t) => this.enableUpdating = t), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t) => t(this));
  }
  addController(t) {
    (this._$EO ?? (this._$EO = /* @__PURE__ */ new Set())).add(t), this.renderRoot !== void 0 && this.isConnected && t.hostConnected?.();
  }
  removeController(t) {
    this._$EO?.delete(t);
  }
  _$E_() {
    const t = /* @__PURE__ */ new Map(), e = this.constructor.elementProperties;
    for (const s of e.keys()) this.hasOwnProperty(s) && (t.set(s, this[s]), delete this[s]);
    t.size > 0 && (this._$Ep = t);
  }
  createRenderRoot() {
    const t = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return oe(t, this.constructor.elementStyles), t;
  }
  connectedCallback() {
    this.renderRoot ?? (this.renderRoot = this.createRenderRoot()), this.enableUpdating(!0), this._$EO?.forEach((t) => t.hostConnected?.());
  }
  enableUpdating(t) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((t) => t.hostDisconnected?.());
  }
  attributeChangedCallback(t, e, s) {
    this._$AK(t, s);
  }
  _$ET(t, e) {
    const s = this.constructor.elementProperties.get(t), i = this.constructor._$Eu(t, s);
    if (i !== void 0 && s.reflect === !0) {
      const r = (s.converter?.toAttribute !== void 0 ? s.converter : et).toAttribute(e, s.type);
      this._$Em = t, r == null ? this.removeAttribute(i) : this.setAttribute(i, r), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const s = this.constructor, i = s._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const r = s.getPropertyOptions(i), o = typeof r.converter == "function" ? { fromAttribute: r.converter } : r.converter?.fromAttribute !== void 0 ? r.converter : et;
      this._$Em = i;
      const a = o.fromAttribute(e, r.type);
      this[i] = a ?? this._$Ej?.get(i) ?? a, this._$Em = null;
    }
  }
  requestUpdate(t, e, s, i = !1, r) {
    if (t !== void 0) {
      const o = this.constructor;
      if (i === !1 && (r = this[t]), s ?? (s = o.getPropertyOptions(t)), !((s.hasChanged ?? Dt)(r, e) || s.useDefault && s.reflect && r === this._$Ej?.get(t) && !this.hasAttribute(o._$Eu(t, s)))) return;
      this.C(t, e, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: s, reflect: i, wrapped: r }, o) {
    s && !(this._$Ej ?? (this._$Ej = /* @__PURE__ */ new Map())).has(t) && (this._$Ej.set(t, o ?? e ?? this[t]), r !== !0 || o !== void 0) || (this._$AL.has(t) || (this.hasUpdated || s || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ?? (this._$Eq = /* @__PURE__ */ new Set())).add(t));
  }
  async _$EP() {
    this.isUpdatePending = !0;
    try {
      await this._$ES;
    } catch (e) {
      Promise.reject(e);
    }
    const t = this.scheduleUpdate();
    return t != null && await t, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ?? (this.renderRoot = this.createRenderRoot()), this._$Ep) {
        for (const [i, r] of this._$Ep) this[i] = r;
        this._$Ep = void 0;
      }
      const s = this.constructor.elementProperties;
      if (s.size > 0) for (const [i, r] of s) {
        const { wrapped: o } = r, a = this[i];
        o !== !0 || this._$AL.has(i) || a === void 0 || this.C(i, void 0, r, a);
      }
    }
    let t = !1;
    const e = this._$AL;
    try {
      t = this.shouldUpdate(e), t ? (this.willUpdate(e), this._$EO?.forEach((s) => s.hostUpdate?.()), this.update(e)) : this._$EM();
    } catch (s) {
      throw t = !1, this._$EM(), s;
    }
    t && this._$AE(e);
  }
  willUpdate(t) {
  }
  _$AE(t) {
    this._$EO?.forEach((e) => e.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(t)), this.updated(t);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = !1;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(t) {
    return !0;
  }
  update(t) {
    this._$Eq && (this._$Eq = this._$Eq.forEach((e) => this._$ET(e, this[e]))), this._$EM();
  }
  updated(t) {
  }
  firstUpdated(t) {
  }
};
M.elementStyles = [], M.shadowRootOptions = { mode: "open" }, M[O("elementProperties")] = /* @__PURE__ */ new Map(), M[O("finalized")] = /* @__PURE__ */ new Map(), pe?.({ ReactiveElement: M }), (x.reactiveElementVersions ?? (x.reactiveElementVersions = [])).push("2.1.2");
const R = globalThis, vt = (n) => n, G = R.trustedTypes, wt = G ? G.createPolicy("lit-html", { createHTML: (n) => n }) : void 0, It = "$lit$", S = `lit$${Math.random().toFixed(9).slice(2)}$`, Ut = "?" + S, me = `<${Ut}>`, k = document, I = () => k.createComment(""), U = (n) => n === null || typeof n != "object" && typeof n != "function", at = Array.isArray, ge = (n) => at(n) || typeof n?.[Symbol.iterator] == "function", J = `[ 	
\f\r]`, T = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, St = /-->/g, xt = />/g, A = RegExp(`>|${J}(?:([^\\s"'>=/]+)(${J}*=${J}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), At = /'/g, _t = /"/g, Ft = /^(?:script|style|textarea|title)$/i, $e = (n) => (t, ...e) => ({ _$litType$: n, strings: t, values: e }), u = $e(1), P = /* @__PURE__ */ Symbol.for("lit-noChange"), m = /* @__PURE__ */ Symbol.for("lit-nothing"), Et = /* @__PURE__ */ new WeakMap(), E = k.createTreeWalker(k, 129);
function Lt(n, t) {
  if (!at(n) || !n.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return wt !== void 0 ? wt.createHTML(t) : t;
}
const ye = (n, t) => {
  const e = n.length - 1, s = [];
  let i, r = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", o = T;
  for (let a = 0; a < e; a++) {
    const h = n[a];
    let c, d, l = -1, f = 0;
    for (; f < h.length && (o.lastIndex = f, d = o.exec(h), d !== null); ) f = o.lastIndex, o === T ? d[1] === "!--" ? o = St : d[1] !== void 0 ? o = xt : d[2] !== void 0 ? (Ft.test(d[2]) && (i = RegExp("</" + d[2], "g")), o = A) : d[3] !== void 0 && (o = A) : o === A ? d[0] === ">" ? (o = i ?? T, l = -1) : d[1] === void 0 ? l = -2 : (l = o.lastIndex - d[2].length, c = d[1], o = d[3] === void 0 ? A : d[3] === '"' ? _t : At) : o === _t || o === At ? o = A : o === St || o === xt ? o = T : (o = A, i = void 0);
    const p = o === A && n[a + 1].startsWith("/>") ? " " : "";
    r += o === T ? h + me : l >= 0 ? (s.push(c), h.slice(0, l) + It + h.slice(l) + S + p) : h + S + (l === -2 ? a : p);
  }
  return [Lt(n, r + (n[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), s];
};
class F {
  constructor({ strings: t, _$litType$: e }, s) {
    let i;
    this.parts = [];
    let r = 0, o = 0;
    const a = t.length - 1, h = this.parts, [c, d] = ye(t, e);
    if (this.el = F.createElement(c, s), E.currentNode = this.el.content, e === 2 || e === 3) {
      const l = this.el.content.firstChild;
      l.replaceWith(...l.childNodes);
    }
    for (; (i = E.nextNode()) !== null && h.length < a; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const l of i.getAttributeNames()) if (l.endsWith(It)) {
          const f = d[o++], p = i.getAttribute(l).split(S), g = /([.?@])?(.*)/.exec(f);
          h.push({ type: 1, index: r, name: g[2], strings: p, ctor: g[1] === "." ? ve : g[1] === "?" ? we : g[1] === "@" ? Se : X }), i.removeAttribute(l);
        } else l.startsWith(S) && (h.push({ type: 6, index: r }), i.removeAttribute(l));
        if (Ft.test(i.tagName)) {
          const l = i.textContent.split(S), f = l.length - 1;
          if (f > 0) {
            i.textContent = G ? G.emptyScript : "";
            for (let p = 0; p < f; p++) i.append(l[p], I()), E.nextNode(), h.push({ type: 2, index: ++r });
            i.append(l[f], I());
          }
        }
      } else if (i.nodeType === 8) if (i.data === Ut) h.push({ type: 2, index: r });
      else {
        let l = -1;
        for (; (l = i.data.indexOf(S, l + 1)) !== -1; ) h.push({ type: 7, index: r }), l += S.length - 1;
      }
      r++;
    }
  }
  static createElement(t, e) {
    const s = k.createElement("template");
    return s.innerHTML = t, s;
  }
}
function N(n, t, e = n, s) {
  if (t === P) return t;
  let i = s !== void 0 ? e._$Co?.[s] : e._$Cl;
  const r = U(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== r && (i?._$AO?.(!1), r === void 0 ? i = void 0 : (i = new r(n), i._$AT(n, e, s)), s !== void 0 ? (e._$Co ?? (e._$Co = []))[s] = i : e._$Cl = i), i !== void 0 && (t = N(n, i._$AS(n, t.values), i, s)), t;
}
class be {
  constructor(t, e) {
    this._$AV = [], this._$AN = void 0, this._$AD = t, this._$AM = e;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t) {
    const { el: { content: e }, parts: s } = this._$AD, i = (t?.creationScope ?? k).importNode(e, !0);
    E.currentNode = i;
    let r = E.nextNode(), o = 0, a = 0, h = s[0];
    for (; h !== void 0; ) {
      if (o === h.index) {
        let c;
        h.type === 2 ? c = new L(r, r.nextSibling, this, t) : h.type === 1 ? c = new h.ctor(r, h.name, h.strings, this, t) : h.type === 6 && (c = new xe(r, this, t)), this._$AV.push(c), h = s[++a];
      }
      o !== h?.index && (r = E.nextNode(), o++);
    }
    return E.currentNode = k, i;
  }
  p(t) {
    let e = 0;
    for (const s of this._$AV) s !== void 0 && (s.strings !== void 0 ? (s._$AI(t, s, e), e += s.strings.length - 2) : s._$AI(t[e])), e++;
  }
}
class L {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, s, i) {
    this.type = 2, this._$AH = m, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = s, this.options = i, this._$Cv = i?.isConnected ?? !0;
  }
  get parentNode() {
    let t = this._$AA.parentNode;
    const e = this._$AM;
    return e !== void 0 && t?.nodeType === 11 && (t = e.parentNode), t;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t, e = this) {
    t = N(this, t, e), U(t) ? t === m || t == null || t === "" ? (this._$AH !== m && this._$AR(), this._$AH = m) : t !== this._$AH && t !== P && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : ge(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== m && U(this._$AH) ? this._$AA.nextSibling.data = t : this.T(k.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: s } = t, i = typeof s == "number" ? this._$AC(t) : (s.el === void 0 && (s.el = F.createElement(Lt(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const r = new be(i, this), o = r.u(this.options);
      r.p(e), this.T(o), this._$AH = r;
    }
  }
  _$AC(t) {
    let e = Et.get(t.strings);
    return e === void 0 && Et.set(t.strings, e = new F(t)), e;
  }
  k(t) {
    at(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let s, i = 0;
    for (const r of t) i === e.length ? e.push(s = new L(this.O(I()), this.O(I()), this, this.options)) : s = e[i], s._$AI(r), i++;
    i < e.length && (this._$AR(s && s._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const s = vt(t).nextSibling;
      vt(t).remove(), t = s;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class X {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, s, i, r) {
    this.type = 1, this._$AH = m, this._$AN = void 0, this.element = t, this.name = e, this._$AM = i, this.options = r, s.length > 2 || s[0] !== "" || s[1] !== "" ? (this._$AH = Array(s.length - 1).fill(new String()), this.strings = s) : this._$AH = m;
  }
  _$AI(t, e = this, s, i) {
    const r = this.strings;
    let o = !1;
    if (r === void 0) t = N(this, t, e, 0), o = !U(t) || t !== this._$AH && t !== P, o && (this._$AH = t);
    else {
      const a = t;
      let h, c;
      for (t = r[0], h = 0; h < r.length - 1; h++) c = N(this, a[s + h], e, h), c === P && (c = this._$AH[h]), o || (o = !U(c) || c !== this._$AH[h]), c === m ? t = m : t !== m && (t += (c ?? "") + r[h + 1]), this._$AH[h] = c;
    }
    o && !i && this.j(t);
  }
  j(t) {
    t === m ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class ve extends X {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === m ? void 0 : t;
  }
}
class we extends X {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== m);
  }
}
class Se extends X {
  constructor(t, e, s, i, r) {
    super(t, e, s, i, r), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = N(this, t, e, 0) ?? m) === P) return;
    const s = this._$AH, i = t === m && s !== m || t.capture !== s.capture || t.once !== s.once || t.passive !== s.passive, r = t !== m && (s === m || i);
    i && this.element.removeEventListener(this.name, this, s), r && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class xe {
  constructor(t, e, s) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    N(this, t);
  }
}
const Ae = R.litHtmlPolyfillSupport;
Ae?.(F, L), (R.litHtmlVersions ?? (R.litHtmlVersions = [])).push("3.3.3");
const _e = (n, t, e) => {
  const s = e?.renderBefore ?? t;
  let i = s._$litPart$;
  if (i === void 0) {
    const r = e?.renderBefore ?? null;
    s._$litPart$ = i = new L(t.insertBefore(I(), r), r, void 0, e ?? {});
  }
  return i._$AI(n), i;
};
const H = globalThis;
let D = class extends M {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    var e;
    const t = super.createRenderRoot();
    return (e = this.renderOptions).renderBefore ?? (e.renderBefore = t.firstChild), t;
  }
  update(t) {
    const e = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = _e(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return P;
  }
};
D._$litElement$ = !0, D.finalized = !0, H.litElementHydrateSupport?.({ LitElement: D });
const Ee = H.litElementPolyfillSupport;
Ee?.({ LitElement: D });
(H.litElementVersions ?? (H.litElementVersions = [])).push("4.2.2");
const Ce = { ELEMENT: 6 }, ke = (n) => (...t) => ({ _$litDirective$: n, values: t });
class Me {
  constructor(t) {
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AT(t, e, s) {
    this._$Ct = t, this._$AM = e, this._$Ci = s;
  }
  _$AS(t, e) {
    return this.update(t, e);
  }
  update(t, e) {
    return this.render(...e);
  }
}
function K(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function Pe(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function Ne(n, t, e) {
  const s = n.style;
  if (!t) return;
  const i = (r, o) => {
    o && s.setProperty(r, o);
  };
  i("color", K(t.color)), i("background", K(t.background)), t.borderWidth && s.setProperty("border", `${t.borderWidth / 10}cqh solid ${K(t.borderColor) || "currentColor"}`), t.radius !== void 0 && s.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && s.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && s.setProperty("opacity", String(t.opacity)), i("font-family", Pe(t.fontFamily, e)), t.fontSize && s.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && s.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && s.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && s.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && s.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && s.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && s.setProperty("box-shadow", "var(--evac-shadow)");
}
function ze(n, t, e) {
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
function Te(n) {
  const t = [];
  let e = "", s = "";
  for (const i of n)
    s ? (i === s && (s = ""), e += i) : i === '"' || i === "'" ? (s = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function Oe(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function Ct(n, t, e) {
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
function $(n) {
  return n == null ? "" : Array.isArray(n) ? n.map($).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function Re(n, t, e) {
  const [s, ...i] = t.split(":"), r = Oe(i.join(":")), o = () => n instanceof Date ? n : new Date(String(n));
  switch (s.trim()) {
    case "upper":
      return $(n).toUpperCase();
    case "lower":
      return $(n).toLowerCase();
    case "title":
      return $(n).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(r) || 30, h = $(n);
      return h.length > a ? `${h.slice(0, Math.max(0, a - 1))}…` : h;
    }
    case "default":
      return $(n) === "" ? r : n;
    case "date":
      return isNaN(o().getTime()) ? "" : Ct(o(), r || "long", e.timezone);
    case "time":
      return isNaN(o().getTime()) ? "" : Ct(o(), r || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map($).join(r || ", ") : $(n);
    default:
      return n;
  }
}
function V(n, t, e = {}) {
  const [s, ...i] = Te(n);
  let r = ze(t, s, e);
  for (const o of i) r = Re(r, o, e);
  return r;
}
function He(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function ht(n, t, e = {}) {
  const s = n.trim();
  if (!s) return !0;
  if (s.startsWith("not ")) return !ht(s.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(s);
  if (i) {
    const r = $(V(i[1], t, e)), o = $(V(i[3], t, e));
    return i[2] === "==" ? r === o : r !== o;
  }
  return He(V(s.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const De = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function Ie(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const s = n.split(De);
  let i = 0;
  const r = (o) => {
    let a = "";
    for (; i < s.length; ) {
      const h = s[i++], c = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(h);
      if (c) {
        const d = c[1].startsWith("if") ? "if" : c[1];
        if (o.includes(d)) return [a, d];
        if (d === "if") {
          const l = ht(c[2], t, e), [f, p] = r(["else", "endif"]);
          let g = "";
          p === "else" && (g = r(["endif"])[0]), a += l ? f : g;
        }
      } else h.startsWith("{{") && h.endsWith("}}") ? a += $(V(h.slice(2, -2), t, e)) : a += h;
    }
    return [a, ""];
  };
  return r([])[0];
}
var _ = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(_ || {});
const Ue = [0, 1], Bt = [1, 0], Wt = [2, 3], jt = [3, 2], Fe = {
  L: Ue,
  M: Bt,
  Q: Wt,
  H: jt
}, Le = /^\d*$/, Be = /^[A-Z0-9 $%*+./:-]*$/, Z = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", ct = 1, lt = 40, kt = 3, We = 3, W = 40, je = 10, qt = [
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
], Kt = [
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
class qe {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, s, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    z(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    z(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    z(this, "modules", []);
    z(this, "types", []);
    if (this.version = t, this.ecc = e, t < ct || t > lt)
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
      for (let h = 0; h < 8; h++) {
        this.applyMask(h), this.drawFormatBits(h);
        const c = this.getPenaltyScore();
        c < a && (i = h, a = c), this.applyMask(h);
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
      this.setFunctionModule(6, s, s % 2 === 0, _.Timing), this.setFunctionModule(s, 6, s % 2 === 0, _.Timing);
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
      this.setFunctionModule(8, r, b(i, r));
    this.setFunctionModule(8, 7, b(i, 6)), this.setFunctionModule(8, 8, b(i, 7)), this.setFunctionModule(7, 8, b(i, 8));
    for (let r = 9; r < 15; r++)
      this.setFunctionModule(14 - r, 8, b(i, r));
    for (let r = 0; r < 8; r++)
      this.setFunctionModule(this.size - 1 - r, 8, b(i, r));
    for (let r = 8; r < 15; r++)
      this.setFunctionModule(8, this.size - 15 + r, b(i, r));
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
      const i = b(e, s), r = this.size - 11 + s % 3, o = Math.floor(s / 3);
      this.setFunctionModule(r, o, i), this.setFunctionModule(o, r, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let s = -4; s <= 4; s++)
      for (let i = -4; i <= 4; i++) {
        const r = Math.max(Math.abs(i), Math.abs(s)), o = t + i, a = e + s;
        o >= 0 && o < this.size && a >= 0 && a < this.size && this.setFunctionModule(o, a, r !== 2 && r !== 4, _.Position);
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
          _.Alignment
        );
  }
  // Sets the color of a module and marks it as a function module.
  // Only used by the constructor. Coordinates must be in bounds.
  setFunctionModule(t, e, s, i = _.Function) {
    this.modules[e][t] = s, this.types[e][t] = i;
  }
  /* -- Private helper methods for constructor: Codewords and masking -- */
  // Returns a new byte string representing the given data with the appropriate error correction
  // codewords appended to it, based on this object's version and error correction level.
  addEccAndInterleave(t) {
    const e = this.version, s = this.ecc;
    if (t.length !== Y(e, s))
      throw new RangeError("Invalid argument");
    const i = Kt[s[0]][e], r = qt[s[0]][e], o = Math.floor(st(e) / 8), a = i - o % i, h = Math.floor(o / i), c = [], d = ts(r);
    for (let f = 0, p = 0; f < i; f++) {
      const g = t.slice(p, p + h - r + (f < a ? 0 : 1));
      p += g.length;
      const B = es(g, d);
      f < a && g.push(0), c.push(g.concat(B));
    }
    const l = [];
    for (let f = 0; f < c[0].length; f++)
      c.forEach((p, g) => {
        (f !== h - r || g >= a) && l.push(p[f]);
      });
    return l;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(st(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let s = this.size - 1; s >= 1; s -= 2) {
      s === 6 && (s = 5);
      for (let i = 0; i < this.size; i++)
        for (let r = 0; r < 2; r++) {
          const o = s - r, h = (s + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[h][o] && e < t.length * 8 && (this.modules[h][o] = b(t[e >>> 3], 7 - (e & 7)), e++);
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
      const h = [0, 0, 0, 0, 0, 0, 0];
      for (let c = 0; c < this.size; c++)
        this.modules[r][c] === o ? (a++, a === 5 ? t += kt : a > 5 && t++) : (this.finderPenaltyAddHistory(a, h), o || (t += this.finderPenaltyCountPatterns(h) * W), o = this.modules[r][c], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, h) * W;
    }
    for (let r = 0; r < this.size; r++) {
      let o = !1, a = 0;
      const h = [0, 0, 0, 0, 0, 0, 0];
      for (let c = 0; c < this.size; c++)
        this.modules[c][r] === o ? (a++, a === 5 ? t += kt : a > 5 && t++) : (this.finderPenaltyAddHistory(a, h), o || (t += this.finderPenaltyCountPatterns(h) * W), o = this.modules[c][r], a = 1);
      t += this.finderPenaltyTerminateAndCount(o, a, h) * W;
    }
    for (let r = 0; r < this.size - 1; r++)
      for (let o = 0; o < this.size - 1; o++) {
        const a = this.modules[r][o];
        a === this.modules[r][o + 1] && a === this.modules[r + 1][o] && a === this.modules[r + 1][o + 1] && (t += We);
      }
    let e = 0;
    for (const r of this.modules)
      e = r.reduce((o, a) => o + (a ? 1 : 0), e);
    const s = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - s * 10) / s) - 1;
    return t += i * je, t;
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
function v(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let s = t - 1; s >= 0; s--)
    e.push(n >>> s & 1);
}
function b(n, t) {
  return (n >>> t & 1) !== 0;
}
class dt {
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
const Ke = [1, 10, 12, 14], Ve = [2, 9, 11, 13], Ye = [4, 8, 16, 16];
function Vt(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function Yt(n) {
  const t = [];
  for (const e of n)
    v(e, 8, t);
  return new dt(Ye, n.length, t);
}
function Ge(n) {
  if (!Gt(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const s = Math.min(n.length - e, 3);
    v(Number.parseInt(n.substring(e, e + s), 10), s * 3 + 1, t), e += s;
  }
  return new dt(Ke, n.length, t);
}
function Xe(n) {
  if (!Xt(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let s = Z.indexOf(n.charAt(e)) * 45;
    s += Z.indexOf(n.charAt(e + 1)), v(s, 11, t);
  }
  return e < n.length && v(Z.indexOf(n.charAt(e)), 6, t), new dt(Ve, n.length, t);
}
function Je(n) {
  return n === "" ? [] : Gt(n) ? [Ge(n)] : Xt(n) ? [Xe(n)] : [Yt(Qe(n))];
}
function Gt(n) {
  return Le.test(n);
}
function Xt(n) {
  return Be.test(n);
}
function Ze(n, t) {
  let e = 0;
  for (const s of n) {
    const i = Vt(s.mode, t);
    if (s.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + s.bitData.length;
  }
  return e;
}
function Qe(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function st(n) {
  if (n < ct || n > lt)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function Y(n, t) {
  return Math.floor(st(n) / 8) - qt[t[0]][n] * Kt[t[0]][n];
}
function ts(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let s = 0; s < n - 1; s++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < t.length; i++)
      t[i] = it(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = it(e, 2);
  }
  return t;
}
function es(n, t) {
  const e = t.map((s) => 0);
  for (const s of n) {
    const i = s ^ e.shift();
    e.push(0), t.forEach((r, o) => e[o] ^= it(r, i));
  }
  return e;
}
function it(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let s = 7; s >= 0; s--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> s & 1) * n;
  return e;
}
function ss(n, t, e = 1, s = 40, i = -1, r = !0) {
  if (!(ct <= e && e <= s && s <= lt) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let o, a;
  for (o = e; ; o++) {
    const l = Y(o, t) * 8, f = Ze(n, o);
    if (f <= l) {
      a = f;
      break;
    }
    if (o >= s)
      throw new RangeError("Data too long");
  }
  for (const l of [Bt, Wt, jt])
    r && a <= Y(o, l) * 8 && (t = l);
  const h = [];
  for (const l of n) {
    v(l.mode[0], 4, h), v(l.numChars, Vt(l.mode, o), h);
    for (const f of l.getData())
      h.push(f);
  }
  const c = Y(o, t) * 8;
  v(0, Math.min(4, c - h.length), h), v(0, (8 - h.length % 8) % 8, h);
  for (let l = 236; h.length < c; l ^= 253)
    v(l, 8, h);
  const d = Array.from({ length: Math.ceil(h.length / 8) }, () => 0);
  return h.forEach((l, f) => d[f >>> 3] |= l << 7 - (f & 7)), new qe(o, t, d, i);
}
function is(n, t) {
  const {
    ecc: e = "L",
    boostEcc: s = !1,
    minVersion: i = 1,
    maxVersion: r = 40,
    maskPattern: o = -1,
    border: a = 1
  } = t || {}, h = typeof n == "string" ? Je(n) : Array.isArray(n) ? [Yt(n)] : void 0;
  if (!h)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const c = ss(
    h,
    Fe[e],
    i,
    r,
    o,
    s
  ), d = ns({
    version: c.version,
    maskPattern: c.mask,
    size: c.size,
    data: c.modules,
    types: c.types
  }, a);
  return t?.invert && (d.data = d.data.map((l) => l.map((f) => !f))), t?.onEncoded?.(d), d;
}
function ns(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, s = e + t * 2;
  n.size = s, n.data.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(!1), r.push(!1);
  });
  for (let r = 0; r < t; r++)
    n.data.unshift(Array.from({ length: s }, (o) => !1)), n.data.push(Array.from({ length: s }, (o) => !1));
  const i = _.Border;
  n.types.forEach((r) => {
    for (let o = 0; o < t; o++)
      r.unshift(i), r.push(i);
  });
  for (let r = 0; r < t; r++)
    n.types.unshift(Array.from({ length: s }, (o) => i)), n.types.push(Array.from({ length: s }, (o) => i));
  return n;
}
const Q = "http://www.w3.org/2000/svg";
function rs(n, t = document) {
  const { data: e, size: s } = is(n, { ecc: "M", border: 2 }), i = t.createElementNS(Q, "svg");
  i.setAttribute("viewBox", `0 0 ${s} ${s}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const r = t.createElementNS(Q, "rect");
  r.setAttribute("width", String(s)), r.setAttribute("height", String(s)), r.setAttribute("fill", "#fff"), i.appendChild(r);
  let o = "";
  e.forEach((h, c) => h.forEach((d, l) => {
    d && (o += `M${l} ${c}h1v1h-1z`);
  }));
  const a = t.createElementNS(Q, "path");
  return a.setAttribute("d", o), a.setAttribute("fill", "#000"), i.appendChild(a), i;
}
class y extends HTMLElement {
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
    return Ie(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function os(n, t) {
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
class as extends y {
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
      const i = () => os(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class hs extends y {
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
function Jt(n, t, e) {
  const s = document.createElement("picture");
  for (const [r, o] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[r]) {
      const a = document.createElement("source");
      a.type = o, a.srcset = n.urls[r], s.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = n.urls.original, i.alt = e || n.alt || "", i.decoding = "async", i.style.objectFit = t, s.appendChild(i), s;
}
class cs extends y {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(Jt(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class ls extends y {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((o) => this.asset(o)).filter((o) => !!o);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), s = t.map((o) => {
      const a = Jt(o, e, "");
      return a.className = "evac-slide", a;
    });
    this.replaceChildren(...s);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, r = () => {
      const o = Math.floor(this.ctx.now() / i) % s.length;
      s.forEach((a, h) => a.classList.toggle("active", h === o));
    };
    r(), this.every(500, r);
  }
}
class ds extends y {
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
class us extends y {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.autoplay = !0, this.replaceChildren(e);
  }
}
class fs extends y {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class ps extends y {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = rs(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const ms = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class gs extends y {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...ms[t], timeZone: e }), i = document.createElement("time"), r = () => {
      i.textContent = s.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(i), this.every(1e3, r);
  }
}
class $s extends y {
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
function ys(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), s = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), r = Math.floor(e % 3600 / 60), o = e % 60, a = (h) => String(h).padStart(2, "0");
  return t === "days" ? `${s} ${s === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(o)}` : t === "hms" || s === 0 ? `${a(i + s * 24)}:${a(r)}:${a(o)}` : `${s}d ${a(i)}:${a(r)}:${a(o)}`;
}
class bs extends y {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), s = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : ys(i, String(this.props.format ?? "auto"));
    };
    s(), this.replaceChildren(e), this.every(250, s);
  }
}
const vs = {
  text: as,
  richtext: hs,
  image: cs,
  slideshow: ls,
  video: ds,
  audio: us,
  shape: fs,
  qr: ps,
  clock: gs,
  countdown: bs,
  date: $s
};
function ws(n = customElements) {
  for (const [t, e] of Object.entries(vs))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
function nt(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function Ss(n, t) {
  const e = !n.visible_if || ht(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const s = document.createElement("div");
  s.className = `evac-el evac-el-${n.type}`, s.dataset.id = n.id, (!e || n.hidden) && s.classList.add("evac-dimmed"), nt(s, n), Ne(s, n.style, t);
  const i = n.animation;
  i?.enter && i.enter !== "none" && !t.reducedMotion && !t.editing && (s.classList.add(`evac-enter-${i.enter}`), s.style.animationDuration = `${i.duration ?? 600}ms`, s.style.animationDelay = `${i.delay ?? 0}ms`);
  const r = `evac-${n.type}`;
  if (!customElements.get(r))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? s : null;
  const o = document.createElement(r);
  return o.className = "evac-widget", s.appendChild(o), o.configure(n, t), s;
}
function xs(n, t, e) {
  ws();
  const s = document.createElement("div");
  s.className = "evac-stage";
  const i = t.background;
  if (i?.color && (s.style.background = K(i.color)), i?.asset && e.assets[i.asset]) {
    const h = e.assets[i.asset], c = h.urls.webp ?? h.urls.original;
    s.style.backgroundImage = `url("${c}")`, s.style.backgroundSize = i.fit ?? "cover", s.style.backgroundPosition = "center";
  }
  const r = /* @__PURE__ */ new Map();
  for (const h of t.elements) {
    const c = Ss(h, e);
    c && (r.set(h.id, c), s.appendChild(c));
  }
  n.replaceChildren(s);
  const o = () => {
    const h = n.clientWidth, c = n.clientHeight;
    if (!h || !c) return;
    const d = Math.min(h / t.width, c / t.height);
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
const C = (n) => JSON.parse(JSON.stringify(n));
class As {
  constructor(t = 200) {
    this.limit = t, this.past = [], this.future = [];
  }
  push(t) {
    this.past.push(C(t)), this.past.length > this.limit && this.past.shift(), this.future = [];
  }
  undo(t) {
    const e = this.past.pop();
    return e ? (this.future.push(C(t)), e) : null;
  }
  redo(t) {
    const e = this.future.pop();
    return e ? (this.past.push(C(t)), e) : null;
  }
  get canUndo() {
    return this.past.length > 0;
  }
  get canRedo() {
    return this.future.length > 0;
  }
}
function Zt(n, t) {
  const e = new Set(n);
  for (let s = 1; ; s++) if (!e.has(`${t}${s}`)) return `${t}${s}`;
}
const Mt = {
  text: { frame: { x: 10, y: 10, w: 50, h: 12 }, style: { fontSize: 6 }, props: { text: "Text", autofit: !0 } },
  richtext: {
    frame: { x: 10, y: 10, w: 50, h: 30 },
    style: { fontSize: 4 },
    props: { text: "A paragraph with **bold** and *italic* text." }
  },
  image: { frame: { x: 10, y: 10, w: 30, h: 30 }, props: { fit: "contain" } },
  slideshow: { frame: { x: 10, y: 10, w: 50, h: 50 }, props: { assets: [], interval: 8, fit: "cover" } },
  video: { frame: { x: 10, y: 10, w: 50, h: 50 }, props: { loop: !0, muted: !0, fit: "cover" } },
  audio: { frame: { x: 2, y: 2, w: 8, h: 8 }, props: { loop: !0 } },
  shape: {
    frame: { x: 10, y: 10, w: 30, h: 20 },
    style: { background: "token:primary", radius: 1 },
    props: { shape: "rect" }
  },
  qr: {
    frame: { x: 70, y: 60, w: 20, h: 30 },
    style: { background: "#ffffff", padding: 1 },
    props: { text: "https://example.org" }
  },
  clock: {
    frame: { x: 70, y: 5, w: 25, h: 12 },
    style: { fontSize: 8, textAlign: "right", tabularNumbers: !0 },
    props: { format: "HH:mm" }
  },
  countdown: {
    frame: { x: 25, y: 40, w: 50, h: 20 },
    style: {
      fontSize: 12,
      textAlign: "center",
      tabularNumbers: !0
    },
    props: { target: "", format: "auto", finished: "Now!" }
  },
  date: { frame: { x: 5, y: 5, w: 40, h: 8 }, style: { fontSize: 4 }, props: { format: "long" } }
};
function _s(n, t, e) {
  const s = C(Mt[n] ?? Mt.text), i = t.length % 8 * 2, r = s.frame;
  return {
    id: Zt(t.map((o) => o.id), n),
    type: n,
    name: e,
    ...s,
    frame: { ...r, x: r.x + i, y: r.y + i }
  };
}
function Pt(n, t) {
  const e = C(n);
  return e.id = Zt(t.map((s) => s.id), `${n.type}`), e.name = `${n.name ?? n.type} copy`, e.frame = { ...e.frame, x: e.frame.x + 2, y: e.frame.y + 2 }, e;
}
const Qt = (n, t) => Math.round(n / t) * t;
function Es(n, t, { grid: e = 0.5, threshold: s = 0.8 } = {}) {
  let i = null;
  for (const r of t) Math.abs(r - n) <= s && (i === null || Math.abs(r - n) < Math.abs(i - n)) && (i = r);
  return i !== null ? [i, i] : [Qt(n, e), null];
}
function Nt(n, t, e) {
  const s = [0, 50, 100];
  for (const i of n) {
    if (t.has(i.id)) continue;
    const r = e === "x" ? i.frame.x : i.frame.y, o = e === "x" ? i.frame.w : i.frame.h;
    s.push(r, r + o / 2, r + o);
  }
  return s;
}
function zt(n, t, e, s) {
  const r = [0, t / 2, t].map((o) => {
    const [a, h] = Es(n + o, e, s);
    return [a - o, h, h === null ? 1 / 0 : Math.abs(a - (n + o))];
  }).filter((o) => o[1] !== null).sort((o, a) => o[2] - a[2])[0];
  return r ? [r[0], r[1]] : [Qt(n, 0.5), null];
}
function Cs(n, t, e) {
  const s = n.filter((c) => t.has(c.id));
  if (!s.length) return n;
  const i = s.length === 1, r = i ? 0 : Math.min(...s.map((c) => c.frame.x)), o = i ? 100 : Math.max(...s.map((c) => c.frame.x + c.frame.w)), a = i ? 0 : Math.min(...s.map((c) => c.frame.y)), h = i ? 100 : Math.max(...s.map((c) => c.frame.y + c.frame.h));
  return n.map((c) => {
    if (!t.has(c.id)) return c;
    const d = { ...c.frame };
    return e === "left" && (d.x = r), e === "right" && (d.x = o - d.w), e === "center" && (d.x = (r + o) / 2 - d.w / 2), e === "top" && (d.y = a), e === "bottom" && (d.y = h - d.h), e === "middle" && (d.y = (a + h) / 2 - d.h / 2), { ...c, frame: d };
  });
}
function Tt(n, t, e) {
  const s = n.findIndex((a) => a.id === t), i = Math.min(n.length - 1, Math.max(0, s + e));
  if (s < 0 || s === i) return n;
  const r = [...n], [o] = r.splice(s, 1);
  return r.splice(i, 0, o), r;
}
function ks(n, t, e, s, i = 1) {
  const r = { ...n };
  return t.includes("w") && (r.x = Math.min(n.x + e, n.x + n.w - i), r.w = n.w - (r.x - n.x)), t.includes("e") && (r.w = Math.max(i, n.w + e)), t.includes("n") && (r.y = Math.min(n.y + s, n.y + n.h - i), r.h = n.h - (r.y - n.y)), t.includes("s") && (r.h = Math.max(i, n.h + s)), r;
}
const w = (n) => Math.round(n * 100) / 100, j = {
  text: "Text",
  richtext: "Rich text",
  image: "Image",
  slideshow: "Slideshow",
  video: "Video",
  audio: "Audio",
  shape: "Shape",
  qr: "QR code",
  clock: "Clock",
  countdown: "Countdown",
  date: "Date"
}, Ms = ["primary", "accent", "text", "muted", "surface", "background", "success", "warning", "danger"], Ps = {
  primary: "Primary",
  accent: "Accent",
  text: "Text",
  muted: "Muted text",
  surface: "Surface",
  background: "Background",
  success: "Success",
  warning: "Warning",
  danger: "Danger"
}, Ns = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
class zs extends Me {
  constructor(t) {
    if (super(t), t.type !== Ce.ELEMENT) throw new Error("ref() only on elements");
  }
  update(t, [e]) {
    return e(t.element), this.render(e);
  }
  render(t) {
    return m;
  }
}
const tt = ke(zs);
function Ot(n, t) {
  const e = document.getElementById(n);
  try {
    return e?.textContent ? JSON.parse(e.textContent) : t;
  } catch {
    return t;
  }
}
function Rt() {
  return document.cookie.split("; ").find((n) => n.startsWith("csrftoken="))?.split("=")[1] ?? "";
}
const ut = class ut extends D {
  constructor() {
    super(...arguments), this.selected = /* @__PURE__ */ new Set(), this.status = "saved", this.zoom = 0, this.guides = { x: null, y: null }, this.error = "", this.cfg = Ot("editor-config", {}), this.strings = Ot("editor-strings", {}), this.history = new As(), this.version = 0, this.rendered = null, this.drag = null, this.clipboardKey = "evac.editor.clipboard";
  }
  createRenderRoot() {
    return this;
  }
  t(t) {
    return this.strings[t] ?? t;
  }
  connectedCallback() {
    this.replaceChildren(), super.connectedCallback(), this.data = C(this.cfg.layout.data), this.version = this.cfg.layout.version, this.tabIndex = 0, this.addEventListener("keydown", (t) => this.onKey(t)), window.addEventListener("beforeunload", (t) => {
      this.status === "dirty" && t.preventDefault();
    });
  }
  // ---------------------------------------------------------------- state changes
  get elements() {
    return this.data.elements;
  }
  get selection() {
    return this.elements.filter((t) => this.selected.has(t.id));
  }
  commit(t, e = !0) {
    e && this.history.push(this.data), this.data = t, this.status = "dirty";
  }
  updateElements(t) {
    this.commit({ ...this.data, elements: t(C(this.elements)) });
  }
  patchSelected(t) {
    this.updateElements((e) => e.map((s) => (this.selected.has(s.id) && t(s), s)));
  }
  select(t, e = !1) {
    const s = new Set(e ? this.selected : []);
    t && (e && s.has(t) ? s.delete(t) : s.add(t)), this.selected = s;
  }
  add(t) {
    const e = _s(t, this.elements, this.t(j[t] ?? t));
    this.updateElements((s) => [...s, e]), this.selected = /* @__PURE__ */ new Set([e.id]);
  }
  removeSelected() {
    this.selected.size && (this.updateElements((t) => t.filter((e) => !this.selected.has(e.id) || e.locked)), this.selected = /* @__PURE__ */ new Set());
  }
  duplicateSelected() {
    const t = [];
    for (const e of this.selection) t.push(Pt(e, [...this.elements, ...t]));
    this.updateElements((e) => [...e, ...t]), this.selected = new Set(t.map((e) => e.id));
  }
  undo() {
    const t = this.history.undo(this.data);
    t && (this.data = t, this.status = "dirty");
  }
  redo() {
    const t = this.history.redo(this.data);
    t && (this.data = t, this.status = "dirty");
  }
  // ---------------------------------------------------------------- save and publish
  async save() {
    this.status = "saving", this.error = "";
    try {
      const t = await fetch(this.cfg.urls.save, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": Rt() },
        body: JSON.stringify({ data: this.data, version: this.version })
      }), e = await t.json().catch(() => ({}));
      if (t.ok && e.ok)
        return this.version = e.version, this.status = "saved", !0;
      this.status = "error", this.error = e.conflict ? this.t("Someone else saved this layout in the meantime.") : [this.t("The layout could not be saved."), ...e.errors ?? []].join(" ");
    } catch {
      this.status = "error", this.error = this.t("The layout could not be saved.");
    }
    return !1;
  }
  async publish() {
    if (this.status !== "saved" && !await this.save()) return;
    const t = await fetch(this.cfg.urls.publish, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": Rt() }
    }), e = await t.json().catch(() => ({}));
    this.error = t.ok ? `${this.t("Published")}: v${e.published}` : this.t("The layout could not be saved.");
  }
  // ---------------------------------------------------------------- keyboard
  onKey(t) {
    if (t.target.closest("input, textarea, select")) return;
    const s = t.ctrlKey || t.metaKey, i = t.shiftKey ? 5 : 0.5, r = (a, h) => this.patchSelected((c) => {
      c.locked || (c.frame = { ...c.frame, x: w(c.frame.x + a), y: w(c.frame.y + h) });
    }), o = {
      ArrowLeft: () => r(-i, 0),
      ArrowRight: () => r(i, 0),
      ArrowUp: () => r(0, -i),
      ArrowDown: () => r(0, i),
      Delete: () => this.removeSelected(),
      Backspace: () => this.removeSelected(),
      Escape: () => this.select(null)
    };
    if (s && t.key.toLowerCase() === "z") t.shiftKey ? this.redo() : this.undo();
    else if (s && t.key.toLowerCase() === "y") this.redo();
    else if (s && t.key.toLowerCase() === "d") this.duplicateSelected();
    else if (s && t.key.toLowerCase() === "s") this.save();
    else if (s && t.key.toLowerCase() === "c")
      try {
        localStorage.setItem(this.clipboardKey, JSON.stringify(this.selection));
      } catch {
      }
    else if (s && t.key.toLowerCase() === "v") {
      let a = [];
      try {
        a = JSON.parse(localStorage.getItem(this.clipboardKey) ?? "[]");
      } catch {
      }
      const h = [];
      for (const c of a) h.push(Pt(c, [...this.elements, ...h]));
      h.length && (this.updateElements((c) => [...c, ...h]), this.selected = new Set(h.map((c) => c.id)));
    } else if (o[t.key]) o[t.key]();
    else return;
    t.preventDefault();
  }
  // ---------------------------------------------------------------- canvas
  get ctx() {
    return {
      vars: this.cfg.vars,
      now: () => Date.now(),
      timezone: this.cfg.timezone,
      assets: this.cfg.assets,
      fonts: this.cfg.fonts,
      editing: !0
    };
  }
  updated() {
    const t = this.querySelector(".ed-host");
    if (t) {
      if (!this.drag) {
        this.rendered?.destroy();
        for (const [e, s] of Object.entries(this.cfg.themeVariables ?? {})) t.style.setProperty(e, s);
        this.rendered = xs(t, this.data, this.ctx), this.zoom && (this.rendered.stage.style.width = `${this.data.width * this.zoom}px`, this.rendered.stage.style.height = `${this.data.height * this.zoom}px`);
      }
      this.placeOverlay();
    }
  }
  placeOverlay() {
    const t = this.querySelector(".ed-overlay"), e = this.rendered?.stage;
    !t || !e || (t.style.left = `${e.offsetLeft}px`, t.style.top = `${e.offsetTop}px`, t.style.width = `${e.offsetWidth}px`, t.style.height = `${e.offsetHeight}px`);
  }
  percent(t) {
    const e = this.rendered?.stage;
    return e ? [t.clientX / e.offsetWidth * 100, t.clientY / e.offsetHeight * 100] : [0, 0];
  }
  startDrag(t, e, s) {
    t.stopPropagation(), (!this.selected.has(e) || t.shiftKey) && this.select(e, t.shiftKey);
    const i = this.selection.filter((a) => !a.locked);
    if (!i.length) return;
    const [r, o] = this.percent(t);
    this.drag = {
      mode: s ? "resize" : "move",
      handle: s,
      x0: r,
      y0: o,
      moved: !1,
      start: Object.fromEntries(i.map((a) => [a.id, { ...a.frame }]))
    }, t.target.setPointerCapture(t.pointerId);
  }
  onMove(t) {
    const e = this.drag;
    if (!e) return;
    const [s, i] = this.percent(t);
    let r = s - e.x0, o = i - e.y0;
    if (!e.moved && Math.abs(r) < 0.2 && Math.abs(o) < 0.2) return;
    e.moved || (this.history.push(this.data), e.moved = !0);
    const a = new Set(Object.keys(e.start)), h = t.altKey, c = Nt(this.elements, a, "x"), d = Nt(this.elements, a, "y"), l = this.elements.map((f) => {
      const p = e.start[f.id];
      if (!p) return f;
      let g;
      if (e.mode === "move") {
        const [pt, te] = h ? [p.x + r, null] : zt(p.x + r, p.w, c), [mt, ee] = h ? [p.y + o, null] : zt(p.y + o, p.h, d);
        this.guides = { x: te, y: ee }, r = pt - p.x, o = mt - p.y, g = { ...p, x: w(pt), y: w(mt) };
      } else
        g = ks(p, e.handle ?? "se", r, o), g = { ...g, x: w(g.x), y: w(g.y), w: w(g.w), h: w(g.h) };
      const B = { ...f, frame: g }, ft = this.rendered?.elements.get(f.id);
      return ft && nt(ft, B), B;
    });
    this.data = { ...this.data, elements: l }, this.status = "dirty";
  }
  endDrag() {
    if (!this.drag) return;
    const t = this.drag.moved;
    this.drag = null, this.guides = { x: null, y: null }, t && this.requestUpdate();
  }
  // ---------------------------------------------------------------- rendering
  render() {
    const t = {
      saved: this.t("Saved"),
      dirty: this.t("Unsaved changes"),
      saving: this.t("Saving…"),
      error: this.error
    }[this.status];
    return u`
      <div class="ed-toolbar" role="toolbar" aria-label=${this.t("Layout")}>
        <strong class="ed-title">${this.cfg.layout?.name}</strong>
        <button class="btn btn-sm" ?disabled=${!this.history.canUndo} @click=${() => this.undo()}>${this.t("Undo")}</button>
        <button class="btn btn-sm" ?disabled=${!this.history.canRedo} @click=${() => this.redo()}>${this.t("Redo")}</button>
        <label class="ed-inline">${this.t("Zoom")}
          <select @change=${(e) => {
      this.zoom = Number(e.target.value);
    }}>
            <option value="0">${this.t("Fit")}</option>${[0.25, 0.5, 0.75, 1].map((e) => u`
            <option value=${e}>${e * 100}%</option>`)}</select></label>
        <span class="ed-status" role="status" data-status=${this.status}>${t}</span>
        ${this.error && this.status !== "error" ? u`<span class="ed-status" role="status">${this.error}</span>` : m}
        <button class="btn btn-sm btn-primary" @click=${() => {
      this.save();
    }}>${this.t("Save")}</button>
        ${this.cfg.canPublish ? u`<button class="btn btn-sm" @click=${() => {
      this.publish();
    }}>${this.t("Publish")}</button>` : m}
        <a class="btn btn-sm btn-ghost" href=${this.cfg.urls?.back}>${this.t("Back")}</a>
      </div>
      <div class="ed-body">
        <aside class="ed-side ed-left" aria-label=${this.t("Layers")}>
          <h2 class="ed-h">${this.t("Add")}</h2>
          <div class="ed-add">${(this.cfg.types ?? []).map((e) => u`
            <button class="btn btn-sm" @click=${() => this.add(e)}>${this.t(j[e] ?? e)}</button>`)}</div>
          <h2 class="ed-h">${this.t("Layers")}</h2>
          <ol class="ed-layers">${[...this.elements].reverse().map((e) => u`
            <li class=${this.selected.has(e.id) ? "selected" : ""}>
              <button class="ed-layer" aria-pressed=${this.selected.has(e.id)}
                      @click=${(s) => this.select(e.id, s.shiftKey)}>
                ${e.hidden ? "◌ " : ""}${e.locked ? "🔒 " : ""}${e.name || e.id}
                <span class="muted small">${this.t(j[e.type] ?? e.type)}</span></button></li>`)}</ol>
        </aside>
        <div class="ed-canvas" @pointerdown=${() => this.select(null)}>
          <div class="ed-host"></div>
          <div class="ed-overlay" @pointermove=${(e) => this.onMove(e)}
               @pointerup=${() => this.endDrag()} @pointercancel=${() => this.endDrag()}>
            ${this.guides.x !== null ? u`<div class="ed-guide ed-guide-x" ${tt((e) => {
      e.style.left = `${this.guides.x}%`;
    })}></div>` : m}
            ${this.guides.y !== null ? u`<div class="ed-guide ed-guide-y" ${tt((e) => {
      e.style.top = `${this.guides.y}%`;
    })}></div>` : m}
            ${this.elements.map((e) => this.box(e))}
          </div>
        </div>
        <aside class="ed-side ed-right" aria-label=${this.t("Properties")}>${this.panel()}</aside>
      </div>`;
  }
  box(t) {
    const e = this.selected.has(t.id);
    return u`<div class="ed-box ${e ? "selected" : ""} ${t.locked ? "locked" : ""}" data-id=${t.id}
        ${tt((s) => {
      s && nt(s, t);
    })}
        @pointerdown=${(s) => this.startDrag(s, t.id)}>
        ${e && this.selected.size === 1 && !t.locked ? Ns.map((s) => u`<span class="ed-handle ed-${s}"
          @pointerdown=${(i) => this.startDrag(i, t.id, s)}></span>`) : m}
      </div>`;
  }
  // ---------------------------------------------------------------- property panel
  field(t, e) {
    return u`<label class="ed-field"><span>${this.t(t)}</span>${e}</label>`;
  }
  num(t, e, s, i = {}) {
    return this.field(t, u`<input type="number" .value=${e === void 0 ? "" : String(e)}
      min=${i.min ?? ""} max=${i.max ?? ""} step=${i.step ?? "any"}
      @change=${(r) => {
      const o = r.target.value;
      s(o === "" ? void 0 : Number(o));
    }}>`);
  }
  check(t, e, s) {
    return u`<label class="ed-check"><input type="checkbox" .checked=${!!e}
      @change=${(i) => s(i.target.checked)}> ${this.t(t)}</label>`;
  }
  choice(t, e, s, i) {
    return this.field(t, u`<select @change=${(r) => i(r.target.value)}>
      ${s.map(([r, o]) => u`<option value=${r} ?selected=${(e ?? "") === r}>${this.t(o)}</option>`)}</select>`);
  }
  colour(t, e, s) {
    const i = !e || e.startsWith("token:") || e === "transparent", r = [["", "None"], ...Ms.map((o) => [
      `token:${o}`,
      Ps[o]
    ]), ["custom", "Custom"]];
    return u`<div class="ed-colour">${this.choice(t, i ? e ?? "" : "custom", r, (o) => s(o === "custom" ? "#ffffff" : o || void 0))}
      ${i ? m : u`<input type="color" aria-label=${this.t(t)} .value=${e ?? "#ffffff"}
        @change=${(o) => s(o.target.value)}>`}</div>`;
  }
  assetSelect(t, e, s, i) {
    const r = Object.values(this.cfg.assets).filter((o) => s.includes(o.kind));
    return this.choice(
      t,
      String(e ?? ""),
      [["", "None"], ...r.map((o) => [o.id, o.name])],
      i
    );
  }
  setProp(t, e) {
    this.patchSelected((s) => {
      s.props = { ...s.props ?? {}, [t]: e }, (e === void 0 || e === "") && delete s.props[t];
    });
  }
  setStyle(t, e) {
    this.patchSelected((s) => {
      s.style = { ...s.style ?? {} }, e === void 0 || e === "" ? delete s.style[t] : s.style[t] = e;
    });
  }
  panel() {
    const t = this.selection;
    if (!t.length) return this.layoutPanel();
    if (t.length > 1) {
      const a = (h, c) => u`<button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: Cs(this.elements, this.selected, h) })}>${this.t(c)}</button>`;
      return u`<h2 class="ed-h">${this.t("Several elements selected")}</h2>
        <div class="ed-add">${a("left", "Align left")}${a("center", "Align centre")}${a("right", "Align right")}
          ${a("top", "Align top")}${a("middle", "Align middle")}${a("bottom", "Align bottom")}</div>
        <div class="ed-add"><button class="btn btn-sm" @click=${() => this.duplicateSelected()}>${this.t("Duplicate")}</button>
          <button class="btn btn-sm btn-danger" @click=${() => this.removeSelected()}>${this.t("Delete")}</button></div>`;
    }
    const e = t[0], s = e.props ?? {}, i = e.style ?? {}, r = e.frame, o = (a) => (h) => this.patchSelected((c) => {
      c.frame = { ...c.frame, [a]: h ?? 0 };
    });
    return u`
      <h2 class="ed-h">${this.t(j[e.type] ?? e.type)}</h2>
      ${this.field("Name", u`<input .value=${e.name ?? ""} maxlength="100"
        @change=${(a) => this.patchSelected((h) => {
      h.name = a.target.value;
    })}>`)}
      <div class="ed-add">
        <button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: Tt(this.elements, e.id, 1) })}>${this.t("Bring forward")}</button>
        <button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: Tt(this.elements, e.id, -1) })}>${this.t("Send backward")}</button>
        <button class="btn btn-sm" @click=${() => this.duplicateSelected()}>${this.t("Duplicate")}</button>
        <button class="btn btn-sm btn-danger" @click=${() => this.removeSelected()}>${this.t("Delete")}</button></div>
      <fieldset class="ed-group"><legend>${this.t("Position and size")}</legend><div class="ed-grid">
        ${this.num("X", r.x, o("x"))}${this.num("Y", r.y, o("y"))}
        ${this.num("Width", r.w, o("w"), { min: 0 })}${this.num("Height", r.h, o("h"), { min: 0 })}
        ${this.num("Rotation", r.rotate, o("rotate"), { min: -360, max: 360 })}</div>
        ${this.check("Hidden", e.hidden, (a) => this.patchSelected((h) => {
      h.hidden = a || void 0;
    }))}
        ${this.check("Locked", e.locked, (a) => this.patchSelected((h) => {
      h.locked = a || void 0;
    }))}</fieldset>
      <fieldset class="ed-group"><legend>${this.t("Content")}</legend>${this.contentFields(e.type, s)}</fieldset>
      <fieldset class="ed-group"><legend>${this.t("Style")}</legend>
        ${this.colour("Colour", i.color, (a) => this.setStyle("color", a))}
        ${this.colour("Background", i.background, (a) => this.setStyle("background", a))}
        ${this.choice("Font", i.fontFamily ?? "", [
      ["", "None"],
      ["token:body", "Body font"],
      ["token:heading", "Heading font"],
      ...this.cfg.fontChoices.map((a) => [a.value, a.label])
    ], (a) => this.setStyle("fontFamily", a || void 0))}
        <div class="ed-grid">
          ${this.num("Font size", i.fontSize, (a) => this.setStyle("fontSize", a), { min: 0.5, max: 100 })}
          ${this.num("Weight", i.fontWeight, (a) => this.setStyle("fontWeight", a), { min: 100, max: 900, step: 100 })}
          ${this.num("Line height", i.lineHeight, (a) => this.setStyle("lineHeight", a), { min: 0.5, max: 4 })}
          ${this.num("Letter spacing", i.letterSpacing, (a) => this.setStyle("letterSpacing", a), { min: -0.5, max: 2 })}
          ${this.num("Padding", i.padding, (a) => this.setStyle("padding", a), { min: 0, max: 50 })}
          ${this.num("Corner radius", i.radius, (a) => this.setStyle("radius", a), { min: 0, max: 50 })}
          ${this.num("Border", i.borderWidth, (a) => this.setStyle("borderWidth", a), { min: 0, max: 20 })}
          ${this.num("Opacity", i.opacity, (a) => this.setStyle("opacity", a), { min: 0, max: 1, step: 0.05 })}</div>
        ${this.colour("Border colour", i.borderColor, (a) => this.setStyle("borderColor", a))}
        ${this.choice("Alignment", i.textAlign, [
      ["", "None"],
      ["left", "Left"],
      ["center", "Center"],
      ["right", "Right"],
      ["justify", "Justify"]
    ], (a) => this.setStyle("textAlign", a || void 0))}
        ${this.choice(
      "Vertical",
      i.verticalAlign,
      [["", "None"], ["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]],
      (a) => this.setStyle("verticalAlign", a || void 0)
    )}
        ${this.choice(
      "Style of text",
      i.fontStyle,
      [["", "None"], ["normal", "Normal"], ["italic", "Italic"]],
      (a) => this.setStyle("fontStyle", a || void 0)
    )}
        ${this.choice("Text case", i.textTransform, [
      ["", "None"],
      ["uppercase", "Uppercase"],
      ["lowercase", "Lowercase"],
      ["capitalize", "Capitalise"]
    ], (a) => this.setStyle("textTransform", a || void 0))}
        ${this.check("Shadow", i.shadow, (a) => this.setStyle("shadow", a || void 0))}
        ${this.check("Tabular numbers", i.tabularNumbers, (a) => this.setStyle("tabularNumbers", a || void 0))}</fieldset>
      <fieldset class="ed-group"><legend>${this.t("Animation")}</legend>
        ${this.choice("Entrance", e.animation?.enter ?? "none", [
      ["none", "None"],
      ["fade", "Fade"],
      ["slide-up", "Slide up"],
      ["slide-left", "Slide in"],
      ["zoom", "Zoom in"]
    ], (a) => this.patchSelected((h) => {
      h.animation = { ...h.animation ?? {}, enter: a };
    }))}
        <div class="ed-grid">${this.num("Duration (ms)", e.animation?.duration, (a) => this.patchSelected((h) => {
      h.animation = { ...h.animation ?? {}, duration: a };
    }), { min: 0, max: 1e4, step: 50 })}
          ${this.num("Delay (ms)", e.animation?.delay, (a) => this.patchSelected((h) => {
      h.animation = { ...h.animation ?? {}, delay: a };
    }), { min: 0, max: 6e4, step: 50 })}</div></fieldset>
      ${this.field("Show only if", u`<input .value=${e.visible_if ?? ""} maxlength="300" placeholder="screen.zone"
        @change=${(a) => this.patchSelected((h) => {
      h.visible_if = a.target.value || void 0;
    })}>`)}`;
  }
  contentFields(t, e) {
    const s = (o, a, h = 3) => this.field(o, u`<textarea rows=${h}
      .value=${String(e[a] ?? "")} @change=${(c) => this.setProp(a, c.target.value)}></textarea>`), i = this.choice(
      "Fit mode",
      String(e.fit ?? ""),
      [["contain", "Contain"], ["cover", "Cover"], ["fill", "Stretch"]],
      (o) => this.setProp("fit", o)
    ), r = u`<p class="small muted">${this.t("Template variables: {{ event.name }}, {{ screen.name }}, {{ screen.zone }}, {{ now|time }}")}</p>`;
    switch (t) {
      case "text":
        return u`${s("Text", "text")}${r}${this.check("Shrink text to fit", e.autofit, (o) => this.setProp("autofit", o))}
          ${this.check("Ticker (scrolling)", e.marquee, (o) => this.setProp("marquee", o))}
          ${this.num("Maximum lines", e.clamp, (o) => this.setProp("clamp", o), { min: 0, max: 50, step: 1 })}`;
      case "richtext":
        return u`${s("Text", "text", 6)}${r}`;
      case "image":
        return u`${this.assetSelect("File", e.asset, ["image", "svg"], (o) => this.setProp("asset", o))}${i}
          <a class="small" href=${this.cfg.urls.assets} target="_blank" rel="noopener">${this.t("Upload files")}</a>`;
      case "slideshow": {
        const o = new Set(e.assets ?? []);
        return u`<p class="ed-label">${this.t("Images")}</p><div class="ed-list">${Object.values(this.cfg.assets).filter((a) => a.kind === "image" || a.kind === "svg").map((a) => this.check(a.name, o.has(a.id), (h) => {
          const c = new Set(o);
          h ? c.add(a.id) : c.delete(a.id), this.setProp("assets", [...c]);
        }))}</div>${this.num("Seconds per image", e.interval, (a) => this.setProp("interval", a), { min: 1, max: 3600 })}${i}`;
      }
      case "video":
        return u`${this.assetSelect("File", e.asset, ["video"], (o) => this.setProp("asset", o))}${i}
          ${this.check("Loop", e.loop, (o) => this.setProp("loop", o))}${this.check("Muted", e.muted, (o) => this.setProp("muted", o))}`;
      case "audio":
        return u`${this.assetSelect("File", e.asset, ["audio"], (o) => this.setProp("asset", o))}
          ${this.check("Loop", e.loop, (o) => this.setProp("loop", o))}`;
      case "shape":
        return this.choice(
          "Form",
          String(e.shape ?? "rect"),
          [["rect", "Rectangle"], ["ellipse", "Ellipse"], ["line", "Line"]],
          (o) => this.setProp("shape", o)
        );
      case "qr":
        return u`${s("Text", "text", 2)}${r}`;
      case "clock":
        return u`${this.choice(
          "Format",
          String(e.format ?? "HH:mm"),
          [["HH:mm", "HH:mm"], ["HH:mm:ss", "HH:mm:ss"], ["h:mm a", "h:mm a"]],
          (o) => this.setProp("format", o)
        )}
          ${this.field("Time zone (empty = event)", u`<input .value=${String(e.timezone ?? "")} placeholder="Europe/Berlin"
            @change=${(o) => this.setProp("timezone", o.target.value)}>`)}`;
      case "countdown":
        return u`${this.field("Target time", u`<input type="datetime-local" .value=${String(e.target ?? "").slice(0, 16)}
            @change=${(o) => this.setProp("target", o.target.value)}>`)}
          ${this.choice("Format", String(e.format ?? "auto"), [
          ["auto", "Automatic"],
          ["hms", "Hours:minutes:seconds"],
          ["ms", "Minutes:seconds"],
          ["days", "Days"]
        ], (o) => this.setProp("format", o))}
          ${s("Text when finished", "finished", 1)}`;
      case "date":
        return this.choice("Format", String(e.format ?? "long"), [
          ["long", "Long"],
          ["short", "Short"],
          ["weekday", "Weekday"],
          ["iso", "ISO"]
        ], (o) => this.setProp("format", o));
      default:
        return u``;
    }
  }
  layoutPanel() {
    const t = this.data, e = t.background ?? {}, s = (i, r) => {
      const o = { ...e, [i]: r };
      r || delete o[i], this.commit({ ...t, background: Object.keys(o).length ? o : void 0 });
    };
    return u`<h2 class="ed-h">${this.t("Layout")}</h2>
      <p class="small muted">${this.t("Select an element on the canvas or in the layers list.")}</p>
      <div class="ed-grid">
        ${this.num("Width", t.width, (i) => this.commit({ ...t, width: Math.max(64, Math.round(i ?? 1920)) }), { min: 64, max: 16384, step: 1 })}
        ${this.num("Height", t.height, (i) => this.commit({ ...t, height: Math.max(64, Math.round(i ?? 1080)) }), { min: 64, max: 16384, step: 1 })}</div>
      ${this.colour("Background", e.color, (i) => s("color", i))}
      ${this.assetSelect("Background image", e.asset, ["image", "svg"], (i) => s("asset", i || void 0))}
      ${this.num("Seconds on screen (playlists)", t.duration, (i) => this.commit({ ...t, duration: i }), { min: 1, max: 86400, step: 1 })}`;
  }
};
ut.properties = {
  data: { state: !0 },
  selected: { state: !0 },
  status: { state: !0 },
  zoom: { state: !0 },
  guides: { state: !0 },
  error: { state: !0 }
};
let rt = ut;
customElements.get("evac-layout-editor") || customElements.define("evac-layout-editor", rt);
export {
  rt as LayoutEditor
};
