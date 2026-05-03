import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    globals: true
  },
  resolve: {
    alias: [
      { find: "@prompt-egress-guard/core/browser", replacement: path.resolve(__dirname, "packages/core/src/browser.ts") },
      { find: "@prompt-egress-guard/core", replacement: path.resolve(__dirname, "packages/core/src/index.ts") },
      { find: "@prompt-egress-guard/extension", replacement: path.resolve(__dirname, "packages/extension/src/index.ts") }
    ]
  }
});
