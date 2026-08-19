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
  // The shell's top bar reads the Rekordbox version from health, and its
  // sidebar counter and Collectie-scan card read the missing queue and the
  // collection; this spec isn't about any of them, so they answer empty.
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
  await page.route("**/api/missing*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/enrichment/status", (route) =>
    route.fulfill({ json: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0 } }),
  );
  await page.route("**/api/enrichment/unenriched*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/structures", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profiles", (route) => route.fulfill({ json: [] }));
  // The sidebar's two playlist sources (GET /api/spotify/playlists and the
  // Rekordbox tree of GET /api/playlists): not what this spec is about, so
  // both answer empty rather than reaching a real backend.
  await page.route("**/api/spotify/playlists", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/playlists", (route) => route.fulfill({ json: [] }));

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
  // Scoped to the main pane: the shell's top bar shows the same display name
  // ("Spotify · DJ Test"), which it reads from this very status call, so an
  // unscoped text query would now match two places. Both are asserted.
  const main = page.getByRole("main");
  await expect(main.getByText("Verbonden als")).toBeVisible();
  await expect(main.getByText("DJ Test")).toBeVisible();
  await expect(page.getByRole("banner").getByText("Spotify · DJ Test")).toBeVisible();

  await page
    .getByLabel("Spotify-afspeellijst URL")
    .fill("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M");
  await page.getByRole("button", { name: "Synchroniseren" }).click();

  await expect(page.getByText("Gematcht: 1")).toBeVisible();
  await expect(page.getByText("Ontbreekt: 1")).toBeVisible();
  await expect(page.getByText("Daft Punk")).toBeVisible();
  await expect(page.getByText("Nobody At All")).toBeVisible();

  // The delivered design's groups (HANDOFF.md, "1. Match-overzicht"): the
  // missing track sits in its own group, the matched one in the collection
  // group, and the filter chips above them really do filter -- which is the
  // one claim no component test can make, since the two groups come from two
  // different feature components.
  await expect(page.getByRole("heading", { name: "Ontbreekt in Rekordbox" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "In collectie" })).toBeVisible();

  const missingChip = page.getByRole("button", { name: "Ontbreekt" });
  await expect(missingChip).toHaveAttribute("aria-pressed", "false");
  await missingChip.click();
  await expect(missingChip).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { name: "In collectie" })).toHaveCount(0);
  await expect(page.getByText("Nobody At All")).toBeVisible();

  await page.getByRole("button", { name: "Alles" }).click();
  await expect(page.getByRole("heading", { name: "In collectie" })).toBeVisible();
});

