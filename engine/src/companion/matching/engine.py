"""T025: tiered matching pipeline (FR-005..FR-008).

Tiers, thresholds and the duration-penalty/remix-veto design decisions are
pinned by T021's tests (`engine/tests/matching/test_engine.py`):
  1. ISRC exact match on both sides -> matched (score 100.0).
  2. Normalised artist+title exact equality AND duration within 3s ->
     matched (score 100.0), unless the remix veto applies.
  3. Otherwise: rapidfuzz token_set_ratio on normalised artist (40%) and
     title (60%), penalised 2 points per second (fractional, not rounded to
     a whole second) beyond a 5s grace, then 92+ -> matched, 75-92 ->
     review, <75 -> missing.
Remix veto (FR-008): whenever the two sides' remix/edit markers differ, tiers 2
and 3 may not auto-match. The veto only demotes (ADR 0019): a pair that would
clear a bar drops into "review", while a pair scoring below 75 stays "missing",
because FR-007 and scenario 5 are unconditional about that and a promoted pair
could never become a Missing Track. Tier 1 (an ISRC match, definitionally the
same recording) is unaffected.

`collection`'s `norm_artist`/`norm_title`/`remix_tokens` are PRECOMPUTED
(data-model.md's "Matching engine seam" note, ADR 0012) -- this module never
re-normalises the collection side, only the `spotify` side (once per call).
"""

from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz, process

from companion.matching.normalize import extract_remix_tokens, normalize

_TIER2_DURATION_GRACE_MS = 3_000
_TIER3_DURATION_GRACE_S = 5
_DURATION_PENALTY_PER_SECOND = 2
_AUTO_MATCH_BAR = 92
_REVIEW_BAR = 75
_ARTIST_WEIGHT = 0.4
_TITLE_WEIGHT = 0.6


@dataclass(frozen=True)
class MatchResult:
    status: str
    score: float


def _duration_diff_ms(spotify: dict, collection: dict) -> int | None:
    if spotify.get("duration_ms") is None or collection.get("duration_ms") is None:
        return None
    return abs(spotify["duration_ms"] - collection["duration_ms"])


def classify_match(spotify: dict, collection: dict) -> MatchResult:
    spotify_isrc = spotify.get("isrc")
    collection_isrc = collection.get("isrc")
    if spotify_isrc and collection_isrc and spotify_isrc == collection_isrc:
        return MatchResult(status="matched", score=100.0)

    spotify_norm_artist = normalize(spotify["artist"])
    spotify_norm_title = normalize(spotify["title"])
    spotify_remix_tokens = extract_remix_tokens(spotify["title"])
    remix_differs = spotify_remix_tokens != tuple(collection.get("remix_tokens", ()))

    duration_diff = _duration_diff_ms(spotify, collection)
    exact_text_match = (
        spotify_norm_artist == collection["norm_artist"]
        and spotify_norm_title == collection["norm_title"]
    )
    if exact_text_match and duration_diff is not None and duration_diff <= _TIER2_DURATION_GRACE_MS:
        if remix_differs:
            return MatchResult(status="review", score=100.0)
        return MatchResult(status="matched", score=100.0)

    artist_score = fuzz.token_set_ratio(spotify_norm_artist, collection["norm_artist"])
    title_score = fuzz.token_set_ratio(spotify_norm_title, collection["norm_title"])
    score = _ARTIST_WEIGHT * artist_score + _TITLE_WEIGHT * title_score

    if duration_diff is not None:
        excess_seconds = max(0.0, duration_diff / 1000 - _TIER3_DURATION_GRACE_S)
        score = max(0.0, score - excess_seconds * _DURATION_PENALTY_PER_SECOND)

    # The veto only ever demotes (ADR 0019): it blocks an auto-match, it does
    # not lift a sub-75 pair into review. Promoting would make a remix-marked
    # track the DJ doesn't own impossible to buy, since it would never become a
    # Missing Track.
    if score >= _AUTO_MATCH_BAR and not remix_differs:
        return MatchResult(status="matched", score=score)
    if score >= _REVIEW_BAR:
        return MatchResult(status="review", score=score)
    return MatchResult(status="missing", score=score)


_MAX_CANDIDATES = 3


