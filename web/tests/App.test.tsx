// Phase 7 review: US2 and US5 both shipped as fully built, fully unit-tested
// components that nothing ever imported, so neither story existed for the DJ.
// Component tests cannot catch that by construction -- they mount the
// component themselves. This file asserts the one thing they cannot: that
// every user story is reachable from the page the app actually serves.
//
// The shell (App.tsx, from web/design-input/HANDOFF.md) put a view switcher
// between page load and the panels, so "reachable" now means "reachable from
// the sidebar nav" -- which is the same guarantee, one click deeper. The
// second block below covers the shell itself: the five nav items, their
// aria-current state, the top bar's live connection data and the sidebar's
// collection-scan control.
//
// Deliberately shallow on the stories themselves. It checks presence, not
// behaviour: each story's own suite owns its behaviour, and duplicating that
// here would make this file a second place to update on every UI change,
// which is how a guard like this stops being maintained.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../src/api/client";
import { App } from "../src/App";

vi.mock("../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), DELETE: vi.fn() },
}));

const HEALTH = {
  status: "ok",
  rekordbox_version: "7.2.17",
  version_pin_ok: true,
  db_path: "/fixtures/master.db",
  rekordbox_running: false,
  ffmpeg_ok: true,
};

// The sidebar's two playlist sources (GET /api/spotify/playlists and the
// Rekordbox tree of GET /api/playlists). Named so no name collides with a
// WORKSPACE nav label.
const SPOTIFY_PLAYLISTS = [
  {
    spotify_playlist_id: "37i9",
    name: "Bruiloft 2026",
    image_url: null,
    owner_display_name: "Martien",
    sync: {
      state: "ready",
      session_id: 12,
      session_created_at: "2026-08-18T00:00:00",
      last_applied_at: null,
      totals: { matched: 2, review: 1, missing: 1, rejected: 0, unmatchable: 0 },
    },
  },
];

const REKORDBOX_NODES = [
  { rb_playlist_id: "1", name: "Bruiloften", parent_id: null, is_folder: true, position: 1 },
  { rb_playlist_id: "2", name: "Warme opener", parent_id: "1", is_folder: false, position: 1 },
];

const PLAYLIST_TRACK = {
  rb_content_id: "rb9",
  artist: "Nightbus",
  title: "Ferro",
  duration_ms: 210_000,
  bpm: 126,
  play_count: 3,
  genres: [],
  format: "mp3",
  musical_key: "9B",
  label: "Eigen release",
};

// Every panel fetches on mount. One empty-but-valid answer per shape keeps the
// page in its loaded state without any panel throwing.
function mockEmptyBackend(spotify: unknown = { connected: false }) {
  vi.mocked(apiClient.GET).mockImplementation((path: string) => {
    if (path.includes("/health")) {
      return Promise.resolve({ data: HEALTH, error: undefined }) as never;
    }
    if (path.includes("/auth/spotify/status")) {
      return Promise.resolve({ data: spotify, error: undefined }) as never;
    }
    if (path.includes("/spotify/playlists")) {
      return Promise.resolve({ data: SPOTIFY_PLAYLISTS, error: undefined }) as never;
    }
    if (path.includes("/playlists/{rb_playlist_id}/tracks")) {
      return Promise.resolve({
        data: { total: 1, items: [PLAYLIST_TRACK] },
        error: undefined,
      }) as never;
    }
    if (path.includes("/api/playlists")) {
      return Promise.resolve({ data: REKORDBOX_NODES, error: undefined }) as never;
    }
    if (path.includes("/enrichment/status")) {
      return Promise.resolve({
        data: { pending: 0, done: 0, none_found: 0, failed: 0, coverage_pct: 0, running: false },
        error: undefined,
      }) as never;
    }
    if (path.includes("/collection")) {
      return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
    }
    if (path.includes("/unenriched")) {
      return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
    }
    return Promise.resolve({ data: [], error: undefined }) as never;
  });
}

// jsdom has no EventSource, and the enrichment panel opens one on mount.
class SilentEventSource {
  addEventListener() {}
  close() {}
}

