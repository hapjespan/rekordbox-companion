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

function navItem(label: string) {
  return within(screen.getByRole("navigation")).getByRole("button", { name: new RegExp(label) });
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

    const nav = screen.getByRole("navigation");
    // A nav item's text is its label plus, where a real number exists, a
    // trailing counter; the order of the five is what this pins.
    const labels = within(nav)
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

  it("the Sync pill returns to Match-overzicht and focuses the playlist URL field", () => {
    render(<App />);
    fireEvent.click(navItem("Genre-verrijking"));

    fireEvent.click(screen.getByRole("button", { name: "Sync" }));

    expect(navItem("Match-overzicht")).toHaveAttribute("aria-current", "page");
    expect(document.activeElement).toBe(screen.getByLabelText("Spotify-afspeellijst URL"));
  });
});
