// The Playlist builder's derived data (HANDOFF.md "3. Playlist builder"):
// which nodes are phases, the BPM bars, and the checks bar's counts. Pure
// functions, so the honesty rules (no fabricated BPM, no fabricated energy,
// absent key is the normal case) are asserted here rather than through the DOM.
import { describe, expect, it } from "vitest";

import {
  bpmBars,
  buildPhases,
  computeChecks,
  formatDuration,
  keysCompatible,
  parseCamelot,
  phaseBpmRangeText,
  phaseDurationText,
} from "../../../src/features/bookings/phaseModel";
import type { PhaseTrack } from "../../../src/features/bookings/phaseModel";
import type { TreeNodeDto } from "../../../src/components/Tree";

function node(overrides: Partial<TreeNodeDto> & { id: number }): TreeNodeDto {
  return {
    parent_id: null,
    kind: "playlist",
    name: `Node ${overrides.id}`,
    position: overrides.id,
    set_phase: null,
    rb_ref: null,
    ...overrides,
  };
}

// A row of GET /api/structures/{id}/nodes/{nid}/tracks: the stored track with
// its collection facts already on it.
function track(id: string, overrides: Partial<PhaseTrack> = {}): PhaseTrack {
  return {
    rb_content_id: id,
    artist: `Artiest ${id}`,
    title: `Titel ${id}`,
    bpm: null,
    musical_key: null,
    duration_ms: null,
    ...overrides,
  };
}

describe("buildPhases", () => {
  it("makes one phase per playlist node that carries a set_phase, in position order", () => {
    const nodes = [
      node({ id: 3, name: "Prime time", position: 2, set_phase: "prime" }),
      node({ id: 1, name: "Vooravond", position: 0, set_phase: "vooravond" }),
    ];

    const phases = buildPhases(nodes, {});

    expect(phases.map((phase) => phase.label)).toEqual(["vooravond", "prime"]);
    expect(phases.map((phase) => phase.node_name)).toEqual(["Vooravond", "Prime time"]);
  });

  it("never invents a phase for a folder, a phaseless playlist or a blank set_phase", () => {
    const nodes = [
      node({ id: 1, kind: "folder", set_phase: "prime" }),
      node({ id: 2, set_phase: null }),
      node({ id: 3, set_phase: "   " }),
    ];

    expect(buildPhases(nodes, {})).toEqual([]);
  });

  it("keeps the node tracks endpoint's own order and its null BPM and key", () => {
    const nodes = [node({ id: 1, set_phase: "mid" })];
    const stored = {
      1: [
        track("a", { bpm: 124, musical_key: "8m", duration_ms: 300_000 }),
        // Rekordbox has not analysed this one: null, never a 0 BPM.
        track("b"),
      ],
    };

    const [phase] = buildPhases(nodes, stored);

    expect(phase.tracks.map((row) => row.rb_content_id)).toEqual(["a", "b"]);
    expect(phase.tracks[0]).toMatchObject({
      rb_content_id: "a",
      bpm: 124,
      musical_key: "8m",
      duration_ms: 300_000,
    });
    expect(phase.tracks[1]).toMatchObject({
      rb_content_id: "b",
      bpm: null,
      musical_key: null,
      duration_ms: null,
    });
  });

  it("does not re-sort a phase's stored order into something of its own", () => {
    const nodes = [node({ id: 1, set_phase: "mid" })];
    const stored = {
      1: [track("c", { bpm: 128 }), track("a", { bpm: 120 }), track("b", { bpm: 124 })],
    };

    expect(buildPhases(nodes, stored)[0].tracks.map((row) => row.rb_content_id)).toEqual([
      "c",
      "a",
      "b",
    ]);
  });

  it("marks a phase whose node was already applied to Rekordbox", () => {
    const nodes = [node({ id: 1, set_phase: "sluit", rb_ref: "rb-9" })];

    expect(buildPhases(nodes, {})[0].applied).toBe(true);
  });
});

describe("bpmBars", () => {
  const nodes = [node({ id: 1, set_phase: "vooravond" }), node({ id: 2, set_phase: "prime" })];

  it("gives a track without a BPM no bar at all instead of a fabricated height", () => {
    const phases = buildPhases(nodes, { 1: [track("a", { bpm: 120 }), track("b")] });

    const bars = bpmBars(phases);

    expect(bars[0].height_percent).toBeGreaterThan(0);
    expect(bars[1].height_percent).toBeNull();
    expect(bars[1].bpm).toBeNull();
  });

  it("scales heights between the lowest and the highest BPM present", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { bpm: 120 }), track("b", { bpm: 130 }), track("c", { bpm: 140 })],
    });

    const bars = bpmBars(phases);

    expect(bars.map((bar) => bar.height_percent)).toEqual([20, 60, 100]);
  });

  it("marks the highest BPM as the peak, which is a computed fact and not an energy guess", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { bpm: 120 }), track("b", { bpm: 138 })],
      2: [track("c", { bpm: 138 })],
    });

    const bars = bpmBars(phases);

    expect(bars.map((bar) => bar.is_peak)).toEqual([false, true, true]);
    expect(bars.map((bar) => bar.phase_label)).toEqual(["vooravond", "vooravond", "prime"]);
  });

  it("gives every bar a full height when every known BPM is the same", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { bpm: 128 }), track("b", { bpm: 128 })],
    });

    expect(bpmBars(phases).map((bar) => bar.height_percent)).toEqual([100, 100]);
  });
});

