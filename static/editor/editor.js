// SPDX-License-Identifier: AGPL-3.0-or-later
// EVAC layout editor, built from frontend/src with `npm run build` - do not edit.
// Includes Lit (BSD-3-Clause, https://lit.dev) and uqr (MIT).
// Includes ISO 7010 safety signs from @iso-safety-signs/core (Copyright (c) Karl Norling, MIT,
// https://github.com/karlnorling/iso-safety-signs).
var ve = Object.defineProperty;
var $e = (n, t, e) => t in n ? ve(n, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : n[t] = e;
var O = (n, t, e) => $e(n, typeof t != "symbol" ? t + "" : t, e);
const X = globalThis, ft = X.ShadowRoot && (X.ShadyCSS === void 0 || X.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, Yt = /* @__PURE__ */ Symbol(), At = /* @__PURE__ */ new WeakMap();
let ye = class {
  constructor(t, e, s) {
    if (this._$cssResult$ = !0, s !== Yt) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (ft && t === void 0) {
      const s = e !== void 0 && e.length === 1;
      s && (t = At.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), s && At.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const we = (n) => new ye(typeof n == "string" ? n : n + "", void 0, Yt), be = (n, t) => {
  if (ft) n.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const s = document.createElement("style"), i = X.litNonce;
    i !== void 0 && s.setAttribute("nonce", i), s.textContent = e.cssText, n.appendChild(s);
  }
}, Et = ft ? (n) => n : (n) => n instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const s of t.cssRules) e += s.cssText;
  return we(e);
})(n) : n;
const { is: Se, defineProperty: xe, getOwnPropertyDescriptor: Ae, getOwnPropertyNames: Ee, getOwnPropertySymbols: Ce, getPrototypeOf: _e } = Object, E = globalThis, Ct = E.trustedTypes, Me = Ct ? Ct.emptyScript : "", ke = E.reactiveElementPolyfillSupport, B = (n, t) => n, lt = { toAttribute(n, t) {
  switch (t) {
    case Boolean:
      n = n ? Me : null;
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
} }, Zt = (n, t) => !Se(n, t), _t = { attribute: !0, type: String, converter: lt, reflect: !1, useDefault: !1, hasChanged: Zt };
Symbol.metadata ?? (Symbol.metadata = /* @__PURE__ */ Symbol("metadata")), E.litPropertyMetadata ?? (E.litPropertyMetadata = /* @__PURE__ */ new WeakMap());
let z = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ?? (this.l = [])).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = _t) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const s = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(t, s, e);
      i !== void 0 && xe(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, s) {
    const { get: i, set: o } = Ae(this.prototype, t) ?? { get() {
      return this[e];
    }, set(r) {
      this[e] = r;
    } };
    return { get: i, set(r) {
      const a = i?.call(this);
      o?.call(this, r), this.requestUpdate(t, a, s);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? _t;
  }
  static _$Ei() {
    if (this.hasOwnProperty(B("elementProperties"))) return;
    const t = _e(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(B("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(B("properties"))) {
      const e = this.properties, s = [...Ee(e), ...Ce(e)];
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
      for (const i of s) e.unshift(Et(i));
    } else t !== void 0 && e.push(Et(t));
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
    return be(t, this.constructor.elementStyles), t;
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
      const o = (s.converter?.toAttribute !== void 0 ? s.converter : lt).toAttribute(e, s.type);
      this._$Em = t, o == null ? this.removeAttribute(i) : this.setAttribute(i, o), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const s = this.constructor, i = s._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const o = s.getPropertyOptions(i), r = typeof o.converter == "function" ? { fromAttribute: o.converter } : o.converter?.fromAttribute !== void 0 ? o.converter : lt;
      this._$Em = i;
      const a = r.fromAttribute(e, o.type);
      this[i] = a ?? this._$Ej?.get(i) ?? a, this._$Em = null;
    }
  }
  requestUpdate(t, e, s, i = !1, o) {
    if (t !== void 0) {
      const r = this.constructor;
      if (i === !1 && (o = this[t]), s ?? (s = r.getPropertyOptions(t)), !((s.hasChanged ?? Zt)(o, e) || s.useDefault && s.reflect && o === this._$Ej?.get(t) && !this.hasAttribute(r._$Eu(t, s)))) return;
      this.C(t, e, s);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: s, reflect: i, wrapped: o }, r) {
    s && !(this._$Ej ?? (this._$Ej = /* @__PURE__ */ new Map())).has(t) && (this._$Ej.set(t, r ?? e ?? this[t]), o !== !0 || r !== void 0) || (this._$AL.has(t) || (this.hasUpdated || s || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ?? (this._$Eq = /* @__PURE__ */ new Set())).add(t));
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
        for (const [i, o] of this._$Ep) this[i] = o;
        this._$Ep = void 0;
      }
      const s = this.constructor.elementProperties;
      if (s.size > 0) for (const [i, o] of s) {
        const { wrapped: r } = o, a = this[i];
        r !== !0 || this._$AL.has(i) || a === void 0 || this.C(i, void 0, o, a);
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
z.elementStyles = [], z.shadowRootOptions = { mode: "open" }, z[B("elementProperties")] = /* @__PURE__ */ new Map(), z[B("finalized")] = /* @__PURE__ */ new Map(), ke?.({ ReactiveElement: z }), (E.reactiveElementVersions ?? (E.reactiveElementVersions = [])).push("2.1.2");
const F = globalThis, Mt = (n) => n, st = F.trustedTypes, kt = st ? st.createPolicy("lit-html", { createHTML: (n) => n }) : void 0, Jt = "$lit$", A = `lit$${Math.random().toFixed(9).slice(2)}$`, Xt = "?" + A, Pe = `<${Xt}>`, P = document, W = () => P.createComment(""), j = (n) => n === null || typeof n != "object" && typeof n != "function", mt = Array.isArray, Ne = (n) => mt(n) || typeof n?.[Symbol.iterator] == "function", nt = `[ 	
\f\r]`, L = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, Pt = /-->/g, Nt = />/g, C = RegExp(`>|${nt}(?:([^\\s"'>=/]+)(${nt}*=${nt}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), zt = /'/g, Tt = /"/g, Qt = /^(?:script|style|textarea|title)$/i, ze = (n) => (t, ...e) => ({ _$litType$: n, strings: t, values: e }), p = ze(1), T = /* @__PURE__ */ Symbol.for("lit-noChange"), g = /* @__PURE__ */ Symbol.for("lit-nothing"), Dt = /* @__PURE__ */ new WeakMap(), M = P.createTreeWalker(P, 129);
function te(n, t) {
  if (!mt(n) || !n.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return kt !== void 0 ? kt.createHTML(t) : t;
}
const Te = (n, t) => {
  const e = n.length - 1, s = [];
  let i, o = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", r = L;
  for (let a = 0; a < e; a++) {
    const c = n[a];
    let l, h, d = -1, u = 0;
    for (; u < c.length && (r.lastIndex = u, h = r.exec(c), h !== null); ) u = r.lastIndex, r === L ? h[1] === "!--" ? r = Pt : h[1] !== void 0 ? r = Nt : h[2] !== void 0 ? (Qt.test(h[2]) && (i = RegExp("</" + h[2], "g")), r = C) : h[3] !== void 0 && (r = C) : r === C ? h[0] === ">" ? (r = i ?? L, d = -1) : h[1] === void 0 ? d = -2 : (d = r.lastIndex - h[2].length, l = h[1], r = h[3] === void 0 ? C : h[3] === '"' ? Tt : zt) : r === Tt || r === zt ? r = C : r === Pt || r === Nt ? r = L : (r = C, i = void 0);
    const m = r === C && n[a + 1].startsWith("/>") ? " " : "";
    o += r === L ? c + Pe : d >= 0 ? (s.push(l), c.slice(0, d) + Jt + c.slice(d) + A + m) : c + A + (d === -2 ? a : m);
  }
  return [te(n, o + (n[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), s];
};
class q {
  constructor({ strings: t, _$litType$: e }, s) {
    let i;
    this.parts = [];
    let o = 0, r = 0;
    const a = t.length - 1, c = this.parts, [l, h] = Te(t, e);
    if (this.el = q.createElement(l, s), M.currentNode = this.el.content, e === 2 || e === 3) {
      const d = this.el.content.firstChild;
      d.replaceWith(...d.childNodes);
    }
    for (; (i = M.nextNode()) !== null && c.length < a; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const d of i.getAttributeNames()) if (d.endsWith(Jt)) {
          const u = h[r++], m = i.getAttribute(d).split(A), v = /([.?@])?(.*)/.exec(u);
          c.push({ type: 1, index: o, name: v[2], strings: m, ctor: v[1] === "." ? He : v[1] === "?" ? Oe : v[1] === "@" ? Le : it }), i.removeAttribute(d);
        } else d.startsWith(A) && (c.push({ type: 6, index: o }), i.removeAttribute(d));
        if (Qt.test(i.tagName)) {
          const d = i.textContent.split(A), u = d.length - 1;
          if (u > 0) {
            i.textContent = st ? st.emptyScript : "";
            for (let m = 0; m < u; m++) i.append(d[m], W()), M.nextNode(), c.push({ type: 2, index: ++o });
            i.append(d[u], W());
          }
        }
      } else if (i.nodeType === 8) if (i.data === Xt) c.push({ type: 2, index: o });
      else {
        let d = -1;
        for (; (d = i.data.indexOf(A, d + 1)) !== -1; ) c.push({ type: 7, index: o }), d += A.length - 1;
      }
      o++;
    }
  }
  static createElement(t, e) {
    const s = P.createElement("template");
    return s.innerHTML = t, s;
  }
}
function D(n, t, e = n, s) {
  if (t === T) return t;
  let i = s !== void 0 ? e._$Co?.[s] : e._$Cl;
  const o = j(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== o && (i?._$AO?.(!1), o === void 0 ? i = void 0 : (i = new o(n), i._$AT(n, e, s)), s !== void 0 ? (e._$Co ?? (e._$Co = []))[s] = i : e._$Cl = i), i !== void 0 && (t = D(n, i._$AS(n, t.values), i, s)), t;
}
class De {
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
    const { el: { content: e }, parts: s } = this._$AD, i = (t?.creationScope ?? P).importNode(e, !0);
    M.currentNode = i;
    let o = M.nextNode(), r = 0, a = 0, c = s[0];
    for (; c !== void 0; ) {
      if (r === c.index) {
        let l;
        c.type === 2 ? l = new V(o, o.nextSibling, this, t) : c.type === 1 ? l = new c.ctor(o, c.name, c.strings, this, t) : c.type === 6 && (l = new Re(o, this, t)), this._$AV.push(l), c = s[++a];
      }
      r !== c?.index && (o = M.nextNode(), r++);
    }
    return M.currentNode = P, i;
  }
  p(t) {
    let e = 0;
    for (const s of this._$AV) s !== void 0 && (s.strings !== void 0 ? (s._$AI(t, s, e), e += s.strings.length - 2) : s._$AI(t[e])), e++;
  }
}
class V {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, s, i) {
    this.type = 2, this._$AH = g, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = s, this.options = i, this._$Cv = i?.isConnected ?? !0;
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
    t = D(this, t, e), j(t) ? t === g || t == null || t === "" ? (this._$AH !== g && this._$AR(), this._$AH = g) : t !== this._$AH && t !== T && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : Ne(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== g && j(this._$AH) ? this._$AA.nextSibling.data = t : this.T(P.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: s } = t, i = typeof s == "number" ? this._$AC(t) : (s.el === void 0 && (s.el = q.createElement(te(s.h, s.h[0]), this.options)), s);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const o = new De(i, this), r = o.u(this.options);
      o.p(e), this.T(r), this._$AH = o;
    }
  }
  _$AC(t) {
    let e = Dt.get(t.strings);
    return e === void 0 && Dt.set(t.strings, e = new q(t)), e;
  }
  k(t) {
    mt(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let s, i = 0;
    for (const o of t) i === e.length ? e.push(s = new V(this.O(W()), this.O(W()), this, this.options)) : s = e[i], s._$AI(o), i++;
    i < e.length && (this._$AR(s && s._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const s = Mt(t).nextSibling;
      Mt(t).remove(), t = s;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class it {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, s, i, o) {
    this.type = 1, this._$AH = g, this._$AN = void 0, this.element = t, this.name = e, this._$AM = i, this.options = o, s.length > 2 || s[0] !== "" || s[1] !== "" ? (this._$AH = Array(s.length - 1).fill(new String()), this.strings = s) : this._$AH = g;
  }
  _$AI(t, e = this, s, i) {
    const o = this.strings;
    let r = !1;
    if (o === void 0) t = D(this, t, e, 0), r = !j(t) || t !== this._$AH && t !== T, r && (this._$AH = t);
    else {
      const a = t;
      let c, l;
      for (t = o[0], c = 0; c < o.length - 1; c++) l = D(this, a[s + c], e, c), l === T && (l = this._$AH[c]), r || (r = !j(l) || l !== this._$AH[c]), l === g ? t = g : t !== g && (t += (l ?? "") + o[c + 1]), this._$AH[c] = l;
    }
    r && !i && this.j(t);
  }
  j(t) {
    t === g ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class He extends it {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === g ? void 0 : t;
  }
}
class Oe extends it {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== g);
  }
}
class Le extends it {
  constructor(t, e, s, i, o) {
    super(t, e, s, i, o), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = D(this, t, e, 0) ?? g) === T) return;
    const s = this._$AH, i = t === g && s !== g || t.capture !== s.capture || t.once !== s.once || t.passive !== s.passive, o = t !== g && (s === g || i);
    i && this.element.removeEventListener(this.name, this, s), o && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class Re {
  constructor(t, e, s) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = s;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    D(this, t);
  }
}
const Be = F.litHtmlPolyfillSupport;
Be?.(q, V), (F.litHtmlVersions ?? (F.litHtmlVersions = [])).push("3.3.3");
const Fe = (n, t, e) => {
  const s = e?.renderBefore ?? t;
  let i = s._$litPart$;
  if (i === void 0) {
    const o = e?.renderBefore ?? null;
    s._$litPart$ = i = new V(t.insertBefore(W(), o), o, void 0, e ?? {});
  }
  return i._$AI(n), i;
};
const I = globalThis;
let U = class extends z {
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
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = Fe(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return T;
  }
};
U._$litElement$ = !0, U.finalized = !0, I.litElementHydrateSupport?.({ LitElement: U });
const Ie = I.litElementPolyfillSupport;
Ie?.({ LitElement: U });
(I.litElementVersions ?? (I.litElementVersions = [])).push("4.2.2");
const Ue = { ELEMENT: 6 }, We = (n) => (...t) => ({ _$litDirective$: n, values: t });
class je {
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
const qe = `(() => {
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
function Ht(n) {
  return n.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}
function Ve(n, t, e, s = "") {
  const i = Ht(t), o = e ? ` ${e}` : "", r = [
    "default-src 'none'",
    `script-src 'nonce-${t}'`,
    `style-src 'nonce-${t}'`,
    `img-src data: blob:${o}`,
    `media-src data: blob:${o}`,
    `font-src data:${o}`,
    "connect-src 'none'",
    "form-action 'none'",
    "base-uri 'none'",
    "frame-src 'none'",
    "worker-src 'none'"
  ].join("; "), a = String(n.css ?? "").replace(/<\/style/gi, "<\\/style"), c = String(n.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${Ht(r)}"><style nonce="${i}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${s}</style><style nonce="${i}">${a}</style><script nonce="${i}">${qe}<\/script></head><body>${String(n.html ?? "")}` + (c.trim() ? `<script nonce="${i}">${c}<\/script>` : "") + "</body></html>";
}
function Ge(n) {
  const t = [];
  try {
    const e = getComputedStyle(n);
    for (let s = 0; s < e.length; s++) {
      const i = e[s];
      if (i.startsWith("--evac-")) {
        const o = e.getPropertyValue(i).trim().replace(/[<>{};]/g, "");
        o && t.push(`${i}:${o}`);
      }
    }
  } catch {
  }
  return t.length ? `:root{${t.join(";")}}` : "";
}
function Ke(n = document) {
  const t = n.querySelector("script[nonce]");
  return t?.nonce || t?.getAttribute("nonce") || "";
}
function Q(n) {
  return n ? n.startsWith("token:") ? `var(--evac-color-${n.slice(6)})` : /^#[0-9a-fA-F]{6}$/.test(n) || n === "transparent" ? n : "" : "";
}
function Ye(n, t) {
  return n ? n === "token:heading" ? "var(--evac-font-heading)" : n === "token:body" ? "var(--evac-font-body)" : t.fonts[n] ?? "" : "";
}
function Ze(n, t, e) {
  const s = n.style;
  if (!t) return;
  const i = (o, r) => {
    r && s.setProperty(o, r);
  };
  i("color", Q(t.color)), i("background", Q(t.background)), t.borderWidth && s.setProperty("border", `${t.borderWidth / 10}cqh solid ${Q(t.borderColor) || "currentColor"}`), t.radius !== void 0 && s.setProperty("border-radius", `${t.radius}cqh`), t.padding !== void 0 && s.setProperty("padding", `${t.padding}cqh`), t.opacity !== void 0 && s.setProperty("opacity", String(t.opacity)), i("font-family", Ye(t.fontFamily, e)), t.fontSize && s.setProperty("font-size", `${t.fontSize}cqh`), t.fontWeight && s.setProperty("font-weight", String(t.fontWeight)), i("font-style", t.fontStyle ?? ""), i("text-align", t.textAlign ?? ""), t.verticalAlign && s.setProperty("justify-content", { top: "flex-start", middle: "center", bottom: "flex-end" }[t.verticalAlign]), t.lineHeight && s.setProperty("line-height", String(t.lineHeight)), t.letterSpacing !== void 0 && s.setProperty("letter-spacing", `${t.letterSpacing}em`), i("text-transform", t.textTransform ?? ""), t.tabularNumbers && s.setProperty("font-variant-numeric", "tabular-nums"), t.shadow && s.setProperty("box-shadow", "var(--evac-shadow)");
}
function Je(n, t, e) {
  const s = t.trim();
  if (s === "now") return new Date(e.now ? e.now() : Date.now());
  if (/^".*"$|^'.*'$/.test(s)) return s.slice(1, -1);
  if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
  let i = n;
  for (const o of s.split(".")) {
    if (i == null || typeof i != "object") return;
    i = i[o];
  }
  return i;
}
function Xe(n) {
  const t = [];
  let e = "", s = "";
  for (const i of n)
    s ? (i === s && (s = ""), e += i) : i === '"' || i === "'" ? (s = i, e += i) : i === "|" ? (t.push(e), e = "") : e += i;
  return t.push(e), t.map((i) => i.trim());
}
function Qe(n) {
  if (!n) return "";
  const t = n.trim();
  return /^".*"$|^'.*'$/.test(t) ? t.slice(1, -1) : t;
}
function Ot(n, t, e) {
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
function w(n) {
  return n == null ? "" : Array.isArray(n) ? n.map(w).join(", ") : n instanceof Date ? n.toISOString() : typeof n == "object" ? n.name ?? "" : String(n);
}
function ts(n, t, e) {
  const [s, ...i] = t.split(":"), o = Qe(i.join(":")), r = () => n instanceof Date ? n : new Date(String(n));
  switch (s.trim()) {
    case "upper":
      return w(n).toUpperCase();
    case "lower":
      return w(n).toLowerCase();
    case "title":
      return w(n).replace(/\b\p{L}/gu, (a) => a.toUpperCase());
    case "truncate": {
      const a = Number(o) || 30, c = w(n);
      return c.length > a ? `${c.slice(0, Math.max(0, a - 1))}…` : c;
    }
    case "default":
      return w(n) === "" ? o : n;
    case "date":
      return isNaN(r().getTime()) ? "" : Ot(r(), o || "long", e.timezone);
    case "time":
      return isNaN(r().getTime()) ? "" : Ot(r(), o || "HH:mm", e.timezone);
    case "join":
      return Array.isArray(n) ? n.map(w).join(o || ", ") : w(n);
    default:
      return n;
  }
}
function tt(n, t, e = {}) {
  const [s, ...i] = Xe(n);
  let o = Je(t, s, e);
  for (const r of i) o = ts(o, r, e);
  return o;
}
function es(n) {
  return Array.isArray(n) ? n.length > 0 : !(n == null || n === !1 || n === "" || n === 0);
}
function gt(n, t, e = {}) {
  const s = n.trim();
  if (!s) return !0;
  if (s.startsWith("not ")) return !gt(s.slice(4), t, e);
  const i = /^(.+?)\s*(==|!=)\s*(.+)$/.exec(s);
  if (i) {
    const o = w(tt(i[1], t, e)), r = w(tt(i[3], t, e));
    return i[2] === "==" ? o === r : o !== r;
  }
  return es(tt(s.replace(/^\{\{|\}\}$/g, ""), t, e));
}
const ss = /(\{%\s*(?:if\s+[^%]+|else|endif)\s*%\}|\{\{[^}]*\}\})/g;
function ee(n, t, e = {}) {
  if (!n || !n.includes("{{") && !n.includes("{%")) return n ?? "";
  const s = n.split(ss);
  let i = 0;
  const o = (r) => {
    let a = "";
    for (; i < s.length; ) {
      const c = s[i++], l = /^\{%\s*(if\s+([^%]+)|else|endif)\s*%\}$/.exec(c);
      if (l) {
        const h = l[1].startsWith("if") ? "if" : l[1];
        if (r.includes(h)) return [a, h];
        if (h === "if") {
          const d = gt(l[2], t, e), [u, m] = o(["else", "endif"]);
          let v = "";
          m === "else" && (v = o(["endif"])[0]), a += d ? u : v;
        }
      } else c.startsWith("{{") && c.endsWith("}}") ? a += w(tt(c.slice(2, -2), t, e)) : a += c;
    }
    return [a, ""];
  };
  return o([])[0];
}
const se = {
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
}, is = "#237f52", ns = ["ahead", "ahead_right", "right", "back_right", "back", "back_left", "left", "ahead_left"], rs = {
  E001: "Emergency exit (left)",
  E002: "Emergency exit (right)",
  E003: "First aid",
  E007: "Assembly point",
  W001: "General warning",
  arrow: "Direction"
};
function os(n) {
  const t = ns.indexOf(n);
  return t < 0 ? 0 : t * 45;
}
function as(n, t, e, s) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="${t}"
 color="${s}" fill="currentColor"><rect width="100" height="100" rx="4" fill="${e}"/>${n}</svg>`;
}
function cs(n, t) {
  return se[n].svg.replace(/^<svg\b/, `<svg role="img" aria-label="${t}"`);
}
function ls(n, t = "ahead") {
  const e = rs[n] ?? "Safety sign";
  if (n in se) return cs(n, e);
  const s = os(t);
  return as(
    `<g transform="rotate(${s} 50 50)"><path d="M50 12 L80 46 H60 V88 H40 V46 H20 Z"/></g>`,
    `${e}: ${String(t).replace("_", " ")}`,
    is,
    "#fff"
  );
}
var _ = /* @__PURE__ */ ((n) => (n[n.Border = -1] = "Border", n[n.Data = 0] = "Data", n[n.Function = 1] = "Function", n[n.Position = 2] = "Position", n[n.Timing = 3] = "Timing", n[n.Alignment = 4] = "Alignment", n))(_ || {});
const hs = [0, 1], ie = [1, 0], ne = [2, 3], re = [3, 2], ds = {
  L: hs,
  M: ie,
  Q: ne,
  H: re
}, us = /^\d*$/, ps = /^[A-Z0-9 $%*+./:-]*$/, rt = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:", vt = 1, $t = 40, Lt = 3, fs = 3, K = 40, ms = 10, oe = [
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
], ae = [
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
class gs {
  /* -- Constructor (low level) and fields -- */
  // Creates a new QR Code with the given version number,
  // error correction level, data codeword bytes, and mask number.
  // This is a low-level API that most users should not use directly.
  // A mid-level API is the encodeSegments() function.
  constructor(t, e, s, i) {
    /* -- Fields -- */
    // The width and height of this QR Code, measured in modules, between
    // 21 and 177 (inclusive). This is equal to version * 4 + 17.
    O(this, "size");
    // The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    // Even if a QR Code is created with automatic masking requested (mask = -1),
    // the resulting object still has a mask value between 0 and 7.
    O(this, "mask");
    // The modules of this QR Code (false = light, true = dark).
    // Immutable after constructor finishes. Accessed through getModule().
    O(this, "modules", []);
    O(this, "types", []);
    if (this.version = t, this.ecc = e, t < vt || t > $t)
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
    for (let o = 0; o < 10; o++)
      s = s << 1 ^ (s >>> 9) * 1335;
    const i = (e << 10 | s) ^ 21522;
    for (let o = 0; o <= 5; o++)
      this.setFunctionModule(8, o, b(i, o));
    this.setFunctionModule(8, 7, b(i, 6)), this.setFunctionModule(8, 8, b(i, 7)), this.setFunctionModule(7, 8, b(i, 8));
    for (let o = 9; o < 15; o++)
      this.setFunctionModule(14 - o, 8, b(i, o));
    for (let o = 0; o < 8; o++)
      this.setFunctionModule(this.size - 1 - o, 8, b(i, o));
    for (let o = 8; o < 15; o++)
      this.setFunctionModule(8, this.size - 15 + o, b(i, o));
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
      const i = b(e, s), o = this.size - 11 + s % 3, r = Math.floor(s / 3);
      this.setFunctionModule(o, r, i), this.setFunctionModule(r, o, i);
    }
  }
  // Draws a 9*9 finder pattern including the border separator,
  // with the center module at (x, y). Modules can be out of bounds.
  drawFinderPattern(t, e) {
    for (let s = -4; s <= 4; s++)
      for (let i = -4; i <= 4; i++) {
        const o = Math.max(Math.abs(i), Math.abs(s)), r = t + i, a = e + s;
        r >= 0 && r < this.size && a >= 0 && a < this.size && this.setFunctionModule(r, a, o !== 2 && o !== 4, _.Position);
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
    if (t.length !== et(e, s))
      throw new RangeError("Invalid argument");
    const i = ae[s[0]][e], o = oe[s[0]][e], r = Math.floor(ht(e) / 8), a = i - r % i, c = Math.floor(r / i), l = [], h = Es(o);
    for (let u = 0, m = 0; u < i; u++) {
      const v = t.slice(m, m + c - o + (u < a ? 0 : 1));
      m += v.length;
      const G = Cs(v, h);
      u < a && v.push(0), l.push(v.concat(G));
    }
    const d = [];
    for (let u = 0; u < l[0].length; u++)
      l.forEach((m, v) => {
        (u !== c - o || v >= a) && d.push(m[u]);
      });
    return d;
  }
  // Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
  // data area of this QR Code. Function modules need to be marked off before this is called.
  drawCodewords(t) {
    if (t.length !== Math.floor(ht(this.version) / 8))
      throw new RangeError("Invalid argument");
    let e = 0;
    for (let s = this.size - 1; s >= 1; s -= 2) {
      s === 6 && (s = 5);
      for (let i = 0; i < this.size; i++)
        for (let o = 0; o < 2; o++) {
          const r = s - o, c = (s + 1 & 2) === 0 ? this.size - 1 - i : i;
          !this.types[c][r] && e < t.length * 8 && (this.modules[c][r] = b(t[e >>> 3], 7 - (e & 7)), e++);
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
        this.modules[o][l] === r ? (a++, a === 5 ? t += Lt : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), r || (t += this.finderPenaltyCountPatterns(c) * K), r = this.modules[o][l], a = 1);
      t += this.finderPenaltyTerminateAndCount(r, a, c) * K;
    }
    for (let o = 0; o < this.size; o++) {
      let r = !1, a = 0;
      const c = [0, 0, 0, 0, 0, 0, 0];
      for (let l = 0; l < this.size; l++)
        this.modules[l][o] === r ? (a++, a === 5 ? t += Lt : a > 5 && t++) : (this.finderPenaltyAddHistory(a, c), r || (t += this.finderPenaltyCountPatterns(c) * K), r = this.modules[l][o], a = 1);
      t += this.finderPenaltyTerminateAndCount(r, a, c) * K;
    }
    for (let o = 0; o < this.size - 1; o++)
      for (let r = 0; r < this.size - 1; r++) {
        const a = this.modules[o][r];
        a === this.modules[o][r + 1] && a === this.modules[o + 1][r] && a === this.modules[o + 1][r + 1] && (t += fs);
      }
    let e = 0;
    for (const o of this.modules)
      e = o.reduce((r, a) => r + (a ? 1 : 0), e);
    const s = this.size * this.size, i = Math.ceil(Math.abs(e * 20 - s * 10) / s) - 1;
    return t += i * ms, t;
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
function S(n, t, e) {
  if (t < 0 || t > 31 || n >>> t)
    throw new RangeError("Value out of range");
  for (let s = t - 1; s >= 0; s--)
    e.push(n >>> s & 1);
}
function b(n, t) {
  return (n >>> t & 1) !== 0;
}
class yt {
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
const vs = [1, 10, 12, 14], $s = [2, 9, 11, 13], ys = [4, 8, 16, 16];
function ce(n, t) {
  return n[Math.floor((t + 7) / 17) + 1];
}
function le(n) {
  const t = [];
  for (const e of n)
    S(e, 8, t);
  return new yt(ys, n.length, t);
}
function ws(n) {
  if (!he(n))
    throw new RangeError("String contains non-numeric characters");
  const t = [];
  for (let e = 0; e < n.length; ) {
    const s = Math.min(n.length - e, 3);
    S(Number.parseInt(n.substring(e, e + s), 10), s * 3 + 1, t), e += s;
  }
  return new yt(vs, n.length, t);
}
function bs(n) {
  if (!de(n))
    throw new RangeError("String contains unencodable characters in alphanumeric mode");
  const t = [];
  let e;
  for (e = 0; e + 2 <= n.length; e += 2) {
    let s = rt.indexOf(n.charAt(e)) * 45;
    s += rt.indexOf(n.charAt(e + 1)), S(s, 11, t);
  }
  return e < n.length && S(rt.indexOf(n.charAt(e)), 6, t), new yt($s, n.length, t);
}
function Ss(n) {
  return n === "" ? [] : he(n) ? [ws(n)] : de(n) ? [bs(n)] : [le(As(n))];
}
function he(n) {
  return us.test(n);
}
function de(n) {
  return ps.test(n);
}
function xs(n, t) {
  let e = 0;
  for (const s of n) {
    const i = ce(s.mode, t);
    if (s.numChars >= 1 << i)
      return Number.POSITIVE_INFINITY;
    e += 4 + i + s.bitData.length;
  }
  return e;
}
function As(n) {
  n = encodeURI(n);
  const t = [];
  for (let e = 0; e < n.length; e++)
    n.charAt(e) !== "%" ? t.push(n.charCodeAt(e)) : (t.push(Number.parseInt(n.substring(e + 1, e + 3), 16)), e += 2);
  return t;
}
function ht(n) {
  if (n < vt || n > $t)
    throw new RangeError("Version number out of range");
  let t = (16 * n + 128) * n + 64;
  if (n >= 2) {
    const e = Math.floor(n / 7) + 2;
    t -= (25 * e - 10) * e - 55, n >= 7 && (t -= 36);
  }
  return t;
}
function et(n, t) {
  return Math.floor(ht(n) / 8) - oe[t[0]][n] * ae[t[0]][n];
}
function Es(n) {
  if (n < 1 || n > 255)
    throw new RangeError("Degree out of range");
  const t = [];
  for (let s = 0; s < n - 1; s++)
    t.push(0);
  t.push(1);
  let e = 1;
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < t.length; i++)
      t[i] = dt(t[i], e), i + 1 < t.length && (t[i] ^= t[i + 1]);
    e = dt(e, 2);
  }
  return t;
}
function Cs(n, t) {
  const e = t.map((s) => 0);
  for (const s of n) {
    const i = s ^ e.shift();
    e.push(0), t.forEach((o, r) => e[r] ^= dt(o, i));
  }
  return e;
}
function dt(n, t) {
  if (n >>> 8 || t >>> 8)
    throw new RangeError("Byte out of range");
  let e = 0;
  for (let s = 7; s >= 0; s--)
    e = e << 1 ^ (e >>> 7) * 285, e ^= (t >>> s & 1) * n;
  return e;
}
function _s(n, t, e = 1, s = 40, i = -1, o = !0) {
  if (!(vt <= e && e <= s && s <= $t) || i < -1 || i > 7)
    throw new RangeError("Invalid value");
  let r, a;
  for (r = e; ; r++) {
    const d = et(r, t) * 8, u = xs(n, r);
    if (u <= d) {
      a = u;
      break;
    }
    if (r >= s)
      throw new RangeError("Data too long");
  }
  for (const d of [ie, ne, re])
    o && a <= et(r, d) * 8 && (t = d);
  const c = [];
  for (const d of n) {
    S(d.mode[0], 4, c), S(d.numChars, ce(d.mode, r), c);
    for (const u of d.getData())
      c.push(u);
  }
  const l = et(r, t) * 8;
  S(0, Math.min(4, l - c.length), c), S(0, (8 - c.length % 8) % 8, c);
  for (let d = 236; c.length < l; d ^= 253)
    S(d, 8, c);
  const h = Array.from({ length: Math.ceil(c.length / 8) }, () => 0);
  return c.forEach((d, u) => h[u >>> 3] |= d << 7 - (u & 7)), new gs(r, t, h, i);
}
function Ms(n, t) {
  const {
    ecc: e = "L",
    boostEcc: s = !1,
    minVersion: i = 1,
    maxVersion: o = 40,
    maskPattern: r = -1,
    border: a = 1
  } = t || {}, c = typeof n == "string" ? Ss(n) : Array.isArray(n) ? [le(n)] : void 0;
  if (!c)
    throw new Error(`uqr only supports encoding string and binary data, but got: ${typeof n}`);
  const l = _s(
    c,
    ds[e],
    i,
    o,
    r,
    s
  ), h = ks({
    version: l.version,
    maskPattern: l.mask,
    size: l.size,
    data: l.modules,
    types: l.types
  }, a);
  return t?.invert && (h.data = h.data.map((d) => d.map((u) => !u))), t?.onEncoded?.(h), h;
}
function ks(n, t = 1) {
  if (!t)
    return n;
  const { size: e } = n, s = e + t * 2;
  n.size = s, n.data.forEach((o) => {
    for (let r = 0; r < t; r++)
      o.unshift(!1), o.push(!1);
  });
  for (let o = 0; o < t; o++)
    n.data.unshift(Array.from({ length: s }, (r) => !1)), n.data.push(Array.from({ length: s }, (r) => !1));
  const i = _.Border;
  n.types.forEach((o) => {
    for (let r = 0; r < t; r++)
      o.unshift(i), o.push(i);
  });
  for (let o = 0; o < t; o++)
    n.types.unshift(Array.from({ length: s }, (r) => i)), n.types.push(Array.from({ length: s }, (r) => i));
  return n;
}
const ot = "http://www.w3.org/2000/svg";
function Ps(n, t = document) {
  const { data: e, size: s } = Ms(n, { ecc: "M", border: 2 }), i = t.createElementNS(ot, "svg");
  i.setAttribute("viewBox", `0 0 ${s} ${s}`), i.setAttribute("shape-rendering", "crispEdges"), i.setAttribute("class", "qr");
  const o = t.createElementNS(ot, "rect");
  o.setAttribute("width", String(s)), o.setAttribute("height", String(s)), o.setAttribute("fill", "#fff"), i.appendChild(o);
  let r = "";
  e.forEach((c, l) => c.forEach((h, d) => {
    h && (r += `M${d} ${l}h1v1h-1z`);
  }));
  const a = t.createElementNS(ot, "path");
  return a.setAttribute("d", r), a.setAttribute("fill", "#000"), i.appendChild(a), i;
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
    return ee(String(t ?? ""), this.ctx.vars, { now: this.ctx.now, timezone: this.ctx.timezone });
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
function Ns(n, t) {
  t.style.removeProperty("font-size");
  const e = parseFloat(getComputedStyle(t).fontSize) || 16, s = () => t.scrollHeight <= n.clientHeight + 1 && t.scrollWidth <= n.clientWidth + 1;
  if (!n.clientHeight || s()) return;
  let i = Math.max(4, e * 0.1), o = e;
  for (let r = 0; r < 12 && o - i > 0.5; r++) {
    const a = (i + o) / 2;
    t.style.fontSize = `${a}px`, s() ? i = a : o = a;
  }
  t.style.fontSize = `${i}px`;
}
class zs extends y {
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
      const i = () => Ns(this, t);
      requestAnimationFrame(i), document.fonts?.ready.then(i).catch(() => {
      }), this.observe(i);
    }
    /\{\{\s*now/.test(String(this.props.text ?? "")) && this.every(1e3, () => {
      t.textContent = this.text(this.props.text);
    });
  }
}
class Ts extends y {
  draw() {
    const t = document.createElement("div");
    t.className = "evac-richtext";
    for (const e of this.text(this.props.text).split(/\n{2,}/)) {
      const s = document.createElement("p");
      e.split(`
`).forEach((i, o) => {
        o && s.appendChild(document.createElement("br"));
        for (const r of i.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/))
          /^\*\*[^*]+\*\*$/.test(r) ? s.appendChild(Object.assign(
            document.createElement("strong"),
            { textContent: r.slice(2, -2) }
          )) : /^\*[^*]+\*$/.test(r) ? s.appendChild(Object.assign(
            document.createElement("em"),
            { textContent: r.slice(1, -1) }
          )) : r && s.appendChild(document.createTextNode(r));
      }), t.appendChild(s);
    }
    this.replaceChildren(t);
  }
}
function ue(n, t, e) {
  const s = document.createElement("picture");
  for (const [o, r] of [["avif", "image/avif"], ["webp", "image/webp"]])
    if (n.urls[o]) {
      const a = document.createElement("source");
      a.type = r, a.srcset = n.urls[o], s.appendChild(a);
    }
  const i = document.createElement("img");
  return i.src = n.urls.original, i.alt = e || n.alt || "", i.decoding = "async", i.style.objectFit = t, s.appendChild(i), s;
}
class Ds extends y {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Image");
    this.replaceChildren(ue(t, String(this.props.fit ?? "contain"), String(this.props.alt ?? "")));
  }
}
class Hs extends y {
  draw() {
    const t = (Array.isArray(this.props.assets) ? this.props.assets : []).map((r) => this.asset(r)).filter((r) => !!r);
    if (!t.length) return this.placeholder("Slideshow");
    const e = String(this.props.fit ?? "cover"), s = t.map((r) => {
      const a = ue(r, e, "");
      return a.className = "evac-slide", a;
    });
    this.replaceChildren(...s);
    const i = Math.max(1, Number(this.props.interval) || 8) * 1e3, o = () => {
      const r = Math.floor(this.ctx.now() / i) % s.length;
      s.forEach((a, c) => a.classList.toggle("active", c === r));
    };
    o(), this.every(500, o);
  }
}
class Os extends y {
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
class Ls extends y {
  draw() {
    const t = this.asset(this.props.asset);
    if (!t) return this.placeholder("Audio");
    if (this.ctx.editing) return this.placeholder(`♪ ${t.name}`);
    const e = document.createElement("audio");
    e.src = t.urls.audio ?? t.urls.original, e.loop = this.props.loop !== !1, e.muted = this.ctx.audio?.enabled === !1, e.volume = Math.max(0, Math.min(1, (this.ctx.audio?.volume ?? 100) / 100)), e.autoplay = !0, this.replaceChildren(e);
  }
}
class Rs extends y {
  draw() {
    this.dataset.shape = String(this.props.shape ?? "rect"), this.replaceChildren();
  }
}
class Bs extends y {
  draw() {
    const t = this.text(this.props.text);
    if (!t) return this.placeholder("QR code");
    const e = Ps(t);
    e.setAttribute("role", "img"), e.setAttribute("aria-label", t), this.replaceChildren(e);
  }
}
const Fs = {
  "HH:mm": { hour: "2-digit", minute: "2-digit", hourCycle: "h23" },
  "HH:mm:ss": { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" },
  "h:mm a": { hour: "numeric", minute: "2-digit", hourCycle: "h12" }
};
class Is extends y {
  draw() {
    const t = String(this.props.format ?? "HH:mm"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = new Intl.DateTimeFormat(t === "h:mm a" ? "en-US" : "en-GB", { ...Fs[t], timeZone: e }), i = document.createElement("time"), o = () => {
      i.textContent = s.format(new Date(this.ctx.now()));
    };
    o(), this.replaceChildren(i), this.every(1e3, o);
  }
}
class Us extends y {
  draw() {
    const t = String(this.props.format ?? "long"), e = String(this.props.timezone || this.ctx.timezone || "") || void 0, s = {
      long: { weekday: "long", day: "numeric", month: "long" },
      short: { day: "numeric", month: "short" },
      weekday: { weekday: "long" },
      iso: { year: "numeric", month: "2-digit", day: "2-digit" }
    }, i = new Intl.DateTimeFormat(t === "iso" ? "sv-SE" : "en-GB", { ...s[t], timeZone: e }), o = document.createElement("time"), r = () => {
      o.textContent = i.format(new Date(this.ctx.now()));
    };
    r(), this.replaceChildren(o), this.every(3e4, r);
  }
}
function Ws(n, t) {
  const e = Math.max(0, Math.floor(n / 1e3)), s = Math.floor(e / 86400), i = Math.floor(e % 86400 / 3600), o = Math.floor(e % 3600 / 60), r = e % 60, a = (c) => String(c).padStart(2, "0");
  return t === "days" ? `${s} ${s === 1 ? "day" : "days"}` : t === "ms" ? `${a(Math.floor(e / 60))}:${a(r)}` : t === "hms" || s === 0 ? `${a(i + s * 24)}:${a(o)}:${a(r)}` : `${s}d ${a(i)}:${a(o)}:${a(r)}`;
}
class js extends y {
  draw() {
    const t = new Date(this.text(this.props.target)).getTime();
    if (isNaN(t)) return this.placeholder("Countdown");
    const e = document.createElement("span"), s = () => {
      const i = t - this.ctx.now();
      e.textContent = i <= 0 && this.props.finished ? this.text(this.props.finished) : Ws(i, String(this.props.format ?? "auto"));
    };
    s(), this.replaceChildren(e), this.every(250, s);
  }
}
class qs extends y {
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
    s.setAttribute("sandbox", "allow-scripts"), s.setAttribute("referrerpolicy", "no-referrer"), s.setAttribute("allow", "autoplay"), s.setAttribute("title", this.el.name || "Code"), s.setAttribute("tabindex", "-1"), s.className = "evac-code-frame", s.srcdoc = Ve(e, t, location.origin, Ge(this)), this.frame = s, window.addEventListener("message", this.onMessage), this.replaceChildren(s), (e.data ?? []).includes("time") && this.every(1e4, () => this.send());
  }
  /** Only the kinds of data the element asked for (and that the server let it ask for). */
  send() {
    const t = new Set(this.props.data ?? []), e = this.ctx.vars, s = {};
    if (t.has("event") && (s.event = e.event ?? null), t.has("screen") && (s.screen = e.screen ?? null), t.has("time") && (s.now = this.ctx.now(), s.timezone = this.ctx.timezone ?? ""), t.has("assets")) {
      const i = {};
      for (const o of this.props.assets ?? []) {
        const r = this.ctx.assets[o];
        if (!r) continue;
        const a = {};
        for (const [c, l] of Object.entries(r.urls)) a[c] = new URL(l, location.href).href;
        i[o] = { name: r.name, kind: r.kind, alt: r.alt, width: r.width, height: r.height, urls: a };
      }
      s.assets = i;
    }
    this.frame?.contentWindow?.postMessage({ type: "evac:data", data: JSON.parse(JSON.stringify(s)) }, "*");
  }
  disconnectedCallback() {
    window.removeEventListener("message", this.onMessage), this.frame = null, super.disconnectedCallback();
  }
}
const H = {
  text: zs,
  richtext: Ts,
  image: Ds,
  slideshow: Hs,
  video: Os,
  audio: Ls,
  shape: Rs,
  qr: Bs,
  clock: Is,
  countdown: js,
  date: Us,
  code: qs
};
function Vs(n = customElements) {
  for (const [t, e] of Object.entries(H))
    n.get(`evac-${t}`) || n.define(`evac-${t}`, e);
}
class Gs extends y {
  draw() {
    const t = String(this.props.code ?? "E002");
    let e = String(this.props.direction ?? "auto");
    if (e === "auto") {
      const s = this.ctx.vars.evac;
      if (t === "arrow" && !s?.arrow) {
        this.replaceChildren(), this.hidden = !0;
        return;
      }
      e = s?.arrow ?? "ahead";
    }
    this.hidden = !1, this.innerHTML = ls(t, e);
  }
}
H.pictogram = Gs;
class Ks {
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
  const s = document.createElement(n);
  return t && (s.className = t), e != null && e !== "" && (s.textContent = String(e)), s;
}
function N(n) {
  if (typeof n == "number") return Number.isFinite(n) ? n : null;
  if (typeof n == "string" && n.trim() !== "") {
    const t = Number(n.replace(",", ".").replace(/[^\d.+-eE]/g, ""));
    return Number.isFinite(t) ? t : null;
  }
  return null;
}
function Y(n, t) {
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
const Ys = ["time", "title", "subtitle", "label", "value"];
class Zs extends y {
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
    const s = f("div", `evac-data evac-data-${e.visual}`), i = String(this.props.title || e.options.heading || "");
    i && s.appendChild(f("div", "evac-data-heading", i));
    const o = f("div", "evac-data-body");
    s.appendChild(o), (Rt[e.visual] ?? Rt.list)(o, e, this), this.ctx.editing && e.stale && s.appendChild(f("span", "evac-data-stale", "stale")), this.replaceChildren(s);
  }
  /** template text with {{ data.first.title }}, {{ data.rows }}, {{ data.count }} next to the usual variables */
  tmpl(t, e) {
    return ee(
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
function R(n, t) {
  return t.rows.length ? !1 : (n.appendChild(f("div", "evac-data-empty", "–")), !0);
}
const Rt = {
  text(n, t, e) {
    n.appendChild(f("div", "evac-data-text", e.tmpl(
      String(t.options.template || "{{ data.first.title }}"),
      t
    )));
  },
  list(n, t, e) {
    if (R(n, t)) return;
    const s = f("ul", "evac-data-list");
    for (const i of t.rows) {
      const o = f("li");
      i.time && o.appendChild(f("span", "evac-data-time", Y(i.time, e.tz)));
      const r = f("span", "evac-data-main");
      r.appendChild(f("span", "evac-data-title", i.title ?? i.label ?? i.value)), i.subtitle && r.appendChild(f("span", "evac-data-sub", i.subtitle)), o.appendChild(r), i.value !== void 0 && i.value !== null && i.title && o.appendChild(f("span", "evac-data-value", i.value)), s.appendChild(o);
    }
    n.appendChild(s);
  },
  table(n, t, e) {
    if (R(n, t)) return;
    const s = Ys.filter((r) => t.rows.some((a) => a[r] !== void 0 && a[r] !== null && a[r] !== "")), i = f("table", "evac-data-table"), o = f("tbody");
    for (const r of t.rows) {
      const a = f("tr");
      for (const c of s) a.appendChild(f("td", `evac-data-${c}`, c === "time" ? Y(r[c], e.tz) : r[c]));
      o.appendChild(a);
    }
    i.appendChild(o), n.appendChild(i);
  },
  cards(n, t, e) {
    if (R(n, t)) return;
    const s = f("div", "evac-data-cards");
    for (const i of t.rows) {
      const o = f("div", "evac-data-card");
      if (typeof i.image == "string" && i.image.startsWith("/")) {
        const r = f("img");
        r.src = i.image, r.alt = "", o.appendChild(r);
      }
      i.time && o.appendChild(f("div", "evac-data-time", Y(i.time, e.tz))), o.appendChild(f("div", "evac-data-title", i.title ?? i.label)), i.subtitle && o.appendChild(f("div", "evac-data-sub", i.subtitle)), i.value !== void 0 && i.value !== null && o.appendChild(f("div", "evac-data-value", i.value)), s.appendChild(o);
    }
    n.appendChild(s);
  },
  counter(n, t) {
    const e = t.rows[0] ?? {}, s = e.value !== void 0 && e.value !== null ? e.value : t.rows.length, i = N(s), o = f("div", "evac-data-number", i === null ? s : i.toLocaleString("en-GB"));
    t.options.unit && o.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(o), (e.label || e.title) && n.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  gauge(n, t) {
    const e = t.rows[0] ?? {}, s = N(e.value) ?? 0, i = N(t.options.minimum) ?? 0, o = N(t.options.maximum) ?? 100, r = Math.max(0, Math.min(1, (s - i) / (o - i || 1))), a = "http://www.w3.org/2000/svg", c = document.createElementNS(a, "svg");
    c.setAttribute("viewBox", "0 0 200 110"), c.setAttribute("class", "evac-data-gauge"), c.setAttribute("role", "img"), c.setAttribute("aria-label", `${s}${t.options.unit ? ` ${t.options.unit}` : ""}`);
    const l = (d, u) => {
      const m = Math.PI * (1 - d), v = document.createElementNS(a, "path");
      v.setAttribute("d", `M 20 100 A 80 80 0 0 1 ${100 + 80 * Math.cos(m)} ${100 - 80 * Math.sin(m)}`), v.setAttribute("class", u), c.appendChild(v);
    };
    l(1, "evac-gauge-track"), r > 0 && l(r, "evac-gauge-fill"), n.appendChild(c);
    const h = f("div", "evac-data-number", s.toLocaleString("en-GB"));
    t.options.unit && h.appendChild(f("span", "evac-data-unit", ` ${t.options.unit}`)), n.appendChild(h), (e.label || e.title) && n.appendChild(f("div", "evac-data-sub", e.label ?? e.title));
  },
  ticker(n, t, e) {
    if (R(n, t)) return;
    const s = t.rows.map((r) => [r.time ? Y(r.time, e.tz) : "", r.title ?? r.label ?? ""].filter(Boolean).join(" ")).join("   ◆   "), i = f("div", "evac-marquee-box"), o = f("span", "evac-marquee", s);
    o.style.animationDuration = `${Math.max(10, s.length / 5)}s`, i.appendChild(o), n.appendChild(i);
  },
  bars(n, t) {
    if (R(n, t)) return;
    const e = t.rows.map((o) => N(o.value) ?? 0), s = N(t.options.maximum) || Math.max(...e, 1), i = f("div", "evac-data-bars");
    t.rows.forEach((o, r) => {
      const a = f("div", "evac-bar");
      a.appendChild(f("span", "evac-bar-label", o.label ?? o.title));
      const c = f("span", "evac-bar-track"), l = f("span", "evac-bar-fill");
      l.style.width = `${Math.max(0, Math.min(100, e[r] / s * 100))}%`, c.appendChild(l), a.appendChild(c), a.appendChild(f("span", "evac-bar-value", `${e[r].toLocaleString("en-GB")}${t.options.unit ? ` ${t.options.unit}` : ""}`)), i.appendChild(a);
    }), n.appendChild(i);
  }
};
H.data = Zs;
class Js {
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
function $(n, t = "", e) {
  const s = document.createElement(n);
  return t && (s.className = t), e != null && e !== "" && (s.textContent = String(e)), s;
}
function Z(n, t) {
  const e = new Date(n);
  if (Number.isNaN(e.getTime())) return "";
  const s = { hour: "2-digit", minute: "2-digit", hour12: !1 };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...s, timeZone: t }).format(e);
  } catch {
    return new Intl.DateTimeFormat("en-GB", s).format(e);
  }
}
function Bt(n, t) {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: t, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(n));
  } catch {
    return new Date(n).toISOString().slice(0, 10);
  }
}
function Xs(n, t, e) {
  const s = n.filter((r) => (t === null || r.stage === t) && r.status !== "cancelled").sort((r, a) => Date.parse(r.start) - Date.parse(a.start)), i = s.find((r) => Date.parse(r.start) <= e && Date.parse(r.end) > e) ?? null, o = s.find((r) => Date.parse(r.start) > e) ?? null;
  return { now: i, next: o };
}
function Qs(n, t) {
  return t || (n.screen_room ? n.stages.find((e) => e.room === n.screen_room)?.id ?? null : null);
}
class ti extends y {
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
    const s = $("div", `evac-program evac-program-${e}`), i = String(this.props.title ?? "");
    i && s.appendChild($("div", "evac-program-heading", i));
    const o = this.ctx.now(), r = Qs(t, String(this.props.stage ?? "")), a = Math.max(1, Math.min(20, Number(this.props.count) || 6));
    e === "changes" ? this.changes(s, t, a) : e === "day" ? this.day(s, t, r, o, a) : this.nowNext(s, t, r, o), this.replaceChildren(s);
  }
  badge(t) {
    return t.status === "cancelled" ? $("span", "evac-program-badge evac-program-cancelled", "Cancelled") : t.delay > 0 ? $("span", "evac-program-badge evac-program-late", `+${t.delay} min`) : t.delay < 0 ? $("span", "evac-program-badge evac-program-late", `${t.delay} min`) : t.moved_from ? $("span", "evac-program-badge evac-program-late", "Room changed") : null;
  }
  session(t, e, s) {
    const i = $("div", `evac-program-session${t.status === "cancelled" ? " is-cancelled" : ""}`);
    t.colour && i.style.setProperty("--evac-track", t.colour);
    const o = $("div", "evac-program-when");
    e && o.appendChild($("span", "evac-program-label", e)), o.appendChild($("span", "evac-program-time", `${Z(t.start, this.tz)}–${Z(t.end, this.tz)}`)), t.planned_start && t.delay && o.appendChild($("s", "evac-program-was", Z(t.planned_start, this.tz)));
    const r = this.badge(t);
    r && o.appendChild(r), i.appendChild(o), i.appendChild($("div", "evac-program-title", t.title));
    const a = [s ? t.stage_name : "", t.speakers.join(", ")].filter(Boolean).join(" · ");
    return a && i.appendChild($("div", "evac-program-meta", a)), t.note && i.appendChild($("div", "evac-program-note", t.note)), i;
  }
  nowNext(t, e, s, i) {
    const o = s ? e.stages.filter((c) => c.id === s) : e.stages;
    let r = 0;
    for (const c of o) {
      const { now: l, next: h } = Xs(e.sessions, c.id, i);
      if (!l && !h) continue;
      const d = $("div", "evac-program-stage");
      s || d.appendChild($("div", "evac-program-stage-name", c.name)), l && d.appendChild(this.session(l, "Now", !1)), h && d.appendChild(this.session(h, "Next", !1)), t.appendChild(d), r++;
    }
    const a = e.sessions.filter((c) => c.status === "cancelled" && (!s || c.stage === s) && Date.parse(c.end) > i && Date.parse(c.start) - 36e5 < i);
    for (const c of a.slice(0, 2)) t.appendChild(this.session(c, "", !s));
    !r && !a.length && t.appendChild($("div", "evac-program-empty", "Nothing more today"));
  }
  day(t, e, s, i, o) {
    const r = Bt(i, this.tz), a = e.sessions.filter((c) => (!s || c.stage === s) && Date.parse(c.end) > i && Bt(Date.parse(c.start), this.tz) === r).sort((c, l) => Date.parse(c.start) - Date.parse(l.start));
    if (!a.length) {
      t.appendChild($("div", "evac-program-empty", "Nothing more today"));
      return;
    }
    for (const c of a.slice(0, o)) {
      const l = Date.parse(c.start) <= i && c.status !== "cancelled";
      t.appendChild(this.session(c, l ? "Now" : "", !s));
    }
  }
  changes(t, e, s) {
    if (!e.changes.length) {
      t.appendChild($("div", "evac-program-empty", "No changes"));
      return;
    }
    const i = $("ul", "evac-program-changes");
    for (const o of e.changes.slice(0, s)) {
      const r = $("li", `evac-program-change evac-program-change-${o.kind}`);
      r.appendChild($("span", "evac-program-time", Z(o.at, this.tz))), r.appendChild($("span", "evac-program-change-text", o.text)), i.appendChild(r);
    }
    t.appendChild(i);
  }
  disconnectedCallback() {
    this.unsubscribe?.(), this.unsubscribe = null, this.ticking = !1, super.disconnectedCallback();
  }
}
H.program = ti;
const at = /* @__PURE__ */ new Map();
function ei(n) {
  let t = at.get(n);
  return t || (t = import(
    /* @vite-ignore */
    n
  ), at.set(n, t), t.catch(() => at.delete(n))), t;
}
function si(n, t, e = () => ({}), s = !1) {
  const i = /* @__PURE__ */ new Map(), o = (r) => `evac.plugin-source.${r}`;
  return {
    get widgets() {
      return n();
    },
    async source(r) {
      try {
        const a = await fetch(`${t}${encodeURIComponent(r)}/`, { headers: e(), cache: "no-store" });
        if (!a.ok) throw new Error(`HTTP ${a.status}`);
        const c = await a.json();
        if (i.set(r, c.data), s)
          try {
            localStorage.setItem(o(r), JSON.stringify(c.data));
          } catch {
          }
        return c.data;
      } catch (a) {
        if (i.has(r)) return i.get(r);
        if (s)
          try {
            const c = localStorage.getItem(o(r));
            if (c !== null) return JSON.parse(c);
          } catch {
          }
        throw a;
      }
    }
  };
}
class ii extends y {
  constructor() {
    super(...arguments), this.inner = null;
  }
  draw() {
    const t = String(this.props.widget ?? ""), e = t ? this.ctx.plugins?.widgets[t] : void 0;
    if (!e) return this.placeholder(t ? `Plugin widget “${t}” is not installed` : "Plugin widget");
    const s = this.props.settings ?? {};
    ei(e.script).then(() => {
      if (!this.isConnected && !this.ctx.editing) return;
      if (!customElements.get(e.element)) throw new Error(`${e.script} did not define <${e.element}>`);
      const i = document.createElement(e.element);
      i.className = "evac-plugin-element", i.settings = s, i.vars = this.ctx.vars, i.data = {}, this.replaceChildren(i), this.inner = i, this.refresh(e), e.sources.length && this.every(Math.max(10, e.ttl) * 1e3, () => this.refresh(e));
    }).catch((i) => this.safely(() => {
      throw i;
    }));
  }
  refresh(t) {
    const e = this.ctx.plugins;
    if (e)
      for (const s of t.sources)
        e.source(s).then((i) => {
          this.inner && (this.inner.data = { ...this.inner.data ?? {}, [s]: i });
        }).catch((i) => this.ctx.onError?.(this.el.id, i));
  }
}
H.plugin = ii;
function Ft(n, t) {
  if (n.slide === null) return null;
  if (n.slide) {
    const s = n.slide.end - n.slide.start;
    return s > 0 ? { start: n.slide.start, total: s, loop: !1 } : null;
  }
  const e = Math.max(1e3, n.loopMs ?? 1e4);
  return { start: t - (t % e + e) % e, total: e, loop: !0 };
}
function ni(n, t, e) {
  const s = Math.max(0, Math.min(1, (t - n.start) / n.total));
  return e ? s : 1 - s;
}
class ri extends y {
  draw() {
    const t = this.props, e = t.orientation === "vertical", s = t.mode === "grow", i = document.createElement("span");
    i.className = "evac-progress-bar", this.dataset.orientation = e ? "vertical" : "horizontal", this.dataset.mode = s ? "grow" : "shrink", this.toggleAttribute("data-reverse", t.reverse === !0), this.replaceChildren(i);
    const o = this.parentElement, r = this.ctx.now(), a = Ft(this.ctx, r);
    o?.classList.toggle("evac-off", !a && t.untimed === "hide");
    const c = e ? "Y" : "X", l = (d) => {
      i.style.transform = `scale${c}(${d.toFixed(4)})`;
    };
    if (!a) {
      l(1);
      return;
    }
    if (this.ctx.reducedMotion || this.ctx.motion === !1) {
      const d = () => l(ni(
        a.loop ? Ft(this.ctx, this.ctx.now()) ?? a : a,
        this.ctx.now(),
        s
      ));
      d(), this.every(1e3, d);
      return;
    }
    const h = i.style;
    h.animationName = `evac-timer-${s ? "grow" : "shrink"}-${c.toLowerCase()}`, h.animationDuration = `${a.total}ms`, h.animationDelay = `${-Math.round(r - a.start)}ms`, h.animationTimingFunction = "linear", h.animationIterationCount = a.loop ? "infinite" : "1", h.animationFillMode = "both";
  }
}
H.progress = ri;
const oi = /* @__PURE__ */ new Set(["fade", "slide-up", "slide-left", "zoom"]), ai = 1e4, ci = 6e4, It = (n, t, e) => Math.max(t, Math.min(e, Number(n) || 0));
function li(n) {
  return !n.reducedMotion && (n.motion ?? !n.editing);
}
function ut(n, t) {
  const e = t.frame;
  n.style.left = `${e.x}%`, n.style.top = `${e.y}%`, n.style.width = `${e.w}%`, n.style.height = `${e.h}%`, n.style.transform = e.rotate ? `rotate(${e.rotate}deg)` : "";
}
function hi(n, t) {
  const e = !n.visible_if || gt(n.visible_if, t.vars, { now: t.now, timezone: t.timezone });
  if (n.hidden && !t.editing || !e && !t.editing) return null;
  const s = document.createElement("div");
  s.className = `evac-el evac-el-${n.type}`, s.dataset.id = n.id, (!e || n.hidden) && s.classList.add("evac-dimmed"), ut(s, n), Ze(s, n.style, t);
  const i = n.animation;
  i?.enter && oi.has(i.enter) && li(t) && (s.classList.add(`evac-enter-${i.enter}`), s.style.animationDuration = `${It(i.duration ?? 600, 0, ai)}ms`, s.style.animationDelay = `${It(i.delay ?? 0, 0, ci)}ms`);
  const o = `evac-${n.type}`;
  if (!customElements.get(o))
    return t.onError?.(n.id, new Error(`unknown element type ${n.type}`)), t.editing ? s : null;
  const r = document.createElement(o);
  return r.className = "evac-widget", s.appendChild(r), r.configure(n, t), s;
}
function di(n, t, e) {
  Vs(), e.loopMs === void 0 && (e = { ...e, loopMs: Math.max(1, t.duration ?? 10) * 1e3 });
  const s = document.createElement("div");
  s.className = "evac-stage";
  const i = t.background;
  if (i?.color && (s.style.background = Q(i.color)), i?.asset && e.assets[i.asset]) {
    const c = e.assets[i.asset], l = c.urls.webp ?? c.urls.original;
    s.style.backgroundImage = `url("${l}")`, s.style.backgroundSize = i.fit ?? "cover", s.style.backgroundPosition = "center";
  }
  const o = /* @__PURE__ */ new Map();
  for (const c of t.elements) {
    const l = hi(c, e);
    l && (o.set(c.id, l), s.appendChild(l));
  }
  n.replaceChildren(s);
  const r = () => {
    const c = n.clientWidth, l = n.clientHeight;
    if (!c || !l) return;
    const h = Math.min(c / t.width, l / t.height);
    s.style.width = `${Math.round(t.width * h)}px`, s.style.height = `${Math.round(t.height * h)}px`;
  };
  r();
  const a = typeof ResizeObserver < "u" ? new ResizeObserver(r) : null;
  return a?.observe(n), {
    stage: s,
    elements: o,
    destroy() {
      a?.disconnect(), s.remove();
    }
  };
}
const k = (n) => JSON.parse(JSON.stringify(n));
class ui {
  constructor(t = 200) {
    this.limit = t, this.past = [], this.future = [];
  }
  push(t) {
    this.past.push(k(t)), this.past.length > this.limit && this.past.shift(), this.future = [];
  }
  undo(t) {
    const e = this.past.pop();
    return e ? (this.future.push(k(t)), e) : null;
  }
  redo(t) {
    const e = this.future.pop();
    return e ? (this.past.push(k(t)), e) : null;
  }
  get canUndo() {
    return this.past.length > 0;
  }
  get canRedo() {
    return this.future.length > 0;
  }
}
function pe(n, t) {
  const e = new Set(n);
  for (let s = 1; ; s++) if (!e.has(`${t}${s}`)) return `${t}${s}`;
}
const Ut = {
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
  date: { frame: { x: 5, y: 5, w: 40, h: 8 }, style: { fontSize: 4 }, props: { format: "long" } },
  progress: {
    frame: { x: 0, y: 98.5, w: 100, h: 1.5 },
    style: { color: "token:accent" },
    props: { orientation: "horizontal", mode: "shrink", untimed: "full" }
  },
  data: { frame: { x: 10, y: 15, w: 45, h: 60 }, style: { fontSize: 4.5 }, props: { widget: "" } },
  program: {
    frame: { x: 5, y: 15, w: 55, h: 70 },
    style: { fontSize: 4 },
    props: { view: "now_next", stage: "", count: 6, title: "" }
  },
  pictogram: { frame: { x: 5, y: 10, w: 20, h: 35 }, props: { code: "E002", direction: "auto" } },
  code: {
    frame: { x: 10, y: 10, w: 40, h: 30 },
    props: {
      html: '<div class="box"><span id="t"></span></div>',
      css: ".box { display: grid; place-items: center; height: 100%; font-size: 12vh; color: var(--evac-color-accent, #ffd400); }",
      js: `evac.onData(() => {
  const t = document.getElementById("t");
  const tick = () => { t.textContent = new Date(evac.now()).toLocaleTimeString(); };
  tick();
  setInterval(tick, 1000);
});`,
      data: ["time"]
    }
  }
};
function pi(n, t, e) {
  const s = k(Ut[n] ?? Ut.text), i = t.length % 8 * 2, o = s.frame;
  return {
    id: pe(t.map((r) => r.id), n),
    type: n,
    name: e,
    ...s,
    frame: { ...o, x: o.x + i, y: o.y + i }
  };
}
function Wt(n, t) {
  const e = k(n);
  return e.id = pe(t.map((s) => s.id), `${n.type}`), e.name = `${n.name ?? n.type} copy`, e.frame = { ...e.frame, x: e.frame.x + 2, y: e.frame.y + 2 }, e;
}
const fe = (n, t) => Math.round(n / t) * t;
function fi(n, t, { grid: e = 0.5, threshold: s = 0.8 } = {}) {
  let i = null;
  for (const o of t) Math.abs(o - n) <= s && (i === null || Math.abs(o - n) < Math.abs(i - n)) && (i = o);
  return i !== null ? [i, i] : [fe(n, e), null];
}
function jt(n, t, e) {
  const s = [0, 50, 100];
  for (const i of n) {
    if (t.has(i.id)) continue;
    const o = e === "x" ? i.frame.x : i.frame.y, r = e === "x" ? i.frame.w : i.frame.h;
    s.push(o, o + r / 2, o + r);
  }
  return s;
}
function qt(n, t, e, s) {
  const o = [0, t / 2, t].map((r) => {
    const [a, c] = fi(n + r, e, s);
    return [a - r, c, c === null ? 1 / 0 : Math.abs(a - (n + r))];
  }).filter((r) => r[1] !== null).sort((r, a) => r[2] - a[2])[0];
  return o ? [o[0], o[1]] : [fe(n, 0.5), null];
}
function mi(n, t, e) {
  const s = n.filter((l) => t.has(l.id));
  if (!s.length) return n;
  const i = s.length === 1, o = i ? 0 : Math.min(...s.map((l) => l.frame.x)), r = i ? 100 : Math.max(...s.map((l) => l.frame.x + l.frame.w)), a = i ? 0 : Math.min(...s.map((l) => l.frame.y)), c = i ? 100 : Math.max(...s.map((l) => l.frame.y + l.frame.h));
  return n.map((l) => {
    if (!t.has(l.id)) return l;
    const h = { ...l.frame };
    return e === "left" && (h.x = o), e === "right" && (h.x = r - h.w), e === "center" && (h.x = (o + r) / 2 - h.w / 2), e === "top" && (h.y = a), e === "bottom" && (h.y = c - h.h), e === "middle" && (h.y = (a + c) / 2 - h.h / 2), { ...l, frame: h };
  });
}
function Vt(n, t, e) {
  const s = n.findIndex((a) => a.id === t), i = Math.min(n.length - 1, Math.max(0, s + e));
  if (s < 0 || s === i) return n;
  const o = [...n], [r] = o.splice(s, 1);
  return o.splice(i, 0, r), o;
}
function gi(n, t, e, s, i = 1) {
  const o = { ...n };
  return t.includes("w") && (o.x = Math.min(n.x + e, n.x + n.w - i), o.w = n.w - (o.x - n.x)), t.includes("e") && (o.w = Math.max(i, n.w + e)), t.includes("n") && (o.y = Math.min(n.y + s, n.y + n.h - i), o.h = n.h - (o.y - n.y)), t.includes("s") && (o.h = Math.max(i, n.h + s)), o;
}
const x = (n) => Math.round(n * 100) / 100, J = {
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
  date: "Date",
  code: "Code",
  data: "Data widget",
  pictogram: "Safety sign",
  program: "Program",
  plugin: "Plugin widget",
  progress: "Slide timer"
}, vi = ["primary", "accent", "text", "muted", "surface", "background", "success", "warning", "danger"], $i = {
  primary: "Primary",
  accent: "Accent",
  text: "Text",
  muted: "Muted text",
  surface: "Surface",
  background: "Background",
  success: "Success",
  warning: "Warning",
  danger: "Danger"
}, yi = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
class wi extends je {
  constructor(t) {
    if (super(t), t.type !== Ue.ELEMENT) throw new Error("ref() only on elements");
  }
  update(t, [e]) {
    return e(t.element), this.render(e);
  }
  render(t) {
    return g;
  }
}
const ct = We(wi);
function Gt(n, t) {
  const e = document.getElementById(n);
  try {
    return e?.textContent ? JSON.parse(e.textContent) : t;
  } catch {
    return t;
  }
}
function Kt() {
  return document.cookie.split("; ").find((n) => n.startsWith("csrftoken="))?.split("=")[1] ?? "";
}
const wt = class wt extends U {
  constructor() {
    super(...arguments), this.selected = /* @__PURE__ */ new Set(), this.status = "saved", this.zoom = 0, this.guides = { x: null, y: null }, this.error = "", this.findings = [], this.cfg = Gt("editor-config", {}), this.strings = Gt("editor-strings", {}), this.history = new ui(), this.version = 0, this.rendered = null, this.drag = null, this.clipboardKey = "evac.editor.clipboard", this.playMotion = !1, this.pluginHost = null;
  }
  createRenderRoot() {
    return this;
  }
  t(t) {
    return this.strings[t] ?? t;
  }
  connectedCallback() {
    this.replaceChildren(), super.connectedCallback(), this.data = k(this.cfg.layout.data), this.version = this.cfg.layout.version, this.findings = this.cfg.findings ?? [], this.tabIndex = 0, this.addEventListener("keydown", (t) => this.onKey(t)), window.addEventListener("beforeunload", (t) => {
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
    this.commit({ ...this.data, elements: t(k(this.elements)) });
  }
  patchSelected(t) {
    this.updateElements((e) => e.map((s) => (this.selected.has(s.id) && t(s), s)));
  }
  select(t, e = !1) {
    const s = new Set(e ? this.selected : []);
    t && (e && s.has(t) ? s.delete(t) : s.add(t)), this.selected = s;
  }
  add(t) {
    const e = pi(t, this.elements, this.t(J[t] ?? t));
    this.updateElements((s) => [...s, e]), this.selected = /* @__PURE__ */ new Set([e.id]);
  }
  removeSelected() {
    this.selected.size && (this.updateElements((t) => t.filter((e) => !this.selected.has(e.id) || e.locked)), this.selected = /* @__PURE__ */ new Set());
  }
  duplicateSelected() {
    const t = [];
    for (const e of this.selection) t.push(Wt(e, [...this.elements, ...t]));
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
  /** Render the canvas once with the entrance effects, as screens show the slide. */
  playAnimations() {
    this.playMotion = !0, this.rendered?.destroy(), this.rendered = null, this.requestUpdate();
  }
  // ---------------------------------------------------------------- save and publish
  async save() {
    this.status = "saving", this.error = "";
    try {
      const t = await fetch(this.cfg.urls.save, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": Kt() },
        body: JSON.stringify({ data: this.data, version: this.version })
      }), e = await t.json().catch(() => ({}));
      if (t.ok && e.ok)
        return this.version = e.version, this.status = "saved", this.findings = e.findings ?? [], !0;
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
      headers: { "X-CSRFToken": Kt() }
    }), e = await t.json().catch(() => ({}));
    e.findings && (this.findings = e.findings), this.error = t.ok ? `${this.t("Published")}: v${e.published}` : [this.t("Not published."), ...e.errors ?? []].join(" ");
  }
  // ---------------------------------------------------------------- keyboard
  onKey(t) {
    if (t.target.closest("input, textarea, select")) return;
    const s = t.ctrlKey || t.metaKey, i = t.shiftKey ? 5 : 0.5, o = (a, c) => this.patchSelected((l) => {
      l.locked || (l.frame = { ...l.frame, x: x(l.frame.x + a), y: x(l.frame.y + c) });
    }), r = {
      ArrowLeft: () => o(-i, 0),
      ArrowRight: () => o(i, 0),
      ArrowUp: () => o(0, -i),
      ArrowDown: () => o(0, i),
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
      const c = [];
      for (const l of a) c.push(Wt(l, [...this.elements, ...c]));
      c.length && (this.updateElements((l) => [...l, ...c]), this.selected = new Set(c.map((l) => l.id)));
    } else if (r[t.key]) r[t.key]();
    else return;
    t.preventDefault();
  }
  get plugins() {
    if (!this.pluginHost) {
      const t = Object.fromEntries((this.cfg.choices?.pluginWidgets ?? []).map((e) => [e.value, e]));
      this.pluginHost = si(() => t, this.cfg.urls.sources ?? "");
    }
    return this.pluginHost;
  }
  get ctx() {
    return {
      vars: this.cfg.vars,
      now: () => Date.now(),
      timezone: this.cfg.timezone,
      assets: this.cfg.assets,
      fonts: this.cfg.fonts,
      editing: !0,
      nonce: Ke(),
      ...this.playMotion ? { motion: !0 } : {},
      data: new Ks(this.cfg.choices?.widgetData ?? {}),
      program: new Js(this.cfg.choices?.programData ?? null),
      plugins: this.plugins
    };
  }
  updated() {
    const t = this.querySelector(".ed-host");
    if (t) {
      if (!this.drag) {
        this.rendered?.destroy();
        for (const [e, s] of Object.entries(this.cfg.themeVariables ?? {})) t.style.setProperty(e, s);
        this.rendered = di(t, this.data, this.ctx), this.playMotion = !1, this.zoom && (this.rendered.stage.style.width = `${this.data.width * this.zoom}px`, this.rendered.stage.style.height = `${this.data.height * this.zoom}px`);
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
    const [o, r] = this.percent(t);
    this.drag = {
      mode: s ? "resize" : "move",
      handle: s,
      x0: o,
      y0: r,
      moved: !1,
      start: Object.fromEntries(i.map((a) => [a.id, { ...a.frame }]))
    }, t.target.setPointerCapture(t.pointerId);
  }
  onMove(t) {
    const e = this.drag;
    if (!e) return;
    const [s, i] = this.percent(t);
    let o = s - e.x0, r = i - e.y0;
    if (!e.moved && Math.abs(o) < 0.2 && Math.abs(r) < 0.2) return;
    e.moved || (this.history.push(this.data), e.moved = !0);
    const a = new Set(Object.keys(e.start)), c = t.altKey, l = jt(this.elements, a, "x"), h = jt(this.elements, a, "y"), d = this.elements.map((u) => {
      const m = e.start[u.id];
      if (!m) return u;
      let v;
      if (e.mode === "move") {
        const [St, me] = c ? [m.x + o, null] : qt(m.x + o, m.w, l), [xt, ge] = c ? [m.y + r, null] : qt(m.y + r, m.h, h);
        this.guides = { x: me, y: ge }, o = St - m.x, r = xt - m.y, v = { ...m, x: x(St), y: x(xt) };
      } else
        v = gi(m, e.handle ?? "se", o, r), v = { ...v, x: x(v.x), y: x(v.y), w: x(v.w), h: x(v.h) };
      const G = { ...u, frame: v }, bt = this.rendered?.elements.get(u.id);
      return bt && ut(bt, G), G;
    });
    this.data = { ...this.data, elements: d }, this.status = "dirty";
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
    return p`
      <div class="ed-toolbar" role="toolbar" aria-label=${this.t("Layout")}>
        <strong class="ed-title">${this.cfg.layout?.name}</strong>
        <button class="btn btn-sm" ?disabled=${!this.history.canUndo} @click=${() => this.undo()}>${this.t("Undo")}</button>
        <button class="btn btn-sm" ?disabled=${!this.history.canRedo} @click=${() => this.redo()}>${this.t("Redo")}</button>
        <label class="ed-inline">${this.t("Zoom")}
          <select @change=${(e) => {
      this.zoom = Number(e.target.value);
    }}>
            <option value="0">${this.t("Fit")}</option>${[0.25, 0.5, 0.75, 1].map((e) => p`
            <option value=${e}>${e * 100}%</option>`)}</select></label>
        <button class="btn btn-sm" @click=${() => this.playAnimations()}>${this.t("Play animations")}</button>
        <span class="ed-status" role="status" data-status=${this.status}>${t}</span>
        ${this.error && this.status !== "error" ? p`<span class="ed-status" role="status">${this.error}</span>` : g}
        <button class="btn btn-sm btn-primary" @click=${() => {
      this.save();
    }}>${this.t("Save")}</button>
        ${this.cfg.canPublish ? p`<button class="btn btn-sm" @click=${() => {
      this.publish();
    }}>${this.t("Publish")}</button>` : g}
        <a class="btn btn-sm btn-ghost" href=${this.cfg.urls?.back}>${this.t("Back")}</a>
      </div>
      <div class="ed-body">
        <aside class="ed-side ed-left" aria-label=${this.t("Layers")}>
          <h2 class="ed-h">${this.t("Add")}</h2>
          <div class="ed-add">${(this.cfg.types ?? []).filter((e) => e !== "code" || this.cfg.canCode).map((e) => p`
            <button class="btn btn-sm" @click=${() => this.add(e)}>${this.t(J[e] ?? e)}</button>`)}</div>
          ${this.findings.length ? p`<h2 class="ed-h">${this.t("Checks")}</h2>
          <ul class="ed-findings" role="status">${this.findings.map((e) => p`
            <li class="ed-finding ed-finding-${e.level}"><button class="ed-layer" @click=${() => e.element && this.select(e.element, !1)}>
              ${e.level === "error" ? "✕ " : "! "}${e.message}</button></li>`)}</ul>` : g}
          <h2 class="ed-h">${this.t("Layers")}</h2>
          <ol class="ed-layers">${[...this.elements].reverse().map((e) => p`
            <li class=${this.selected.has(e.id) ? "selected" : ""}>
              <button class="ed-layer" aria-pressed=${this.selected.has(e.id)}
                      @click=${(s) => this.select(e.id, s.shiftKey)}>
                ${e.hidden ? "◌ " : ""}${e.locked ? "🔒 " : ""}${e.name || e.id}
                <span class="muted small">${this.t(J[e.type] ?? e.type)}</span></button></li>`)}</ol>
        </aside>
        <div class="ed-canvas" @pointerdown=${() => this.select(null)}>
          <div class="ed-host"></div>
          <div class="ed-overlay" @pointermove=${(e) => this.onMove(e)}
               @pointerup=${() => this.endDrag()} @pointercancel=${() => this.endDrag()}>
            ${this.guides.x !== null ? p`<div class="ed-guide ed-guide-x" ${ct((e) => {
      e.style.left = `${this.guides.x}%`;
    })}></div>` : g}
            ${this.guides.y !== null ? p`<div class="ed-guide ed-guide-y" ${ct((e) => {
      e.style.top = `${this.guides.y}%`;
    })}></div>` : g}
            ${this.elements.map((e) => this.box(e))}
          </div>
        </div>
        <aside class="ed-side ed-right" aria-label=${this.t("Properties")}>${this.panel()}</aside>
      </div>`;
  }
  box(t) {
    const e = this.selected.has(t.id);
    return p`<div class="ed-box ${e ? "selected" : ""} ${t.locked ? "locked" : ""}" data-id=${t.id}
        ${ct((s) => {
      s && ut(s, t);
    })}
        @pointerdown=${(s) => this.startDrag(s, t.id)}>
        ${e && this.selected.size === 1 && !t.locked ? yi.map((s) => p`<span class="ed-handle ed-${s}"
          @pointerdown=${(i) => this.startDrag(i, t.id, s)}></span>`) : g}
      </div>`;
  }
  // ---------------------------------------------------------------- property panel
  field(t, e) {
    return p`<label class="ed-field"><span>${this.t(t)}</span>${e}</label>`;
  }
  num(t, e, s, i = {}) {
    return this.field(t, p`<input type="number" .value=${e === void 0 ? "" : String(e)}
      min=${i.min ?? ""} max=${i.max ?? ""} step=${i.step ?? "any"}
      @change=${(o) => {
      const r = o.target.value;
      s(r === "" ? void 0 : Number(r));
    }}>`);
  }
  check(t, e, s) {
    return p`<label class="ed-check"><input type="checkbox" .checked=${!!e}
      @change=${(i) => s(i.target.checked)}> ${this.t(t)}</label>`;
  }
  choice(t, e, s, i) {
    return this.field(t, p`<select @change=${(o) => i(o.target.value)}>
      ${s.map(([o, r]) => p`<option value=${o} ?selected=${(e ?? "") === o}>${this.t(r)}</option>`)}</select>`);
  }
  colour(t, e, s) {
    const i = !e || e.startsWith("token:") || e === "transparent", o = [["", "None"], ...vi.map((r) => [
      `token:${r}`,
      $i[r]
    ]), ["custom", "Custom"]];
    return p`<div class="ed-colour">${this.choice(t, i ? e ?? "" : "custom", o, (r) => s(r === "custom" ? "#ffffff" : r || void 0))}
      ${i ? g : p`<input type="color" aria-label=${this.t(t)} .value=${e ?? "#ffffff"}
        @change=${(r) => s(r.target.value)}>`}</div>`;
  }
  assetSelect(t, e, s, i) {
    const o = Object.values(this.cfg.assets).filter((r) => s.includes(r.kind));
    return this.choice(
      t,
      String(e ?? ""),
      [["", "None"], ...o.map((r) => [r.id, r.name])],
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
      const a = (c, l) => p`<button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: mi(this.elements, this.selected, c) })}>${this.t(l)}</button>`;
      return p`<h2 class="ed-h">${this.t("Several elements selected")}</h2>
        <div class="ed-add">${a("left", "Align left")}${a("center", "Align centre")}${a("right", "Align right")}
          ${a("top", "Align top")}${a("middle", "Align middle")}${a("bottom", "Align bottom")}</div>
        <div class="ed-add"><button class="btn btn-sm" @click=${() => this.duplicateSelected()}>${this.t("Duplicate")}</button>
          <button class="btn btn-sm btn-danger" @click=${() => this.removeSelected()}>${this.t("Delete")}</button></div>`;
    }
    const e = t[0], s = e.props ?? {}, i = e.style ?? {}, o = e.frame, r = (a) => (c) => this.patchSelected((l) => {
      l.frame = { ...l.frame, [a]: c ?? 0 };
    });
    return p`
      <h2 class="ed-h">${this.t(J[e.type] ?? e.type)}</h2>
      ${this.field("Name", p`<input .value=${e.name ?? ""} maxlength="100"
        @change=${(a) => this.patchSelected((c) => {
      c.name = a.target.value;
    })}>`)}
      <div class="ed-add">
        <button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: Vt(this.elements, e.id, 1) })}>${this.t("Bring forward")}</button>
        <button class="btn btn-sm" @click=${() => this.commit({ ...this.data, elements: Vt(this.elements, e.id, -1) })}>${this.t("Send backward")}</button>
        <button class="btn btn-sm" @click=${() => this.duplicateSelected()}>${this.t("Duplicate")}</button>
        <button class="btn btn-sm btn-danger" @click=${() => this.removeSelected()}>${this.t("Delete")}</button></div>
      <fieldset class="ed-group"><legend>${this.t("Position and size")}</legend><div class="ed-grid">
        ${this.num("X", o.x, r("x"))}${this.num("Y", o.y, r("y"))}
        ${this.num("Width", o.w, r("w"), { min: 0 })}${this.num("Height", o.h, r("h"), { min: 0 })}
        ${this.num("Rotation", o.rotate, r("rotate"), { min: -360, max: 360 })}</div>
        ${this.check("Hidden", e.hidden, (a) => this.patchSelected((c) => {
      c.hidden = a || void 0;
    }))}
        ${this.check("Locked", e.locked, (a) => this.patchSelected((c) => {
      c.locked = a || void 0;
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
    ], (a) => this.patchSelected((c) => {
      c.animation = { ...c.animation ?? {}, enter: a };
    }))}
        <div class="ed-grid">${this.num("Duration (ms)", e.animation?.duration, (a) => this.patchSelected((c) => {
      c.animation = { ...c.animation ?? {}, duration: a };
    }), { min: 0, max: 1e4, step: 50 })}
          ${this.num("Delay (ms)", e.animation?.delay, (a) => this.patchSelected((c) => {
      c.animation = { ...c.animation ?? {}, delay: a };
    }), { min: 0, max: 6e4, step: 50 })}</div></fieldset>
      ${this.field("Show only if", p`<input .value=${e.visible_if ?? ""} maxlength="300" placeholder="screen.zone"
        @change=${(a) => this.patchSelected((c) => {
      c.visible_if = a.target.value || void 0;
    })}>`)}`;
  }
  contentFields(t, e) {
    const s = (r, a, c = 3) => this.field(r, p`<textarea rows=${c}
      .value=${String(e[a] ?? "")} @change=${(l) => this.setProp(a, l.target.value)}></textarea>`), i = this.choice(
      "Fit mode",
      String(e.fit ?? ""),
      [["contain", "Contain"], ["cover", "Cover"], ["fill", "Stretch"]],
      (r) => this.setProp("fit", r)
    ), o = p`<p class="small muted">${this.t("Template variables: {{ event.name }}, {{ screen.name }}, {{ screen.zone }}, {{ now|time }}")}</p>`;
    switch (t) {
      case "text":
        return p`${s("Text", "text")}${o}${this.check("Shrink text to fit", e.autofit, (r) => this.setProp("autofit", r))}
          ${this.check("Ticker (scrolling)", e.marquee, (r) => this.setProp("marquee", r))}
          ${this.num("Maximum lines", e.clamp, (r) => this.setProp("clamp", r), { min: 0, max: 50, step: 1 })}`;
      case "richtext":
        return p`${s("Text", "text", 6)}${o}`;
      case "image":
        return p`${this.assetSelect("File", e.asset, ["image", "svg"], (r) => this.setProp("asset", r))}${i}
          <a class="small" href=${this.cfg.urls.assets} target="_blank" rel="noopener">${this.t("Upload files")}</a>`;
      case "slideshow": {
        const r = new Set(e.assets ?? []);
        return p`<p class="ed-label">${this.t("Images")}</p><div class="ed-list">${Object.values(this.cfg.assets).filter((a) => a.kind === "image" || a.kind === "svg").map((a) => this.check(a.name, r.has(a.id), (c) => {
          const l = new Set(r);
          c ? l.add(a.id) : l.delete(a.id), this.setProp("assets", [...l]);
        }))}</div>${this.num("Seconds per image", e.interval, (a) => this.setProp("interval", a), { min: 1, max: 3600 })}${i}`;
      }
      case "video":
        return p`${this.assetSelect("File", e.asset, ["video"], (r) => this.setProp("asset", r))}${i}
          ${this.check("Loop", e.loop, (r) => this.setProp("loop", r))}${this.check("Muted", e.muted, (r) => this.setProp("muted", r))}`;
      case "audio":
        return p`${this.assetSelect("File", e.asset, ["audio"], (r) => this.setProp("asset", r))}
          ${this.check("Loop", e.loop, (r) => this.setProp("loop", r))}`;
      case "shape":
        return this.choice(
          "Form",
          String(e.shape ?? "rect"),
          [["rect", "Rectangle"], ["ellipse", "Ellipse"], ["line", "Line"]],
          (r) => this.setProp("shape", r)
        );
      case "qr":
        return p`${s("Text", "text", 2)}${o}`;
      case "clock":
        return p`${this.choice(
          "Format",
          String(e.format ?? "HH:mm"),
          [["HH:mm", "HH:mm"], ["HH:mm:ss", "HH:mm:ss"], ["h:mm a", "h:mm a"]],
          (r) => this.setProp("format", r)
        )}
          ${this.field("Time zone (empty = event)", p`<input .value=${String(e.timezone ?? "")} placeholder="Europe/Berlin"
            @change=${(r) => this.setProp("timezone", r.target.value)}>`)}`;
      case "countdown":
        return p`${this.field("Target time", p`<input type="datetime-local" .value=${String(e.target ?? "").slice(0, 16)}
            @change=${(r) => this.setProp("target", r.target.value)}>`)}
          ${this.choice("Format", String(e.format ?? "auto"), [
          ["auto", "Automatic"],
          ["hms", "Hours:minutes:seconds"],
          ["ms", "Minutes:seconds"],
          ["days", "Days"]
        ], (r) => this.setProp("format", r))}
          ${s("Text when finished", "finished", 1)}`;
      case "date":
        return this.choice("Format", String(e.format ?? "long"), [
          ["long", "Long"],
          ["short", "Short"],
          ["weekday", "Weekday"],
          ["iso", "ISO"]
        ], (r) => this.setProp("format", r));
      case "code":
        return this.codeFields(e);
      case "pictogram":
        return p`${this.choice("Sign", String(e.code ?? "E002"), [
          ["E001", "E001 Emergency exit (left)"],
          ["E002", "E002 Emergency exit (right)"],
          ["E007", "E007 Assembly point"],
          ["E003", "E003 First aid"],
          ["W001", "W001 General warning"],
          ["arrow", "Direction arrow"]
        ], (r) => this.setProp("code", r))}
          ${e.code === "arrow" ? this.choice("Direction", String(e.direction ?? "auto"), [
          ["auto", "Automatic (the screen's way out)"],
          ["ahead", "Ahead"],
          ["ahead_right", "Ahead right"],
          ["right", "Right"],
          ["back_right", "Back right"],
          ["back", "Back"],
          ["back_left", "Back left"],
          ["left", "Left"],
          ["ahead_left", "Ahead left"]
        ], (r) => this.setProp("direction", r)) : g}`;
      case "data": {
        const r = this.cfg.choices?.dataWidgets ?? [];
        return p`${this.choice(
          "Widget",
          String(e.widget ?? ""),
          [
            ["", r.length ? "Choose…" : "No custom widgets yet (Data & widgets)"],
            ...r.map((a) => [a.value, a.label])
          ],
          (a) => this.setProp("widget", a)
        )}
          ${s("Heading (empty: the widget's)", "title", 1)}`;
      }
      case "program": {
        const r = this.cfg.choices?.programStages ?? [];
        return p`${this.choice("Show", String(e.view ?? "now_next"), [
          ["now_next", "Now and next"],
          ["day", "The day's sessions"],
          ["changes", "Live changes"]
        ], (a) => this.setProp("view", a))}
          ${e.view === "changes" ? g : this.choice(
          "Stage",
          String(e.stage ?? ""),
          [
            ["", "Automatic: the screen's room, else all stages"],
            ...r.map((a) => [a.value, a.label])
          ],
          (a) => this.setProp("stage", a)
        )}
          ${e.view === "now_next" || !e.view ? g : this.num("Rows", Number(e.count ?? 6), (a) => this.setProp(
          "count",
          Math.max(1, Math.min(20, Math.round(a ?? 6)))
        ), { min: 1, max: 20, step: 1 })}
          ${s("Heading", "title", 1)}`;
      }
      case "plugin":
        return this.pluginFields(e);
      case "progress":
        return p`<p class="small muted">${this.t("Counts down the time the slide stays on screen in a playlist. The editor loops over the layout's seconds on screen.")}</p>
          ${this.choice("Orientation", String(e.orientation ?? "horizontal"), [
          ["horizontal", "Horizontal"],
          ["vertical", "Vertical"]
        ], (r) => this.setProp("orientation", r))}
          ${this.choice(
          "Bar",
          String(e.mode ?? "shrink"),
          [["shrink", "Shrinks"], ["grow", "Grows"]],
          (r) => this.setProp("mode", r)
        )}
          ${this.check("Start from the other end", e.reverse, (r) => this.setProp("reverse", r || void 0))}
          ${this.choice("Without an end time", String(e.untimed ?? "full"), [
          ["full", "Show a full bar"],
          ["hide", "Hide"]
        ], (r) => this.setProp("untimed", r))}`;
      default:
        return p``;
    }
  }
  /** Plugin widget: the widget, then a form generated from its settings schema (string, number, boolean, enum). */
  pluginFields(t) {
    const e = this.cfg.choices?.pluginWidgets ?? [], s = e.find((a) => a.value === t.widget), i = t.settings ?? {}, o = (a, c) => {
      const l = { ...i, [a]: c };
      (c === void 0 || c === "") && delete l[a], this.setProp("settings", l);
    }, r = Object.entries(s?.schema?.properties ?? {}).slice(0, 50).map(([a, c]) => {
      const l = c.title ?? a, h = i[a] ?? c.default;
      let d;
      return c.enum ? d = this.choice(l, String(h ?? ""), [["", "Default"], ...c.enum.map((u) => [String(u), String(u)])], (u) => o(a, u ? c.enum?.find((m) => String(m) === u) : void 0)) : c.type === "boolean" ? d = this.check(l, !!h, (u) => o(a, u)) : c.type === "number" || c.type === "integer" ? d = this.num(l, h, (u) => o(a, u === void 0 ? void 0 : c.type === "integer" ? Math.round(u) : u), {
        min: c.minimum,
        max: c.maximum,
        step: c.type === "integer" ? 1 : void 0
      }) : d = this.field(l, p`<input .value=${String(h ?? "")} maxlength=${c.maxLength ?? 500}
          @change=${(u) => o(a, u.target.value)}>`), p`${d}${c.description ? p`<p class="small muted">${c.description}</p>` : g}`;
    });
    return p`${this.choice(
      "Widget",
      String(t.widget ?? ""),
      [
        ["", e.length ? "Choose…" : "No plugin widgets installed"],
        ...e.map((a) => [a.value, a.label])
      ],
      (a) => this.patchSelected((c) => {
        c.props = { ...c.props ?? {}, widget: a, settings: {} };
      })
    )}
      ${s?.description ? p`<p class="small muted">${s.description}</p>` : g}${r}`;
  }
  codeFields(t) {
    const e = this.cfg.canCode, s = (a, c, l) => this.field(a, p`<textarea class="ed-code" rows=${l}
      spellcheck="false" ?readonly=${!e} .value=${String(t[c] ?? "")}
      @change=${(h) => this.setProp(c, h.target.value)}></textarea>`), i = new Set(t.data ?? []), o = (a) => (c) => {
      const l = new Set(i);
      c ? l.add(a) : l.delete(a), this.setProp("data", ["event", "screen", "time", "assets"].filter((h) => l.has(h)));
    }, r = new Set(t.assets ?? []);
    return p`${e ? g : p`<p class="small muted">${this.t("Only people allowed to write code can change this element.")}</p>`}
      ${s("HTML", "html", 5)}${s("CSS", "css", 5)}${s("JavaScript", "js", 8)}
      <p class="small muted">${this.t("Code runs in a sandbox without network. Read data with evac.data and evac.onData(fn); evac.now() is the server time.")}</p>
      <fieldset class="ed-group" ?disabled=${!e}><legend>${this.t("Data for the code")}</legend>
        ${this.check("Event", i.has("event"), o("event"))}${this.check("Screen", i.has("screen"), o("screen"))}
        ${this.check("Time", i.has("time"), o("time"))}${this.check("Files", i.has("assets"), o("assets"))}
        ${i.has("assets") ? p`<div class="ed-list">${Object.values(this.cfg.assets).map((a) => this.check(
      a.name,
      r.has(a.id),
      (c) => {
        const l = new Set(r);
        c ? l.add(a.id) : l.delete(a.id), this.setProp("assets", [...l].slice(0, 20));
      }
    ))}</div>` : g}</fieldset>`;
  }
  layoutPanel() {
    const t = this.data, e = t.background ?? {}, s = (i, o) => {
      const r = { ...e, [i]: o };
      o || delete r[i], this.commit({ ...t, background: Object.keys(r).length ? r : void 0 });
    };
    return p`<h2 class="ed-h">${this.t("Layout")}</h2>
      <p class="small muted">${this.t("Select an element on the canvas or in the layers list.")}</p>
      <div class="ed-grid">
        ${this.num("Width", t.width, (i) => this.commit({ ...t, width: Math.max(64, Math.round(i ?? 1920)) }), { min: 64, max: 16384, step: 1 })}
        ${this.num("Height", t.height, (i) => this.commit({ ...t, height: Math.max(64, Math.round(i ?? 1080)) }), { min: 64, max: 16384, step: 1 })}</div>
      ${this.colour("Background", e.color, (i) => s("color", i))}
      ${this.assetSelect("Background image", e.asset, ["image", "svg"], (i) => s("asset", i || void 0))}
      ${this.num("Seconds on screen (playlists)", t.duration, (i) => this.commit({ ...t, duration: i }), { min: 1, max: 86400, step: 1 })}`;
  }
};
wt.properties = {
  data: { state: !0 },
  selected: { state: !0 },
  status: { state: !0 },
  zoom: { state: !0 },
  guides: { state: !0 },
  error: { state: !0 },
  findings: { state: !0 }
};
let pt = wt;
customElements.get("evac-layout-editor") || customElements.define("evac-layout-editor", pt);
export {
  pt as LayoutEditor
};
