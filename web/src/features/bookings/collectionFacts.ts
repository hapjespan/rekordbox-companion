// Resolving a phase playlist's `rb_content_id`s to BPM, musical key and
// duration.
//
// The node track rows the Playlist builder renders carry an id and nothing
// else, and `GET /api/collection` has no per-id lookup: it pages
// (`?limit=&offset=`, capped at 200 rows per page by the backend) or filters
// by a free-text `?query=` over artist/title. So the cheapest correct thing
// available is a paged sweep that stops the moment every wanted id is
// resolved, with every row it passes cached for the rest of the session --
// one request for the owner's 119-track fixture, and never a fetch per row.
//
// Above `MAX_COLLECTION_PAGES` pages the sweep gives up rather than walking a
// 40.000-track collection page by page: the unresolved ids come back to the
// caller and render as "onbekend", never as a fabricated BPM or key. The real
// fix is a per-id (or `?ids=`) collection endpoint; that is a backend change
// and is reported rather than faked here.

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";
import type { TrackFacts } from "./phaseModel";

// The backend caps `limit` at 200 (api/collection.py `_MAX_LIMIT`).
export const COLLECTION_PAGE_SIZE = 200;
export const MAX_COLLECTION_PAGES = 10;

interface CollectionRowDto {
  rb_content_id: string;
  bpm: number | null;
  musical_key: string | null;
  duration_ms: number | null;
}

interface CollectionPageDto {
  total: number;
  items: CollectionRowDto[];
}

export interface FactsResolution {
  facts: Map<string, TrackFacts>;
  unresolved: string[];
}

export async function resolveTrackFacts(
  ids: string[],
  cache: Map<string, TrackFacts>,
): Promise<FactsResolution> {
  const wanted = new Set(ids.filter((id) => !cache.has(id)));
  let page = 0;
  let total = Number.POSITIVE_INFINITY;

  while (wanted.size > 0 && page < MAX_COLLECTION_PAGES && page * COLLECTION_PAGE_SIZE < total) {
    let body: CollectionPageDto | undefined;
    try {
      const { data } = await apiClient.GET("/api/collection", {
        params: { query: { limit: COLLECTION_PAGE_SIZE, offset: page * COLLECTION_PAGE_SIZE } },
      });
      body = asApiResponse<CollectionPageDto | undefined>(data);
    } catch {
      // A failed sweep degrades to "unknown" for the ids it never reached,
      // which the UI states in words -- it never invents values and never
      // takes the view down with it.
      break;
    }
    if (!body) break;
    total = body.total;
    for (const row of body.items ?? []) {
      cache.set(row.rb_content_id, {
        bpm: row.bpm,
        musical_key: row.musical_key,
        duration_ms: row.duration_ms,
      });
      wanted.delete(row.rb_content_id);
    }
    if ((body.items ?? []).length === 0) break;
    page += 1;
  }

  return { facts: cache, unresolved: [...wanted] };
}