describe("parseCamelot / keysCompatible", () => {
  it("reads Rekordbox's own m/d suffix and the A/B form", () => {
    expect(parseCamelot("8m")).toEqual({ number: 8, minor: true });
    expect(parseCamelot("2d")).toEqual({ number: 2, minor: false });
    expect(parseCamelot("11A")).toEqual({ number: 11, minor: true });
    expect(parseCamelot("12B")).toEqual({ number: 12, minor: false });
  });

  it("refuses classical notation instead of guessing a Camelot number for it", () => {
    expect(parseCamelot("G m")).toBeNull();
    expect(parseCamelot("")).toBeNull();
    expect(parseCamelot(null)).toBeNull();
  });

  it("accepts the same key, a neighbour on the wheel and the relative major/minor", () => {
    expect(keysCompatible("8m", "8m")).toBe(true);
    expect(keysCompatible("8m", "9m")).toBe(true);
    expect(keysCompatible("12m", "1m")).toBe(true);
    expect(keysCompatible("8m", "8d")).toBe(true);
  });

  it("rejects a jump of more than one step and anything unparseable", () => {
    expect(keysCompatible("8m", "2d")).toBe(false);
    expect(keysCompatible("8m", "G m")).toBe(false);
    expect(keysCompatible(null, "8m")).toBe(false);
  });
});

describe("computeChecks", () => {
  const nodes = [
    node({ id: 1, name: "Vooravond", position: 0, set_phase: "vooravond" }),
    node({ id: 2, name: "Prime", position: 1, set_phase: "prime" }),
  ];

  it("reports a key conflict on the seam between two adjacent phases", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { musical_key: "1m" }), track("b", { musical_key: "8m" })],
      2: [track("c", { musical_key: "2d" })],
    });

    const checks = computeChecks(phases, []);

    // The seam is b -> c (last of vooravond, first of prime); a is interior.
    expect(checks.key_conflicts).toEqual([
      { from_phase: "vooravond", to_phase: "prime", from_key: "8m", to_key: "2d" },
    ]);
  });

  it("does not call a compatible seam a conflict", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { musical_key: "8m" })],
      2: [track("b", { musical_key: "9m" })],
    });

    expect(computeChecks(phases, []).key_conflicts).toEqual([]);
  });

  it("counts an unparseable seam key as not comparable rather than as a conflict", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { musical_key: "G m" })],
      2: [track("b", { musical_key: "9m" })],
    });

    const checks = computeChecks(phases, []);

    expect(checks.key_conflicts).toEqual([]);
    expect(checks.uncomparable_seams).toBe(1);
  });

  it("counts tracks without a BPM and without a key separately", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { bpm: 124, musical_key: "8m" }), track("b", { bpm: 130 })],
      2: [track("c")],
    });

    const checks = computeChecks(phases, []);

    expect(checks.without_bpm).toBe(1);
    expect(checks.without_key).toBe(2);
    expect(checks.track_count).toBe(3);
  });

  it("matches the still-open buy queue on artist and title, case and spacing insensitively", () => {
    const phases = buildPhases(nodes, {
      1: [track("a", { artist: "Daft Punk", title: "One More Time", bpm: 123 })],
    });

    const checks = computeChecks(phases, [
      { artist: "daft  punk", title: "ONE MORE TIME" },
      { artist: "Someone Else", title: "Other" },
    ]);

    expect(checks.in_buy_queue).toEqual([{ artist: "Daft Punk", title: "One More Time" }]);
  });
});

describe("formatting", () => {
  it("formats minutes, and hours the way the design writes them", () => {
    expect(formatDuration(28 * 60_000)).toBe("28 min");
    expect(formatDuration((2 * 60 + 14) * 60_000)).toBe("2u14");
    expect(formatDuration(0)).toBe("0 min");
  });

  it("says a phase duration is a lower bound while a track's duration is unknown", () => {
    const nodes = [node({ id: 1, set_phase: "mid" })];
    const known = buildPhases(nodes, { 1: [track("a", { duration_ms: 300_000 })] });
    const partly = buildPhases(nodes, {
      1: [track("a", { duration_ms: 300_000 }), track("b")],
    });

    expect(phaseDurationText(known[0])).toBe("5 min");
    expect(phaseDurationText(partly[0])).toBe("≥ 5 min");
    expect(phaseDurationText(buildPhases(nodes, {})[0])).toBe("duur onbekend");
  });

  it("states the BPM range actually present, never an invented rule", () => {
    const nodes = [node({ id: 1, set_phase: "mid" })];
    const range = buildPhases(nodes, {
      1: [track("a", { bpm: 122 }), track("b", { bpm: 126 })],
    });
    const single = buildPhases(nodes, { 1: [track("a", { bpm: 124 })] });

    expect(phaseBpmRangeText(range[0])).toBe("122–126 BPM");
    expect(phaseBpmRangeText(single[0])).toBe("124 BPM");
    expect(phaseBpmRangeText(buildPhases(nodes, { 1: [track("a")] })[0])).toBe("BPM onbekend");
  });
});
