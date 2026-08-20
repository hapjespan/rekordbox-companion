// Shared types for the spotify-sync feature.
//
// The backend's response bodies aren't declared with a Pydantic
// `response_model` yet (engine/src/companion/api/sync.py, api/auth.py), so
// the generated OpenAPI client types every response `unknown` -- pre-
// existing debt across every router (T028 review finding), not something
// this frontend task's scope extends to fixing. These interfaces mirror
// contracts/api.md's documented shapes by hand instead.

// Single, grep-able cast point for every `unknown` response body (T031/
// T102/T032 review finding: scattered `as X` casts per call site are harder
// to find and harden later than one named function). Still just a cast, not
// runtime validation -- the real fix is a `response_model=` on each FastAPI
// route, out of scope for this frontend task.
export function asApiResponse<T>(data: unknown): T {
  return data as T;
}

export type TrackStatus = "matched" | "review" | "missing" | "rejected" | "unmatchable";

// Shared Dutch labels/order for a totals breakdown (T032's MatchReport and
// T041's QueueComplete both render "label: count" for the same five
// statuses; a single source avoids the two drifting apart).
export const TRACK_STATUS_LABELS: Record<TrackStatus, string> = {
  matched: "Gematcht",
  review: "Controleren",
  missing: "Ontbreekt",
  rejected: "Afgewezen",
  unmatchable: "Niet matchbaar",
};

export const TRACK_STATUS_ORDER: TrackStatus[] = [
  "matched",
  "review",
  "missing",
  "rejected",
  "unmatchable",
];

export interface SyncTotals {
  matched: number;
  review: number;
  missing: number;
  rejected: number;
  unmatchable: number;
}

export interface SyncTrack {
  id: number;
  position: number;
  spotify_track_id: string | null;
  isrc: string | null;
  artist: string;
  title: string;
  duration_ms: number | null;
  status: TrackStatus;
  rb_content_id: string | null;
  match_score: number | null;
  candidates: Array<{ rb_content_id: string; score: number; reason: string }>;
  matched_at: string | null;
}

export interface SyncSession {
  id: number;
  playlist_link_id: number;
  spotify_snapshot_id: string;
  name: string;
  status: "fetching" | "matching" | "ready" | "applied" | "failed";
  created_at: string;
  totals: SyncTotals;
}

export interface SyncSessionDetail extends SyncSession {
  tracks: SyncTrack[];
}

export interface SpotifyConnectionStatus {
  connected: boolean;
  display_name: string | null;
  product: string | null;
}

export interface ApiError {
  code: string;
  message: string;
  field?: string;
}
