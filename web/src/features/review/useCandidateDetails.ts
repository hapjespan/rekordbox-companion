import { useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";

// GET /api/collection's row shape (contracts/api.md, engine
// api/collection.py). `musical_key` is verbatim Rekordbox notation ("8m",
// "2d", "G m"), never converted, and both it and `label` are independently
// nullable.
export interface CollectionTrackDetail {
  rb_content_id: string;
  artist: string;
  title: string;
  duration_ms: number | null;
  bpm: number | null;
  musical_key: string | null;
  label: string | null;
}

interface CollectionPage {
  total: number;
  items: CollectionTrackDetail[];
}

export interface CandidateLookupItem {
  spotify_artist: string;
  spotify_title: string;
  candidates: { rb_content_id: string }[];
}

// The endpoint's own maximum (`_MAX_LIMIT` in engine api/collection.py).
const PAGE_LIMIT = 200;

// Resolves the Rekordbox side of a review card.
//
// A candidate row of GET /api/sync/sessions/{id} carries `{rb_content_id,
// score, reason}` only -- no artist, title, duration, BPM or key -- and the
// API has NO per-id collection lookup. So the ids are resolved through the
// one endpoint that does return those fields, GET /api/collection, using its
// `query` filter: the backend matches the normalised query as a substring of
// a track's normalised artist OR title, and a review candidate scored 75-92
// against exactly that artist/title pair, so the Spotify artist (and failing
// that, the Spotify title) is the cheapest query that is likely to contain
// the candidate.
//
// Cost: at most two requests per review track, each of at most 200 rows, and
// only for tracks that still have an unresolved candidate. Every row that
// comes back is cached by `rb_content_id` for the whole session, so cards
// sharing an artist cost nothing extra and no card ever re-fetches. What this
// cannot guarantee is a hit: an artist with more than 200 collection tracks,
// or a candidate whose artist and title both differ too much from the
// Spotify side, stays unresolved -- the card then names it by its Rekordbox
// id, which is honest rather than wrong. A real per-id endpoint (GET
// /api/collection/{rb_content_id}, or an `ids=` filter) would make this exact
// and one request; that is a backend change, out of this task's scope.
export function useCandidateDetails(
  items: CandidateLookupItem[],
): Map<string, CollectionTrackDetail> {
  const [details, setDetails] = useState<Map<string, CollectionTrackDetail>>(new Map());
  // Query strings already spent. A lookup that found nothing must never be
  // retried, or an unresolvable candidate would loop this effect forever.
  const attemptedQueries = useRef(new Set<string>());
  const itemsRef = useRef(items);
  itemsRef.current = items;

  // The effect keys off the ids still missing, not off `items` (a fresh array
  // on every parent render): resolving some ids shortens this signature and
  // re-runs the effect for the rest, and resolving none leaves it unchanged,
  // so the run stops by itself.
  const unresolvedSignature = items
    .flatMap((item) => item.candidates.map((candidate) => candidate.rb_content_id))
    .filter((id) => !details.has(id))
    .join(",");

  useEffect(() => {
    if (unresolvedSignature === "") return;
    let cancelled = false;

    async function fetchPage(query: string): Promise<CollectionTrackDetail[]> {
      try {
        const { data, error } = await apiClient.GET("/api/collection", {
          params: { query: { query, limit: PAGE_LIMIT } },
        });
        if (error) return [];
        return asApiResponse<CollectionPage | undefined>(data)?.items ?? [];
      } catch {
        // A failed decoration lookup is not a failed review: the card falls
        // back to naming the candidate by its Rekordbox id (visible, not
        // silent), and the DJ can still accept, reject and preview.
        return [];
      }
    }

    async function resolve() {
      const found = new Map<string, CollectionTrackDetail>();
      for (const item of itemsRef.current) {
        const stillMissing = () =>
          item.candidates.some(
            (candidate) =>
              !details.has(candidate.rb_content_id) && !found.has(candidate.rb_content_id),
          );
        for (const query of [item.spotify_artist, item.spotify_title]) {
          if (cancelled || !stillMissing()) break;
          if (query.trim() === "" || attemptedQueries.current.has(query)) continue;
          attemptedQueries.current.add(query);
          for (const row of await fetchPage(query)) found.set(row.rb_content_id, row);
        }
      }
      if (!cancelled && found.size > 0) {
        setDetails((current) => new Map([...current, ...found]));
      }
    }

    void resolve();
    return () => {
      cancelled = true;
    };
    // `items`/`details` are deliberately not dependencies: the effect reads
    // them through a ref and through the signature above, which is what keeps
    // it from re-running on every render of the parent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unresolvedSignature]);

  return details;
}
