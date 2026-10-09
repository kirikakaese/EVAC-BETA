// SPDX-License-Identifier: AGPL-3.0-or-later
// Three bundles with stable names (Django adds ?v=<hash>): TARGET=player | sw | editor.
//   player -> static/player/player.js + player.css      (screens)
//   sw     -> static/player/sw.js                       (service worker, served at /player/sw.js)
//   editor -> static/editor/editor.js + editor.css      (layout editor island in the portal)
import { defineConfig } from "vite";

const TARGETS = {
  player: { entry: "src/player/main.ts", out: "../static/player", file: "player.js", css: "player" },
  sw: { entry: "src/player/sw.ts", out: "../static/player", file: "sw.js", css: "sw" },
  editor: { entry: "src/editor/main.ts", out: "../static/editor", file: "editor.js", css: "editor" },
} as const;
declare const process: { env: Record<string, string | undefined> };
const target = TARGETS[(process.env.TARGET ?? "player") as keyof typeof TARGETS];

export default defineConfig({
  build: {
    outDir: target.out,
    emptyOutDir: false,
    target: "es2020",
    sourcemap: false,
    lib: { entry: target.entry, formats: ["es"], fileName: () => target.file, cssFileName: target.css },
    rollupOptions: { output: { assetFileNames: "[name][extname]" } },
  },
  test: { environment: "jsdom" },
} as never);
