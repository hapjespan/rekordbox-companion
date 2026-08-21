// T023: Vitest for the match report table (WCAG: status conveyed in text,
// not colour alone; contracts/api.md's SyncSession.totals / SyncTrack).
//
// Props shape pinned here since web/src/features/spotify-sync/MatchReport.tsx
// doesn't exist until T032 builds it (Implementation for User Story 1):
//   totals: { matched, review, missing, rejected, unmatchable } (contracts/api.md)
//   tracks: { position, artist, title, status }[]
// UI copy is Dutch (project rule 6). Status labels are asserted by their
// Dutch text content, never by CSS class or colour, so this test doubles as
// the WCAG "text, not colour alone" acceptance check (spec.md US1). All five
// `sync_track.status` values (data-model.md) get a pinned Dutch label here,
// not just the three most common ones (T023 review finding) -- T032 must
// not be able to ship without deciding a label for `rejected`/`unmatchable`:
//   matched -> "Gematcht", review -> "Controleren", missing -> "Ontbreekt",
//   rejected -> "Afgewezen", unmatchable -> "Niet matchbaar"
// The totals summary renders each count paired with its own label in one
// text node ("Gematcht: 12"), not bare numbers (T023 review finding: bare
// numbers can collide with unrelated digits elsewhere on the page, e.g. a
// track's playlist `position`), so asserting on it is a real check of the
// `totals` prop being used, not a coincidental substring match.
//
// Committed RED: the component doesn't exist until T032 (owner-confirmed
// US1 red/green split, same as T019-T022).
//
// The delivered design's Missing group (HANDOFF.md, "1. Match-overzicht")
// lives in the same module and is covered in its own describe block below.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MatchReport, MissingTracks } from "../../../src/features/spotify-sync/MatchReport";

const TRACKS = [
  { position: 1, artist: "Daft Punk", title: "One More Time", status: "matched" as const },
  { position: 2, artist: "Example Artist", title: "Example Song", status: "review" as const },
  { position: 3, artist: "Nobody At All", title: "Nothing Similar", status: "missing" as const },
  {
    position: 4,
    artist: "Wrong Match Artist",
    title: "Wrong Match Song",
    status: "rejected" as const,
  },
  { position: 5, artist: "Local File", title: "Unavailable Track", status: "unmatchable" as const },
];

const TOTALS = { matched: 12, review: 34, missing: 56, rejected: 78, unmatchable: 90 };

describe("MatchReport", () => {
  it("renders one row per track", () => {
    render(<MatchReport totals={TOTALS} tracks={TRACKS} />);

    expect(screen.getByText("Daft Punk")).toBeTruthy();
    expect(screen.getByText("Example Artist")).toBeTruthy();
    expect(screen.getByText("Nobody At All")).toBeTruthy();
    expect(screen.getByText("Wrong Match Artist")).toBeTruthy();
    expect(screen.getByText("Local File")).toBeTruthy();
  });

  it("conveys every track status as Dutch text, not colour alone", () => {
    render(<MatchReport totals={TOTALS} tracks={TRACKS} />);

    expect(screen.getByText("Gematcht")).toBeTruthy();
    expect(screen.getByText("Controleren")).toBeTruthy();
    expect(screen.getByText("Ontbreekt")).toBeTruthy();
    expect(screen.getByText("Afgewezen")).toBeTruthy();
    expect(screen.getByText("Niet matchbaar")).toBeTruthy();
  });

  it("renders each total paired with its own Dutch label", () => {
    render(<MatchReport totals={TOTALS} tracks={TRACKS} />);

    expect(screen.getByText("Gematcht: 12")).toBeTruthy();
    expect(screen.getByText("Controleren: 34")).toBeTruthy();
    expect(screen.getByText("Ontbreekt: 56")).toBeTruthy();
    expect(screen.getByText("Afgewezen: 78")).toBeTruthy();
    expect(screen.getByText("Niet matchbaar: 90")).toBeTruthy();
  });

  it("renders nothing in the table body when there are no tracks", () => {
    render(
      <MatchReport
        totals={{ matched: 0, review: 0, missing: 0, rejected: 0, unmatchable: 0 }}
        tracks={[]}
      />,
    );

    const rows = screen.queryAllByRole("row");
    // Header row only, no track rows.
    expect(rows.length).toBe(1);
  });
});

// The Missing group of the delivered design: the handoff's grid, minus the
// three columns whose values do not exist anywhere for a track that is not in
// the collection (LABEL, BPM, KEY -- see the component's own comment). These
// assertions therefore pin the ABSENCE of those columns as much as the
// presence of the rest: rendering them full of em dashes would be three
// columns of nothing.
const MISSING_TRACKS = [
  {
    position: 3,
    artist: "Anna Kovač",
    title: "Hydraulic (Original Mix)",
    status: "missing" as const,
  },
  { position: 12, artist: "Tolga Ergün", title: "Static Bloom", status: "missing" as const },
];

describe("MissingTracks", () => {
  it("renders the design's columns and no LABEL, BPM or KEY column", () => {
    render(<MissingTracks tracks={MISSING_TRACKS} onGoToBuyQueue={vi.fn()} />);

    const headers = screen.getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual(["#", "TRACK", "ACTIE"]);
    expect(screen.queryByText("LABEL")).not.toBeInTheDocument();
    expect(screen.queryByText("BPM")).not.toBeInTheDocument();
    expect(screen.queryByText("KEY")).not.toBeInTheDocument();
  });

  it("numbers every row two-digit and names artist and title", () => {
    render(<MissingTracks tracks={MISSING_TRACKS} onGoToBuyQueue={vi.fn()} />);

    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("03")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Hydraulic (Original Mix)")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Anna Kovač")).toBeInTheDocument();
    expect(within(rows[1]).getByText("12")).toBeInTheDocument();
  });

  it("its row action leads to the buy queue", () => {
    const onGoToBuyQueue = vi.fn();
    render(<MissingTracks tracks={MISSING_TRACKS} onGoToBuyQueue={onGoToBuyQueue} />);

    const buttons = screen.getAllByRole("button", { name: "Naar wachtrij" });
    expect(buttons).toHaveLength(2);
    fireEvent.click(buttons[1]);

    expect(onGoToBuyQueue).toHaveBeenCalledTimes(1);
  });

  it("says in Dutch that nothing is missing instead of rendering an empty table", () => {
    render(<MissingTracks tracks={[]} onGoToBuyQueue={vi.fn()} />);

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      screen.getByText("Geen ontbrekende nummers in deze synchronisatie."),
    ).toBeInTheDocument();
  });
});
