// SPDX-License-Identifier: AGPL-3.0-or-later
// QR code as inline SVG (built with DOM APIs: the strict CSP allows no inline styles or markup injection).
import { encode } from "uqr";

const SVG = "http://www.w3.org/2000/svg";

export function qrSvg(text: string, doc: Document = document): SVGSVGElement {
  const { data, size } = encode(text, { ecc: "M", border: 2 });
  const svg = doc.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("shape-rendering", "crispEdges");
  svg.setAttribute("class", "qr");
  const bg = doc.createElementNS(SVG, "rect");
  bg.setAttribute("width", String(size));
  bg.setAttribute("height", String(size));
  bg.setAttribute("fill", "#fff");
  svg.appendChild(bg);
  let d = "";
  data.forEach((row, y) => row.forEach((on, x) => { if (on) d += `M${x} ${y}h1v1h-1z`; }));
  const path = doc.createElementNS(SVG, "path");
  path.setAttribute("d", d);
  path.setAttribute("fill", "#000");
  svg.appendChild(path);
  return svg;
}
