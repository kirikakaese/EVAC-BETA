// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC venue map editor, built from frontend/src with `npm run build` - do not edit.
// Includes Lit (BSD-3-Clause, https://lit.dev).
const R = globalThis, Z = R.ShadowRoot && (R.ShadyCSS === void 0 || R.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, ut = /* @__PURE__ */ Symbol(), G = /* @__PURE__ */ new WeakMap();
let kt = class {
  constructor(t, e, s) {
    if (this._$cssResult$ = !0, s !== ut) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (Z && t === void 0) {
      const s = e !== void 0 && e.length === 1;
      s && (t = G.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), s && G.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const Pt = (n) => new kt(typeof n == "string" ? n : n + "", void 0, ut), Ct = (n, t) => {
  if (Z) n.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const s = document.createElement("style"), i = R.litNonce;
    i !== void 0 && s.setAttribute("nonce", i), s.textContent = e.cssText, n.appendChild(s);
  }
}, Q = Z ? (n) => n : (n) => n instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const s of t.cssRules) e += s.cssText;
  return Pt(e);
})(n) : n;
const { is: Ot, defineProperty: Ut, getOwnPropertyDescriptor: Nt, getOwnPropertyNames: Tt, getOwnPropertySymbols: zt, getPrototypeOf: It } = Object, x = globalThis, tt = x.trustedTypes, Ht = tt ? tt.emptyScript : "", Rt = x.reactiveElementPolyfillSupport, C = (n, t) => n, K = { toAttribute(n, t) {
  switch (t) {
    case Boolean:
      n = n ? Ht : null;
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
} }, $t = (n, t) => !Ot(n, t), et = { attribute: !0, type: String, converter: K, reflect: !1, useDefault: !1, hasChanged: $t };
Symbol.metadata ?? (Symbol.metadata = /* @__PURE__ */ Symbol("metadata")), x.litPropertyMetadata ?? (x.litPropertyMetadata = /* @__PURE__ */ new WeakMap());
let M = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ?? (this.l = [])).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = et) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const s = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(t, s, e);
      i !== void 0 && Ut(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, s) {
    const { get: i, set: a } = Nt(this.prototype, t) ?? { get() {
      return this[e];
    }, set(o) {
      this[e] = o;
    } };
    return { get: i, set(o) {
      const r = i?.call(this);
      a?.call(this, o), this.requestUpdate(t, r, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? et;
  }
  static _$Ei() {
    if (this.hasOwnProperty(C("elementProperties"))) return;
    const t = It(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(C("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(C("properties"))) {
      const e = this.properties, s = [...Tt(e), ...zt(e)];
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
      for (const i of s) e.unshift(Q(i));
    } else t !== void 0 && e.push(Q(t));
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
    return Ct(t, this.constructor.elementStyles), t;
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
      const a = (s.converter?.toAttribute !== void 0 ? s.converter : K).toAttribute(e, s.type);
      this._$Em = t, a == null ? this.removeAttribute(i) : this.setAttribute(i, a), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const s = this.constructor, i = s._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const a = s.getPropertyOptions(i), o = typeof a.converter == "function" ? { fromAttribute: a.converter } : a.converter?.fromAttribute !== void 0 ? a.converter : K;
      this._$Em = i;
      const r = o.fromAttribute(e, a.type);
      this[i] = r ?? this._$Ej?.get(i) ?? r, this._$Em = null;
    }
  }
  requestUpdate(t, e, s, i = !1, a) {
    if (t !== void 0) {
      const o = this.constructor;
      if (i === !1 && (a = this[t]), s ?? (s = o.getPropertyOptions(t)), !((s.hasChanged ?? $t)(a, e) || s.useDefault && s.reflect && a === this._$Ej?.get(t) && !this.hasAttribute(o._$Eu(t, s)))) return;
      this.C(t, e, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: s, reflect: i, wrapped: a }, o) {
    s && !(this._$Ej ?? (this._$Ej = /* @__PURE__ */ new Map())).has(t) && (this._$Ej.set(t, o ?? e ?? this[t]), a !== !0 || o !== void 0) || (this._$AL.has(t) || (this.hasUpdated || s || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ?? (this._$Eq = /* @__PURE__ */ new Set())).add(t));
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
        for (const [i, a] of this._$Ep) this[i] = a;
        this._$Ep = void 0;
      }
      const s = this.constructor.elementProperties;
      if (s.size > 0) for (const [i, a] of s) {
        const { wrapped: o } = a, r = this[i];
        o !== !0 || this._$AL.has(i) || r === void 0 || this.C(i, void 0, a, r);
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
M.elementStyles = [], M.shadowRootOptions = { mode: "open" }, M[C("elementProperties")] = /* @__PURE__ */ new Map(), M[C("finalized")] = /* @__PURE__ */ new Map(), Rt?.({ ReactiveElement: M }), (x.reactiveElementVersions ?? (x.reactiveElementVersions = [])).push("2.1.2");
const O = globalThis, st = (n) => n, D = O.trustedTypes, it = D ? D.createPolicy("lit-html", { createHTML: (n) => n }) : void 0, mt = "$lit$", v = `lit$${Math.random().toFixed(9).slice(2)}$`, yt = "?" + v, Dt = `<${yt}>`, A = document, T = () => A.createComment(""), z = (n) => n === null || typeof n != "object" && typeof n != "function", V = Array.isArray, jt = (n) => V(n) || typeof n?.[Symbol.iterator] == "function", W = `[ 	
\f\r]`, P = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, nt = /-->/g, ot = />/g, _ = RegExp(`>|${W}(?:([^\\s"'>=/]+)(${W}*=${W}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), at = /'/g, rt = /"/g, ft = /^(?:script|style|textarea|title)$/i, gt = (n) => (t, ...e) => ({ _$litType$: n, strings: t, values: e }), d = gt(1), f = gt(2), E = /* @__PURE__ */ Symbol.for("lit-noChange"), c = /* @__PURE__ */ Symbol.for("lit-nothing"), lt = /* @__PURE__ */ new WeakMap(), w = A.createTreeWalker(A, 129);
function bt(n, t) {
  if (!V(n) || !n.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return it !== void 0 ? it.createHTML(t) : t;
}
const Lt = (n, t) => {
  const e = n.length - 1, s = [];
  let i, a = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", o = P;
  for (let r = 0; r < e; r++) {
    const l = n[r];
    let h, u, p = -1, m = 0;
    for (; m < l.length && (o.lastIndex = m, u = o.exec(l), u !== null); ) m = o.lastIndex, o === P ? u[1] === "!--" ? o = nt : u[1] !== void 0 ? o = ot : u[2] !== void 0 ? (ft.test(u[2]) && (i = RegExp("</" + u[2], "g")), o = _) : u[3] !== void 0 && (o = _) : o === _ ? u[0] === ">" ? (o = i ?? P, p = -1) : u[1] === void 0 ? p = -2 : (p = o.lastIndex - u[2].length, h = u[1], o = u[3] === void 0 ? _ : u[3] === '"' ? rt : at) : o === rt || o === at ? o = _ : o === nt || o === ot ? o = P : (o = _, i = void 0);
    const y = o === _ && n[r + 1].startsWith("/>") ? " " : "";
    a += o === P ? l + Dt : p >= 0 ? (s.push(h), l.slice(0, p) + mt + l.slice(p) + v + y) : l + v + (p === -2 ? r : y);
  }
  return [bt(n, a + (n[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), s];
};
class I {
  constructor({ strings: t, _$litType$: e }, s) {
    let i;
    this.parts = [];
    let a = 0, o = 0;
    const r = t.length - 1, l = this.parts, [h, u] = Lt(t, e);
    if (this.el = I.createElement(h, s), w.currentNode = this.el.content, e === 2 || e === 3) {
      const p = this.el.content.firstChild;
      p.replaceWith(...p.childNodes);
    }
    for (; (i = w.nextNode()) !== null && l.length < r; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const p of i.getAttributeNames()) if (p.endsWith(mt)) {
          const m = u[o++], y = i.getAttribute(p).split(v), g = /([.?@])?(.*)/.exec(m);
          l.push({ type: 1, index: a, name: g[2], strings: y, ctor: g[1] === "." ? Bt : g[1] === "?" ? qt : g[1] === "@" ? Ft : L }), i.removeAttribute(p);
        } else p.startsWith(v) && (l.push({ type: 6, index: a }), i.removeAttribute(p));
        if (ft.test(i.tagName)) {
          const p = i.textContent.split(v), m = p.length - 1;
          if (m > 0) {
            i.textContent = D ? D.emptyScript : "";
            for (let y = 0; y < m; y++) i.append(p[y], T()), w.nextNode(), l.push({ type: 2, index: ++a });
            i.append(p[m], T());
          }
        }
      } else if (i.nodeType === 8) if (i.data === yt) l.push({ type: 2, index: a });
      else {
        let p = -1;
        for (; (p = i.data.indexOf(v, p + 1)) !== -1; ) l.push({ type: 7, index: a }), p += v.length - 1;
      }
      a++;
    }
  }
  static createElement(t, e) {
    const s = A.createElement("template");
    return s.innerHTML = t, s;
  }
}
function S(n, t, e = n, s) {
  if (t === E) return t;
  let i = s !== void 0 ? e._$Co?.[s] : e._$Cl;
  const a = z(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== a && (i?._$AO?.(!1), a === void 0 ? i = void 0 : (i = new a(n), i._$AT(n, e, s)), s !== void 0 ? (e._$Co ?? (e._$Co = []))[s] = i : e._$Cl = i), i !== void 0 && (t = S(n, i._$AS(n, t.values), i, s)), t;
}
class Wt {
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
    const { el: { content: e }, parts: s } = this._$AD, i = (t?.creationScope ?? A).importNode(e, !0);
    w.currentNode = i;
    let a = w.nextNode(), o = 0, r = 0, l = s[0];
    for (; l !== void 0; ) {
      if (o === l.index) {
        let h;
        l.type === 2 ? h = new H(a, a.nextSibling, this, t) : l.type === 1 ? h = new l.ctor(a, l.name, l.strings, this, t) : l.type === 6 && (h = new Yt(a, this, t)), this._$AV.push(h), l = s[++r];
      }
      o !== l?.index && (a = w.nextNode(), o++);
    }
    return w.currentNode = A, i;
  }
  p(t) {
    let e = 0;
    for (const s of this._$AV) s !== void 0 && (s.strings !== void 0 ? (s._$AI(t, s, e), e += s.strings.length - 2) : s._$AI(t[e])), e++;
  }
}
class H {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, s, i) {
    this.type = 2, this._$AH = c, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = s, this.options = i, this._$Cv = i?.isConnected ?? !0;
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
    t = S(this, t, e), z(t) ? t === c || t == null || t === "" ? (this._$AH !== c && this._$AR(), this._$AH = c) : t !== this._$AH && t !== E && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : jt(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== c && z(this._$AH) ? this._$AA.nextSibling.data = t : this.T(A.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: s } = t, i = typeof s == "number" ? this._$AC(t) : (s.el === void 0 && (s.el = I.createElement(bt(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const a = new Wt(i, this), o = a.u(this.options);
      a.p(e), this.T(o), this._$AH = a;
    }
  }
  _$AC(t) {
    let e = lt.get(t.strings);
    return e === void 0 && lt.set(t.strings, e = new I(t)), e;
  }
  k(t) {
    V(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let s, i = 0;
    for (const a of t) i === e.length ? e.push(s = new H(this.O(T()), this.O(T()), this, this.options)) : s = e[i], s._$AI(a), i++;
    i < e.length && (this._$AR(s && s._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const s = st(t).nextSibling;
      st(t).remove(), t = s;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class L {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, s, i, a) {
    this.type = 1, this._$AH = c, this._$AN = void 0, this.element = t, this.name = e, this._$AM = i, this.options = a, s.length > 2 || s[0] !== "" || s[1] !== "" ? (this._$AH = Array(s.length - 1).fill(new String()), this.strings = s) : this._$AH = c;
  }
  _$AI(t, e = this, s, i) {
    const a = this.strings;
    let o = !1;
    if (a === void 0) t = S(this, t, e, 0), o = !z(t) || t !== this._$AH && t !== E, o && (this._$AH = t);
    else {
      const r = t;
      let l, h;
      for (t = a[0], l = 0; l < a.length - 1; l++) h = S(this, r[s + l], e, l), h === E && (h = this._$AH[l]), o || (o = !z(h) || h !== this._$AH[l]), h === c ? t = c : t !== c && (t += (h ?? "") + a[l + 1]), this._$AH[l] = h;
    }
    o && !i && this.j(t);
  }
  j(t) {
    t === c ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class Bt extends L {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === c ? void 0 : t;
  }
}
class qt extends L {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== c);
  }
}
class Ft extends L {
  constructor(t, e, s, i, a) {
    super(t, e, s, i, a), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = S(this, t, e, 0) ?? c) === E) return;
    const s = this._$AH, i = t === c && s !== c || t.capture !== s.capture || t.once !== s.once || t.passive !== s.passive, a = t !== c && (s === c || i);
    i && this.element.removeEventListener(this.name, this, s), a && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class Yt {
  constructor(t, e, s) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    S(this, t);
  }
}
const Kt = O.litHtmlPolyfillSupport;
Kt?.(I, H), (O.litHtmlVersions ?? (O.litHtmlVersions = [])).push("3.3.3");
const Xt = (n, t, e) => {
  const s = e?.renderBefore ?? t;
  let i = s._$litPart$;
  if (i === void 0) {
    const a = e?.renderBefore ?? null;
    s._$litPart$ = i = new H(t.insertBefore(T(), a), a, void 0, e ?? {});
  }
  return i._$AI(n), i;
};
const U = globalThis;
class N extends M {
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
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = Xt(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return E;
  }
}
N._$litElement$ = !0, N.finalized = !0, U.litElementHydrateSupport?.({ LitElement: N });
const Zt = U.litElementPolyfillSupport;
Zt?.({ LitElement: N });
(U.litElementVersions ?? (U.litElementVersions = [])).push("4.2.2");
const B = {
  waypoint: "W",
  door: "D",
  stairs: "S",
  lift: "L",
  exit: "E",
  assembly: "A"
}, $ = (n) => Math.round(n * 1e3) / 1e3;
function q(n) {
  if (n.plan) {
    const a = n.plan.width * n.plan.metresPerPx, o = n.plan.height * n.plan.metresPerPx;
    return F({ x: 0, y: 0, w: a, h: o });
  }
  const t = [], e = [];
  for (const a of n.points)
    t.push(a.x), e.push(a.y);
  for (const a of n.zones) for (const [o, r] of a.area ?? [])
    t.push(o), e.push(r);
  for (const a of n.layers) for (const o of a.items) o.placed && o.x !== null && o.y !== null && (t.push(o.x), e.push(o.y));
  if (!t.length) return F({ x: 0, y: 0, w: 100, h: 60 });
  const s = Math.min(...t), i = Math.min(...e);
  return F({ x: s, y: i, w: Math.max(Math.max(...t) - s, 20), h: Math.max(Math.max(...e) - i, 12) });
}
function F(n, t = 0.05) {
  return { x: n.x - n.w * t, y: n.y - n.h * t, w: n.w * (1 + 2 * t), h: n.h * (1 + 2 * t) };
}
function Y(n, t, e, s) {
  const i = Math.min(Math.max(n.w / t, 1), 1e5), a = n.h * (i / n.w);
  return { x: e - (e - n.x) * (i / n.w), y: s - (s - n.y) * (a / n.h), w: i, h: a };
}
function Vt(n, t) {
  return Math.hypot(n[0] - t[0], n[1] - t[1]);
}
function ht(n, t, e, s) {
  const i = t.x - n.x, a = t.y - n.y, o = Math.hypot(i, a);
  if (o < 1e-6) return null;
  const r = i / o, l = a / o, h = Math.min(e, o * 0.6), u = n.x + r * h, p = n.y + l * h, m = (y) => {
    const g = Math.cos(y), b = Math.sin(y);
    return [$(u - s * (r * g - l * b)), $(p - s * (r * b + l * g))];
  };
  return { x1: $(n.x), y1: $(n.y), x2: $(u), y2: $(p), barbs: [m(0.5), m(-0.5)] };
}
function Jt(n, t, e, s) {
  const i = e * Math.PI / 180, a = Math.sin(i), o = -Math.cos(i), r = [n + a * s * 3, t + o * s * 3], l = [n + o * s * 1.1, t - a * s * 1.1], h = [n - o * s * 1.1, t + a * s * 1.1];
  return [r, l, h].map(([u, p]) => `${$(u)},${$(p)}`).join(" ");
}
function Gt(n, t) {
  return n / t.metresPerPx;
}
const j = 111320;
function Qt(n, t, e) {
  const s = n.rotation * Math.PI / 180;
  return [t * Math.cos(s) - e * Math.sin(s), t * Math.sin(s) + e * Math.cos(s)];
}
function te(n, t, e) {
  return [n.lat - e / j, n.lon + t / (j * Math.cos(n.lat * Math.PI / 180))];
}
function ct(n, t, e) {
  return [(e - n.lon) * j * Math.cos(n.lat * Math.PI / 180), (n.lat - t) * j];
}
function dt(n, t, e) {
  const s = 2 ** e, i = Math.max(Math.min(n, 85.0511), -85.0511) * Math.PI / 180, a = Math.floor((t + 180) / 360 * s), o = Math.floor((1 - Math.asinh(Math.tan(i)) / Math.PI) / 2 * s);
  return [Math.min(Math.max(a, 0), s - 1), Math.min(Math.max(o, 0), s - 1)];
}
function pt(n, t, e) {
  const s = 2 ** n;
  return [Math.atan(Math.sinh(Math.PI * (1 - 2 * e / s))) * 180 / Math.PI, t / s * 360 - 180];
}
function ee(n, t, e, s, i = 80) {
  const a = [
    [n.x, n.y],
    [n.x + n.w, n.y],
    [n.x, n.y + n.h],
    [n.x + n.w, n.y + n.h]
  ].map(([h, u]) => te(t, ...Qt(t, h, u))), o = a.map((h) => h[0]), r = a.map((h) => h[1]), l = Math.log2(156543.03 * Math.cos(t.lat * Math.PI / 180) / Math.max(e, 1e-3));
  for (let h = Math.min(Math.max(Math.round(l), 1), s); h >= 1; h--) {
    const [u, p] = dt(Math.max(...o), Math.min(...r), h), [m, y] = dt(Math.min(...o), Math.max(...r), h);
    if ((m - u + 1) * (y - p + 1) > i) continue;
    const g = [];
    for (let b = u; b <= m; b++) for (let k = p; k <= y; k++) {
      const [vt, xt] = pt(h, b, k), [_t, wt] = pt(h, b + 1, k + 1), [At, Mt] = ct(t, vt, xt), [Et, St] = ct(t, _t, wt);
      g.push({ z: h, x: b, y: k, e0: $(At), s0: $(Mt), e1: $(Et), s1: $(St) });
    }
    return g;
  }
  return [];
}
function se() {
  return document.cookie.split("; ").find((n) => n.startsWith("csrftoken="))?.split("=")[1] ?? "";
}
function ie() {
  const n = document.getElementById("map-config");
  return n?.textContent ? JSON.parse(n.textContent) : null;
}
const J = class J extends N {
  constructor() {
    super(...arguments), this.data = null, this.view = { x: 0, y: 0, w: 100, h: 60 }, this.tool = "select", this.selected = null, this.status = "", this.pointKind = "exit", this.pending = null, this.corners = [], this.zoneId = "", this.placing = null, this.measured = [], this.planOpacity = 1, this.alignOffset = [0, 0], this.tileTries = /* @__PURE__ */ new Map(), this.cfg = ie(), this.drag = null, this.queue = Promise.resolve();
  }
  createRenderRoot() {
    return this;
  }
  // light DOM: portal styles apply
  connectedCallback() {
    super.connectedCallback(), this.textContent = "", this.load(!0);
  }
  t(t) {
    return this.cfg?.strings[t] ?? t;
  }
  async load(t = !1) {
    if (!this.cfg) return;
    const e = await fetch(this.cfg.dataUrl, { credentials: "same-origin" });
    if (!e.ok) {
      this.status = this.t("Could not save");
      return;
    }
    this.data = await e.json(), t && (this.view = q(this.data));
  }
  /** One operation at a time, in order (a drag and a click must not race). */
  op(t) {
    const e = this.queue.then(() => this.send(t), () => this.send(t));
    return this.queue = e, e;
  }
  async send(t) {
    if (!this.cfg) return null;
    this.status = this.t("Saving…");
    const e = await fetch(this.cfg.opUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": se() },
      body: JSON.stringify(t)
    }), s = await e.json().catch(() => ({}));
    return this.status = e.ok ? this.t("Saved") : `${this.t("Could not save")}: ${String(s.error ?? e.status)}`, await this.load(), e.ok ? s : null;
  }
  // ---------------------------------------------------------------- coordinates
  svgEl() {
    return this.querySelector("svg.mapeditor-canvas");
  }
  toMap(t) {
    const e = this.svgEl(), s = e?.getScreenCTM();
    if (!e || !s) return [0, 0];
    const i = new DOMPoint(t.clientX, t.clientY).matrixTransform(s.inverse());
    return [$(i.x), $(i.y)];
  }
  pointById(t) {
    return this.data?.points.find((e) => e.id === t);
  }
  item(t, e) {
    return this.data?.layers.find((s) => s.key === t)?.items.find((s) => s.id === e);
  }
  // ---------------------------------------------------------------- pointer handling
  onWheel(t) {
    t.preventDefault();
    const [e, s] = this.toMap(t);
    this.view = Y(this.view, t.deltaY < 0 ? 1.2 : 1 / 1.2, e, s);
  }
  onDown(t) {
    const e = t.target, s = e.closest("[data-point]")?.getAttribute("data-point"), i = e.closest("[data-item]"), [a, o] = this.toMap(t), r = this.data?.canEdit ?? !1;
    if (this.tool === "align") {
      if (!r || !this.data?.map?.frame) return;
      this.drag = { kind: "align", sx: t.clientX, sy: t.clientY, start: this.view, moved: !1 };
    } else if (this.tool === "select" && s && r)
      this.selected = { type: "point", id: s }, this.drag = { kind: "point", id: s, sx: t.clientX, sy: t.clientY, start: this.view, moved: !1 };
    else if (this.tool === "select" && i) {
      const l = i.getAttribute("data-item") ?? "", h = i.getAttribute("data-layer") ?? "";
      this.selected = { type: "item", id: l, layer: h }, r && (this.drag = { kind: "item", id: l, layer: h, sx: t.clientX, sy: t.clientY, start: this.view, moved: !1 });
    } else if (this.tool === "select") {
      const l = e.closest("[data-edge]")?.getAttribute("data-edge");
      this.selected = l ? { type: "edge", id: l } : null, this.drag = { kind: "pan", sx: t.clientX, sy: t.clientY, start: this.view, moved: !1 };
    } else {
      this.mapClick(a, o, s ?? null);
      return;
    }
    t.currentTarget.setPointerCapture?.(t.pointerId);
  }
  onMove(t) {
    const e = this.drag;
    if (!e || (e.moved = e.moved || Math.abs(t.clientX - e.sx) + Math.abs(t.clientY - e.sy) > 3, !e.moved)) return;
    if (e.kind === "pan" || e.kind === "align") {
      const a = this.svgEl(), o = a ? e.start.w / a.clientWidth : 1;
      if (e.kind === "align") {
        this.alignOffset = [$((t.clientX - e.sx) * o), $((t.clientY - e.sy) * o)];
        return;
      }
      this.view = { ...e.start, x: e.start.x - (t.clientX - e.sx) * o, y: e.start.y - (t.clientY - e.sy) * o };
      return;
    }
    const [s, i] = this.toMap(t);
    if (e.x = s, e.y = i, e.kind === "point") {
      const a = this.pointById(e.id ?? "");
      a && (a.x = s, a.y = i);
    } else {
      const a = this.item(e.layer ?? "", e.id ?? "");
      a && (a.x = s, a.y = i);
    }
    this.requestUpdate();
  }
  onUp() {
    const t = this.drag;
    if (this.drag = null, t?.kind === "align") {
      const [e, s] = this.alignOffset;
      t.moved && (e || s) ? this.op({ op: "georef.move", dx: e, dy: s }).then(() => {
        this.alignOffset = [0, 0];
      }) : this.alignOffset = [0, 0];
      return;
    }
    if (!(!t || !t.moved || t.x === void 0) && (t.kind === "point" && this.op({ op: "point.update", id: t.id, x: t.x, y: t.y }), t.kind === "item")) {
      const e = this.item(t.layer ?? "", t.id ?? "");
      this.op({ op: "layer.place", layer: t.layer, id: t.id, x: t.x, y: t.y, facing: e?.facing ?? 0 });
    }
  }
  async mapClick(t, e, s) {
    if (!(!this.data?.canEdit && this.tool !== "measure"))
      if (this.tool === "point") {
        const i = await this.op({ op: "point.add", kind: this.pointKind, x: t, y: e });
        i?.id && (this.selected = { type: "point", id: String(i.id) });
      } else if (this.tool === "connect" && s) {
        if (!this.pending) {
          this.pending = s;
          return;
        }
        s !== this.pending && await this.op({ op: "edge.add", a: this.pending, b: s }), this.pending = null;
      } else if (this.tool === "zone" && this.zoneId)
        this.corners = [...this.corners, [t, e]];
      else if (this.tool === "place" && this.placing) {
        const i = this.item(this.placing.layer, this.placing.id);
        await this.op({
          op: "layer.place",
          layer: this.placing.layer,
          id: this.placing.id,
          x: t,
          y: e,
          facing: i?.facing ?? 0
        }), this.selected = { type: "item", ...this.placing }, this.placing = null, this.tool = "select";
      } else this.tool === "measure" && (this.measured = this.measured.length >= 2 ? [[t, e]] : [...this.measured, [t, e]]);
  }
  setTool(t) {
    this.tool = t, this.pending = null, this.corners = [], this.measured = [], t !== "place" && (this.placing = null);
  }
  // ---------------------------------------------------------------- rendering
  render() {
    const t = this.data;
    if (!t) return d`<p class="muted">${this.t("Loading…")}</p>`;
    const e = [
      ["select", "Select"],
      ["point", "Add point"],
      ["connect", "Connect"],
      ["zone", "Zone outline"],
      ["place", "Place"],
      ["measure", "Measure"],
      ...t.map ? [["align", "Align with map"]] : []
    ];
    return d`
      <div class="mapeditor">
        <div class="mapeditor-toolbar" role="toolbar" aria-label=${this.t("Tools")}>
          ${e.filter(([s]) => t.canEdit || s === "select" || s === "measure").map(([s, i]) => d`
            <button type="button" class="btn btn-sm ${this.tool === s ? "btn-primary" : ""}" aria-pressed=${this.tool === s}
              @click=${() => this.setTool(s)}>${this.t(i)}</button>`)}
          <span class="mapeditor-sep"></span>
          <button type="button" class="btn btn-sm" aria-label=${this.t("Zoom in")}
            @click=${() => {
      this.view = Y(this.view, 1.4, this.view.x + this.view.w / 2, this.view.y + this.view.h / 2);
    }}>+</button>
          <button type="button" class="btn btn-sm" aria-label=${this.t("Zoom out")}
            @click=${() => {
      this.view = Y(this.view, 1 / 1.4, this.view.x + this.view.w / 2, this.view.y + this.view.h / 2);
    }}>−</button>
          <button type="button" class="btn btn-sm" @click=${() => {
      this.view = q(t);
    }}>${this.t("Fit")}</button>
          <span class="mapeditor-status small muted" role="status" aria-live="polite">${this.status}</span>
        </div>
        <div class="mapeditor-body">
          <div class="mapeditor-stage">${this.canvas(t)}
            ${t.map ? d`<div class="mapeditor-attribution small">${t.map.attribution}</div>` : c}</div>
          <aside class="mapeditor-panel">${this.panel(t)}</aside>
        </div>
      </div>`;
  }
  canvas(t) {
    const e = this.view, s = e.w / 120, i = new Map(t.points.map((o) => [o.id, o])), a = t.plan;
    return d`<svg class="mapeditor-canvas tool-${this.tool}" viewBox="${e.x} ${e.y} ${e.w} ${e.h}"
        role="img" aria-label=${this.t("Map")} @wheel=${this.onWheel} @pointerdown=${this.onDown}
        @pointermove=${this.onMove} @pointerup=${this.onUp} @pointercancel=${this.onUp}>
      <defs><pattern id="mapeditor-grid" width="10" height="10" patternUnits="userSpaceOnUse">
        <path d="M 10 0 L 0 0 0 10" class="mapeditor-gridline"></path></pattern></defs>
      ${this.tiles(t)}
      ${a ? f`<image href=${a.url} x="0" y="0" width=${a.width * a.metresPerPx}
          height=${a.height * a.metresPerPx} preserveAspectRatio="none" opacity=${this.planOpacity}></image>` : t.map?.frame ? c : f`<rect x=${e.x - e.w} y=${e.y - e.h} width=${e.w * 3} height=${e.h * 3} fill="url(#mapeditor-grid)"></rect>`}
      ${t.zones.filter((o) => o.area).map((o) => f`<g class="mapeditor-zone">
          <polygon points=${(o.area ?? []).map(([r, l]) => `${r},${l}`).join(" ")} fill=${o.color} stroke=${o.color}
            stroke-width=${s * 0.3}></polygon>
          <text x=${(o.area ?? [[0, 0]])[0][0]} y=${(o.area ?? [[0, 0]])[0][1] - s} font-size=${s * 1.8}>${o.name}</text></g>`)}
      ${t.edges.map((o) => {
      const r = i.get(o.a), l = i.get(o.b);
      if (!r || !l) {
        const p = r ?? l;
        return p ? f`<g class="mapeditor-edge elsewhere" data-edge=${o.id}><title>${o.elsewhere ?? ""}</title>
            <circle cx=${p.x} cy=${p.y} r=${s * 1.6} stroke-width=${s * 0.25}></circle></g>` : c;
      }
      const h = this.selected?.type === "edge" && this.selected.id === o.id, u = o.oneWay ? ht({ x: (r.x + l.x) / 2, y: (r.y + l.y) / 2 }, l, s * 1.5, s) : null;
      return f`<g class="mapeditor-edge ${o.stepFree ? "" : "steps"} ${h ? "selected" : ""}" data-edge=${o.id}>
          <line x1=${r.x} y1=${r.y} x2=${l.x} y2=${l.y} class="hit" stroke-width=${s * 1.5}></line>
          <line x1=${r.x} y1=${r.y} x2=${l.x} y2=${l.y} stroke-width=${s * 0.35}></line>
          ${u ? f`<polyline points="${u.barbs[0].join(",")} ${u.x2},${u.y2} ${u.barbs[1].join(",")}"
            stroke-width=${s * 0.35}></polyline>` : c}</g>`;
    })}
      ${t.points.map((o) => {
      const r = o.next ? i.get(o.next) : void 0, l = r ? ht(o, r, s * 4, s * 1.2) : null;
      return l ? f`<g class="mapeditor-route"><line x1=${l.x1} y1=${l.y1} x2=${l.x2} y2=${l.y2}
          stroke-width=${s * 0.5}></line><polyline points="${l.barbs[0].join(",")} ${l.x2},${l.y2} ${l.barbs[1].join(",")}"
          stroke-width=${s * 0.5}></polyline></g>` : c;
    })}
      ${t.points.map((o) => {
      const r = this.selected?.type === "point" && this.selected.id === o.id || this.pending === o.id;
      return f`<g class="mapeditor-point kind-${o.kind} ${r ? "selected" : ""} ${o.noWayOut ? "no-way-out" : ""}"
            data-point=${o.id}><title>${o.name}${o.noWayOut ? ` – ${this.t("No way out")}` : ""}</title>
          <circle cx=${o.x} cy=${o.y} r=${s * 1.4} stroke-width=${s * 0.3}></circle>
          <text x=${o.x} y=${o.y + s * 0.55} font-size=${s * 1.5} text-anchor="middle">${B[o.kind] ?? "?"}</text>
          <text x=${o.x + s * 2} y=${o.y + s * 0.5} font-size=${s * 1.4} class="label">${o.name}${o.noWayOut ? " !" : ""}</text></g>`;
    })}
      ${t.layers.flatMap((o) => o.items.filter((r) => r.placed && r.x !== null && r.y !== null).map((r) => {
      const l = this.selected?.type === "item" && this.selected.id === r.id;
      return f`<g class="mapeditor-item layer-${o.key} ${l ? "selected" : ""}" data-item=${r.id} data-layer=${o.key}>
          <title>${r.label}</title>
          <polygon points=${Jt(r.x ?? 0, r.y ?? 0, r.facing ?? 0, s)} class="facing"></polygon>
          <rect x=${(r.x ?? 0) - s} y=${(r.y ?? 0) - s * 0.7} width=${s * 2} height=${s * 1.4}
            stroke-width=${s * 0.25}></rect>
          <text x=${(r.x ?? 0) + s * 2} y=${(r.y ?? 0) + s * 0.5} font-size=${s * 1.3} class="label">${r.label}</text></g>`;
    }))}
      ${this.corners.length ? f`<polyline class="mapeditor-draft" points=${this.corners.map(([o, r]) => `${o},${r}`).join(" ")}
        stroke-width=${s * 0.4}></polyline>` : c}
      ${this.measured.length ? f`<polyline class="mapeditor-measure" points=${this.measured.map(([o, r]) => `${o},${r}`).join(" ")}
        stroke-width=${s * 0.4}></polyline>${this.measured.map(([o, r]) => f`<circle class="mapeditor-measure"
        cx=${o} cy=${r} r=${s * 0.6}></circle>`)}` : c}
    </svg>`;
  }
  tiles(t) {
    const e = t.map, s = e?.frame;
    if (!e || !s) return c;
    const i = this.svgEl()?.clientWidth || 900, a = ee(this.view, s, this.view.w / i, e.maxZoom), [o, r] = this.alignOffset;
    return f`<g class="mapeditor-tiles" transform="translate(${o} ${r}) rotate(${-s.rotation})">
      ${a.map((l) => {
      const h = `${l.z}/${l.x}/${l.y}`, u = this.tileTries.get(h) ?? 0, p = e.tileUrl.replace("{z}", String(l.z)).replace("{x}", String(l.x)).replace("{y}", String(l.y)) + (u ? `?try=${u}` : "");
      return f`<image href=${p} x=${l.e0} y=${l.s0} width=${$(l.e1 - l.e0)} height=${$(l.s1 - l.s0)}
          preserveAspectRatio="none" @error=${() => this.retryTile(h)}></image>`;
    })}</g>`;
  }
  /** A tile not cached yet: the server fetches it in the background; try again a few times. */
  retryTile(t) {
    const e = this.tileTries.get(t) ?? 0;
    e >= 5 || window.setTimeout(() => {
      this.tileTries.set(t, e + 1), this.requestUpdate();
    }, 1500 * (e + 1));
  }
  // ---------------------------------------------------------------- side panel
  panel(t) {
    return d`
      ${this.hint(t)}
      ${this.toolPanel(t)}
      ${this.selectionPanel(t)}
      <details class="mapeditor-list" open><summary>${this.t("Points")} (${t.points.length})</summary>
        <ul class="plain small">${t.points.map((e) => d`<li><button type="button" class="link-button"
          @click=${() => {
      this.selected = { type: "point", id: e.id }, this.tool = "select";
    }}>
          ${B[e.kind]} ${e.name}</button>${e.noWayOut ? d` <span class="badge badge-err">${this.t("No way out")}</span>` : c}</li>`)}</ul>
      </details>
      ${t.layers.map((e) => d`<details class="mapeditor-list" open><summary>${e.title}</summary>
        <ul class="plain small">${e.items.map((s) => d`<li><button type="button" class="link-button"
          @click=${() => {
      this.selected = { type: "item", id: s.id, layer: e.key }, this.tool = "select";
    }}>${s.label}</button>
          ${s.placed ? c : d` <span class="muted">(${this.t("Not on this map")})</span>`}</li>`)}</ul></details>`)}`;
  }
  hint(t) {
    const e = {
      select: "Drag points to move them. Arrows show the way out.",
      point: "Click on the map to place it.",
      connect: "Click two points to connect them.",
      zone: "Click the corners, then Finish outline.",
      place: "Click on the map to place it.",
      measure: "Click two ends of a known distance.",
      align: "Drag the map until it matches the plan."
    };
    return d`<p class="small muted">${this.t(e[this.tool])}${t.plan && !t.plan.scaled ? d`<br><span class="badge badge-warn">${this.t("Plan not measured yet")}</span>` : c}</p>`;
  }
  toolPanel(t) {
    if (this.tool === "point")
      return d`<label class="field">${this.t("Kind")}<select .value=${this.pointKind}
        @change=${(e) => {
        this.pointKind = e.target.value;
      }}>
        ${t.kinds.map(([e, s]) => d`<option value=${e} ?selected=${e === this.pointKind}>${s}</option>`)}</select></label>`;
    if (this.tool === "zone")
      return d`<label class="field">${this.t("Zone")}<select @change=${(e) => {
        this.zoneId = e.target.value, this.corners = [];
      }}>
        <option value="">${this.t("Choose a zone")}</option>
        ${t.zones.map((e) => d`<option value=${e.id} ?selected=${e.id === this.zoneId}>${e.name}</option>`)}</select></label>
        <div class="form-actions">
          <button type="button" class="btn btn-sm btn-primary" ?disabled=${this.corners.length < 3}
            @click=${async () => {
        await this.op({ op: "zone.area", zone: this.zoneId, points: this.corners }), this.corners = [];
      }}>
            ${this.t("Finish outline")}</button>
          <button type="button" class="btn btn-sm" ?disabled=${!this.zoneId}
            @click=${async () => {
        await this.op({ op: "zone.area", zone: this.zoneId, points: [] }), this.corners = [];
      }}>
            ${this.t("Clear outline")}</button></div>`;
    if (this.tool === "place") {
      const e = t.layers.filter((s) => s.editable).flatMap((s) => s.items.map((i) => ({ l: s, i })));
      return d`<label class="field">${this.t("Choose what to place")}<select @change=${(s) => {
        const [i, a] = s.target.value.split("|");
        this.placing = a ? { layer: i, id: a } : null;
      }}>
        <option value="">–</option>
        ${e.map(({ l: s, i }) => d`<option value="${s.key}|${i.id}">${s.title}: ${i.label}${i.placed ? ` (${this.t("On this floor")})` : ""}</option>`)}
      </select></label>`;
    }
    if (this.tool === "align" && t.map)
      return this.alignPanel(t);
    if (this.tool === "measure" && this.measured.length === 2 && t.plan) {
      const e = Vt(this.measured[0], this.measured[1]);
      return d`<form class="field" @submit=${async (s) => {
        s.preventDefault();
        const i = Number(s.target.elements.namedItem("metres") instanceof HTMLInputElement ? s.target.elements.namedItem("metres").value : 0);
        t.plan && i > 0 && (await this.op({ op: "scale", px: Gt(e, t.plan), metres: i }), this.measured = [], await this.load(!0));
      }}>
        <label>${this.t("Distance in metres")} <input name="metres" type="number" min="0.01" step="0.01" required
          .value=${String(Math.round(e * 100) / 100)}></label>
        ${t.canEdit ? d`<button class="btn btn-sm btn-primary">${this.t("Set scale")}</button>` : c}</form>`;
    }
    return c;
  }
  alignPanel(t) {
    const e = t.map, s = e?.frame, i = (a) => this.querySelector(`.mapeditor-align [name=${a}]`)?.value;
    return d`<form class="mapeditor-props mapeditor-align" @submit=${async (a) => {
      a.preventDefault(), await this.op({
        op: "georef",
        lat: Number(i("lat")),
        lon: Number(i("lon")),
        rotation: Number(i("rotation") ?? 0)
      }), this.view = q(this.data ?? t);
    }}>
      ${s ? c : d`<p class="small">${this.t("Enter the position of the plan's top-left corner.")}</p>`}
      <div class="grid-xy">
        <label class="field">${this.t("Latitude")}<input name="lat" type="number" step="any" min="-85" max="85"
          required .value=${s ? s.lat.toFixed(6) : ""} ?disabled=${!t.canEdit}></label>
        <label class="field">${this.t("Longitude")}<input name="lon" type="number" step="any" min="-180" max="180"
          required .value=${s ? s.lon.toFixed(6) : ""} ?disabled=${!t.canEdit}></label></div>
      ${e?.rotatable ? d`<label class="field">${this.t("Rotation (°)")}<input name="rotation" type="number" step="0.5"
        min="0" max="359.5" .value=${String(s?.rotation ?? 0)} ?disabled=${!t.canEdit}></label>` : c}
      ${t.canEdit ? d`<button class="btn btn-sm btn-primary">${this.t("Apply")}</button>` : c}
      ${t.plan ? d`<label class="field">${this.t("Plan opacity")}<input type="range" min="0.2" max="1" step="0.05"
        .value=${String(this.planOpacity)} @input=${(a) => {
      this.planOpacity = Number(a.target.value);
    }}></label>` : c}
      ${e?.areaDownload && s && t.canEdit ? d`<button type="button" class="btn btn-sm"
        @click=${() => this.op({ op: "map.download" })}>${this.t("Download area for offline use")}</button>` : c}
    </form>`;
  }
  selectionPanel(t) {
    const e = this.selected;
    if (!e) return c;
    const s = t.canEdit;
    if (e.type === "point") {
      const r = this.pointById(e.id);
      if (!r) return c;
      const l = r.next ? this.pointById(r.next) ?? t.elsewhere[r.next] : void 0;
      return d`<section class="mapeditor-props"><h2 class="h3">${B[r.kind]} ${r.name}</h2>
        <label class="field">${this.t("Name")}<input .value=${r.name} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, name: h.target.value })}></label>
        <label class="field">${this.t("Kind")}<select ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, kind: h.target.value })}>
          ${t.kinds.map(([h, u]) => d`<option value=${h} ?selected=${h === r.kind}>${u}</option>`)}</select></label>
        <label class="field">${this.t("Zone")}<select ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, zone: h.target.value || null })}>
          <option value="">–</option>
          ${t.zones.map((h) => d`<option value=${h.id} ?selected=${h.id === r.zone}>${h.name}</option>`)}</select></label>
        <div class="grid-xy"><label class="field">x (m)<input type="number" step="0.1" .value=${String(r.x)} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, x: Number(h.target.value) })}></label>
        <label class="field">y (m)<input type="number" step="0.1" .value=${String(r.y)} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, y: Number(h.target.value) })}></label></div>
        <label class="check"><input type="checkbox" .checked=${r.stepFree} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, stepFree: h.target.checked })}>
          ${this.t("Step-free")}</label>
        <p class="small">${this.t("Next step")}: ${l ? l.name : d`<span class="badge badge-err">${this.t("No way out")}</span>`}</p>
        ${s ? d`<button type="button" class="btn btn-sm btn-ghost" @click=${async () => {
        await this.op({ op: "point.delete", id: r.id }), this.selected = null;
      }}>${this.t("Delete")}</button>` : c}
      </section>`;
    }
    if (e.type === "edge") {
      const r = t.edges.find((h) => h.id === e.id);
      if (!r) return c;
      const l = (h) => this.pointById(h)?.name ?? t.elsewhere[h]?.name ?? "?";
      return d`<section class="mapeditor-props"><h2 class="h3">${l(r.a)} ${r.oneWay ? "→" : "↔"} ${l(r.b)}</h2>
        <label class="check"><input type="checkbox" .checked=${r.oneWay} ?disabled=${!s}
          @change=${(h) => this.op({ op: "edge.update", id: r.id, oneWay: h.target.checked })}>
          ${this.t("One way")}</label>
        <label class="check"><input type="checkbox" .checked=${r.stepFree} ?disabled=${!s}
          @change=${(h) => this.op({ op: "edge.update", id: r.id, stepFree: h.target.checked })}>
          ${this.t("Step-free")}</label>
        ${s ? d`<button type="button" class="btn btn-sm btn-ghost" @click=${async () => {
        await this.op({ op: "edge.delete", id: r.id }), this.selected = null;
      }}>${this.t("Delete")}</button>` : c}
      </section>`;
    }
    const i = t.layers.find((r) => r.key === e.layer), a = i?.items.find((r) => r.id === e.id);
    if (!i || !a) return c;
    const o = i.editable;
    return d`<section class="mapeditor-props"><h2 class="h3">${i.title}: ${a.label}</h2>
      ${a.placed ? d`
        <label class="field">${this.t("Facing")} (°)<input type="range" min="0" max="359" step="1" .value=${String(a.facing ?? 0)}
          ?disabled=${!o} @change=${(r) => this.op({
      op: "layer.place",
      layer: i.key,
      id: a.id,
      x: a.x,
      y: a.y,
      facing: Number(r.target.value)
    })}></label>
        <p class="small muted">${Math.round(a.facing ?? 0)}°</p>
        ${o ? d`<button type="button" class="btn btn-sm btn-ghost"
          @click=${() => this.op({ op: "layer.place", layer: i.key, id: a.id, x: null })}>${this.t("Remove from map")}</button>` : c}` : d`<p class="small">${this.t("Not on this map")}</p>${o ? d`<button type="button" class="btn btn-sm"
          @click=${() => {
      this.tool = "place", this.placing = { layer: i.key, id: a.id };
    }}>${this.t("Place")}</button>` : c}`}
    </section>`;
  }
};
J.properties = {
  data: { state: !0 },
  view: { state: !0 },
  tool: { state: !0 },
  selected: { state: !0 },
  status: { state: !0 },
  pointKind: { state: !0 },
  pending: { state: !0 },
  corners: { state: !0 },
  zoneId: { state: !0 },
  placing: { state: !0 },
  measured: { state: !0 },
  planOpacity: { state: !0 },
  alignOffset: { state: !0 }
};
let X = J;
customElements.get("evac-map-editor") || customElements.define("evac-map-editor", X);
export {
  X as EvacMapEditor
};
