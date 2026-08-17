import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    // Dev-only: routes the SPA's relative /api calls to the real backend
    // (127.0.0.1:8787) as same-origin, avoiding the need for CORS headers
    // FastAPI doesn't set (production doesn't need this -- the built SPA is
    // served by the same FastAPI app, already same-origin).
    proxy: {
      "/api": "http://127.0.0.1:8787",
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./tests/setup.ts"],
    // T033: tests/e2e/ holds Playwright specs (run via `pnpm test:e2e`,
    // not Vitest) -- without this exclusion, vitest's default glob also
    // picks up *.spec.ts under tests/ and fails trying to collect them.
    exclude: ["node_modules/**", "tests/e2e/**"],
  },
});
