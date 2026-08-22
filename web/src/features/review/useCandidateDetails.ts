import { useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import { asApiResponse } from "../spotify-sync/types";

// GET /api/collection's row shape (contracts/api.md, engine
// api/collection.py). `musical_key` is verbatim Rekordbox notation ("8m",
// "2d", "G m"), never converted, and both it and `label` are independently
// nullable. `bpm` is null for a track Rekordbox has not analysed -- never 0,
// which would be an absence rendered as a measurement.
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

// Only the candidate ids matter now: the lookup is exact, so the Spotify
// artist and title it used to guess a query from are no longer part of it.
export interface CandidateLookupItem {
  candidates: { rb_content_id: string }[];
}

// `?ids=` is capped at 200 values per request (`_MAX_IDS` in engine
// api/collection.py, `422 too_many_ids` above it), and `limit` at the same
// 200 -- deliberately equal, so one request can return every id it asked for
// in a single page. A session with more candidates than that is batched.
export const MAX_IDS_PER_REQUEST = 200;

// Resolves the Rekordbox side of a review card.
//
// A candidate row of GET /api/sync/sessions/{id} carries `{rb_content_id,
// score, reason}` only -- no artist, title, duration, BPM or key. The ids are
// resolved exactly, through GET /api/collection's `?ids=` filter: one request
// for every candidate of every card in the queue, no query guessing, and no
// dependence on a candidate's artist or title resembling the Spotify side.
//
// Cost: one request per 200 unresolved candidate ids, so one for any real
// review queue. Every row that comes back is cached by `rb_content_id` for
// the whole session, so no card ever re-fetches. An id the collection does
// not know is simply absent from the answer (the endpoint's documented
// behaviour, not an error) and is never asked for again: the card then names
// that candidate by its Rekordbox id, which is honest rather than wrong, and
// stays fully reviewable.
export function useCandidateDetails(
  items: CandidateLookupItem[],
): Map<string, CollectionTrackDetail> {
  const [details, setDetails] = useState<Map<string, CollectionTrackDetail>>(new Map());
  // Ids the endpoint has already answered for, found or not. Without this an
  // id the collection genuinely does not have would be requested again on
  // every render that changes the queue.
  const answeredIds = useRef(new Set<string>());
  // The effect reads the ids through a ref and keys off their signature, so it
  // re-runs when the set of still-unknown ids changes and not on every render
  // of the parent.
  const pendingIdsRef = useRef<string[]>([]);
  // Deliberate render-time write, read back on the next line and in the
  // effect below: this is what lets the effect key off the *signature* of
  // the still-unknown ids instead of re-running on every render of the
  // parent. react-hooks 7's refs rule flags any ref read during render, but
  // there is no re-render loop here -- the ref is fully recomputed before
  // being read, every render, not carried over stale from a previous one.
  /* eslint-disable react-hooks/refs */
  pendingIdsRef.current = [
    ...new Set(items.flatMap((item) => item.candidates.map((c) => c.rb_content_id))),
  ].filter((id) => !details.has(id) && !answeredIds.current.has(id));
  const pendingSignature = pendingIdsRef.current.join(",");
  /* eslint-enable react-hooks/refs */

  useEffect(() => {
    const ids = pendingIdsRef.current;
    if (ids.length === 0) return;
    let cancelled = false;

    // null means the request itself failed (offline, backend down), which is
    // not an answer about these ids: they are left out of `answeredIds`
    // below. An empty array is different -- the endpoint saying it does not
    // have them -- and those ids ARE marked answered. Note that "left
    // pending" is not automatically retried: a retry needs `pendingSignature`
    // to change, which needs a re-render with `found.size > 0` (see
    // `resolve()`), and a wholly failed batch never sets that. In practice
    // the ids only get another attempt if a later render adds a new,
    // still-unresolved id to the queue (which changes `pendingSignature` on
    // its own) -- never on their own account.
    async function fetchBatch(batch: string[]): Promise<CollectionTrackDetail[] | null> {
      try {
        const { data, error } = await apiClient.GET("/api/collection", {
          params: { query: { ids: batch, limit: MAX_IDS_PER_REQUEST } },
        });
        if (error) return null;
        return asApiResponse<CollectionPage | undefined>(data)?.items ?? [];
      } catch {
        // A failed decoration lookup is not a failed review: the card falls
        // back to naming the candidate by its Rekordbox id (visible, not
        // silent), and the DJ can still accept, reject and preview.
        return null;
      }
    }

    async function resolve() {
      const found = new Map<string, CollectionTrackDetail>();
      for (let start = 0; start < ids.length; start += MAX_IDS_PER_REQUEST) {
        const batch = ids.slice(start, start + MAX_IDS_PER_REQUEST);
        const rows = await fetchBatch(batch);
        if (cancelled) return;
        if (rows === null) break;
        for (const id of batch) answeredIds.current.add(id);
        for (const row of rows) found.set(row.rb_content_id, row);
      }
      if (found.size > 0) setDetails((current) => new Map([...current, ...found]));
    }

    void resolve();
    return () => {
      cancelled = true;
    };
  }, [pendingSignature]);

  return details;
}
