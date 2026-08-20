import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// T091: accessibility sweep across all seven stories (WCAG 2.2 AA).
//
// The shell (web/design-input/HANDOFF.md) gave every story its own view
// behind the sidebar's WORKSPACE nav, so the sweep now walks the five views
// instead of scanning one long page: same coverage, one click deeper. The
// second test below adds the states that only render after user action (a
// match report, ready to apply), which no amount of navigating reaches.
//
// The first two tests keep the EMPTY states covered (no structures, nothing to
// review). The third scans the two densest interactive surfaces in their
// populated state -- the review cards with their candidate listboxes, and the
// builder with phase columns, the BPM chart and the checks bar -- which are
// exactly the surfaces the empty-state mocks never reach (backlog B6).
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

// The two review candidates of the queue below, as GET /api/collection returns
// them: one Rekordbox analysed (BPM and Camelot key), one it never analysed
// (`bpm: null`, `musical_key: null` -- an absence, never a 0).
const CANDIDATE_ROWS = [
  {
    rb_content_id: "rb-a",
    artist: "Daft Punk",
    title: "One More Time (Club Edit)",
    duration_ms: 408_000,
    bpm: 123,
    play_count: 12,
    genres: [],
    format: "mp3",
    musical_key: "8m",
    label: "Virgin",
  },
  {
    rb_content_id: "rb-b",
    artist: "Daft Punk",
    title: "One More Time (Radio)",
    duration_ms: 320_000,
    bpm: null,
    play_count: 0,
    genres: [],
    format: "aiff",
    musical_key: null,
    label: null,
  },
];

// Two phase columns, each holding one track Rekordbox analysed and one it did
// not: the phase rows, the BPM chart (bar plus its table text alternative) and
// the checks bar all have both cases to render.
const PHASE_TRACKS: Record<string, unknown[]> = {
  "2": [
    {
      rb_content_id: "rb-a",
      artist: "Daft Punk",
      title: "One More Time",
      duration_ms: 320_000,
      bpm: 123,
      play_count: 12,
      genres: [],
      format: "mp3",
      musical_key: "8m",
      label: "Virgin",
    },
    {
      rb_content_id: "rb-b",
      artist: "Stardust",
      title: "Music Sounds Better With You",
      duration_ms: null,
      bpm: null,
      play_count: 0,
      genres: [],
      format: "aiff",
      musical_key: null,
      label: null,
    },
  ],
  "3": [
    {
      rb_content_id: "rb-c",
      artist: "Justice",
      title: "D.A.N.C.E.",
      duration_ms: 244_000,
      bpm: 118,
      play_count: 3,
      genres: [],
      format: "mp3",
      musical_key: "2d",
      label: "Ed Banger",
    },
    {
      rb_content_id: "rb-d",
      artist: "Cassius",
      title: "Feeling For You",
      duration_ms: null,
      bpm: null,
      play_count: 0,
      genres: [],
      format: "mp3",
      musical_key: null,
      label: null,
    },
  ],
};

