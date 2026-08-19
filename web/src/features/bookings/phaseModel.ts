// Derived data for the Playlist builder (HANDOFF.md "3. Playlist builder"),
// kept as pure functions so the honesty rules can be asserted directly:
//
// - a phase is a playlist node with a `set_phase` label, never a hardcoded
//   Warmup/Build/Peak/Outro. `set_phase` is free text and explicitly not
//   logic (ADR 0008), so nothing here reads meaning into the label.
// - the bars plot BPM, not energy. Spotify's audio-features endpoint answers
//   403 for this application, so no per-track energy value exists anywhere;
//   drawing one would be a fabricated chart. A track without a BPM gets no
//   bar rather than an invented one.
// - BPM, key and duration are absent for most of the collection (34 of 119
//   tracks carry a BPM, 7 a key in the owner's fixture), so "absent" is the
//   normal case and every formatter has to say so in words.

import type { TreeNodeDto } from "../../components/Tree";

// What the app can read about a track that sits in a phase playlist.
// `GET /api/structures/{id}/nodes/{nid}/suggestions` is the only endpoint
// that reports membership (its `already_in_playlist` flag), and it carries
// artist, title and BPM but no musical key -- hence the split between the
// member row and the collection facts resolved for it.
export interface PhaseMember {
  rb_content_id: string;
  artist: string;
  title: string;
  bpm: number | null;
}

export interface TrackFacts {
  bpm: number | null;
  musical_key: string | null;
  duration_ms: number | null;
}

export interface PhaseTrack {
  rb_content_id: string;
  artist: string;
  title: string;
  bpm: number | null;
  // Verbatim Rekordbox notation ("8m", "2d", occasionally "G m"), never
  // normalised or converted.
  musical_key: string | null;
  duration_ms: number | null;
  // false when no collection row was resolved for this id: "unknown", which
  // is a different thing from "this track has no BPM/key in Rekordbox".
  facts_resolved: boolean;
}

export interface Phase {
  node_id: number;
  label: string;
  node_name: string;
  applied: boolean;
  tracks: PhaseTrack[];
}

export interface BpmBar {
  rb_content_id: string;
  artist: string;
  title: string;
  bpm: number | null;
  phase_label: string;
  // null means "no bar": the track has no BPM, and no height may be invented.
  height_percent: number | null;
  is_peak: boolean;
}

export interface KeyConflict {
  from_phase: string;
  to_phase: string;
  from_key: string;
  to_key: string;
}

export interface ChecksResult {
  track_count: number;
  key_conflicts: KeyConflict[];
  uncomparable_seams: number;
  without_bpm: number;
  without_key: number;
  unresolved: number;
  in_buy_queue: { artist: string; title: string }[];
}

// The lowest bar still has to be visible as a bar, so the scale runs from 20%
// to 100% of the container instead of 0% to 100%.
const MIN_BAR_PERCENT = 20;

export function isPhaseNode(node: TreeNodeDto): boolean {
  return node.kind === "playlist" && (node.set_phase ?? "").trim().length > 0;
}

export function buildPhases(
  nodes: TreeNodeDto[],
  membersByNode: Record<number, PhaseMember[]>,
  facts: Map<string, TrackFacts>,
): Phase[] {
  return nodes
    .filter(isPhaseNode)
    .slice()
    .sort((a, b) => a.position - b.position)
    .map((node) => ({
      node_id: node.id,
      label: (node.set_phase ?? "").trim(),
      node_name: node.name,
      applied: node.rb_ref !== null,
      tracks: (membersByNode[node.id] ?? []).map((member) => {
        const resolved = facts.get(member.rb_content_id);
        return {
          rb_content_id: member.rb_content_id,
          artist: member.artist,
          title: member.title,
          bpm: resolved ? resolved.bpm : member.bpm,
          musical_key: resolved ? resolved.musical_key : null,
          duration_ms: resolved ? resolved.duration_ms : null,
          facts_resolved: resolved !== undefined,
        };
      }),
    }));
}

export function bpmBars(phases: Phase[]): BpmBar[] {
  const tracks = phases.flatMap((phase) =>
    phase.tracks.map((track) => ({ track, label: phase.label })),
  );
  const known = tracks.map(({ track }) => track.bpm).filter((bpm): bpm is number => bpm !== null);
  const lowest = known.length > 0 ? Math.min(...known) : null;
  const highest = known.length > 0 ? Math.max(...known) : null;

  return tracks.map(({ track, label }) => ({
    rb_content_id: track.rb_content_id,
    artist: track.artist,
    title: track.title,
    bpm: track.bpm,
    phase_label: label,
    height_percent:
      track.bpm === null || lowest === null || highest === null
        ? null
        : highest === lowest
          ? 100
          : Math.round(
              MIN_BAR_PERCENT +
                ((track.bpm - lowest) / (highest - lowest)) * (100 - MIN_BAR_PERCENT),
            ),
    // The highest BPM in the set is a fact the data supports. It is not an
    // energy peak, and the card's copy says so.
    is_peak: track.bpm !== null && track.bpm === highest,
  }));
}

