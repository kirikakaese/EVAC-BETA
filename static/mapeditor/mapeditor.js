// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC venue map editor, built from frontend/src with `npm run build` - do not edit.
// Includes Lit (BSD-3-Clause, https://lit.dev).
const z = globalThis, F = z.ShadowRoot && (z.ShadyCSS === void 0 || z.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, lt = /* @__PURE__ */ Symbol(), Z = /* @__PURE__ */ new WeakMap();
let mt = class {
  constructor(t, e, s) {
    if (this._$cssResult$ = !0, s !== lt) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (F && t === void 0) {
      const s = e !== void 0 && e.length === 1;
      s && (t = Z.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), s && Z.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const yt = (o) => new mt(typeof o == "string" ? o : o + "", void 0, lt), ft = (o, t) => {
  if (F) o.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const s = document.createElement("style"), i = z.litNonce;
    i !== void 0 && s.setAttribute("nonce", i), s.textContent = e.cssText, o.appendChild(s);
  }
}, V = F ? (o) => o : (o) => o instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const s of t.cssRules) e += s.cssText;
  return yt(e);
})(o) : o;
const { is: gt, defineProperty: bt, getOwnPropertyDescriptor: vt, getOwnPropertyNames: _t, getOwnPropertySymbols: xt, getPrototypeOf: wt } = Object, b = globalThis, J = b.trustedTypes, At = J ? J.emptyScript : "", St = b.reactiveElementPolyfillSupport, C = (o, t) => o, B = { toAttribute(o, t) {
  switch (t) {
    case Boolean:
      o = o ? At : null;
      break;
    case Object:
    case Array:
      o = o == null ? o : JSON.stringify(o);
  }
  return o;
}, fromAttribute(o, t) {
  let e = o;
  switch (t) {
    case Boolean:
      e = o !== null;
      break;
    case Number:
      e = o === null ? null : Number(o);
      break;
    case Object:
    case Array:
      try {
        e = JSON.parse(o);
      } catch {
        e = null;
      }
  }
  return e;
} }, ht = (o, t) => !gt(o, t), G = { attribute: !0, type: String, converter: B, reflect: !1, useDefault: !1, hasChanged: ht };
Symbol.metadata ?? (Symbol.metadata = /* @__PURE__ */ Symbol("metadata")), b.litPropertyMetadata ?? (b.litPropertyMetadata = /* @__PURE__ */ new WeakMap());
let A = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ?? (this.l = [])).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = G) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const s = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(t, s, e);
      i !== void 0 && bt(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, s) {
    const { get: i, set: a } = vt(this.prototype, t) ?? { get() {
      return this[e];
    }, set(n) {
      this[e] = n;
    } };
    return { get: i, set(n) {
      const r = i?.call(this);
      a?.call(this, n), this.requestUpdate(t, r, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? G;
  }
  static _$Ei() {
    if (this.hasOwnProperty(C("elementProperties"))) return;
    const t = wt(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(C("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(C("properties"))) {
      const e = this.properties, s = [..._t(e), ...xt(e)];
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
      for (const i of s) e.unshift(V(i));
    } else t !== void 0 && e.push(V(t));
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
    return ft(t, this.constructor.elementStyles), t;
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
      const a = (s.converter?.toAttribute !== void 0 ? s.converter : B).toAttribute(e, s.type);
      this._$Em = t, a == null ? this.removeAttribute(i) : this.setAttribute(i, a), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const s = this.constructor, i = s._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const a = s.getPropertyOptions(i), n = typeof a.converter == "function" ? { fromAttribute: a.converter } : a.converter?.fromAttribute !== void 0 ? a.converter : B;
      this._$Em = i;
      const r = n.fromAttribute(e, a.type);
      this[i] = r ?? this._$Ej?.get(i) ?? r, this._$Em = null;
    }
  }
  requestUpdate(t, e, s, i = !1, a) {
    if (t !== void 0) {
      const n = this.constructor;
      if (i === !1 && (a = this[t]), s ?? (s = n.getPropertyOptions(t)), !((s.hasChanged ?? ht)(a, e) || s.useDefault && s.reflect && a === this._$Ej?.get(t) && !this.hasAttribute(n._$Eu(t, s)))) return;
      this.C(t, e, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: s, reflect: i, wrapped: a }, n) {
    s && !(this._$Ej ?? (this._$Ej = /* @__PURE__ */ new Map())).has(t) && (this._$Ej.set(t, n ?? e ?? this[t]), a !== !0 || n !== void 0) || (this._$AL.has(t) || (this.hasUpdated || s || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ?? (this._$Eq = /* @__PURE__ */ new Set())).add(t));
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
        const { wrapped: n } = a, r = this[i];
        n !== !0 || this._$AL.has(i) || r === void 0 || this.C(i, void 0, a, r);
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
A.elementStyles = [], A.shadowRootOptions = { mode: "open" }, A[C("elementProperties")] = /* @__PURE__ */ new Map(), A[C("finalized")] = /* @__PURE__ */ new Map(), St?.({ ReactiveElement: A }), (b.reactiveElementVersions ?? (b.reactiveElementVersions = [])).push("2.1.2");
const P = globalThis, Q = (o) => o, R = P.trustedTypes, tt = R ? R.createPolicy("lit-html", { createHTML: (o) => o }) : void 0, ct = "$lit$", g = `lit$${Math.random().toFixed(9).slice(2)}$`, dt = "?" + g, Et = `<${dt}>`, w = document, O = () => w.createComment(""), N = (o) => o === null || typeof o != "object" && typeof o != "function", K = Array.isArray, kt = (o) => K(o) || typeof o?.[Symbol.iterator] == "function", D = `[ 	
\f\r]`, k = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, et = /-->/g, st = />/g, _ = RegExp(`>|${D}(?:([^\\s"'>=/]+)(${D}*=${D}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), it = /'/g, nt = /"/g, pt = /^(?:script|style|textarea|title)$/i, ut = (o) => (t, ...e) => ({ _$litType$: o, strings: t, values: e }), p = ut(1), m = ut(2), S = /* @__PURE__ */ Symbol.for("lit-noChange"), c = /* @__PURE__ */ Symbol.for("lit-nothing"), ot = /* @__PURE__ */ new WeakMap(), x = w.createTreeWalker(w, 129);
function $t(o, t) {
  if (!K(o) || !o.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return tt !== void 0 ? tt.createHTML(t) : t;
}
const Ct = (o, t) => {
  const e = o.length - 1, s = [];
  let i, a = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", n = k;
  for (let r = 0; r < e; r++) {
    const l = o[r];
    let h, u, d = -1, $ = 0;
    for (; $ < l.length && (n.lastIndex = $, u = n.exec(l), u !== null); ) $ = n.lastIndex, n === k ? u[1] === "!--" ? n = et : u[1] !== void 0 ? n = st : u[2] !== void 0 ? (pt.test(u[2]) && (i = RegExp("</" + u[2], "g")), n = _) : u[3] !== void 0 && (n = _) : n === _ ? u[0] === ">" ? (n = i ?? k, d = -1) : u[1] === void 0 ? d = -2 : (d = n.lastIndex - u[2].length, h = u[1], n = u[3] === void 0 ? _ : u[3] === '"' ? nt : it) : n === nt || n === it ? n = _ : n === et || n === st ? n = k : (n = _, i = void 0);
    const y = n === _ && o[r + 1].startsWith("/>") ? " " : "";
    a += n === k ? l + Et : d >= 0 ? (s.push(h), l.slice(0, d) + ct + l.slice(d) + g + y) : l + g + (d === -2 ? r : y);
  }
  return [$t(o, a + (o[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), s];
};
class T {
  constructor({ strings: t, _$litType$: e }, s) {
    let i;
    this.parts = [];
    let a = 0, n = 0;
    const r = t.length - 1, l = this.parts, [h, u] = Ct(t, e);
    if (this.el = T.createElement(h, s), x.currentNode = this.el.content, e === 2 || e === 3) {
      const d = this.el.content.firstChild;
      d.replaceWith(...d.childNodes);
    }
    for (; (i = x.nextNode()) !== null && l.length < r; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const d of i.getAttributeNames()) if (d.endsWith(ct)) {
          const $ = u[n++], y = i.getAttribute(d).split(g), v = /([.?@])?(.*)/.exec($);
          l.push({ type: 1, index: a, name: v[2], strings: y, ctor: v[1] === "." ? Mt : v[1] === "?" ? Ut : v[1] === "@" ? Ot : I }), i.removeAttribute(d);
        } else d.startsWith(g) && (l.push({ type: 6, index: a }), i.removeAttribute(d));
        if (pt.test(i.tagName)) {
          const d = i.textContent.split(g), $ = d.length - 1;
          if ($ > 0) {
            i.textContent = R ? R.emptyScript : "";
            for (let y = 0; y < $; y++) i.append(d[y], O()), x.nextNode(), l.push({ type: 2, index: ++a });
            i.append(d[$], O());
          }
        }
      } else if (i.nodeType === 8) if (i.data === dt) l.push({ type: 2, index: a });
      else {
        let d = -1;
        for (; (d = i.data.indexOf(g, d + 1)) !== -1; ) l.push({ type: 7, index: a }), d += g.length - 1;
      }
      a++;
    }
  }
  static createElement(t, e) {
    const s = w.createElement("template");
    return s.innerHTML = t, s;
  }
}
function E(o, t, e = o, s) {
  if (t === S) return t;
  let i = s !== void 0 ? e._$Co?.[s] : e._$Cl;
  const a = N(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== a && (i?._$AO?.(!1), a === void 0 ? i = void 0 : (i = new a(o), i._$AT(o, e, s)), s !== void 0 ? (e._$Co ?? (e._$Co = []))[s] = i : e._$Cl = i), i !== void 0 && (t = E(o, i._$AS(o, t.values), i, s)), t;
}
class Pt {
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
    const { el: { content: e }, parts: s } = this._$AD, i = (t?.creationScope ?? w).importNode(e, !0);
    x.currentNode = i;
    let a = x.nextNode(), n = 0, r = 0, l = s[0];
    for (; l !== void 0; ) {
      if (n === l.index) {
        let h;
        l.type === 2 ? h = new H(a, a.nextSibling, this, t) : l.type === 1 ? h = new l.ctor(a, l.name, l.strings, this, t) : l.type === 6 && (h = new Nt(a, this, t)), this._$AV.push(h), l = s[++r];
      }
      n !== l?.index && (a = x.nextNode(), n++);
    }
    return x.currentNode = w, i;
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
    t = E(this, t, e), N(t) ? t === c || t == null || t === "" ? (this._$AH !== c && this._$AR(), this._$AH = c) : t !== this._$AH && t !== S && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : kt(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== c && N(this._$AH) ? this._$AA.nextSibling.data = t : this.T(w.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: s } = t, i = typeof s == "number" ? this._$AC(t) : (s.el === void 0 && (s.el = T.createElement($t(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const a = new Pt(i, this), n = a.u(this.options);
      a.p(e), this.T(n), this._$AH = a;
    }
  }
  _$AC(t) {
    let e = ot.get(t.strings);
    return e === void 0 && ot.set(t.strings, e = new T(t)), e;
  }
  k(t) {
    K(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let s, i = 0;
    for (const a of t) i === e.length ? e.push(s = new H(this.O(O()), this.O(O()), this, this.options)) : s = e[i], s._$AI(a), i++;
    i < e.length && (this._$AR(s && s._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const s = Q(t).nextSibling;
      Q(t).remove(), t = s;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class I {
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
    let n = !1;
    if (a === void 0) t = E(this, t, e, 0), n = !N(t) || t !== this._$AH && t !== S, n && (this._$AH = t);
    else {
      const r = t;
      let l, h;
      for (t = a[0], l = 0; l < a.length - 1; l++) h = E(this, r[s + l], e, l), h === S && (h = this._$AH[l]), n || (n = !N(h) || h !== this._$AH[l]), h === c ? t = c : t !== c && (t += (h ?? "") + a[l + 1]), this._$AH[l] = h;
    }
    n && !i && this.j(t);
  }
  j(t) {
    t === c ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class Mt extends I {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === c ? void 0 : t;
  }
}
class Ut extends I {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== c);
  }
}
class Ot extends I {
  constructor(t, e, s, i, a) {
    super(t, e, s, i, a), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = E(this, t, e, 0) ?? c) === S) return;
    const s = this._$AH, i = t === c && s !== c || t.capture !== s.capture || t.once !== s.once || t.passive !== s.passive, a = t !== c && (s === c || i);
    i && this.element.removeEventListener(this.name, this, s), a && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class Nt {
  constructor(t, e, s) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    E(this, t);
  }
}
const Tt = P.litHtmlPolyfillSupport;
Tt?.(T, H), (P.litHtmlVersions ?? (P.litHtmlVersions = [])).push("3.3.3");
const Ht = (o, t, e) => {
  const s = e?.renderBefore ?? t;
  let i = s._$litPart$;
  if (i === void 0) {
    const a = e?.renderBefore ?? null;
    s._$litPart$ = i = new H(t.insertBefore(O(), a), a, void 0, e ?? {});
  }
  return i._$AI(o), i;
};
const M = globalThis;
class U extends A {
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
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = Ht(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return S;
  }
}
U._$litElement$ = !0, U.finalized = !0, M.litElementHydrateSupport?.({ LitElement: U });
const zt = M.litElementPolyfillSupport;
zt?.({ LitElement: U });
(M.litElementVersions ?? (M.litElementVersions = [])).push("4.2.2");
const j = {
  waypoint: "W",
  door: "D",
  stairs: "S",
  lift: "L",
  exit: "E",
  assembly: "A"
}, f = (o) => Math.round(o * 1e3) / 1e3;
function at(o) {
  if (o.plan) {
    const a = o.plan.width * o.plan.metresPerPx, n = o.plan.height * o.plan.metresPerPx;
    return L({ x: 0, y: 0, w: a, h: n });
  }
  const t = [], e = [];
  for (const a of o.points)
    t.push(a.x), e.push(a.y);
  for (const a of o.zones) for (const [n, r] of a.area ?? [])
    t.push(n), e.push(r);
  for (const a of o.layers) for (const n of a.items) n.placed && n.x !== null && n.y !== null && (t.push(n.x), e.push(n.y));
  if (!t.length) return L({ x: 0, y: 0, w: 100, h: 60 });
  const s = Math.min(...t), i = Math.min(...e);
  return L({ x: s, y: i, w: Math.max(Math.max(...t) - s, 20), h: Math.max(Math.max(...e) - i, 12) });
}
function L(o, t = 0.05) {
  return { x: o.x - o.w * t, y: o.y - o.h * t, w: o.w * (1 + 2 * t), h: o.h * (1 + 2 * t) };
}
function W(o, t, e, s) {
  const i = Math.min(Math.max(o.w / t, 1), 1e5), a = o.h * (i / o.w);
  return { x: e - (e - o.x) * (i / o.w), y: s - (s - o.y) * (a / o.h), w: i, h: a };
}
function Rt(o, t) {
  return Math.hypot(o[0] - t[0], o[1] - t[1]);
}
function rt(o, t, e, s) {
  const i = t.x - o.x, a = t.y - o.y, n = Math.hypot(i, a);
  if (n < 1e-6) return null;
  const r = i / n, l = a / n, h = Math.min(e, n * 0.6), u = o.x + r * h, d = o.y + l * h, $ = (y) => {
    const v = Math.cos(y), X = Math.sin(y);
    return [f(u - s * (r * v - l * X)), f(d - s * (r * X + l * v))];
  };
  return { x1: f(o.x), y1: f(o.y), x2: f(u), y2: f(d), barbs: [$(0.5), $(-0.5)] };
}
function It(o, t, e, s) {
  const i = e * Math.PI / 180, a = Math.sin(i), n = -Math.cos(i), r = [o + a * s * 3, t + n * s * 3], l = [o + n * s * 1.1, t - a * s * 1.1], h = [o - n * s * 1.1, t + a * s * 1.1];
  return [r, l, h].map(([u, d]) => `${f(u)},${f(d)}`).join(" ");
}
function Dt(o, t) {
  return o / t.metresPerPx;
}
function jt() {
  return document.cookie.split("; ").find((o) => o.startsWith("csrftoken="))?.split("=")[1] ?? "";
}
function Lt() {
  const o = document.getElementById("map-config");
  return o?.textContent ? JSON.parse(o.textContent) : null;
}
const Y = class Y extends U {
  constructor() {
    super(...arguments), this.data = null, this.view = { x: 0, y: 0, w: 100, h: 60 }, this.tool = "select", this.selected = null, this.status = "", this.pointKind = "exit", this.pending = null, this.corners = [], this.zoneId = "", this.placing = null, this.measured = [], this.cfg = Lt(), this.drag = null, this.queue = Promise.resolve();
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
    this.data = await e.json(), t && (this.view = at(this.data));
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
      headers: { "Content-Type": "application/json", "X-CSRFToken": jt() },
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
    return [f(i.x), f(i.y)];
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
    this.view = W(this.view, t.deltaY < 0 ? 1.2 : 1 / 1.2, e, s);
  }
  onDown(t) {
    const e = t.target, s = e.closest("[data-point]")?.getAttribute("data-point"), i = e.closest("[data-item]"), [a, n] = this.toMap(t), r = this.data?.canEdit ?? !1;
    if (this.tool === "select" && s && r)
      this.selected = { type: "point", id: s }, this.drag = { kind: "point", id: s, sx: t.clientX, sy: t.clientY, start: this.view, moved: !1 };
    else if (this.tool === "select" && i) {
      const l = i.getAttribute("data-item") ?? "", h = i.getAttribute("data-layer") ?? "";
      this.selected = { type: "item", id: l, layer: h }, r && (this.drag = { kind: "item", id: l, layer: h, sx: t.clientX, sy: t.clientY, start: this.view, moved: !1 });
    } else if (this.tool === "select") {
      const l = e.closest("[data-edge]")?.getAttribute("data-edge");
      this.selected = l ? { type: "edge", id: l } : null, this.drag = { kind: "pan", sx: t.clientX, sy: t.clientY, start: this.view, moved: !1 };
    } else {
      this.mapClick(a, n, s ?? null);
      return;
    }
    t.currentTarget.setPointerCapture?.(t.pointerId);
  }
  onMove(t) {
    const e = this.drag;
    if (!e || (e.moved = e.moved || Math.abs(t.clientX - e.sx) + Math.abs(t.clientY - e.sy) > 3, !e.moved)) return;
    if (e.kind === "pan") {
      const a = this.svgEl(), n = a ? e.start.w / a.clientWidth : 1;
      this.view = { ...e.start, x: e.start.x - (t.clientX - e.sx) * n, y: e.start.y - (t.clientY - e.sy) * n };
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
    if (this.drag = null, !(!t || !t.moved || t.x === void 0) && (t.kind === "point" && this.op({ op: "point.update", id: t.id, x: t.x, y: t.y }), t.kind === "item")) {
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
    if (!t) return p`<p class="muted">${this.t("Loading…")}</p>`;
    const e = [
      ["select", "Select"],
      ["point", "Add point"],
      ["connect", "Connect"],
      ["zone", "Zone outline"],
      ["place", "Place"],
      ["measure", "Measure"]
    ];
    return p`
      <div class="mapeditor">
        <div class="mapeditor-toolbar" role="toolbar" aria-label=${this.t("Tools")}>
          ${e.filter(([s]) => t.canEdit || s === "select" || s === "measure").map(([s, i]) => p`
            <button type="button" class="btn btn-sm ${this.tool === s ? "btn-primary" : ""}" aria-pressed=${this.tool === s}
              @click=${() => this.setTool(s)}>${this.t(i)}</button>`)}
          <span class="mapeditor-sep"></span>
          <button type="button" class="btn btn-sm" aria-label=${this.t("Zoom in")}
            @click=${() => {
      this.view = W(this.view, 1.4, this.view.x + this.view.w / 2, this.view.y + this.view.h / 2);
    }}>+</button>
          <button type="button" class="btn btn-sm" aria-label=${this.t("Zoom out")}
            @click=${() => {
      this.view = W(this.view, 1 / 1.4, this.view.x + this.view.w / 2, this.view.y + this.view.h / 2);
    }}>−</button>
          <button type="button" class="btn btn-sm" @click=${() => {
      this.view = at(t);
    }}>${this.t("Fit")}</button>
          <span class="mapeditor-status small muted" role="status" aria-live="polite">${this.status}</span>
        </div>
        <div class="mapeditor-body">
          ${this.canvas(t)}
          <aside class="mapeditor-panel">${this.panel(t)}</aside>
        </div>
      </div>`;
  }
  canvas(t) {
    const e = this.view, s = e.w / 120, i = new Map(t.points.map((n) => [n.id, n])), a = t.plan;
    return p`<svg class="mapeditor-canvas tool-${this.tool}" viewBox="${e.x} ${e.y} ${e.w} ${e.h}"
        role="img" aria-label=${this.t("Map")} @wheel=${this.onWheel} @pointerdown=${this.onDown}
        @pointermove=${this.onMove} @pointerup=${this.onUp} @pointercancel=${this.onUp}>
      <defs><pattern id="mapeditor-grid" width="10" height="10" patternUnits="userSpaceOnUse">
        <path d="M 10 0 L 0 0 0 10" class="mapeditor-gridline"></path></pattern></defs>
      ${a ? m`<image href=${a.url} x="0" y="0" width=${a.width * a.metresPerPx}
          height=${a.height * a.metresPerPx} preserveAspectRatio="none"></image>` : m`<rect x=${e.x - e.w} y=${e.y - e.h} width=${e.w * 3} height=${e.h * 3} fill="url(#mapeditor-grid)"></rect>`}
      ${t.zones.filter((n) => n.area).map((n) => m`<g class="mapeditor-zone">
          <polygon points=${(n.area ?? []).map(([r, l]) => `${r},${l}`).join(" ")} fill=${n.color} stroke=${n.color}
            stroke-width=${s * 0.3}></polygon>
          <text x=${(n.area ?? [[0, 0]])[0][0]} y=${(n.area ?? [[0, 0]])[0][1] - s} font-size=${s * 1.8}>${n.name}</text></g>`)}
      ${t.edges.map((n) => {
      const r = i.get(n.a), l = i.get(n.b);
      if (!r || !l) {
        const d = r ?? l;
        return d ? m`<g class="mapeditor-edge elsewhere" data-edge=${n.id}><title>${n.elsewhere ?? ""}</title>
            <circle cx=${d.x} cy=${d.y} r=${s * 1.6} stroke-width=${s * 0.25}></circle></g>` : c;
      }
      const h = this.selected?.type === "edge" && this.selected.id === n.id, u = n.oneWay ? rt({ x: (r.x + l.x) / 2, y: (r.y + l.y) / 2 }, l, s * 1.5, s) : null;
      return m`<g class="mapeditor-edge ${n.stepFree ? "" : "steps"} ${h ? "selected" : ""}" data-edge=${n.id}>
          <line x1=${r.x} y1=${r.y} x2=${l.x} y2=${l.y} class="hit" stroke-width=${s * 1.5}></line>
          <line x1=${r.x} y1=${r.y} x2=${l.x} y2=${l.y} stroke-width=${s * 0.35}></line>
          ${u ? m`<polyline points="${u.barbs[0].join(",")} ${u.x2},${u.y2} ${u.barbs[1].join(",")}"
            stroke-width=${s * 0.35}></polyline>` : c}</g>`;
    })}
      ${t.points.map((n) => {
      const r = n.next ? i.get(n.next) : void 0, l = r ? rt(n, r, s * 4, s * 1.2) : null;
      return l ? m`<g class="mapeditor-route"><line x1=${l.x1} y1=${l.y1} x2=${l.x2} y2=${l.y2}
          stroke-width=${s * 0.5}></line><polyline points="${l.barbs[0].join(",")} ${l.x2},${l.y2} ${l.barbs[1].join(",")}"
          stroke-width=${s * 0.5}></polyline></g>` : c;
    })}
      ${t.points.map((n) => {
      const r = this.selected?.type === "point" && this.selected.id === n.id || this.pending === n.id;
      return m`<g class="mapeditor-point kind-${n.kind} ${r ? "selected" : ""} ${n.noWayOut ? "no-way-out" : ""}"
            data-point=${n.id}><title>${n.name}${n.noWayOut ? ` – ${this.t("No way out")}` : ""}</title>
          <circle cx=${n.x} cy=${n.y} r=${s * 1.4} stroke-width=${s * 0.3}></circle>
          <text x=${n.x} y=${n.y + s * 0.55} font-size=${s * 1.5} text-anchor="middle">${j[n.kind] ?? "?"}</text>
          <text x=${n.x + s * 2} y=${n.y + s * 0.5} font-size=${s * 1.4} class="label">${n.name}${n.noWayOut ? " !" : ""}</text></g>`;
    })}
      ${t.layers.flatMap((n) => n.items.filter((r) => r.placed && r.x !== null && r.y !== null).map((r) => {
      const l = this.selected?.type === "item" && this.selected.id === r.id;
      return m`<g class="mapeditor-item layer-${n.key} ${l ? "selected" : ""}" data-item=${r.id} data-layer=${n.key}>
          <title>${r.label}</title>
          <polygon points=${It(r.x ?? 0, r.y ?? 0, r.facing ?? 0, s)} class="facing"></polygon>
          <rect x=${(r.x ?? 0) - s} y=${(r.y ?? 0) - s * 0.7} width=${s * 2} height=${s * 1.4}
            stroke-width=${s * 0.25}></rect>
          <text x=${(r.x ?? 0) + s * 2} y=${(r.y ?? 0) + s * 0.5} font-size=${s * 1.3} class="label">${r.label}</text></g>`;
    }))}
      ${this.corners.length ? m`<polyline class="mapeditor-draft" points=${this.corners.map(([n, r]) => `${n},${r}`).join(" ")}
        stroke-width=${s * 0.4}></polyline>` : c}
      ${this.measured.length ? m`<polyline class="mapeditor-measure" points=${this.measured.map(([n, r]) => `${n},${r}`).join(" ")}
        stroke-width=${s * 0.4}></polyline>${this.measured.map(([n, r]) => m`<circle class="mapeditor-measure"
        cx=${n} cy=${r} r=${s * 0.6}></circle>`)}` : c}
    </svg>`;
  }
  // ---------------------------------------------------------------- side panel
  panel(t) {
    return p`
      ${this.hint(t)}
      ${this.toolPanel(t)}
      ${this.selectionPanel(t)}
      <details class="mapeditor-list" open><summary>${this.t("Points")} (${t.points.length})</summary>
        <ul class="plain small">${t.points.map((e) => p`<li><button type="button" class="link-button"
          @click=${() => {
      this.selected = { type: "point", id: e.id }, this.tool = "select";
    }}>
          ${j[e.kind]} ${e.name}</button>${e.noWayOut ? p` <span class="badge badge-err">${this.t("No way out")}</span>` : c}</li>`)}</ul>
      </details>
      ${t.layers.map((e) => p`<details class="mapeditor-list" open><summary>${e.title}</summary>
        <ul class="plain small">${e.items.map((s) => p`<li><button type="button" class="link-button"
          @click=${() => {
      this.selected = { type: "item", id: s.id, layer: e.key }, this.tool = "select";
    }}>${s.label}</button>
          ${s.placed ? c : p` <span class="muted">(${this.t("Not on this map")})</span>`}</li>`)}</ul></details>`)}`;
  }
  hint(t) {
    const e = {
      select: "Drag points to move them. Arrows show the way out.",
      point: "Click on the map to place it.",
      connect: "Click two points to connect them.",
      zone: "Click the corners, then Finish outline.",
      place: "Click on the map to place it.",
      measure: "Click two ends of a known distance."
    };
    return p`<p class="small muted">${this.t(e[this.tool])}${t.plan && !t.plan.scaled ? p`<br><span class="badge badge-warn">${this.t("Plan not measured yet")}</span>` : c}</p>`;
  }
  toolPanel(t) {
    if (this.tool === "point")
      return p`<label class="field">${this.t("Kind")}<select .value=${this.pointKind}
        @change=${(e) => {
        this.pointKind = e.target.value;
      }}>
        ${t.kinds.map(([e, s]) => p`<option value=${e} ?selected=${e === this.pointKind}>${s}</option>`)}</select></label>`;
    if (this.tool === "zone")
      return p`<label class="field">${this.t("Zone")}<select @change=${(e) => {
        this.zoneId = e.target.value, this.corners = [];
      }}>
        <option value="">${this.t("Choose a zone")}</option>
        ${t.zones.map((e) => p`<option value=${e.id} ?selected=${e.id === this.zoneId}>${e.name}</option>`)}</select></label>
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
      return p`<label class="field">${this.t("Choose what to place")}<select @change=${(s) => {
        const [i, a] = s.target.value.split("|");
        this.placing = a ? { layer: i, id: a } : null;
      }}>
        <option value="">–</option>
        ${e.map(({ l: s, i }) => p`<option value="${s.key}|${i.id}">${s.title}: ${i.label}${i.placed ? ` (${this.t("On this floor")})` : ""}</option>`)}
      </select></label>`;
    }
    if (this.tool === "measure" && this.measured.length === 2 && t.plan) {
      const e = Rt(this.measured[0], this.measured[1]);
      return p`<form class="field" @submit=${async (s) => {
        s.preventDefault();
        const i = Number(s.target.elements.namedItem("metres") instanceof HTMLInputElement ? s.target.elements.namedItem("metres").value : 0);
        t.plan && i > 0 && (await this.op({ op: "scale", px: Dt(e, t.plan), metres: i }), this.measured = [], await this.load(!0));
      }}>
        <label>${this.t("Distance in metres")} <input name="metres" type="number" min="0.01" step="0.01" required
          .value=${String(Math.round(e * 100) / 100)}></label>
        ${t.canEdit ? p`<button class="btn btn-sm btn-primary">${this.t("Set scale")}</button>` : c}</form>`;
    }
    return c;
  }
  selectionPanel(t) {
    const e = this.selected;
    if (!e) return c;
    const s = t.canEdit;
    if (e.type === "point") {
      const r = this.pointById(e.id);
      if (!r) return c;
      const l = r.next ? this.pointById(r.next) ?? t.elsewhere[r.next] : void 0;
      return p`<section class="mapeditor-props"><h2 class="h3">${j[r.kind]} ${r.name}</h2>
        <label class="field">${this.t("Name")}<input .value=${r.name} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, name: h.target.value })}></label>
        <label class="field">${this.t("Kind")}<select ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, kind: h.target.value })}>
          ${t.kinds.map(([h, u]) => p`<option value=${h} ?selected=${h === r.kind}>${u}</option>`)}</select></label>
        <label class="field">${this.t("Zone")}<select ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, zone: h.target.value || null })}>
          <option value="">–</option>
          ${t.zones.map((h) => p`<option value=${h.id} ?selected=${h.id === r.zone}>${h.name}</option>`)}</select></label>
        <div class="grid-xy"><label class="field">x (m)<input type="number" step="0.1" .value=${String(r.x)} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, x: Number(h.target.value) })}></label>
        <label class="field">y (m)<input type="number" step="0.1" .value=${String(r.y)} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, y: Number(h.target.value) })}></label></div>
        <label class="check"><input type="checkbox" .checked=${r.stepFree} ?disabled=${!s}
          @change=${(h) => this.op({ op: "point.update", id: r.id, stepFree: h.target.checked })}>
          ${this.t("Step-free")}</label>
        <p class="small">${this.t("Next step")}: ${l ? l.name : p`<span class="badge badge-err">${this.t("No way out")}</span>`}</p>
        ${s ? p`<button type="button" class="btn btn-sm btn-ghost" @click=${async () => {
        await this.op({ op: "point.delete", id: r.id }), this.selected = null;
      }}>${this.t("Delete")}</button>` : c}
      </section>`;
    }
    if (e.type === "edge") {
      const r = t.edges.find((h) => h.id === e.id);
      if (!r) return c;
      const l = (h) => this.pointById(h)?.name ?? t.elsewhere[h]?.name ?? "?";
      return p`<section class="mapeditor-props"><h2 class="h3">${l(r.a)} ${r.oneWay ? "→" : "↔"} ${l(r.b)}</h2>
        <label class="check"><input type="checkbox" .checked=${r.oneWay} ?disabled=${!s}
          @change=${(h) => this.op({ op: "edge.update", id: r.id, oneWay: h.target.checked })}>
          ${this.t("One way")}</label>
        <label class="check"><input type="checkbox" .checked=${r.stepFree} ?disabled=${!s}
          @change=${(h) => this.op({ op: "edge.update", id: r.id, stepFree: h.target.checked })}>
          ${this.t("Step-free")}</label>
        ${s ? p`<button type="button" class="btn btn-sm btn-ghost" @click=${async () => {
        await this.op({ op: "edge.delete", id: r.id }), this.selected = null;
      }}>${this.t("Delete")}</button>` : c}
      </section>`;
    }
    const i = t.layers.find((r) => r.key === e.layer), a = i?.items.find((r) => r.id === e.id);
    if (!i || !a) return c;
    const n = i.editable;
    return p`<section class="mapeditor-props"><h2 class="h3">${i.title}: ${a.label}</h2>
      ${a.placed ? p`
        <label class="field">${this.t("Facing")} (°)<input type="range" min="0" max="359" step="1" .value=${String(a.facing ?? 0)}
          ?disabled=${!n} @change=${(r) => this.op({
      op: "layer.place",
      layer: i.key,
      id: a.id,
      x: a.x,
      y: a.y,
      facing: Number(r.target.value)
    })}></label>
        <p class="small muted">${Math.round(a.facing ?? 0)}°</p>
        ${n ? p`<button type="button" class="btn btn-sm btn-ghost"
          @click=${() => this.op({ op: "layer.place", layer: i.key, id: a.id, x: null })}>${this.t("Remove from map")}</button>` : c}` : p`<p class="small">${this.t("Not on this map")}</p>${n ? p`<button type="button" class="btn btn-sm"
          @click=${() => {
      this.tool = "place", this.placing = { layer: i.key, id: a.id };
    }}>${this.t("Place")}</button>` : c}`}
    </section>`;
  }
};
Y.properties = {
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
  measured: { state: !0 }
};
let q = Y;
customElements.get("evac-map-editor") || customElements.define("evac-map-editor", q);
export {
  q as EvacMapEditor
};