// The coverage half of backlog item B6: the review card with its candidate
// listbox and the phase board with populated columns were both verified
// axe-clean out of band, with throwaway specs. This is that guarantee, in the
// repo. The routes registered here override mockCommonEndpoints' empty
// answers: Playwright matches routes in reverse registration order.
test("the populated review queue and phase board have no automatically detectable accessibility violations", async ({
  page,
}) => {
  await mockCommonEndpoints(page);

  await page.route("**/api/collection?*", (route) => {
    const ids = new URL(route.request().url()).searchParams.getAll("ids");
    const items =
      ids.length === 0
        ? CANDIDATE_ROWS
        : CANDIDATE_ROWS.filter((row) => ids.includes(row.rb_content_id));
    return route.fulfill({ json: { total: items.length, items } });
  });
  // No Spotify session in this suite, so the review card degrades to the
  // `spotify:track:` deep link (spec.md's documented fallback) instead of
  // loading Spotify's SDK from its CDN. The candidate's own audio element is
  // answered locally for the same offline reason.
  await page.route("**/api/auth/spotify/player-token", (route) =>
    route.fulfill({
      status: 409,
      json: { code: "spotify_not_connected", message: "geen Spotify-sessie" },
    }),
  );
  await page.route("**/api/player/stream/*", (route) =>
    route.fulfill({ status: 200, contentType: "audio/mpeg", body: "" }),
  );

  await page.route("**/api/structures", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          name: "Bruiloft Jansen",
          booking_profile_id: 1,
          created_at: "2026-08-18T00:00:00",
          last_applied_at: null,
        },
      ],
    }),
  );
  await page.route("**/api/profiles", (route) =>
    route.fulfill({
      json: [
        {
          id: 1,
          name: "Bruiloft",
          slug: "bruiloft",
          bpm_min: 118,
          bpm_max: 128,
          genre_tags: ["house"],
        },
      ],
    }),
  );
  await page.route("**/api/structures/*/nodes", (route) =>
    route.fulfill({
      json: [
        {
          id: 2,
          parent_id: null,
          kind: "playlist",
          name: "Ontvangst",
          position: 0,
          set_phase: "vooravond",
          rb_ref: null,
        },
        {
          id: 3,
          parent_id: null,
          kind: "playlist",
          name: "Dansvloer",
          position: 1,
          set_phase: "prime",
          rb_ref: null,
        },
      ],
    }),
  );
  await page.route("**/api/structures/*/nodes/*/tracks*", (route) => {
    const nodeId = /\/nodes\/(\d+)\/tracks/.exec(route.request().url())?.[1] ?? "";
    const items = PHASE_TRACKS[nodeId] ?? [];
    return route.fulfill({ json: { total: items.length, items } });
  });

  const session = {
    id: 1,
    playlist_link_id: 1,
    spotify_snapshot_id: "snap-1",
    name: "Booking 2026",
    status: "ready",
    created_at: "2026-08-18T00:00:00",
    totals: { matched: 1, review: 2, missing: 1, rejected: 0, unmatchable: 0 },
  };
  await page.route("**/api/sync/sessions", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({ json: session });
  });
  await page.route("**/api/sync/sessions/1", (route) =>
    route.fulfill({
      json: {
        ...session,
        tracks: [
          {
            id: 1,
            position: 1,
            spotify_track_id: "sp-1",
            isrc: null,
            artist: "Daft Punk",
            title: "One More Time",
            duration_ms: 320_000,
            status: "review",
            rb_content_id: null,
            match_score: 84,
            // Two candidates, so the card's picker listbox and its "Andere"
            // control both have something to own.
            candidates: [
              { rb_content_id: "rb-a", score: 88.4, reason: "fuzzy" },
              { rb_content_id: "rb-b", score: 76.2, reason: "fuzzy" },
            ],
            matched_at: null,
          },
          {
            id: 2,
            position: 2,
            spotify_track_id: "sp-2",
            isrc: null,
            artist: "Stardust",
            title: "Music Sounds Better With You",
            duration_ms: 250_000,
            status: "review",
            rb_content_id: null,
            match_score: 79,
            // An id the collection does not know: the card names it by its
            // Rekordbox id, which is a state of its own to scan.
            candidates: [{ rb_content_id: "rb-onbekend", score: 79.1, reason: "fuzzy" }],
            matched_at: null,
          },
        ],
      },
    }),
  );

  await page.goto("/");
  await page.getByLabel("Spotify-afspeellijst URL").fill("https://open.spotify.com/playlist/abc");
  await page.getByRole("button", { name: "Synchroniseren" }).click();

  // The review cards, with their candidates resolved to real Rekordbox rows.
  await expect(page.getByTestId("review-queue")).toBeVisible();
  // Twice each: the card's Rekordbox title, and the same candidate's row in
  // the picker listbox below it.
  await expect(page.getByText("One More Time (Club Edit)").first()).toBeVisible();
  await expect(page.getByText("Rekordbox-id rb-onbekend").first()).toBeVisible();

  const review = await new AxeBuilder({ page }).analyze();

  expect(review.violations, JSON.stringify(review.violations, null, 2)).toEqual([]);

  // The builder with populated phase columns, the BPM chart and the checks bar.
  await page
    .getByRole("navigation")
    .getByRole("button", { name: /Playlist builder/ })
    .click();
  await page.getByRole("group", { name: "Structuren" }).getByRole("button").first().click();
  await expect(page.getByRole("heading", { name: "vooravond" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "prime" })).toBeVisible();
  // Exact: the same title also sits in the BPM chart's text alternative,
  // which is still folded shut at this point.
  await expect(page.getByText("D.A.N.C.E.", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("geen BPM").first()).toBeVisible();

  const builder = await new AxeBuilder({ page }).analyze();

  expect(builder.violations, JSON.stringify(builder.violations, null, 2)).toEqual([]);

  // The BPM chart's text alternative is a real table, open it and scan that
  // state too: a <details> body is not in the accessibility tree while closed.
  await page.getByText("Tekstalternatief: BPM per track").click();
  await expect(page.getByRole("table")).toBeVisible();

  const alternative = await new AxeBuilder({ page }).analyze();

  expect(alternative.violations, JSON.stringify(alternative.violations, null, 2)).toEqual([]);
});
