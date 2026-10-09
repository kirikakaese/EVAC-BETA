// SPDX-License-Identifier: AGPL-3.0-or-later
// Post-build: licence banners on the bundles and size budgets (gzipped): player < 300 kB (brief), editor < 500 kB.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const BANNER = (what) => `// SPDX-License-Identifier: AGPL-3.0-or-later\n// EVAC ${what}, built from frontend/src with \`npm run build\` - do not edit.\n`;
const CSS_BANNER = (what) => `/* SPDX-License-Identifier: AGPL-3.0-or-later */\n/* EVAC ${what}, built from frontend/src with \`npm run build\` - do not edit. */\n`;
const BUNDLES = [
  { dir: "player", budget: 300, banners: {
    "player.js": BANNER("player") + "// Includes uqr (MIT, https://github.com/unjs/uqr).\n",
    "sw.js": BANNER("player service worker"), "player.css": CSS_BANNER("player") } },
  { dir: "editor", budget: 500, banners: {
    "editor.js": BANNER("layout editor") + "// Includes Lit (BSD-3-Clause, https://lit.dev) and uqr (MIT).\n",
    "editor.css": CSS_BANNER("layout editor") } },
];
let failed = false;
for (const b of BUNDLES) {
  const dir = new URL(`../../static/${b.dir}/`, import.meta.url);
  let total = 0;
  for (const name of readdirSync(dir)) {
    if (!/\.(js|css)$/.test(name)) continue;
    const file = new URL(name, dir);
    let text = readFileSync(file, "utf8");
    const banner = b.banners[name];
    if (banner && !text.startsWith(banner)) {
      text = banner + text;
      writeFileSync(file, text);
    }
    const size = gzipSync(text).length;
    total += size;
    console.log(`${(b.dir + "/" + name).padEnd(22)} ${(size / 1024).toFixed(1)} kB gz`);
  }
  console.log(`${(b.dir + " total").padEnd(22)} ${(total / 1024).toFixed(1)} kB gz (budget ${b.budget} kB)`);
  if (total > b.budget * 1024) {
    console.error(`${b.dir} bundle over budget`);
    failed = true;
  }
}
if (failed) process.exit(1);
