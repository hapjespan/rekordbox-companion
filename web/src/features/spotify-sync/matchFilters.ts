import type { TrackStatus } from "./types";

// The delivered design's filter row and sort control (HANDOFF.md,
// "1. Match-overzicht" -> Filter row), which its own notes list under
// "Intended but not built". The state lives in the view that renders the
// groups (views/MatchOverviewView.tsx), because the groups are rendered by
// two different components -- the missing table (spotify-sync/MatchReport)
// and the review cards (review/ReviewView) -- and one owner above both is
// the only way a chip can actually filter and a sort can actually reorder
// all of them.

export type MatchGroup = "missing" | "review" | "collection";

export type MatchFilter = "all" | MatchGroup;

export type MatchSort = "score" | "position" | "title";

// Chip copy is the design's, verbatim and in Dutch.
export const MATCH_FILTER_CHIPS: { value: MatchFilter; label: string }[] = [
  { value: "all", label: "Alles" },
  { value: "missing", label: "Ontbreekt" },
  { value: "review", label: "Twijfel" },
  { value: "collection", label: "In collectie" },
];

// The design shows a static "Sorteer op zekerheid" caption; WCAG 2.2 AA needs
// a real labelled control, so it is a <select> whose default option reads the
// same ("Sorteer op" + "Zekerheid").
export const MATCH_SORT_OPTIONS: { value: MatchSort; label: string }[] = [
  { value: "score", label: "Zekerheid" },
  { value: "position", label: "Positie in afspeellijst" },
  { value: "title", label: "Titel" },
];

// Which group a track belongs to. `rejected` and `unmatchable` have no group
// of their own in the design: they are review outcomes of tracks the DJ has
// already seen, so they ride along in the collection group, where every row
// states its own status in text (never colour alone).
export function groupOf(status: TrackStatus): MatchGroup {
  if (status === "missing") return "missing";
  if (status === "review") return "review";
  return "collection";
}

export function isGroupVisible(filter: MatchFilter, group: MatchGroup): boolean {
  return filter === "all" || filter === group;
}

export interface SortableTrack {
  position: number;
  title: string;
  match_score: number | null;
}

// "Zekerheid" is the match score, highest first; a track without a score is
// unranked rather than the lowest score, so it sorts last in both cases. The
// playlist position is the tiebreaker everywhere, so the order is total and
// stable regardless of the array's incoming order.
function compareTracks<T extends SortableTrack>(a: T, b: T, sort: MatchSort): number {
  if (sort === "position") return a.position - b.position;
  if (sort === "title") {
    const byTitle = a.title.localeCompare(b.title, "nl");
    return byTitle !== 0 ? byTitle : a.position - b.position;
  }
  const scoreA = a.match_score;
  const scoreB = b.match_score;
  if (scoreA === null && scoreB === null) return a.position - b.position;
  if (scoreA === null) return 1;
  if (scoreB === null) return -1;
  return scoreB - scoreA || a.position - b.position;
}

export function sortTracks<T extends SortableTrack>(tracks: T[], sort: MatchSort): T[] {
  return [...tracks].sort((a, b) => compareTracks(a, b, sort));
}
