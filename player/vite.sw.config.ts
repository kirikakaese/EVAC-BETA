// SPDX-License-Identifier: AGPL-3.0-or-later
// Service worker bundle (served by Django at /player/sw.js so that its scope is /player/).
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "../static/player",
    emptyOutDir: false,
    target: "es2020",
    sourcemap: false,
    lib: { entry: "src/sw.ts", formats: ["es"], fileName: () => "sw.js" },
  },
});
