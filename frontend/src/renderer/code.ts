// SPDX-License-Identifier: AGPL-3.0-or-later
// Code mode (ADR-0018): a layout element with its own HTML, CSS and JavaScript runs in an iframe with
// sandbox="allow-scripts" (opaque origin: no access to the page, its storage or cookies) built from srcdoc, so it
// works offline. The frame inherits the page's CSP (scripts need the page nonce) and adds a stricter one:
// no network at all, media only from EVAC itself. Data reaches it only through postMessage, and only the kinds
// the element lists in "data" (event, screen, time, assets).

export interface CodeProps { html?: string; css?: string; js?: string; data?: string[]; assets?: string[] }

const BOOTSTRAP = `(() => {
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

function attr(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

/** The frame document. ``nonce`` is the page's CSP nonce, ``origin`` the EVAC origin (media may load from it). */
export function codeDocument(props: CodeProps, nonce: string, origin: string, themeCss = ""): string {
  const n = attr(nonce);
  const src = origin ? ` ${origin}` : "";
  const csp = [
    "default-src 'none'", `script-src 'nonce-${nonce}'`, `style-src 'nonce-${nonce}'`,
    `img-src data: blob:${src}`, `media-src data: blob:${src}`, `font-src data:${src}`,
    "connect-src 'none'", "form-action 'none'", "base-uri 'none'", "frame-src 'none'", "worker-src 'none'",
  ].join("; ");
  const css = String(props.css ?? "").replace(/<\/style/gi, "<\\/style");
  const js = String(props.js ?? "").replace(/<\/script/gi, "<\\/script");
  return `<!doctype html><html><head><meta charset="utf-8">`
    + `<meta http-equiv="Content-Security-Policy" content="${attr(csp)}">`
    + `<style nonce="${n}">html,body{margin:0;height:100%;overflow:hidden;background:transparent;`
    + `color:var(--evac-color-text,#fff);font-family:var(--evac-font-body,system-ui,sans-serif)}${themeCss}</style>`
    + `<style nonce="${n}">${css}</style>`
    + `<script nonce="${n}">${BOOTSTRAP}</script></head><body>${String(props.html ?? "")}`
    + (js.trim() ? `<script nonce="${n}">${js}</script>` : "") + `</body></html>`;
}

/** ``:root{--evac-…}`` with the theme variables that apply to ``el`` (the frame cannot see the page's CSS). */
export function themeVariables(el: Element): string {
  const out: string[] = [];
  try {
    const cs = getComputedStyle(el);
    for (let i = 0; i < cs.length; i++) {
      const name = cs[i];
      if (name.startsWith("--evac-")) {
        const value = cs.getPropertyValue(name).trim().replace(/[<>{};]/g, "");
        if (value) out.push(`${name}:${value}`);
      }
    }
  } catch { /* no layout engine (tests) */ }
  return out.length ? `:root{${out.join(";")}}` : "";
}

/** The page's CSP nonce (the module script that loaded us carries it). */
export function pageNonce(doc: Document = document): string {
  const s = doc.querySelector<HTMLScriptElement>("script[nonce]");
  return s?.nonce || s?.getAttribute("nonce") || "";
}
