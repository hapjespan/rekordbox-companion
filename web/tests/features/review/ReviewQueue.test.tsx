// T035: keyboard handling for the Review Queue (FR-011) -- arrows navigate,
// A accepts the selected candidate, R rejects (spec.md US2 acceptance
// scenarios 1-3), space previews (scenario 4, wired here as an onPreview
// callback; actual audio is DualPlayback's concern, T040, not this test).
//
// Props shape pinned here since web/src/features/review/ReviewQueue.tsx
// doesn't exist until T039 builds it:
//   items: { sync_track_id, spotify_artist, spotify_title, candidates:
//     { rb_content_id, score, artist, title }[] }[]
//   onAccept(syncTrackId, rbContentId), onReject(syncTrackId),
//   onPreview({ kind: "candidate", rbContentId } | { kind: "spotify",
//     syncTrackId })
//
// Focus is REAL DOM focus, not just visual state (T035/T036 review
// finding: an earlier draft tracked "focus" purely via aria-current/
// aria-selected attributes with no element ever actually receiving
// browser focus, which would leave a screen reader's real focus
// stranded -- failing WCAG's focus-visibility intent for US2's
// accessibility criteria even though the keyboard *operability* worked).
// The container itself (role="listbox") holds real DOM focus for the
// entire session -- it never moves away, which is what makes "focus never
// lost when an item is resolved" true in the strongest sense -- and
// `aria-activedescendant` names the active candidate, the standard WAI-ARIA
// technique for a composite widget where moving real focus per-item isn't
// practical (APG's listbox pattern).
//
// Committed RED: the component doesn't exist until T039 (owner-confirmed
// US1 red/green split, same pattern continued for US2).
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReviewQueue } from "../../../src/features/review/ReviewQueue";

const ITEMS = [
  {
    sync_track_id: 1,
    spotify_artist: "Daft Punk",
    spotify_title: "One More Time",
    candidates: [
      { rb_content_id: "rb-a", score: 88, artist: "Daft Punk", title: "One More Time (Edit)" },
      { rb_content_id: "rb-b", score: 76, artist: "Daft Punk", title: "One More Time Reprise" },
    ],
  },
  {
    sync_track_id: 2,
    spotify_artist: "Example Artist",
    spotify_title: "Example Song",
    candidates: [
      { rb_content_id: "rb-c", score: 80, artist: "Example Artist", title: "Example Song (Live)" },
    ],
  },
  {
    sync_track_id: 3,
    spotify_artist: "Nobody At All",
    spotify_title: "Nothing Similar",
    candidates: [
      {
        rb_content_id: "rb-d",
        score: 78,
        artist: "Nobody At All",
        title: "Nothing Similar (Live)",
      },
    ],
  },
];

function renderQueue(overrides = {}) {
  const onAccept = vi.fn();
  const onReject = vi.fn();
  const onPreview = vi.fn();
  render(
    <ReviewQueue
      items={ITEMS}
      onAccept={onAccept}
      onReject={onReject}
      onPreview={onPreview}
      {...overrides}
    />,
  );
  return { onAccept, onReject, onPreview };
}

function queue() {
  return screen.getByTestId("review-queue");
}

function activeCandidateId() {
  return queue().getAttribute("aria-activedescendant");
}

