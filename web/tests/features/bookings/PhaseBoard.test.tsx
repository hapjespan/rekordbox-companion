// The phase columns and the move-between-phases interaction (HANDOFF.md
// "3. Playlist builder"). The keyboard path is the one that has to work:
// accessible name, announcement, focus following the moved row into its new
// column. Pointer dragging is the addition on top of it.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { PhaseBoard } from "../../../src/features/bookings/PhaseBoard";
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

// The two rows GET .../nodes/{nid}/tracks returns for the first phase: one
// analysed by Rekordbox, one not (null BPM and null key, never a 0).
function track(id: string, title: string, overrides: Partial<PhaseTrack> = {}): PhaseTrack {
  return {
    rb_content_id: id,
    artist: "Artiest",
    title,
    bpm: null,
    musical_key: null,
    duration_ms: null,
    ...overrides,
  };
}

const ANALYSED = { bpm: 124, musical_key: "8m", duration_ms: 300_000 };

// A harness that owns the membership, the way BookingWorkspace does: the move
// has to land in the rendered tree for the focus assertion to mean anything.
function Harness({ onMove }: { onMove?: () => void }) {
  const [members, setMembers] = useState<Record<number, PhaseTrack[]>>({
    1: [track("a", "One More Time", ANALYSED), track("b", "Digital Love")],
    2: [],
  });

  return (
    <PhaseBoard
      phases={buildPhases(NODES, members)}
      onMove={async (rbContentId, fromNodeId, toNodeId) => {
        onMove?.();
        setMembers((current) => {
          const moved = current[fromNodeId].find((row) => row.rb_content_id === rbContentId);
          if (!moved) return current;
          return {
            ...current,
            [fromNodeId]: current[fromNodeId].filter((row) => row.rb_content_id !== rbContentId),
            [toNodeId]: [...current[toNodeId], moved],
          };
        });
        return null;
      }}
    />
  );
}

describe("PhaseBoard", () => {
  it("renders one column per phase with its name, duration and rule text", () => {
    render(<Harness />);

    const column = screen.getByRole("heading", { name: "vooravond" }).closest("li");
    expect(column).not.toBeNull();
    expect(within(column as HTMLElement).getByText("≥ 5 min")).toBeInTheDocument();
    expect(
      within(column as HTMLElement).getByText("Ontvangst · 124 BPM · 2 nummers"),
    ).toBeInTheDocument();
    expect(within(column as HTMLElement).getByText("124 BPM")).toBeInTheDocument();
    expect(within(column as HTMLElement).getByText("8m")).toBeInTheDocument();
  });

  it("renders a phase's rows in the order it was given, and claims nothing else about it", () => {
    // The board used to carry a caveat line: its rows came from the
    // Suggestions endpoint's play-count ranking, not from the phase's stored
    // order. They now come from the node's own tracks endpoint, in stored
    // order, so the caveat is gone and must not come back.
    render(<Harness />);

    const column = screen.getByRole("heading", { name: "vooravond" }).closest("li") as HTMLElement;
    const text = column.textContent ?? "";
    expect(text.indexOf("One More Time")).toBeGreaterThanOrEqual(0);
    expect(text.indexOf("One More Time")).toBeLessThan(text.indexOf("Digital Love"));
    expect(screen.queryByText(/De volgorde binnen een fase/)).not.toBeInTheDocument();
    expect(screen.queryByText(/afspeelfrequentie/)).not.toBeInTheDocument();
  });

  it("says a track has no BPM and no key instead of leaving the cells blank", () => {
    render(<Harness />);

    const row = screen.getByText("Digital Love").closest("li");
    expect(within(row as HTMLElement).getByText("geen BPM")).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText("geen toonaard")).toBeInTheDocument();
  });

  it("offers a keyboard-operable move with an accessible name naming track and phase", () => {
    render(<Harness />);

    const button = screen.getByRole("button", {
      name: "Verplaats One More Time naar fase prime",
    });
    expect(button).toBeInTheDocument();
    // No move to a phase that does not exist on that side.
    expect(
      screen.queryByRole("button", { name: /Verplaats One More Time naar fase vooravond/ }),
    ).not.toBeInTheDocument();
  });

  it("moves the track, announces it, and keeps focus on the moved row in its new column", async () => {
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);

    const button = screen.getByRole("button", {
      name: "Verplaats One More Time naar fase prime",
    });
    button.focus();
    fireEvent.click(button);

    await waitFor(() => {
      expect(onMove).toHaveBeenCalledTimes(1);
    });
    const primeColumn = screen.getByRole("heading", { name: "prime" }).closest("li");
    await waitFor(() => {
      expect(within(primeColumn as HTMLElement).getByText("One More Time")).toBeInTheDocument();
    });
    expect(screen.getByRole("status")).toHaveTextContent(
      "One More Time verplaatst van fase vooravond naar fase prime.",
    );
    // Focus followed the row: the button now under focus is the one that moves
    // it back, inside the destination column.
    await waitFor(() => {
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: "Verplaats One More Time naar fase vooravond" }),
      );
    });
  });

  it("also accepts a pointer drag onto another phase column", async () => {
    const onMove = vi.fn();
    render(<Harness onMove={onMove} />);

    const row = screen.getByText("One More Time").closest("li") as HTMLElement;
    const primeColumn = screen.getByRole("heading", { name: "prime" }).closest("li") as HTMLElement;
    fireEvent.dragStart(row);
    fireEvent.dragOver(primeColumn);
    fireEvent.drop(primeColumn);

    await waitFor(() => {
      expect(onMove).toHaveBeenCalledTimes(1);
    });
    expect(within(primeColumn).getByText("One More Time")).toBeInTheDocument();
  });

  it("shows the move refusal without moving anything", async () => {
    render(
      <PhaseBoard
        phases={buildPhases(NODES, { 1: [track("a", "One More Time", ANALYSED)], 2: [] })}
        onMove={async () => "Deze fase is al toegepast in Rekordbox; verplaats het nummer daar."}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "Verplaats One More Time naar fase prime" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Deze fase is al toegepast in Rekordbox; verplaats het nummer daar.",
    );
  });

  it("says a structure has no phases yet instead of inventing four", () => {
    render(<PhaseBoard phases={[]} onMove={async () => null} />);

    expect(screen.getByText(/Deze structuur heeft nog geen fases/)).toBeInTheDocument();
  });

  // Review finding: a phase whose own tracks endpoint failed (409
  // collection_not_indexed, or a deleted structure/node) used to render
  // exactly like a phase that genuinely has zero tracks.
  it("says a phase could not be read instead of rendering it as empty", () => {
    const phases = buildPhases(NODES, { 1: [] }, { 1: "De collectie is nog niet ingelezen." });

    render(<PhaseBoard phases={phases} onMove={async () => null} />);

    const column = screen.getByRole("heading", { name: "vooravond" }).closest("li") as HTMLElement;
    expect(within(column).getByRole("alert")).toHaveTextContent(
      "De collectie is nog niet ingelezen.",
    );
    expect(within(column).queryByText("Nog geen nummers in deze fase.")).not.toBeInTheDocument();
    // The meta line must not still claim "0 nummers" beside that alert.
    expect(within(column).queryByText(/0 nummers/)).not.toBeInTheDocument();
  });
});
