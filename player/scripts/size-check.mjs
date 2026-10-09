// SPDX-License-Identifier: AGPL-3.0-or-later
// Post-build: put the licence banner on the bundles and fail when the gzipped player exceeds the budget from
// the brief (< 300 kB).
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const BUDGET = 300 * 1024;
const BANNER = {
  "player.js": "// SPDX-License-Identifier: AGPL-3.0-or-later\n// EVAC player, built from player/src with `npm run build` - do not edit.\n// Includes uqr (MIT, https://github.com/unjs/uqr).\n",
  "sw.js": "// SPDX-License-Identifier: AGPL-3.0-or-later\n// EVAC player service worker, built from player/src with `npm run build` - do not edit.\n",
  "player.css": "/* SPDX-License-Identifier: AGPL-3.0-or-later */\n/* EVAC player, built from player/src with `npm run build` - do not edit. */\n",
};
const dir = new URL("../../static/player/", import.meta.url);
let total = 0;
for (const name of readdirSync(dir)) {
  if (!/\.(js|css)$/.test(name)) continue;
  const file = new URL(name, dir);
  let text = readFileSync(file, "utf8");
  if (BANNER[name] && !text.startsWith(BANNER[name])) {
    text = BANNER[name] + text;
    writeFileSync(file, text);
  }
  const size = gzipSync(text).length;
  total += size;
  console.log(`${name.padEnd(16)} ${(size / 1024).toFixed(1)} kB gz`);
}
console.log(`total            ${(total / 1024).toFixed(1)} kB gz (budget ${BUDGET / 1024} kB)`);
if (total > BUDGET) {
  console.error("player bundle over budget");
  process.exit(1);
}