describe("ReviewQueue", () => {
  it("holds real DOM focus on the container and marks the first item/candidate active", () => {
    renderQueue();

    expect(document.activeElement).toBe(queue());
    const items = screen.getAllByTestId("review-queue-item");
    expect(items[0]).toHaveAttribute("aria-current", "true");
    const candidates = screen.getAllByTestId("review-queue-candidate");
    expect(activeCandidateId()).toBe(candidates[0].id);
  });

  it("ArrowDown moves the active item forward, ArrowUp moves it back", () => {
    renderQueue();

    fireEvent.keyDown(queue(), { key: "ArrowDown" });
    let items = screen.getAllByTestId("review-queue-item");
    expect(items[1]).toHaveAttribute("aria-current", "true");

    fireEvent.keyDown(queue(), { key: "ArrowUp" });
    items = screen.getAllByTestId("review-queue-item");
    expect(items[0]).toHaveAttribute("aria-current", "true");
  });

  it("ArrowUp at the first item does not wrap or move focus away", () => {
    renderQueue();

    fireEvent.keyDown(queue(), { key: "ArrowUp" });

    expect(document.activeElement).toBe(queue());
    const items = screen.getAllByTestId("review-queue-item");
    expect(items[0]).toHaveAttribute("aria-current", "true");
  });

  it("ArrowDown at the last item does not wrap", () => {
    renderQueue();

    fireEvent.keyDown(queue(), { key: "ArrowDown" });
    fireEvent.keyDown(queue(), { key: "ArrowDown" });
    fireEvent.keyDown(queue(), { key: "ArrowDown" }); // already at the last item

    const items = screen.getAllByTestId("review-queue-item");
    expect(items[2]).toHaveAttribute("aria-current", "true");
  });

  it("ArrowRight/ArrowLeft move the active candidate within the focused item", () => {
    renderQueue();

    fireEvent.keyDown(queue(), { key: "ArrowRight" });
    let candidates = screen.getAllByTestId("review-queue-candidate");
    expect(activeCandidateId()).toBe(candidates[1].id);

    fireEvent.keyDown(queue(), { key: "ArrowLeft" });
    candidates = screen.getAllByTestId("review-queue-candidate");
    expect(activeCandidateId()).toBe(candidates[0].id);
  });

  it("pressing A accepts the active candidate for the active item", () => {
    const { onAccept } = renderQueue();

    fireEvent.keyDown(queue(), { key: "ArrowRight" }); // select the 2nd candidate
    fireEvent.keyDown(queue(), { key: "a" });

    expect(onAccept).toHaveBeenCalledWith(1, "rb-b");
  });

  it("pressing R rejects the active item regardless of candidate selection", () => {
    const { onReject } = renderQueue();

    fireEvent.keyDown(queue(), { key: "r" });

    expect(onReject).toHaveBeenCalledWith(1);
  });

  it("pressing space previews the currently active candidate", () => {
    const { onPreview } = renderQueue();

    fireEvent.keyDown(queue(), { key: " " });

    expect(onPreview).toHaveBeenCalledWith({ kind: "candidate", rbContentId: "rb-a" });
  });

  it("moves the active item to whatever now occupies its position when the active item is removed", () => {
    // Simulates the parent removing an ACCEPTED/REJECTED item that was the
    // active one (not just any item): spec.md's "focus moves to the next
    // unresolved item" means the item now sitting at the resolved item's
    // old position becomes active, not that focus stays put by coincidence.
    const { rerender } = render(
      <ReviewQueue items={ITEMS} onAccept={vi.fn()} onReject={vi.fn()} onPreview={vi.fn()} />,
    );
    fireEvent.keyDown(queue(), { key: "ArrowDown" }); // active item is now index 1 (track 2)

    const remaining = [ITEMS[0], ITEMS[2]]; // track 2 (the active one) resolved and removed
    rerender(
      <ReviewQueue items={remaining} onAccept={vi.fn()} onReject={vi.fn()} onPreview={vi.fn()} />,
    );

    const items = screen.getAllByTestId("review-queue-item");
    expect(items).toHaveLength(2);
    // Track 3 now occupies index 1, the old active position, and becomes active.
    expect(items[1]).toHaveAttribute("aria-current", "true");
    expect(document.activeElement).toBe(queue());
  });

  it("resets the candidate selection when another item takes over the active position", () => {
    // The bug this pins (review finding): the candidate index survived the
    // parent removing the resolved item, so the NEXT item arrived with a
    // non-first candidate pre-selected and a rapid follow-up A accepted the
    // wrong candidate. Both items here have two candidates, so a surviving
    // index would not be clamped away.
    const secondItem = {
      sync_track_id: 9,
      spotify_artist: "Second Artist",
      spotify_title: "Second Song",
      candidates: [
        { rb_content_id: "rb-x1", score: 84, artist: "Second Artist", title: "Second Song" },
        { rb_content_id: "rb-x2", score: 62, artist: "Second Artist", title: "Second Song (Dub)" },
      ],
    };
    const onAccept = vi.fn();
    const { rerender } = render(
      <ReviewQueue
        items={[ITEMS[0], secondItem]}
        onAccept={onAccept}
        onReject={vi.fn()}
        onPreview={vi.fn()}
      />,
    );

    fireEvent.keyDown(queue(), { key: "ArrowRight" }); // 2nd candidate of item 1
    expect(activeCandidateId()).toBe("review-candidate-1-rb-b");

    // Item 1 resolved and removed by the parent; item 9 now sits at the
    // active position.
    rerender(
      <ReviewQueue
        items={[secondItem]}
        onAccept={onAccept}
        onReject={vi.fn()}
        onPreview={vi.fn()}
      />,
    );

    expect(activeCandidateId()).toBe("review-candidate-9-rb-x1");

    fireEvent.keyDown(queue(), { key: "a" });
    expect(onAccept).toHaveBeenCalledWith(9, "rb-x1");
  });

  it("reports the active item and candidate to the parent so playback can follow the selection", () => {
    const onActiveChange = vi.fn();
    render(
      <ReviewQueue
        items={ITEMS}
        onAccept={vi.fn()}
        onReject={vi.fn()}
        onPreview={vi.fn()}
        onActiveChange={onActiveChange}
      />,
    );

    expect(onActiveChange).toHaveBeenLastCalledWith(1, "rb-a");

    fireEvent.keyDown(queue(), { key: "ArrowRight" });
    expect(onActiveChange).toHaveBeenLastCalledWith(1, "rb-b");

    fireEvent.keyDown(queue(), { key: "ArrowDown" });
    expect(onActiveChange).toHaveBeenLastCalledWith(2, "rb-c");
  });

  it("identifies a candidate by its Rekordbox id when the API gives no artist/title", () => {
    // The real GET /api/sync/sessions/{id} candidate rows carry
    // {rb_content_id, score, reason} only (contracts/api.md).
    renderQueue({
      items: [
        {
          sync_track_id: 4,
          spotify_artist: "Daft Punk",
          spotify_title: "One More Time",
          candidates: [{ rb_content_id: "rb-z", score: 81 }],
        },
      ],
    });

    expect(screen.getByText(/Rekordbox-id rb-z · score 81/)).toBeInTheDocument();
  });

  // The delivered design's Uncertain group card (HANDOFF.md, "1. Match-
  // overzicht" -> Uncertain group): Spotify left, the match score in the
  // middle, the Rekordbox candidate right with duration, BPM and musical key,
  // and the two actions. Everything the keyboard already guaranteed above must
  // keep holding with those buttons on the card.
  const RESOLVED_ITEM = {
    sync_track_id: 11,
    spotify_artist: "Sora Watanabe",
    spotify_title: "Falling Light (Extended)",
    spotify_duration_ms: 432_000,
    candidates: [
      {
        rb_content_id: "rb-p",
        score: 84,
        artist: "Sora Watanabe",
        title: "Falling Light (Original Mix)",
        duration_ms: 408_000,
        bpm: 130,
        musical_key: "5A",
      },
      {
        rb_content_id: "rb-q",
        score: 71,
        artist: "Sora Watanabe",
        title: "Falling Light (Rework)",
        duration_ms: 362_000,
        bpm: 128,
        musical_key: "8B",
      },
    ],
  };

  it("shows both sides of the match, the score, and the candidate's BPM and key", () => {
    renderQueue({ items: [RESOLVED_ITEM] });

    expect(screen.getByText("SPOTIFY")).toBeInTheDocument();
    expect(screen.getByText("Falling Light (Extended)")).toBeInTheDocument();
    expect(screen.getByText("Sora Watanabe · 7:12")).toBeInTheDocument();
    expect(screen.getByText("84%")).toBeInTheDocument();
    // The design shows the bare percentage; read out of the layout it
    // needs to say what it measures, so the label is hidden, not absent.
    expect(screen.getByText("Matchscore")).toBeInTheDocument();
    expect(screen.getByText("REKORDBOX")).toBeInTheDocument();
    expect(screen.getByText("Falling Light (Original Mix)")).toBeInTheDocument();
    expect(screen.getByText("6:48 · 130 BPM · 5A")).toBeInTheDocument();
  });

  it("Andere moves to the next candidate and Bevestig accepts that one", () => {
    const onAccept = vi.fn();
    renderQueue({ items: [RESOLVED_ITEM], onAccept });

    fireEvent.click(screen.getByRole("button", { name: "Andere" }));

    expect(screen.getByText("Falling Light (Rework)")).toBeInTheDocument();
    expect(screen.getByText("6:02 · 128 BPM · 8B")).toBeInTheDocument();
    expect(activeCandidateId()).toBe("review-candidate-11-rb-q");

    fireEvent.click(screen.getByRole("button", { name: "Bevestig" }));

    expect(onAccept).toHaveBeenCalledWith(11, "rb-q");
    // A pointer action must never strand the focus on a button the next
    // render unmounts: the queue keeps it, so the keys keep working.
    expect(document.activeElement).toBe(queue());
  });

  it("keeps Andere out of the tab order's way when there is nothing to switch to", () => {
    renderQueue({
      items: [
        {
          sync_track_id: 12,
          spotify_artist: "VETA",
          spotify_title: "Ritual Machine",
          candidates: [{ rb_content_id: "rb-only", score: 68 }],
        },
      ],
    });

    expect(screen.getByRole("button", { name: "Andere" })).toBeDisabled();
  });

  it("says the Rekordbox side could not be resolved rather than inventing one", () => {
    renderQueue({
      items: [
        {
          sync_track_id: 13,
          spotify_artist: "Kamera",
          spotify_title: "Untitled B2",
          candidates: [{ rb_content_id: "rb-z", score: 81 }],
        },
      ],
    });

    expect(screen.getByText("Rekordbox-id rb-z")).toBeInTheDocument();
    expect(screen.getByText("Niet gevonden in de collectie")).toBeInTheDocument();
  });

  it("clicking a candidate row selects it for the keyboard too", () => {
    const onAccept = vi.fn();
    renderQueue({ items: [RESOLVED_ITEM], onAccept });

    fireEvent.click(screen.getAllByTestId("review-queue-candidate")[1]);
    fireEvent.keyDown(queue(), { key: "a" });

    expect(onAccept).toHaveBeenCalledWith(11, "rb-q");
  });

  it("keeps only the active card's actions in the tab order", () => {
    renderQueue();

    const others = screen.getAllByRole("button", { name: "Andere" });
    const confirms = screen.getAllByRole("button", { name: "Bevestig" });
    expect(others[0]).toHaveAttribute("tabindex", "0");
    expect(confirms[0]).toHaveAttribute("tabindex", "0");
    expect(others[1]).toHaveAttribute("tabindex", "-1");
    expect(confirms[1]).toHaveAttribute("tabindex", "-1");

    fireEvent.keyDown(queue(), { key: "ArrowDown" });

    expect(screen.getAllByRole("button", { name: "Bevestig" })[0]).toHaveAttribute(
      "tabindex",
      "-1",
    );
    expect(screen.getAllByRole("button", { name: "Bevestig" })[1]).toHaveAttribute("tabindex", "0");
  });

  it("does not also preview when space activates a focused card button", () => {
    const { onPreview } = renderQueue();

    // Space on a button is that button's own activation; the queue must not
    // fire a preview from the same press as well.
    fireEvent.keyDown(screen.getAllByRole("button", { name: "Bevestig" })[0], { key: " " });

    expect(onPreview).not.toHaveBeenCalled();
  });

  it("renders no queue items when the list is empty", () => {
    // The completion state itself is QueueComplete.tsx's job (T041, a
    // separate component) -- the parent composing them decides which to
    // render when the queue empties; ReviewQueue itself just has nothing
    // to show.
    renderQueue({ items: [] });

    expect(screen.queryAllByTestId("review-queue-item")).toHaveLength(0);
  });
});
