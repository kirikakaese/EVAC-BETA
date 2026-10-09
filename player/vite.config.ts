// SPDX-License-Identifier: AGPL-3.0-or-later
// Player bundle: one ES module + one stylesheet with stable names in static/player/ (Django adds ?v=<hash>).
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "../static/player",
    emptyOutDir: false,
    target: "es2020",
    sourcemap: false,
    lib: { entry: "src/main.ts", formats: ["es"], fileName: () => "player.js", cssFileName: "player" },
    rollupOptions: { output: { assetFileNames: "[name][extname]" } },
  },
  test: { environment: "jsdom" },
} as never);
