// Runs before every test file. `globals: false` (vite.config.ts) means
// vitest never registers an implicit afterEach, so without this,
// @testing-library/react's rendered DOM from one test would still be
// mounted when the next test in the same file runs -- needed the moment
// the repo's first component-rendering test (MatchReport.test.tsx, T023)
// got a real component to render against (T032 finding).
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
