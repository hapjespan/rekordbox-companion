// The checks bar shows the checks that are computable from real data, not the
// design's illustrative ones, and it does not offer the reordering action the
// owner explicitly left out.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChecksBar } from "../../../src/features/bookings/ChecksBar";
import type { ChecksResult } from "../../../src/features/bookings/phaseModel";

const EMPTY: ChecksResult = {
  track_count: 0,
  key_conflicts: [],
  uncomparable_seams: 0,
  without_bpm: 0,
  without_key: 0,
  in_buy_queue: [],
};

describe("ChecksBar", () => {
  it("names the phases and keys of every seam conflict", () => {
    render(
      <ChecksBar
        checks={{
          ...EMPTY,
          key_conflicts: [
            { from_phase: "vooravond", to_phase: "prime", from_key: "8m", to_key: "2d" },
          ],
        }}
      />,
    );

    expect(
      screen.getByText(
        "1 toonaard-conflict(en) op de fase-overgangen: vooravond → prime (8m → 2d)",
      ),
    ).toBeInTheDocument();
  });

  it("states the counts of missing BPM and missing key in words", () => {
    render(<ChecksBar checks={{ ...EMPTY, without_bpm: 3, without_key: 5 }} />);

    expect(screen.getByText("3 nummer(s) zonder BPM in Rekordbox")).toBeInTheDocument();
    expect(screen.getByText("5 nummer(s) zonder toonaard in Rekordbox")).toBeInTheDocument();
    // A phase row now comes from the node's own tracks endpoint, which serves
    // every field from the collection index: there is no "could not fetch the
    // BPM and key" state left to report.
    expect(screen.queryByText(/niet opgehaald/)).not.toBeInTheDocument();
  });

  it("lists the tracks that still sit in the buy queue", () => {
    render(
      <ChecksBar
        checks={{ ...EMPTY, in_buy_queue: [{ artist: "Daft Punk", title: "One More Time" }] }}
      />,
    );

    expect(
      screen.getByText("1 nummer(s) staan nog in de koop-wachtrij: Daft Punk – One More Time"),
    ).toBeInTheDocument();
  });

  it("reports a clean set as clean rather than hiding the checks", () => {
    render(<ChecksBar checks={EMPTY} />);

    expect(screen.getByText("Geen toonaard-conflicten op de fase-overgangen")).toBeInTheDocument();
    expect(screen.getByText("Geen nummers meer in de koop-wachtrij")).toBeInTheDocument();
  });

  it("does not offer the reordering action the owner left out of scope", () => {
    render(<ChecksBar checks={EMPTY} />);

    expect(screen.queryByText(/herordenen/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
