import { expect, test } from "@playwright/test";

// T033/T052: smoke e2e covering the sync -> review -> apply flow (one of
// the two flows in the proof-of-value e2e budget, plan.md). The backend is
// mocked entirely at the network layer (`page.route`) rather than run for
// real: a real run needs a connected Spotify account and an indexed
// Collection (owner-supplied fixtures, quickstart.md), which T089
// explicitly defers to the owner. This spec instead proves the frontend's
// own wiring, which is what CI can verify without those fixtures.
//
// research.md R7 draws this exact line on purpose: "write-path integration
// tests against a fixture master.db copy" is the pytest layer's job
// (engine/tests/rb/test_writer_integration.py, T043/T045/T096, already
// exercising the real owner-supplied fixture end to end); "Playwright smoke
// e2e for the two core flows" is this file's job, and does not re-verify
// the real write mechanics -- only that the UI drives the apply endpoint
// correctly and renders whatever it returns.
test("pasting a playlist URL renders the match report", async ({ page }) => {
  await page.route("**/api/auth/spotify/status", (route) =>
    route.fulfill({
      json: { connected: true, display_name: "DJ Test", product: "premium" },
    }),
  );

  await page.route("**/api/sync/sessions", async (route) => {
    if (route.request().method() !== "POST") {
      return route.continue();
    }
    return route.fulfill({
      json: {
        id: 1,
        playlist_link_id: 1,
        spotify_snapshot_id: "snap-1",
        name: "Booking 2026",
        status: "ready",
        created_at: "2026-08-17T00:00:00",
        totals: { matched: 1, review: 0, missing: 1, rejected: 0, unmatchable: 0 },
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
        totals: { matched: 1, review: 0, missing: 1, rejected: 0, unmatchable: 0 },
        tracks: [
          {
            id: 1,
            position: 1,
            spotify_track_id: "sp1",
            isrc: "USRC17607839",
            artist: "Daft Punk",
            title: "One More Time",
            duration_ms: 210_000,
            status: "matched",
            rb_content_id: "rb1",
            match_score: 100,
            candidates: [],
            matched_at: "2026-08-17T00:00:00",
          },
          {
            id: 2,
            position: 2,
            spotify_track_id: "sp2",
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

  await page.goto("/");

  // T033 review finding: App.tsx renders PlaylistUrlForm unconditionally,
  // regardless of Spotify connection state -- there is no gate to prove the
  // "connected: true" mock above actually feeds into. Asserting the
  // connection banner itself at least confirms that mock is genuinely
  // consumed (spec.md US1 acceptance scenario 1's "connected Spotify
  // account" precondition renders correctly), even though the sync flow
  // below would run identically without it.
  await expect(page.getByText("Verbonden als")).toBeVisible();
  await expect(page.getByText("DJ Test")).toBeVisible();

  await page
    .getByLabel("Spotify-afspeellijst URL")
    .fill("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M");
  await page.getByRole("button", { name: "Synchroniseren" }).click();

  await expect(page.getByText("Gematcht: 1")).toBeVisible();
  await expect(page.getByText("Ontbreekt: 1")).toBeVisible();
  await expect(page.getByText("Daft Punk")).toBeVisible();
  await expect(page.getByText("Nobody At All")).toBeVisible();
});

test("applying a synced session confirms, writes, and shows the backup result", async ({
  page,
}) => {
  await page.route("**/api/auth/spotify/status", (route) =>
    route.fulfill({
      json: { connected: true, display_name: "DJ Test", product: "premium" },
    }),
  );

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
        totals: { matched: 1, review: 0, missing: 0, rejected: 0, unmatchable: 0 },
      },
    });
  });

  const sessionDetail = {
    id: 1,
    playlist_link_id: 1,
    spotify_snapshot_id: "snap-1",
    name: "Booking 2026",
    status: "ready",
    created_at: "2026-08-17T00:00:00",
    totals: { matched: 1, review: 0, missing: 0, rejected: 0, unmatchable: 0 },
    tracks: [
      {
        id: 1,
        position: 1,
        spotify_track_id: "sp1",
        isrc: "USRC17607839",
        artist: "Daft Punk",
        title: "One More Time",
        duration_ms: 210_000,
        status: "matched",
        rb_content_id: "rb1",
        match_score: 100,
        candidates: [],
        matched_at: "2026-08-17T00:00:00",
      },
    ],
  };
  await page.route("**/api/sync/sessions/1", (route) => route.fulfill({ json: sessionDetail }));

  await page.route("**/api/sync/sessions/1/apply", async (route) => {
    expect(route.request().method()).toBe("POST");
    return route.fulfill({
      json: {
        rb_playlist_id: "rb-playlist-1",
        created: true,
        tracks_added: 1,
        tracks_already_present: 0,
        backup_path: "/data/backups/master-20260817T120000000000Z.db.zip",
        readback_ok: true,
      },
    });
  });

  await page.goto("/");
  await page
    .getByLabel("Spotify-afspeellijst URL")
    .fill("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M");
  await page.getByRole("button", { name: "Synchroniseren" }).click();
  await expect(page.getByText("Gematcht: 1")).toBeVisible();

  await page.getByRole("button", { name: "Toepassen op Rekordbox" }).click();
  await expect(page.getByLabel("Playlistnaam")).toHaveValue("Booking 2026");
  await page.getByRole("button", { name: "Bevestig toepassen" }).click();

  await expect(page.getByText(/Toegepast: 1 nieuw, 0 al aanwezig/)).toBeVisible();
  await expect(page.getByText(/master-20260817T120000000000Z\.db\.zip/)).toBeVisible();
});
