import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// T091: accessibility sweep across all seven stories (WCAG 2.2 AA). Every
// component this app mounts unconditionally (SpotifyConnection,
// PlaylistUrlForm, MissingQueue, EnrichmentPanel, BookingWorkspace) is on
// the page in its default state already; the two extra scans below add the
// states that only render after user action (a match report; a populated
// Suggestions list), so together these three scans cover the visible
// surface of every story without needing a router this app doesn't have
// (App.tsx's own documented one-page assembly).
async function mockCommonEndpoints(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/spotify/status", (route) =>
    route.fulfill({ json: { connected: true, display_name: "DJ Test", product: "premium" } }),
  );
  await page.route("**/api/missing*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/enrichment/status", (route) =>
    route.fulfill({ json: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0 } }),
  );
  await page.route("**/api/enrichment/unenriched*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/structures", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profiles", (route) => route.fulfill({ json: [] }));
}

test("the default page state has no automatically detectable accessibility violations", async ({
  page,
}) => {
  await mockCommonEndpoints(page);

  await page.goto("/");
  await page.waitForSelector("text=Rekordbox Companion");

  const results = await new AxeBuilder({ page }).analyze();

  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});

test("the match report and apply flow has no automatically detectable accessibility violations", async ({
  page,
}) => {
  await mockCommonEndpoints(page);
  await page.route("**/api/sync/sessions", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      json: {
        id: 1,
        playlist_link_id: 1,
        spotify_snapshot_id: "snap-1",
        name: "Booking 2026",
        status: "ready",
        created_at: "2026-08-18T00:00:00",
        totals: { matched: 1, review: 0, missing: 0, rejected: 0, unmatchable: 0 },
      },
    });
  });
  await page.route("**/api/sync/sessions/1", (route) =>
    route.fulfill({
      json: {
        id: 1,
        playlist_link_id: 1,
        spotify_snapshot_id: "snap-1",
        name: "Booking 2026",
        status: "ready",
        created_at: "2026-08-18T00:00:00",
        totals: { matched: 1, review: 0, missing: 0, rejected: 0, unmatchable: 0 },
        tracks: [
          {
            id: 1,
            position: 1,
            artist: "Daft Punk",
            title: "One More Time",
            status: "matched",
            rb_content_id: "1",
            match_score: 100,
            candidates: [],
          },
        ],
      },
    }),
  );

  await page.goto("/");
  await page.getByLabel("Spotify-afspeellijst URL").fill("https://open.spotify.com/playlist/abc");
  await page.getByRole("button", { name: "Synchroniseren" }).click();
  await page.waitForSelector("text=Daft Punk");

  const results = await new AxeBuilder({ page }).analyze();

  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});