test("applying a synced session confirms, writes, and shows the backup result", async ({
  page,
}) => {
  await page.route("**/api/auth/spotify/status", (route) =>
    route.fulfill({
      json: { connected: true, display_name: "DJ Test", product: "premium" },
    }),
  );
  // The shell's top bar reads the Rekordbox version from health, and its
  // sidebar counter and Collectie-scan card read the missing queue and the
  // collection; this spec isn't about any of them, so they answer empty.
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
  await page.route("**/api/missing*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/enrichment/status", (route) =>
    route.fulfill({ json: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0 } }),
  );
  await page.route("**/api/enrichment/unenriched*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/structures", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profiles", (route) => route.fulfill({ json: [] }));
  // The sidebar's two playlist sources (GET /api/spotify/playlists and the
  // Rekordbox tree of GET /api/playlists): not what this spec is about, so
  // both answer empty rather than reaching a real backend.
  await page.route("**/api/spotify/playlists", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/playlists", (route) => route.fulfill({ json: [] }));

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

  // The mock answers `created: true`, and since the phase 7 review the success
  // message distinguishes a created or recreated playlist from an updated one
  // (FR-019, US3 scenario 5), instead of reading identically for both.
  await expect(page.getByText(/Playlist aangemaakt: 1 nummer\(s\) toegevoegd/)).toBeVisible();
  await expect(page.getByText(/master-20260817T120000000000Z\.db\.zip/)).toBeVisible();
});

// The delivered design's Uncertain group (HANDOFF.md, "1. Match-overzicht"):
// Spotify on the left, the score in the middle, the Rekordbox candidate on the
// right with duration, BPM and musical key, and "Andere"/"Bevestig".
//
// The Rekordbox side is the part only a full-stack run can prove: a session's
// candidate rows carry `{rb_content_id, score, reason}` only, so the UI has to
// resolve the id through GET /api/collection before it can show a title, a BPM
// or a key. This mocks that endpoint the way the real one answers, and asserts
// the card renders the resolved row rather than the bare id.
test("the uncertain group shows the resolved Rekordbox candidate and confirms it", async ({
  page,
}) => {
  await page.route("**/api/auth/spotify/status", (route) =>
    route.fulfill({ json: { connected: true, display_name: "DJ Test", product: "premium" } }),
  );
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
  await page.route("**/api/missing*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/enrichment/status", (route) =>
    route.fulfill({ json: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0 } }),
  );
  await page.route("**/api/enrichment/unenriched*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/structures", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profiles", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/spotify/playlists", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/playlists", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/auth/spotify/player-token", (route) =>
    route.fulfill({
      status: 409,
      json: { code: "spotify_not_connected", message: "geen sessie" },
    }),
  );
  // GET /api/collection's real row shape, including the verbatim Rekordbox
  // `musical_key` ("8m", never converted) and the nullable `label`.
  await page.route("**/api/collection?*", (route) =>
    route.fulfill({
      json: {
        total: 1,
        items: [
          {
            rb_content_id: "rb-a",
            artist: "Daft Punk",
            title: "One More Time (Club Edit)",
            duration_ms: 408_000,
            bpm: 123,
            play_count: 5,
            genres: [],
            format: "aiff",
            musical_key: "8m",
            label: "Virgin",
          },
        ],
      },
    }),
  );

  const sessionDetail = {
    id: 1,
    playlist_link_id: 1,
    spotify_snapshot_id: "snap-1",
    name: "Booking 2026",
    status: "ready",
    created_at: "2026-08-18T00:00:00",
    totals: { matched: 0, review: 1, missing: 0, rejected: 0, unmatchable: 0 },
    tracks: [
      {
        id: 1,
        position: 1,
        spotify_track_id: "sp1",
        isrc: null,
        artist: "Daft Punk",
        title: "One More Time",
        duration_ms: 432_000,
        status: "review",
        rb_content_id: null,
        match_score: 84.2,
        candidates: [{ rb_content_id: "rb-a", score: 84.2, reason: "fuzzy" }],
        matched_at: null,
      },
    ],
  };
  await page.route("**/api/sync/sessions", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({ json: { ...sessionDetail, tracks: undefined } });
  });
  await page.route("**/api/sync/sessions/1", (route) => route.fulfill({ json: sessionDetail }));
  await page.route("**/api/sync/sessions/1/tracks/1/accept", (route) =>
    route.fulfill({ json: { ...sessionDetail.tracks[0], status: "matched" } }),
  );

  await page.goto("/");
  await page
    .getByLabel("Spotify-afspeellijst URL")
    .fill("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M");
  await page.getByRole("button", { name: "Synchroniseren" }).click();

  await expect(
    page.getByRole("heading", { name: "Twijfelgevallen — jouw beslissing" }),
  ).toBeVisible();
  await expect(page.getByText("84%")).toBeVisible();
  // `exact` matters: the candidate picker below the card repeats the title in
  // its own row ("Daft Punk – One More Time (Club Edit) · score 84").
  await expect(page.getByText("One More Time (Club Edit)", { exact: true })).toBeVisible();
  await expect(page.getByText("6:48 · 123 BPM · 8m")).toBeVisible();

  const accepted = page.waitForRequest(
    (request) => request.url().includes("/tracks/1/accept") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Bevestig" }).click();
  const request = await accepted;
  expect(JSON.parse(request.postData() ?? "{}")).toEqual({ rb_content_id: "rb-a" });
});
