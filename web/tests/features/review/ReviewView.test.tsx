// Phase 7 finding: ReviewQueue, DualPlayback, KeymapOverlay and QueueComplete
// all existed but nothing composed or mounted them, so US2's independent test
// ("every queue item can be resolved to accepted or rejected using only the
// documented keys, and both audio sources are playable per item") and its
// "key map discoverable from the screen" criterion were unreachable in the
// running app. These tests drive the composed view exactly the way the DJ
// does: keys only.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../../src/api/client";
import { ReviewView } from "../../../src/features/review/ReviewView";
import type { SyncSessionDetail, SyncTrack } from "../../../src/features/spotify-sync/types";

vi.mock("../../../src/api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

function track(overrides: Partial<SyncTrack> & { id: number }): SyncTrack {
  return {
    position: overrides.id,
    spotify_track_id: `sp-${overrides.id}`,
    isrc: null,
    artist: "Daft Punk",
    title: "One More Time",
    duration_ms: 210_000,
    status: "review",
    rb_content_id: null,
    match_score: 84,
    candidates: [],
    matched_at: null,
    ...overrides,
  };
}

const REVIEW_TRACK_1 = track({
  id: 1,
  artist: "Daft Punk",
  title: "One More Time",
  candidates: [
    { rb_content_id: "rb-a", score: 88.4, reason: "fuzzy" },
    { rb_content_id: "rb-b", score: 76.2, reason: "fuzzy" },
  ],
});

const REVIEW_TRACK_2 = track({
  id: 2,
  artist: "Example Artist",
  title: "Example Song",
  candidates: [{ rb_content_id: "rb-c", score: 80.0, reason: "fuzzy" }],
});

const MATCHED_TRACK = track({
  id: 3,
  artist: "Already",
  title: "Matched",
  status: "matched",
  rb_content_id: "rb-m",
  candidates: [],
});

function session(tracks: SyncTrack[]): SyncSessionDetail {
  return {
    id: 7,
    playlist_link_id: 1,
    spotify_snapshot_id: "snap-1",
    name: "Booking 2026",
    status: "ready",
    created_at: "2026-08-17T00:00:00",
    totals: {
      matched: 1,
      review: tracks.filter((t) => t.status === "review").length,
      missing: 0,
      rejected: 0,
      unmatchable: 0,
    },
    tracks,
  };
}

function renderView(tracks: SyncTrack[] = [REVIEW_TRACK_1, REVIEW_TRACK_2, MATCHED_TRACK]) {
  const onResolved = vi.fn().mockResolvedValue(undefined);
  const detail = session(tracks);
  const view = render(<ReviewView session={detail} onResolved={onResolved} />);
  return { ...view, onResolved, detail };
}

function queue() {
  return screen.getByTestId("review-queue");
}

beforeEach(() => {
  vi.mocked(apiClient.GET).mockReset();
  vi.mocked(apiClient.POST).mockReset();
  // The Spotify side degrades to the deep link here: embedded playback needs
  // a real session and a real device, which is the owner's Mac's job (ADR
  // 0009), not jsdom's.
  vi.mocked(apiClient.GET).mockResolvedValue({
    data: undefined,
    error: { code: "spotify_not_connected", message: "not connected" },
  } as never);
  vi.mocked(apiClient.POST).mockResolvedValue({ data: {} } as never);
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

describe("ReviewView", () => {
  it("queues only the session's review tracks, with the key map on screen", () => {
    renderView();

    const items = screen.getAllByTestId("review-queue-item");
    expect(items).toHaveLength(2);
    expect(screen.queryByText(/Already/)).not.toBeInTheDocument();

    // "the documented key map (arrows, A, R, space) is discoverable from the
    // screen" (spec.md US2 accessibility criteria).
    const keymap = screen.getByRole("note", { name: "Toetsenbordbediening" });
    expect(keymap).toHaveTextContent("Accepteer kandidaat");
    expect(keymap).toHaveTextContent("Wijs af");

    // Both playback sides are present for the active item.
    expect(screen.getByRole("button", { name: "Speel kandidaat af" })).toBeEnabled();
    expect(document.activeElement).toBe(queue());
  });

  it("A posts the selected candidate to the accept endpoint and refreshes the session", async () => {
    const { onResolved } = renderView();

    fireEvent.keyDown(queue(), { key: "a" });

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/sync/sessions/{session_id}/tracks/{track_id}/accept",
        { params: { path: { session_id: 7, track_id: 1 } }, body: { rb_content_id: "rb-a" } },
      ),
    );
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
  });

  it("ArrowRight then A accepts the second candidate", async () => {
    renderView();

    fireEvent.keyDown(queue(), { key: "ArrowRight" });
    fireEvent.keyDown(queue(), { key: "a" });

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/sync/sessions/{session_id}/tracks/{track_id}/accept",
        expect.objectContaining({ body: { rb_content_id: "rb-b" } }),
      ),
    );
  });

  it("R posts to the reject endpoint for the active item", async () => {
    const { onResolved } = renderView();

    fireEvent.keyDown(queue(), { key: "ArrowDown" });
    fireEvent.keyDown(queue(), { key: "r" });

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/sync/sessions/{session_id}/tracks/{track_id}/reject",
        { params: { path: { session_id: 7, track_id: 2 } } },
      ),
    );
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
  });

  it("space previews the local candidate through DualPlayback", async () => {
    renderView();

    fireEvent.keyDown(queue(), { key: " " });

    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1));
  });

  it("shows the completion state with the session totals once the last item is resolved", async () => {
    const onResolved = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <ReviewView session={session([REVIEW_TRACK_1, MATCHED_TRACK])} onResolved={onResolved} />,
    );

    fireEvent.keyDown(queue(), { key: "a" });
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));

    // The refreshed session no longer has a review track: the accepted one
    // is now matched (spec.md US2 scenario 6).
    const resolved = { ...REVIEW_TRACK_1, status: "matched" as const, rb_content_id: "rb-a" };
    rerender(<ReviewView session={session([resolved, MATCHED_TRACK])} onResolved={onResolved} />);

    expect(screen.getByText("Review afgerond")).toBeInTheDocument();
    expect(screen.getByText("Controleren: 0")).toBeInTheDocument();
    expect(screen.queryByTestId("review-queue")).not.toBeInTheDocument();
  });

  it("does not claim a completed review for a session that never had doubtful matches", () => {
    renderView([MATCHED_TRACK]);

    expect(screen.queryByText("Review afgerond")).not.toBeInTheDocument();
    expect(
      screen.getByText("Geen nummers om te controleren in deze synchronisatie."),
    ).toBeInTheDocument();
  });

  it("reports a refused resolution in Dutch and keeps the queue usable", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: undefined,
      error: { code: "not_in_review", message: "track 1 is 'matched', not review" },
    } as never);
    const { onResolved } = renderView();

    fireEvent.keyDown(queue(), { key: "a" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Dit nummer is al beoordeeld.");
    expect(onResolved).not.toHaveBeenCalled();
    expect(screen.getAllByTestId("review-queue-item")).toHaveLength(2);
  });

  // The Rekordbox side of the delivered design's card needs the candidate's
  // title, duration, BPM and musical key, none of which a session's candidate
  // rows carry. They are resolved exactly, through GET /api/collection's
  // `?ids=` filter: one request for every candidate in the queue, cached for
  // the session.
  it("resolves every candidate's Rekordbox detail by id, in one request for the queue", async () => {
    vi.mocked(apiClient.GET).mockImplementation((path: string) => {
      if (path === "/api/collection") {
        return Promise.resolve({
          data: {
            total: 1,
            items: [
              {
                rb_content_id: "rb-a",
                artist: "Daft Punk",
                title: "One More Time (Club Edit)",
                duration_ms: 408_000,
                bpm: 123,
                musical_key: "8m",
                label: "Virgin",
              },
            ],
          },
          error: undefined,
        }) as never;
      }
      return Promise.resolve({
        data: undefined,
        error: { code: "spotify_not_connected", message: "not connected" },
      }) as never;
    });

    renderView();

    expect(await screen.findByText("One More Time (Club Edit)")).toBeInTheDocument();
    expect(screen.getByText("6:48 · 123 BPM · 8m")).toBeInTheDocument();
    // Every candidate of every card in one request, by id -- no artist or
    // title query, and nothing guessed from the Spotify side.
    expect(apiClient.GET).toHaveBeenCalledWith("/api/collection", {
      params: { query: { ids: ["rb-a", "rb-b", "rb-c"], limit: 200 } },
    });
    expect(
      vi.mocked(apiClient.GET).mock.calls.filter((call) => call[0] === "/api/collection"),
    ).toHaveLength(1);
  });

  it("keeps the Rekordbox id as the label for an id the collection does not know", async () => {
    vi.mocked(apiClient.GET).mockImplementation((path: string) => {
      if (path === "/api/collection") {
        return Promise.resolve({ data: { total: 0, items: [] }, error: undefined }) as never;
      }
      return Promise.resolve({
        data: undefined,
        error: { code: "spotify_not_connected", message: "not connected" },
      }) as never;
    });

    renderView([REVIEW_TRACK_1]);

    await waitFor(() =>
      expect(apiClient.GET).toHaveBeenCalledWith("/api/collection", {
        params: { query: { ids: ["rb-a", "rb-b"], limit: 200 } },
      }),
    );
    expect(screen.getByText("Rekordbox-id rb-a")).toBeInTheDocument();
    // Still fully reviewable: the lookup only decorates the card.
    fireEvent.keyDown(queue(), { key: "a" });
    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith(
        "/api/sync/sessions/{session_id}/tracks/{track_id}/accept",
        expect.objectContaining({ body: { rb_content_id: "rb-a" } }),
      ),
    );
  });

  it("orders the queue by the Match-overzicht sort control", () => {
    const first = track({ id: 21, title: "Zebra", match_score: 60, candidates: [] });
    const second = track({ id: 22, title: "Alpha", match_score: 90, candidates: [] });
    const onResolved = vi.fn().mockResolvedValue(undefined);

    const { rerender } = render(
      <ReviewView session={session([first, second])} onResolved={onResolved} sort="score" />,
    );
    const byScore = screen
      .getAllByTestId("review-queue-item")
      .map((item) => (item.textContent ?? "").match(/Alpha|Zebra/)?.[0]);
    expect(byScore).toEqual(["Alpha", "Zebra"]);

    rerender(
      <ReviewView session={session([first, second])} onResolved={onResolved} sort="position" />,
    );
    const byPosition = screen
      .getAllByTestId("review-queue-item")
      .map((item) => (item.textContent ?? "").match(/Alpha|Zebra/)?.[0]);
    expect(byPosition).toEqual(["Zebra", "Alpha"]);
  });

  it("reports an unreachable backend in Dutch instead of crashing", async () => {
    vi.mocked(apiClient.POST).mockRejectedValue(new Error("network down"));
    renderView();

    fireEvent.keyDown(queue(), { key: "r" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "De Companion-server is niet bereikbaar.",
    );
  });
});
