"""T025: tiered matching pipeline (FR-005..FR-008).

Tiers, thresholds and the duration-penalty/remix-veto design decisions are
pinned by T021's tests (`engine/tests/matching/test_engine.py`):
  1. ISRC exact match on both sides -> matched (score 100.0).
  2. Normalised artist+title exact equality AND duration within 3s ->
     matched (score 100.0), unless the remix veto applies.
  3. Otherwise: rapidfuzz token_set_ratio on normalised artist (40%) and
     title (60%), penalised 2 points per whole second beyond a 5s grace,
     then 92+ -> matched, 75-92 -> review, <75 -> missing.
Remix veto (FR-008): whenever the two sides' remix/edit markers differ,
tiers 2 and 3 are forced to "review" regardless of score; tier 1 (an ISRC
match, definitionally the same recording) is unaffected.

`collection`'s `norm_artist`/`norm_title`/`remix_tokens` are PRECOMPUTED
(data-model.md's "Matching engine seam" note, ADR 0012) -- this module never
re-normalises the collection side, only the `spotify` side (once per call).
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

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

    if remix_differs:
        return MatchResult(status="review", score=score)
    if score >= _AUTO_MATCH_BAR:
        return MatchResult(status="matched", score=score)
    if score >= _REVIEW_BAR:
        return MatchResult(status="review", score=score)
    return MatchResult(status="missing", score=score)
