// T017: web/src/theme/index.css wires the delivered design tokens as the
// Tailwind v4 @theme, with the proprietary SpotifyMixUI fonts substituted
// by self-hosted Inter under the original token names (project rule 5).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const WEB_ROOT = resolve(__dirname, "..");
const THEME_CSS = readFileSync(resolve(WEB_ROOT, "src/theme/index.css"), "utf-8");

describe("theme wiring", () => {
  it("imports tailwindcss", () => {
    expect(THEME_CSS).toMatch(/@import\s+["']tailwindcss["']/);
  });

  it("imports the delivered design tokens as the @theme source", () => {
    expect(THEME_CSS).toMatch(/@import\s+["'].*design-input\/theme\.css["']/);
  });

  it("declares tailwindcss and the vite plugin as dependencies", () => {
    const pkg = JSON.parse(readFileSync(resolve(WEB_ROOT, "package.json"), "utf-8"));
    expect(pkg.dependencies.tailwindcss).toBeDefined();
    expect(pkg.dependencies["@tailwindcss/vite"]).toBeDefined();
  });

  it("registers the tailwindcss vite plugin", () => {
    const viteConfig = readFileSync(resolve(WEB_ROOT, "vite.config.ts"), "utf-8");
    expect(viteConfig).toMatch(/@tailwindcss\/vite/);
    expect(viteConfig).toMatch(/tailwindcss\(\)/);
  });

  it("never references SpotifyMixUI font files, only Inter's", () => {
    // The proprietary font must never ship (project rule 5): no file
    // extension referencing a SpotifyMixUI-named asset anywhere.
    expect(THEME_CSS).not.toMatch(/spotifymixui[^"']*\.(woff2?|ttf|otf)/i);
    expect(THEME_CSS).toMatch(/@fontsource\/inter/);
  });

  it("aliases the SpotifyMixUI and SpotifyMixUITitle token names to Inter", () => {
    // theme.css's --font-spotifymixui/--font-spotifymixuititle tokens name
    // these families; this file must make those names resolve to real
    // (Inter) glyph data via @font-face, not leave them dangling.
    const familyBlocks = [...THEME_CSS.matchAll(/@font-face\s*{[^}]*}/g)].map((m) => m[0]);
    const spotifyMixUiBlocks = familyBlocks.filter((b) =>
      /font-family:\s*["']SpotifyMixUI["']/.test(b),
    );
    const spotifyMixUiTitleBlocks = familyBlocks.filter((b) =>
      /font-family:\s*["']SpotifyMixUITitle["']/.test(b),
    );
    expect(spotifyMixUiBlocks.length).toBeGreaterThan(0);
    expect(spotifyMixUiTitleBlocks.length).toBeGreaterThan(0);
    for (const block of [...spotifyMixUiBlocks, ...spotifyMixUiTitleBlocks]) {
      expect(block).toMatch(/@fontsource\/inter/);
    }
  });

  it("declares SpotifyMixUITitle at weight 700, matching DESIGN.md", () => {
    const familyBlocks = [...THEME_CSS.matchAll(/@font-face\s*{[^}]*}/g)].map((m) => m[0]);
    const titleBlocks = familyBlocks.filter((b) =>
      /font-family:\s*["']SpotifyMixUITitle["']/.test(b),
    );
    expect(titleBlocks.every((b) => /font-weight:\s*700/.test(b))).toBe(true);
  });
});
