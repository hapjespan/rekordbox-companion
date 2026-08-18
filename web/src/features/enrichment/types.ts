export interface EnrichmentStatusDto {
  pending: number;
  done: number;
  none_found: number;
  failed: number;
  coverage_pct: number;
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
