import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// T091: accessibility sweep across all seven stories (WCAG 2.2 AA).
//
// The shell (web/design-input/HANDOFF.md) gave every story its own view
// behind the sidebar's WORKSPACE nav, so the sweep now walks the five views
// instead of scanning one long page: same coverage, one click deeper. The
// second test below adds the states that only render after user action (a
// match report, ready to apply), which no amount of navigating reaches.
async function mockCommonEndpoints(page: import("@playwright/test").Page) {
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
  await page.route("**/api/auth/spotify/status", (route) =>
    route.fulfill({ json: { connected: true, display_name: "DJ Test", product: "premium" } }),
  );
  // One real row, not an empty queue: FR-041's preview control and price
  // only exist on a row, and the WCAG 2.2 AA claim covers them too.
  await page.route("**/api/missing*", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          artist: "Daft Punk",
          title: "One More Time",
          status: "open",
          itunes_url_auto: "https://music.apple.com/nl/album/one-more-time/1",
          itunes_url_chosen: null,
          effective_url: "https://music.apple.com/nl/album/one-more-time/1",
          no_link_found: false,
          itunes_preview_url: "https://audio-ssl.itunes.apple.com/itunes-assets/preview.m4a",
          itunes_price: 1.29,
          itunes_currency: "EUR",
        },
      ],
    }),
  );
  // The sweep never plays anything, but the <audio> element still resolves
  // its src: answered locally so this suite stays offline (playwright.config
  // comment) instead of reaching Apple's preview host.
  await page.route("https://audio-ssl.itunes.apple.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "audio/mp4", body: "" }),
  );
  await page.route("**/api/enrichment/status", (route) =>
    route.fulfill({ json: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0 } }),
  );
  await page.route("**/api/enrichment/unenriched*", (route) =>
    route.fulfill({ json: { total: 0, items: [] } }),
  );
  await page.route("**/api/structures", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/profiles", (route) => route.fulfill({ json: [] }));
  // The sidebar's two playlist sources. One real Spotify row (its cover stays
  // a placeholder so this suite makes no request to Spotify's CDN) and a
  // folder holding one playlist, so the tree's fold control and a nested row
  // are both in the sweep. No name here collides with a WORKSPACE nav label.
  await page.route("**/api/spotify/playlists", (route) =>
    route.fulfill({
      json: [
        {
          spotify_playlist_id: "37i9",
          name: "Bruiloft 2026",
          image_url: null,
          owner_display_name: "DJ Test",
          sync: {
            state: "ready",
            session_id: 1,
            session_created_at: "2026-08-18T00:00:00",
            last_applied_at: null,
            totals: { matched: 2, review: 1, missing: 1, rejected: 0, unmatchable: 0 },
          },
        },
      ],
    }),
  );
  await page.route("**/api/playlists", (route) =>
    route.fulfill({
      json: [
        { rb_playlist_id: "1", name: "Bruiloften", parent_id: null, is_folder: true, position: 1 },
        {
          rb_playlist_id: "2",
          name: "Warme opener",
          parent_id: "1",
          is_folder: false,
          position: 1,
        },
      ],
    }),
  );
  await page.route("**/api/playlists/*/tracks?*", (route) =>
    route.fulfill({
      json: {
        total: 1,
        items: [
          {
            rb_content_id: "rb1",
            artist: "Daft Punk",
            title: "One More Time",
            duration_ms: 210_000,
            bpm: 123,
            play_count: 5,
            genres: [],
            format: "mp3",
            musical_key: "9B",
            label: "Virgin",
          },
        ],
      },
    }),
  );
  // The shell's sidebar card and the collection table both read this one.
  await page.route("**/api/collection?*", (route) =>
    route.fulfill({
      json: {
        total: 1,
        items: [
          {
            rb_content_id: "rb1",
            artist: "Daft Punk",
            title: "One More Time",
            duration_ms: 210_000,
            bpm: 123,
            play_count: 5,
            genres: [],
            format: "mp3",
            musical_key: "8m",
            label: "Virgin",
          },
        ],
      },
    }),
  );
}

test("every workspace view has no automatically detectable accessibility violations", async ({
  page,
}) => {
  await mockCommonEndpoints(page);

  await page.goto("/");
  await page.waitForSelector("text=Rekordbox Companion");

  // The default view (Match-overzicht: US1 sync, and the shell itself --
  // top bar, nav, collection-scan card) plus the four the nav reaches.
  const views = [
    "Match-overzicht",
    "Koop-wachtrij",
    "Playlist builder",
    "Collectie",
    "Genre-verrijking",
  ];

  for (const view of views) {
    const item = page.getByRole("navigation").getByRole("button", { name: new RegExp(view) });
    await item.click();
    await expect(item).toHaveAttribute("aria-current", "page");

    const results = await new AxeBuilder({ page }).analyze();

    expect(results.violations, `${view}: ${JSON.stringify(results.violations, null, 2)}`).toEqual(
      [],
    );
  }

  // The sixth state the nav cannot reach on its own: the Collection view
  // filtered to a Rekordbox playlist, reached by folding open the sidebar's
  // library tree and picking a playlist inside it.
  await page.getByRole("button", { name: "Warme opener" }).click();
  await expect(page.getByRole("heading", { name: "Warme opener" })).toBeVisible();

  const filtered = await new AxeBuilder({ page }).analyze();

  expect(filtered.violations, JSON.stringify(filtered.violations, null, 2)).toEqual([]);
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
  await page.waitForSelector("text=Gematcht: 1");

  const results = await new AxeBuilder({ page }).analyze();

  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});
