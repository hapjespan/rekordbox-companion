// The delivered design's Match-overzicht, assembled (HANDOFF.md,
// "1. Match-overzicht"): a filter row above the groups it filters, and the
// groups themselves -- what is missing, what needs a decision, what is already
// in the collection.
//
// This is the level at which "the chips actually filter and the sort control
// actually sorts" is a real claim: the groups are rendered by two different
// feature components, so a test of either one alone cannot prove it.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../src/api/client";
import type { SyncSessionDetail, SyncTrack } from "../../src/features/spotify-sync/types";
import { MatchOverviewView } from "../../src/views/MatchOverviewView";

vi.mock("../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

function track(overrides: Partial<SyncTrack> & { id: number }): SyncTrack {
  return {
    position: overrides.id,
    spotify_track_id: `sp-${overrides.id}`,
    isrc: null,
    artist: "Artiest",
    title: "Titel",
    duration_ms: 210_000,
    status: "matched",
    rb_content_id: null,
    match_score: null,
    candidates: [],
    matched_at: null,
    ...overrides,
  };
}

const MATCHED = track({ id: 1, title: "Gematcht nummer", status: "matched", match_score: 100 });
const REVIEW = track({
  id: 2,
  title: "Twijfelnummer",
  status: "review",
  match_score: 84,
  candidates: [{ rb_content_id: "rb-a", score: 84, reason: "fuzzy" }],
});
// Sorted on "zekerheid" these two land Zebra (60) before Alpha (40); sorted on
// title they swap, which is what makes the sort control provable.
const MISSING_LOW = track({ id: 3, title: "Alpha", status: "missing", match_score: 40 });
const MISSING_HIGH = track({ id: 5, title: "Zebra", status: "missing", match_score: 60 });
const REJECTED = track({ id: 4, title: "Afgewezen nummer", status: "rejected", match_score: 80 });

const SESSION: SyncSessionDetail = {
  id: 7,
  playlist_link_id: 1,
  spotify_snapshot_id: "snap-1",
  name: "Warehouse Winter 2026",
  status: "ready",
  created_at: "2026-08-18T00:00:00",
  totals: { matched: 1, review: 1, missing: 2, rejected: 1, unmatchable: 0 },
  tracks: [MATCHED, REVIEW, MISSING_LOW, REJECTED, MISSING_HIGH],
};

function renderView() {
  return render(
    <MatchOverviewView
      session={SESSION}
      onSessionCreated={vi.fn()}
      onSessionChanged={vi.fn()}
      onSpotifyStatus={vi.fn()}
      onGoToBuyQueue={vi.fn()}
      focusUrlToken={0}
    />,
  );
}

function missingTable() {
  return screen.getByRole("table", { name: "Nummers die ontbreken in de Rekordbox-collectie" });
}

// The rendered order of the missing rows, by the only two titles in the
// fixture.
function missingTitles() {
  return within(missingTable())
    .getAllByRole("row")
    .slice(1)
    .map((row) => (row.textContent ?? "").match(/Alpha|Zebra/)?.[0] ?? "?");
}

beforeEach(() => {
  vi.mocked(apiClient.GET).mockReset();
  vi.mocked(apiClient.POST).mockReset();
  vi.mocked(apiClient.GET).mockImplementation((path: string) => {
    if (path.includes("/api/collection")) {
      return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
    }
    return Promise.resolve({
      data: undefined,
      error: { code: "spotify_not_connected", message: "not connected" },
    }) as never;
  });
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

describe("MatchOverviewView", () => {
  it("renders all three groups with a coloured dot, a title and a count", async () => {
    renderView();

    expect(screen.getByRole("heading", { name: "Ontbreekt in Rekordbox" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Twijfelgevallen — jouw beslissing" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "In collectie" })).toBeInTheDocument();
    expect(screen.getByText("2 tracks")).toBeInTheDocument();
    expect(screen.getByText("1 tracks")).toBeInTheDocument();
    // rejected/unmatchable have no group of their own in the design and ride
    // along in the collection group, where the row states its own status.
    await waitFor(() => expect(screen.getByText("Afgewezen")).toBeInTheDocument());
  });

  it("the Twijfel chip hides every other group", () => {
    renderView();

    fireEvent.click(screen.getByRole("button", { name: "Twijfel" }));

    expect(
      screen.queryByRole("heading", { name: "Ontbreekt in Rekordbox" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "In collectie" })).not.toBeInTheDocument();
    expect(screen.getByTestId("review-queue")).toBeInTheDocument();
  });

  it("the Ontbreekt chip leaves only the missing table", () => {
    renderView();

    fireEvent.click(screen.getByRole("button", { name: "Ontbreekt" }));

    expect(missingTable()).toBeInTheDocument();
    expect(screen.queryByTestId("review-queue")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "In collectie" })).not.toBeInTheDocument();
  });

  it("the In collectie chip leaves only the collection group", () => {
    renderView();

    fireEvent.click(screen.getByRole("button", { name: "In collectie" }));

    expect(screen.getByRole("table", { name: "Matchresultaten per nummer" })).toBeInTheDocument();
    expect(
      screen.queryByRole("table", { name: "Nummers die ontbreken in de Rekordbox-collectie" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("review-queue")).not.toBeInTheDocument();
  });

  it("sorts the rendered rows by the sort control, not by playlist order", () => {
    renderView();

    // The design's default: most certain first.
    expect(missingTitles()).toEqual(["Zebra", "Alpha"]);

    fireEvent.change(screen.getByLabelText("Sorteer op"), { target: { value: "title" } });
    expect(missingTitles()).toEqual(["Alpha", "Zebra"]);

    fireEvent.change(screen.getByLabelText("Sorteer op"), { target: { value: "position" } });
    expect(missingTitles()).toEqual(["Alpha", "Zebra"]);
  });
});
