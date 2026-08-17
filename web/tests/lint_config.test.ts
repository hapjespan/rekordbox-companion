// T004: TypeScript linting/formatting configuration exists and passes clean.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(__dirname, "..");

describe("web lint/format configuration", () => {
  it("declares an eslint flat config file", () => {
    expect(existsSync(resolve(WEB_ROOT, "eslint.config.js"))).toBe(true);
  });

  it("declares a prettier config file", () => {
    expect(existsSync(resolve(WEB_ROOT, ".prettierrc"))).toBe(true);
    JSON.parse(readFileSync(resolve(WEB_ROOT, ".prettierrc"), "utf-8"));
  });

  it("passes the lint script on the current source tree", () => {
    expect(() =>
      execFileSync("pnpm", ["run", "lint"], { cwd: WEB_ROOT, stdio: "pipe" }),
    ).not.toThrow();
  });

  it("passes the format:check script on the current source tree", () => {
    expect(() =>
      execFileSync("pnpm", ["run", "format:check"], { cwd: WEB_ROOT, stdio: "pipe" }),
    ).not.toThrow();
  });
});
