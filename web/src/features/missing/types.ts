export type MissingTrackStatus = "open" | "acquired" | "ignored";

export interface MissingTrackDto {
  id: number;
  artist: string;
  title: string;
  status: MissingTrackStatus;
  itunes_url_auto: string | null;
  itunes_url_chosen: string | null;
  effective_url: string | null;
  no_link_found: boolean;
  // FR-041 (ADR 0021): the automatic pick's own 30 second store preview and
  // its storefront price. Every one of the three is independently absent:
  // a track can have no preview, and a streaming-only or album-only track
  // has no single-track price, so neither may be assumed present just
  // because a link resolved.
  itunes_preview_url: string | null;
  itunes_price: number | null;
  itunes_currency: string | null;
  // ADR 0022: the Spotify track id this Missing Track originated from.
  // Nullable because SyncTrack.spotify_track_id itself is (a local/
  // unavailable Spotify track); the buy queue plays through Spotify when
  // this is present and falls back to the store preview above when it is
  // absent, exactly like an SDK/account error does.
  //
  // GET /api/missing returns a plain dict (no Pydantic response_model), so
  // this field -- like every other field on this type -- has no generated
  // counterpart in src/api/generated/schema.d.ts; this hand-written type is
  // the contract, kept in step with contracts/api.md by hand (same
  // precedent as itunes_preview_url/itunes_price/itunes_currency above).
  spotify_track_id: string | null;
}
