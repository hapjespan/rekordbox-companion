// The design's curve card, plotting BPM instead of energy: no per-track energy
// value exists (Spotify's audio-features endpoint answers 403 for this
// application), so the card must not claim one, and a track without a BPM must
// not get a bar. A chart of coloured bars also needs a text alternative.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BpmProgressionCard } from "../../../src/features/bookings/BpmProgressionCard";
import { buildPhases } from "../../../src/features/bookings/phaseModel";
import type { PhaseTrack } from "../../../src/features/bookings/phaseModel";
import type { TreeNodeDto } from "../../../src/components/Tree";

const NODES: TreeNodeDto[] = [
  {
    id: 1,
    parent_id: null,
    kind: "playlist",
    name: "Ontvangst",
    position: 0,
    set_phase: "vooravond",
    rb_ref: null,
  },
  {
    id: 2,
    parent_id: null,
    kind: "playlist",
    name: "Dansvloer",
    position: 1,
    set_phase: "prime",
    rb_ref: null,
  },
];

function track(id: string, title: string, overrides: Partial<PhaseTrack> = {}): PhaseTrack {
  return {
    rb_content_id: id,
    artist: "Artiest",
    title,
    bpm: null,
    musical_key: null,
    duration_ms: 300_000,
    ...overrides,
  };
}

function renderCard() {
  return render(
    <BpmProgressionCard
      phases={buildPhases(NODES, {
        1: [
          track("a", "Laag", { bpm: 122, musical_key: "8m" }),
          // Rekordbox has not analysed this one: null, not 0.
          track("b", "Onbekend"),
        ],
        2: [track("c", "Hoog", { bpm: 138, musical_key: "9m" })],
      })}
    />,
  );
}

describe("BpmProgressionCard", () => {
  it("is titled as a BPM progression and says the bars are not an energy value", () => {
    renderCard();

    expect(screen.getByRole("heading", { name: "BPM-verloop" })).toBeInTheDocument();
    expect(screen.queryByText(/Energiecurve/)).not.toBeInTheDocument();
    expect(screen.getByText(/geen energiewaarde/)).toBeInTheDocument();
    expect(screen.getByText("122–138 BPM")).toBeInTheDocument();
  });

  it("draws one bar per track with a BPM and none at all for a track without one", () => {
    const { container } = renderCard();

    const heights = [...container.querySelectorAll("[style*='height']")].map(
      (element) => (element as HTMLElement).style.height,
    );
    expect(heights).toEqual(["20%", "100%"]);
  });

  it("offers the same numbers as a text alternative, naming the unknown BPM as unknown", () => {
    renderCard();

    const table = screen.getByRole("table");
    expect(within(table).getByRole("row", { name: /Onbekend/ })).toHaveTextContent("onbekend");
    // The peak is the highest BPM, stated in words as well as by bar height,
    // so the highlight never depends on colour.
    expect(within(table).getByRole("row", { name: /Hoog/ })).toHaveTextContent("ja");
    expect(within(table).getByRole("row", { name: /Laag/ })).toHaveTextContent("nee");
  });

  it("keeps the phase ruler under the bars", () => {
    renderCard();

    expect(screen.getAllByText("vooravond").length).toBeGreaterThan(0);
    expect(screen.getAllByText("prime").length).toBeGreaterThan(0);
  });

  it("says there is nothing to plot yet instead of drawing an empty chart", () => {
    render(<BpmProgressionCard phases={[]} />);

    expect(screen.getByText(/nog geen BPM-verloop/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
