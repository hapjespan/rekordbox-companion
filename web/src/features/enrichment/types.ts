export interface EnrichmentStatusDto {
  pending: number;
  done: number;
  none_found: number;
  failed: number;
  coverage_pct: number;
  // Server-side truth for whether a background run is currently in
  // progress (review finding): the panel derives its disabled state from
  // this, not from local `useState` alone, so a reload mid-run, a second
  // tab, or a run started before the page loaded all show the real state.
  running: boolean;
}

export interface UnenrichedTrackDto {
  rb_content_id: string;
  artist: string;
  title: string;
}

export interface EnrichmentProgressEvent {
  done: number;
  none_found: number;
  failed: number;
  remaining: number;
}