// Scoped to the WORKSPACE list, not to the whole navigation landmark: the
// sidebar's nav now also holds the Spotify playlist rows and the Rekordbox
// tree, whose rows are buttons too.
function navItem(label: string) {
  return within(screen.getByRole("list", { name: "WORKSPACE" })).getByRole("button", {
    name: new RegExp(label),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("EventSource", SilentEventSource);
  mockEmptyBackend();
});

describe("App", () => {
  it("reaches every user story from the sidebar nav", async () => {
    render(<App />);

    // US1 sync (the default view) and US2 review / US3 apply live in
    // Match-overzicht; US2 and US3 are session-scoped, so they only appear
    // once a session exists and their own suites cover them.
    expect(screen.getByLabelText("Spotify-afspeellijst URL")).toBeInTheDocument();

    // US4 missing tracks.
    fireEvent.click(navItem("Koop-wachtrij"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Ontbrekende nummers" })).toBeInTheDocument();
    });

    // US7 booking structures.
    fireEvent.click(navItem("Playlist builder"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Boekingstructuren" })).toBeInTheDocument();
    });

    // US5 the collection browser and its player.
    fireEvent.click(navItem("Collectie"));
    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Zoeken in collectie")).toBeInTheDocument();

    // US6 genre enrichment.
    fireEvent.click(navItem("Genre-verrijking"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Genre-verrijking" })).toBeInTheDocument();
    });
  });
});

describe("shell", () => {
  it("puts the five workspace views in a nav landmark", () => {
    render(<App />);

    // One navigation landmark for the whole sidebar, holding the three
    // sections: nested landmarks per section would leave the page with three
    // navs and no clear "the nav" any more.
    expect(screen.getAllByRole("navigation")).toHaveLength(1);
    const workspace = screen.getByRole("list", { name: "WORKSPACE" });
    // A nav item's text is its label plus, where a real number exists, a
    // trailing counter; the order of the five is what this pins.
    const labels = within(workspace)
      .getAllByRole("button")
      .map((button) => button.textContent?.replace(/\d+$/, ""));

    expect(labels).toEqual([
      "Match-overzicht",
      "Koop-wachtrij",
      "Playlist builder",
      "Collectie",
      "Genre-verrijking",
    ]);
  });

  it("marks the current view with aria-current, and moves it when switching", () => {
    render(<App />);

    expect(navItem("Match-overzicht")).toHaveAttribute("aria-current", "page");
    expect(navItem("Collectie")).not.toHaveAttribute("aria-current");

    fireEvent.click(navItem("Collectie"));

    expect(navItem("Collectie")).toHaveAttribute("aria-current", "page");
    expect(navItem("Match-overzicht")).not.toHaveAttribute("aria-current");
  });

  it("shows the Rekordbox version health reports and the Spotify display name", async () => {
    mockEmptyBackend({ connected: true, display_name: "djmarijn", product: "premium" });

    render(<App />);

    // The pinned 7.2.17 is not hardcoded in the UI: this is whatever
    // GET /api/health answered.
    await waitFor(() => {
      expect(screen.getByText("Rekordbox 7.2.17 verbonden")).toBeInTheDocument();
    });
    expect(screen.getByText("Spotify · djmarijn")).toBeInTheDocument();
  });

  it("rebuilds the collection index from the sidebar's scan card", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { indexed_count: 2, took_ms: 5 },
      error: undefined,
    } as never);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Opnieuw scannen" }));

    await waitFor(() => {
      expect(vi.mocked(apiClient.POST)).toHaveBeenCalledWith("/api/collection/reindex", {});
    });
  });

  it("searching in the top bar opens the collection view with that query", async () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText("Zoek in collectie of playlist"), {
      target: { value: "daft" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zoeken" }));

    expect(navItem("Collectie")).toHaveAttribute("aria-current", "page");
    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenCalledWith(
        "/api/collection",
        expect.objectContaining({
          params: expect.objectContaining({
            query: expect.objectContaining({ query: "daft" }),
          }),
        }),
      ),
    );
  });

  it("keeps the workspace nav and the Collectie-scan card reachable beside both playlist sources", async () => {
    // 101 Spotify playlists plus a deep tree must not push the nav or the
    // scan card out of reach: each list scrolls inside its own bounded box.
    const many = Array.from({ length: 101 }, (_, index) => ({
      ...SPOTIFY_PLAYLISTS[0],
      spotify_playlist_id: `pl-${index}`,
      name: `Afspeellijst ${index}`,
    }));
    vi.mocked(apiClient.GET).mockImplementation((path: string) => {
      if (path.includes("/spotify/playlists")) {
        return Promise.resolve({ data: many, error: undefined }) as never;
      }
      if (path.includes("/health")) {
        return Promise.resolve({ data: HEALTH, error: undefined }) as never;
      }
      if (path.includes("/api/playlists")) {
        return Promise.resolve({ data: REKORDBOX_NODES, error: undefined }) as never;
      }
      if (path.includes("/collection")) {
        return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
      }
      return Promise.resolve({ data: [], error: undefined }) as never;
    });

    render(<App />);
    await screen.findByRole("button", { name: /Afspeellijst 100/ });

    expect(navItem("Match-overzicht")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Opnieuw scannen" })).toBeInTheDocument();
    // Each of the two sources scrolls inside its own box, so neither can push
    // the other, the nav or the card off screen.
    for (const label of ["SPOTIFY PLAYLISTS", "REKORDBOX-BIBLIOTHEEK"]) {
      expect(screen.getByRole("group", { name: label }).className).toContain("overflow-y-auto");
    }
  });

  it("folds a source away so the other one gets the whole middle", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /Bruiloft 2026/ });

    const heading = screen.getByRole("button", { name: "SPOTIFY PLAYLISTS" });
    expect(heading).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(heading);

    expect(heading).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /Bruiloft 2026/ })).not.toBeInTheDocument();
    // The Rekordbox tree is untouched by its neighbour folding.
    expect(screen.getByRole("button", { name: "Bruiloften" })).toBeInTheDocument();

    fireEvent.click(heading);

    expect(screen.getByRole("button", { name: /Bruiloft 2026/ })).toBeInTheDocument();
  });

  it("clicking a Spotify playlist syncs it and shows the match report, without pasting a URL", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        id: 12,
        playlist_link_id: 1,
        spotify_snapshot_id: "snap",
        name: "Bruiloft 2026",
        status: "ready",
        created_at: "2026-08-18T00:00:00",
        totals: { matched: 2, review: 1, missing: 1, rejected: 0, unmatchable: 0 },
      },
      error: undefined,
    } as never);
    vi.mocked(apiClient.GET).mockImplementation((path: string) => {
      if (path.includes("/sync/sessions/")) {
        return Promise.resolve({
          data: {
            id: 12,
            playlist_link_id: 1,
            spotify_snapshot_id: "snap",
            name: "Bruiloft 2026",
            status: "ready",
            created_at: "2026-08-18T00:00:00",
            totals: { matched: 2, review: 1, missing: 1, rejected: 0, unmatchable: 0 },
            tracks: [],
          },
          error: undefined,
        }) as never;
      }
      if (path.includes("/health")) {
        return Promise.resolve({ data: HEALTH, error: undefined }) as never;
      }
      if (path.includes("/spotify/playlists")) {
        return Promise.resolve({ data: SPOTIFY_PLAYLISTS, error: undefined }) as never;
      }
      if (path.includes("/api/playlists")) {
        return Promise.resolve({ data: REKORDBOX_NODES, error: undefined }) as never;
      }
      if (path.includes("/collection")) {
        return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
      }
      return Promise.resolve({ data: [], error: undefined }) as never;
    });

    render(<App />);
    fireEvent.click(navItem("Genre-verrijking"));
    fireEvent.click(await screen.findByRole("button", { name: /Bruiloft 2026/ }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith("/api/sync/sessions", {
        body: { playlist_url: "https://open.spotify.com/playlist/37i9" },
      }),
    );
    expect(navItem("Match-overzicht")).toHaveAttribute("aria-current", "page");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Bruiloft 2026" })).toBeInTheDocument(),
    );
  });

  it("clicking a Rekordbox playlist opens the collection filtered to it, with a way back", async () => {
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Warme opener" }));

    expect(navItem("Collectie")).toHaveAttribute("aria-current", "page");
    // The view names the playlist it is showing, so the filter is never silent.
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Warme opener" })).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenCalledWith(
        "/api/playlists/{rb_playlist_id}/tracks",
        expect.objectContaining({
          params: expect.objectContaining({ path: { rb_playlist_id: "2" } }),
        }),
      ),
    );
    expect(screen.getByText("Ferro")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hele collectie tonen" }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Collectie" })).toBeInTheDocument(),
    );
  });

  it("a top-bar search leaves a playlist filter and lands on the whole collection", async () => {
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Warme opener" }));
    await screen.findByRole("heading", { name: "Warme opener" });

    fireEvent.change(screen.getByLabelText("Zoek in collectie of playlist"), {
      target: { value: "daft" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Zoeken" }));

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Collectie" })).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenLastCalledWith(
        "/api/collection",
        expect.objectContaining({
          params: expect.objectContaining({ query: expect.objectContaining({ query: "daft" }) }),
        }),
      ),
    );
  });

  it("the Sync pill returns to Match-overzicht and focuses the playlist URL field", () => {
    render(<App />);
    fireEvent.click(navItem("Genre-verrijking"));

    fireEvent.click(screen.getByRole("button", { name: "Sync" }));

    expect(navItem("Match-overzicht")).toHaveAttribute("aria-current", "page");
    expect(document.activeElement).toBe(screen.getByLabelText("Spotify-afspeellijst URL"));
  });
});