def find_best_match(
    spotify: dict, collection: list[dict]
) -> tuple[MatchResult, str | None, list[dict]]:
    """Score `spotify` against every entry in `collection`, returning the
    winning `MatchResult`, that entry's `rb_content_id` (only set when the
    result is "matched"), and up to the top 3 candidates for a "review"
    result (data-model.md's `sync_track.candidates`, FR-007's "top 3
    candidates"). `collection` entries carry `rb_content_id` alongside the
    precomputed fields `classify_match` reads.

    This is the search/ranking step `classify_match` deliberately doesn't do
    itself (it only classifies ONE pair) -- a gap identified while building
    T028 (`POST /api/sync/sessions`, which needs to find a Spotify track's
    best candidate among up to ~40k Collection entries, not just classify a
    single given pair), not something task text for T025/T028 spelled out.

    ISRC (tier 1) is checked as its own lane BEFORE the general score sort,
    exactly like `find_best_matches`' `isrc_index` lookup, rather than
    relying on `classify_match`'s tier-1/tier-2 results both scoring 100.0
    to sort together (phase-7 review finding): a vetoed tier-2 entry (remix
    markers differ, forced to "review" at score 100.0) can appear earlier in
    `collection` than a genuine ISRC match (also score 100.0, "matched") --
    sorting by score alone is a tie there, and Python's stable sort would
    then let COLLECTION ORDER, not match quality, decide the winner. An ISRC
    match is definitionally the same recording (FR-005), so it must win that
    tie unconditionally, not just when it happens to sort first.
    """
    if not collection:
        return MatchResult(status="missing", score=0.0), None, []

    spotify_isrc = spotify.get("isrc")
    if spotify_isrc:
        for entry in collection:
            if entry.get("isrc") == spotify_isrc:
                return MatchResult(status="matched", score=100.0), entry["rb_content_id"], []

    scored = sorted(
        ((classify_match(spotify, entry), entry) for entry in collection),
        key=lambda pair: pair[0].score,
        reverse=True,
    )
    best_result, best_entry = scored[0]

    if best_result.status == "matched":
        return best_result, best_entry["rb_content_id"], []
    if best_result.status == "review":
        candidates = [
            {"rb_content_id": entry["rb_content_id"], "score": result.score, "reason": "fuzzy"}
            for result, entry in scored[:_MAX_CANDIDATES]
        ]
        return best_result, None, candidates
    return best_result, None, []


