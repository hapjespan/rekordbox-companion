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
}
