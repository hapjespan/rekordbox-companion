import { expect, test } from "@playwright/test";

// T107 (gate-review finding: this flow was referenced by T095 but no task
// ever authored it): the second of the two proof-of-value e2e flows
// (missing -> link, plan.md). Same network-mocking convention as
// sync-review-apply.spec.ts (T033/T052) -- see that file's own comment for
// why real fixtures aren't needed here either.
test("a completed sync with Missing Tracks shows the queue, and a Store Link resolves and copies", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);

  await page.route("**/api/auth/spotify/status", (route) =>
    route.fulfill({
      json: { connected: true, display_name: "DJ Test", product: "premium" },
    }),
  );
  // The shell's top bar reads the Rekordbox version from health and its
  // Collectie-scan card reads the collection total; neither is what this spec
  // is about, so both answer with a fixture. EnrichmentPanel (T077) and
  // BookingWorkspace (T088) are equally beside the point here.
  await page.route("**/api/health", (route) =>
    route.fulfill({
      json: {
        status: "ok",
        rekordbox_version: "7.2.17",
        version_pin_ok: true,
        db_path: "/fixtures/master.db",
        rekordbox_running: false,
        ffmpeg_ok: true,
      },
    }),
  );
  await page.route("**/api/collection?*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/enrichment/status", (route) =>
    route.fulfill({ json: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0 } }),
  );
  await page.route("**/api/enrichment/unenriched*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/structures", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profiles", (route) => route.fulfill({ json: [] }));

  await page.route("**/api/sync/sessions", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      json: {
        id: 1,
        playlist_link_id: 1,
        spotify_snapshot_id: "snap-1",
        name: "Booking 2026",
        status: "ready",
        created_at: "2026-08-17T00:00:00",
        totals: { matched: 0, review: 0, missing: 1, rejected: 0, unmatchable: 0 },
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
        created_at: "2026-08-17T00:00:00",
        totals: { matched: 0, review: 0, missing: 1, rejected: 0, unmatchable: 0 },
        tracks: [
          {
            id: 1,
            position: 1,
            spotify_track_id: "sp1",
            isrc: null,
            artist: "Nobody At All",
            title: "Nothing Similar",
            duration_ms: 180_000,
            status: "missing",
            rb_content_id: null,
            match_score: 40,
            candidates: [],
            matched_at: null,
          },
        ],
      },
    }),
  );

  let missingTrackStatus = "open";
  await page.route("**/api/missing?status=open", (route) => {
    if (missingTrackStatus !== "open") {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({
      json: [
        {
          id: 1,
          artist: "Nobody At All",
          title: "Nothing Similar",
          status: "open",
          itunes_url_auto: "https://music.apple.com/nl/album/nothing-similar/1",
          itunes_url_chosen: null,
          effective_url: "https://music.apple.com/nl/album/nothing-similar/1",
          no_link_found: false,
        },
      ],
    });
  });

  await page.route("**/api/missing/1/status", async (route) => {
    const body = route.request().postDataJSON() as { status: string };
    missingTrackStatus = body.status;
    return route.fulfill({ json: {} });
  });

  await page.goto("/");

  const nav = page.getByRole("navigation");

  // Drive the actual sync first, per the task's named flow. It lives on the
  // shell's default view (Match-overzicht), which is where the app opens.
  await page
    .getByLabel("Spotify-afspeellijst URL")
    .fill("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M");
  await page.getByRole("button", { name: "Synchroniseren" }).click();
  await expect(page.getByText("Ontbreekt: 1")).toBeVisible();

  // The queue is independent of the sync flow (GET /api/missing has no
  // session id), so it shows the seeded Missing Track as soon as its view is
  // opened -- proving the "a completed sync with Missing Tracks shows the
  // queue" scenario doesn't depend on the sync above having run.
  await nav.getByRole("button", { name: /Koop-wachtrij/ }).click();
  await expect(page.getByText("Nobody At All – Nothing Similar")).toBeVisible();
  await expect(page.getByText("Status: Open")).toBeVisible();

  const copyButton = page.getByRole("button", { name: "Kopieer link" });
  await copyButton.click();
  await expect(page.getByRole("button", { name: "Gekopieerd" })).toBeVisible();
  const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboardText).toBe("https://music.apple.com/nl/album/nothing-similar/1");

  // Scoped to the row: the status filter group added in the phase 7 review has
  // a "Genegeerd" button of its own, so the bare role query is ambiguous now.
  await page.getByTestId("missing-track-row").getByRole("button", { name: "Genegeerd" }).click();
  await expect(page.getByText("Geen openstaande ontbrekende nummers.")).toBeVisible();
});
