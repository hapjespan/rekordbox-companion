// T002: the web/ Vite + React + TypeScript skeleton exists and is wired to
// the delivered design tokens.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";

const WEB_ROOT = resolve(__dirname, "..");

describe("web project skeleton", () => {
  let pkg: Record<string, unknown>;

  beforeAll(() => {
    pkg = JSON.parse(readFileSync(resolve(WEB_ROOT, "package.json"), "utf-8"));
  });

  it("declares pnpm as the package manager", () => {
    expect(pkg.packageManager).toMatch(/^pnpm@/);
  });

  it("declares React 18, Vite and TypeScript as dependencies", () => {
    const allDeps = {
      ...(pkg.dependencies as object),
      ...(pkg.devDependencies as object),
    } as Record<string, string>;
    expect(allDeps.react).toMatch(/^\^?18\./);
    expect(allDeps["react-dom"]).toMatch(/^\^?18\./);
    expect(allDeps.vite).toBeDefined();
    expect(allDeps.typescript).toBeDefined();
  });

  it("wires the app entrypoint to the theme (T017 wires theme.css itself)", () => {
    const main = readFileSync(resolve(WEB_ROOT, "src/main.tsx"), "utf-8");
    expect(main).toMatch(/theme\/index\.css/);
  });
});
