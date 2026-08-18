// T008: the OpenAPI client generation pipeline exists with a placeholder
// client until the backend's real schema exists (T015 GET /api/health).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { apiClient } from "../src/api/client";

const WEB_ROOT = resolve(__dirname, "..");

describe("OpenAPI client generation", () => {
  it("declares openapi-typescript and openapi-fetch as dependencies", () => {
    const pkg = JSON.parse(readFileSync(resolve(WEB_ROOT, "package.json"), "utf-8"));
    const allDeps = { ...pkg.dependencies, ...pkg.devDependencies };
    expect(allDeps["openapi-typescript"]).toBeDefined();
    expect(allDeps["openapi-fetch"]).toBeDefined();
  });

  it("declares an openapi regeneration script that runs offline and formats its output", () => {
    // Phase 7 review finding: the script used to scrape a live backend on
    // 127.0.0.1:8787 and emit output that failed format:check, so the next
    // regeneration left the tree dirty. It now dumps the schema straight from
    // the app factory and pipes the result through prettier, which makes
    // regeneration deterministic and needs no running server.
    const pkg = JSON.parse(readFileSync(resolve(WEB_ROOT, "package.json"), "utf-8"));
    expect(pkg.scripts.openapi).toMatch(/create_app\(\)\.openapi\(\)/);
    expect(pkg.scripts.openapi).not.toMatch(/127\.0\.0\.1:8787/);
    expect(pkg.scripts.openapi).toMatch(/prettier --write/);
    expect(pkg.scripts.openapi).toMatch(/generated\/schema\.d\.ts/);
  });

  it("exports a typed placeholder client that speaks openapi-fetch's contract", () => {
    expect(typeof apiClient.GET).toBe("function");
    expect(typeof apiClient.POST).toBe("function");
  });
});
