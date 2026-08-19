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
}
