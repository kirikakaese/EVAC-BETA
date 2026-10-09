// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it, vi } from "vitest";

import { codeDocument, pageNonce, themeVariables } from "../src/renderer/code";
import { renderLayout } from "../src/renderer/render";
import type { LayoutData, RenderContext } from "../src/renderer/types";

describe("code mode", () => {
  it("builds a frame document with a strict policy and nonce'd scripts", () => {
    const doc = codeDocument({ html: "<p>Hi</p>", css: "p{color:red}</style><script>alert(1)</script>",
                               js: "evac.log('x');</script><script>alert(2)</script>" }, "N0nce", "https://evac.test");
    expect(doc).toContain(`content="default-src 'none'; script-src 'nonce-N0nce'; style-src 'nonce-N0nce'; `
                          + "img-src data: blob: https://evac.test; media-src data: blob: https://evac.test; "
                          + "font-src data: https://evac.test; connect-src 'none'; form-action 'none'; "
                          + "base-uri 'none'; frame-src 'none'; worker-src 'none'\"");
    // breaking out of the style or script element is neutralised (and an injected script has no nonce)
    expect(doc).not.toContain("</style><script>alert(1)");
    expect(doc).not.toContain("</script><script>alert(2)");
    expect(doc).toContain("<\\/style><script>alert(1)");
    expect(doc.match(/<script nonce="N0nce">/g)?.length).toBe(2);
    expect(doc).toContain("<body><p>Hi</p>");
    // no js: only the bootstrap script
    expect(codeDocument({ html: "x" }, "n", "").match(/<script /g)?.length).toBe(1);
    expect(codeDocument({}, 'a"b', "")).toContain('nonce="a&quot;b"');
  });

  it("finds the page nonce and copies theme variables", () => {
    const s = document.createElement("script");
    s.setAttribute("nonce", "abc");
    document.head.appendChild(s);
    expect(pageNonce()).toBe("abc");
    s.remove();
    expect(pageNonce()).toBe("");
    expect(themeVariables(document.body)).toBe("");
  });

  it("renders a sandboxed frame and answers only its own frame", () => {
    const data: LayoutData = { format: 1, width: 1920, height: 1080, elements: [
      { id: "c", type: "code", frame: { x: 0, y: 0, w: 50, h: 50 },
        props: { html: "<b>x</b>", js: "1", data: ["event", "time"] } }] };
    const ctx: RenderContext = { vars: { event: { name: "Demo" }, screen: { name: "S" } }, now: () => 1000,
                                 assets: {}, fonts: {}, nonce: "n1", onError: vi.fn() };
    const host = document.createElement("div");
    document.body.appendChild(host);
    renderLayout(host, data, ctx);
    const frame = host.querySelector("iframe") as HTMLIFrameElement;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame.srcdoc).toContain("<b>x</b>");
    // a message from another window is ignored; an error from the frame is reported
    window.dispatchEvent(new MessageEvent("message", { data: { type: "evac:error", message: "boom" }, source: window }));
    expect(ctx.onError).not.toHaveBeenCalled();
    window.dispatchEvent(new MessageEvent("message", { data: { type: "evac:error", message: "boom" },
                                                       source: frame.contentWindow }));
    expect(ctx.onError).toHaveBeenCalledTimes(1);
    // without a nonce the element is not rendered (placeholder in the editor only)
    const host2 = document.createElement("div");
    renderLayout(host2, data, { ...ctx, nonce: "" });
    expect(host2.querySelector("iframe")).toBeNull();
  });
});