def find_best_matches(
    tracks: list[dict], collection: list[dict]
) -> list[tuple[MatchResult, str | None, list[dict]]]:
    """Batched `find_best_match` for many Spotify tracks against one
    Collection (T097 perf finding).

    Calling `find_best_match` once per track -- `classify_match` against
    every Collection entry, in a Python loop -- cannot meet SC-001's time
    budget at Collection scale (~40k entries, phase-3 grilling): benchmarked
    at ~10us/`classify_match` call, a 999-track playlist against 40k entries
    is ~40M calls, ~400s, blowing the 5-minute cap. `rapidfuzz.process.cdist`
    scores an entire batch of queries against an entire batch of choices in
    C in one call (~150x faster in practice here) -- this function uses one
    `cdist` call for all tracks' artists and one for all tracks' titles,
    tiers 1/2 as O(1) dict lookups (built once, not scanned per track), and
    numpy-vectorised duration penalties instead of a nested Python loop.

    Produces the SAME results as calling `find_best_match` once per track for
    the same inputs (proven by a differential test in test_engine.py) -- this
    is purely a performance rewrite, not a behaviour change.
    """
    if not tracks:
        return []
    if not collection:
        return [(MatchResult(status="missing", score=0.0), None, []) for _ in tracks]

    collection_artists = [entry["norm_artist"] for entry in collection]
    collection_titles = [entry["norm_title"] for entry in collection]
    collection_remix = [tuple(entry.get("remix_tokens", ())) for entry in collection]
    collection_durations = np.array(
        [
            entry["duration_ms"] if entry.get("duration_ms") is not None else np.nan
            for entry in collection
        ],
        dtype=float,
    )

    isrc_index: dict[str, int] = {}
    for idx, entry in enumerate(collection):
        isrc = entry.get("isrc")
        if isrc:
            isrc_index.setdefault(isrc, idx)

    text_index: dict[tuple[str, str], list[int]] = {}
    for idx in range(len(collection)):
        text_index.setdefault((collection_artists[idx], collection_titles[idx]), []).append(idx)

    artist_queries = [normalize(track["artist"]) for track in tracks]
    title_queries = [normalize(track["title"]) for track in tracks]
    artist_scores = process.cdist(artist_queries, collection_artists, scorer=fuzz.token_set_ratio)
    title_scores = process.cdist(title_queries, collection_titles, scorer=fuzz.token_set_ratio)
    weighted = _ARTIST_WEIGHT * artist_scores + _TITLE_WEIGHT * title_scores

    def top_candidates(scores_row: np.ndarray) -> list[dict]:
        # Stable sort on the negated scores, not `argsort(...)[::-1]`: a
        # stable ascending sort followed by reversal also reverses tied
        # entries' relative order, but find_best_match's `sorted(...,
        # reverse=True)` (Python's sort is stable both ways) keeps ties in
        # their original Collection order -- this matches that for entries
        # tied on score (a real case: several unrelated Collection entries
        # can score identically low against one query).
        top_indices = np.argsort(-scores_row, kind="stable")[:_MAX_CANDIDATES]
        return [
            {
                "rb_content_id": collection[i]["rb_content_id"],
                "score": float(scores_row[i]),
                "reason": "fuzzy",
            }
            for i in top_indices
        ]

    results: list[tuple[MatchResult, str | None, list[dict]]] = []
    for row, spotify in enumerate(tracks):
        spotify_isrc = spotify.get("isrc")
        duration_ms = spotify.get("duration_ms")
        spotify_remix = extract_remix_tokens(spotify["title"])

        isrc_hit = isrc_index.get(spotify_isrc) if spotify_isrc else None
        if isrc_hit is not None:
            rb_content_id = collection[isrc_hit]["rb_content_id"]
            results.append((MatchResult(status="matched", score=100.0), rb_content_id, []))
            continue

        # Computed unconditionally (not just in the tier-3 fallback below):
        # a tier-2 hit whose remix veto forces "review" still needs these
        # scores to build its candidates list, exactly as find_best_match's
        # per-entry classify_match + sort-by-score would (a Collection can
        # legitimately hold both a track and its own remix side by side).
        scores_row = weighted[row].copy()
        if duration_ms is not None:
            diff_s = np.abs(duration_ms - collection_durations) / 1000
            excess = np.nan_to_num(np.maximum(0.0, diff_s - _TIER3_DURATION_GRACE_S), nan=0.0)
            scores_row = scores_row - excess * _DURATION_PENALTY_PER_SECOND
        scores_row = np.maximum(scores_row, 0.0)

        tier2_hit = None
        for idx in text_index.get((artist_queries[row], title_queries[row]), []):
            entry_duration = collection_durations[idx]
            if duration_ms is None or np.isnan(entry_duration):
                continue
            if abs(duration_ms - entry_duration) <= _TIER2_DURATION_GRACE_MS:
                tier2_hit = idx
                break
        if tier2_hit is not None:
            if spotify_remix != collection_remix[tier2_hit]:
                # classify_match pins an exact-text tier-2 pair's score to
                # 100.0 regardless of the fuzzy formula; match that before
                # ranking candidates, so the vetoed entry itself still
                # surfaces top-1 the way find_best_match's per-entry sort
                # would produce. In practice the vectorised fuzzy score at
                # this index is already ~100 anyway (identical normalised
                # text scores 100 via token_set_ratio, and tier 2's 3s
                # duration grace sits inside tier 3's 5s penalty-free grace,
                # so no penalty applies) -- this line only changes anything
                # in a degenerate case (e.g. an empty-string normalised
                # match), but is kept unconditional so that invariant
                # between the two grace periods is never load-bearing for
                # correctness, only for this being usually a no-op.
                scores_row[tier2_hit] = 100.0
                results.append(
                    (MatchResult(status="review", score=100.0), None, top_candidates(scores_row))
                )
            else:
                rb_content_id = collection[tier2_hit]["rb_content_id"]
                results.append((MatchResult(status="matched", score=100.0), rb_content_id, []))
            continue

        best_idx = int(np.argmax(scores_row))
        best_score = float(scores_row[best_idx])
        remix_differs = spotify_remix != collection_remix[best_idx]

        # Same demote-only veto as `classify_match` (ADR 0019); the two must
        # agree, which the differential test pins.
        if best_score >= _AUTO_MATCH_BAR and not remix_differs:
            rb_content_id = collection[best_idx]["rb_content_id"]
            results.append((MatchResult(status="matched", score=best_score), rb_content_id, []))
        elif best_score >= _REVIEW_BAR:
            candidates = top_candidates(scores_row)
            results.append((MatchResult(status="review", score=best_score), None, candidates))
        else:
            results.append((MatchResult(status="missing", score=best_score), None, []))

    return results
