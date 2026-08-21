import { defineConfig, devices } from "@playwright/test";

// T033/T095: the "proof-of-value e2e budget" (plan.md) -- Playwright smoke
// flows guard the two core user journeys in CI, distinct from Vitest's
// component-level tests. Runs against the Vite dev server only (`pnpm dev`,
// no backend) because every spec mocks the API at the network layer
// (`page.route`) -- real Rekordbox/Spotify fixtures are owner-supplied and
// explicitly deferred to T089 ("blocked on the owner, not on this
// decomposition"), so this suite must not depend on them to run in CI.
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  webServer: {
    command: "pnpm dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
