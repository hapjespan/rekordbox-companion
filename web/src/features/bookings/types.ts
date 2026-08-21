export interface StructureDto {
  id: number;
  name: string;
  booking_profile_id: number | null;
  created_at: string;
  last_applied_at: string | null;
}

export interface ProfileDto {
  id: number;
  name: string;
  slug: string;
  bpm_min: number | null;
  bpm_max: number | null;
  genre_tags: string[];
}

export interface SuggestionDto {
  rb_content_id: string;
  artist: string;
  title: string;
  bpm: number | null;
  play_count: number;
  already_in_playlist: boolean;
}

export interface NodeApplyResultDto {
  node_id: number;
  rb_ref: string;
  created: boolean;
  tracks_added: number;
  tracks_already_present: number;
  readback_ok: boolean;
}

export interface ApplyResultDto {
  nodes: NodeApplyResultDto[];
  backup_path: string;
  readback_ok: boolean;
}