export interface CamelotKey {
  number: number;
  minor: boolean;
}

// Rekordbox writes Camelot as a number plus "m" (moll/minor, the A ring) or
// "d" (dur/major, the B ring); the A/B form shows up too. Anything else
// (classical "G m", an empty string) is not a Camelot key and is never
// guessed into one.
export function parseCamelot(key: string | null): CamelotKey | null {
  if (key === null) return null;
  const match = /^\s*(\d{1,2})\s*([mdAaBb])\s*$/.exec(key);
  if (!match) return null;
  const number = Number(match[1]);
  if (number < 1 || number > 12) return null;
  const letter = match[2].toLowerCase();
  return { number, minor: letter === "m" || letter === "a" };
}

export function keysCompatible(a: string | null, b: string | null): boolean {
  const left = parseCamelot(a);
  const right = parseCamelot(b);
  if (!left || !right) return false;
  if (left.number === right.number) return true;
  if (left.minor !== right.minor) return false;
  const distance = Math.abs(left.number - right.number);
  return distance === 1 || distance === 11;
}

function normalizeForMatch(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

export function computeChecks(
  phases: Phase[],
  openBuyQueue: { artist: string; title: string }[],
): ChecksResult {
  const tracks = phases.flatMap((phase) => phase.tracks);

  const keyConflicts: KeyConflict[] = [];
  let uncomparableSeams = 0;
  // The seam between two adjacent phases is the only place a phase boundary
  // can clash: the last track of one and the first of the next.
  for (let index = 0; index < phases.length - 1; index += 1) {
    const before = phases[index].tracks.at(-1);
    const after = phases[index + 1].tracks[0];
    if (!before || !after) continue;
    const fromKey = before.musical_key;
    const toKey = after.musical_key;
    if (parseCamelot(fromKey) === null || parseCamelot(toKey) === null) {
      uncomparableSeams += 1;
      continue;
    }
    if (!keysCompatible(fromKey, toKey)) {
      keyConflicts.push({
        from_phase: phases[index].label,
        to_phase: phases[index + 1].label,
        from_key: fromKey as string,
        to_key: toKey as string,
      });
    }
  }

  const queueKeys = new Set(
    openBuyQueue.map(
      (item) => `${normalizeForMatch(item.artist)}|${normalizeForMatch(item.title)}`,
    ),
  );

  return {
    track_count: tracks.length,
    key_conflicts: keyConflicts,
    uncomparable_seams: uncomparableSeams,
    without_bpm: tracks.filter((track) => track.facts_resolved && track.bpm === null).length,
    without_key: tracks.filter((track) => track.facts_resolved && track.musical_key === null)
      .length,
    unresolved: tracks.filter((track) => !track.facts_resolved).length,
    in_buy_queue: tracks
      .filter((track) =>
        queueKeys.has(`${normalizeForMatch(track.artist)}|${normalizeForMatch(track.title)}`),
      )
      .map((track) => ({ artist: track.artist, title: track.title })),
  };
}

export function formatDuration(ms: number): string {
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours}u${String(minutes % 60).padStart(2, "0")}`;
}

export function phaseDurationText(phase: Phase): string {
  const known = phase.tracks.filter((track) => track.duration_ms !== null);
  if (known.length === 0) return "duur onbekend";
  const total = known.reduce((sum, track) => sum + (track.duration_ms ?? 0), 0);
  const text = formatDuration(total);
  return known.length === phase.tracks.length ? text : `≥ ${text}`;
}

function bpmRangeText(tracks: PhaseTrack[]): string {
  const known = tracks.map((track) => track.bpm).filter((bpm): bpm is number => bpm !== null);
  if (known.length === 0) return "BPM onbekend";
  const lowest = Math.round(Math.min(...known));
  const highest = Math.round(Math.max(...known));
  return lowest === highest ? `${lowest} BPM` : `${lowest}–${highest} BPM`;
}

export function phaseBpmRangeText(phase: Phase): string {
  return bpmRangeText(phase.tracks);
}

export function setBpmRangeText(phases: Phase[]): string {
  return bpmRangeText(phases.flatMap((phase) => phase.tracks));
}

export function setDurationText(phases: Phase[]): string {
  const tracks = phases.flatMap((phase) => phase.tracks);
  const known = tracks.filter((track) => track.duration_ms !== null);
  if (known.length === 0) return "speelduur onbekend";
  const total = known.reduce((sum, track) => sum + (track.duration_ms ?? 0), 0);
  const text = formatDuration(total);
  return known.length === tracks.length ? text : `≥ ${text}`;
}
