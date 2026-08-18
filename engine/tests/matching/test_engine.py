"""T021: Unit tests for tiered scoring/classification (FR-005..FR-008).

Interface pinned in data-model.md's "Matching engine seam" note (T019 review
finding, corrected by this task's own review): `classify_match(spotify: dict,
collection: dict) -> MatchResult`. `spotify` is raw `{artist, title,
duration_ms, isrc?}`, as fetched per playlist track. `collection` carries the
PRECOMPUTED `{norm_artist, norm_title, remix_tokens, duration_ms, isrc?}`
fields of a Collection index entry, never raw `artist`/`title` --
`classify_match` is a hot loop scored against up to ~40k Collection entries
per Spotify track (phase-3 grilling), so re-normalising that side per
comparison would be O(tracks x collection) instead of the O(collection)
ADR 0012's precomputation already pays for once. `_collection()` below
builds that precomputed shape via the real `normalize`/`extract_remix_tokens`
functions, exactly as `rb/index.py`'s `CollectionIndex.rebuild()` will once
T024 replaces its placeholder. `MatchResult.status` is one of `{"matched",
"review", "missing"}`, `.score` a float 0-100.

Tiers (kickoff.md section 8, FR-005..FR-007):
  1. ISRC exact match on both sides -> matched (score fixed at 100.0).
  2. Normalised artist+title exact equality AND duration within 3s ->
     matched (score fixed at 100.0), UNLESS the remix veto (below) applies.
  3. Otherwise: rapidfuzz token_set_ratio on normalised artist (40%) and
     title (60%), penalised for duration beyond a 5s grace period, then
     92+ -> matched, 75-92 -> review, <75 -> missing.
  Remix veto (FR-008): whenever `extract_remix_tokens` disagrees between the
  two sides, tier 1 is unaffected (an ISRC match is definitionally the same
  recording) but tiers 2 and 3 are forced to "review" regardless of score --
  FR-008 says "never auto-match", not "never auto-match via fuzzy scoring
  only", so a tier-2 pair that only looks identical because remix markers
  were stripped out of the comparison text (FR-004) still needs the veto.
  Confirmed against spec.md's acceptance scenario 6 and kickoff.md section 9's
  step ordering (T020/T021 review): this reading is correct, not a gap.

One numeric design decision this test file pins, not specified beyond "a
duration penalty" (FR-007) -- T024/T025's to implement and this suite's to
hold fixed once chosen: 2 score points per second beyond the 5s grace, using
the fractional excess, not rounded to a whole second (e.g. 10s difference =
5s excess = 10 points off; a 6.5s difference would be 1.5s excess = 3 points
off -- every boundary case below uses whole-second diffs, so this fractional
behaviour isn't itself exercised by a test here, only documented accurately;
see engine.py's module docstring). Fuzzy scores are computed
by rapidfuzz.fuzz.token_set_ratio on the normalised strings, so this file's
expected numbers were read off real rapidfuzz output for the exact strings
below, not hand-derived -- an independent source of truth per the TDD
skill's anti-tautology rule.

Committed RED: `companion.matching.engine` doesn't exist until T025 builds
it, same US1 red/green split as T019/T020 (owner-confirmed).
"""

from companion.matching.engine import classify_match, find_best_match, find_best_matches
from companion.matching.normalize import extract_remix_tokens, normalize


def _collection(artist, title, duration_ms, isrc=None, rb_content_id="rb1"):
    return {
        "rb_content_id": rb_content_id,
        "norm_artist": normalize(artist),
        "norm_title": normalize(title),
        "remix_tokens": extract_remix_tokens(title),
        "duration_ms": duration_ms,
        "isrc": isrc,
    }


def test_isrc_exact_match_wins_regardless_of_text_similarity():
    spotify = {
        "artist": "Completely Different Artist",
        "title": "Completely Different Title",
        "duration_ms": 180_000,
        "isrc": "USRC17607839",
    }
    collection = _collection("Example Artist", "Example Song", 210_000, isrc="USRC17607839")

    result = classify_match(spotify, collection)

    assert result.status == "matched"
    assert result.score == 100.0


def test_isrc_mismatch_falls_through_to_text_based_tiers():
    spotify = {
        "artist": "Daft Punk",
        "title": "One More Time",
        "duration_ms": 210_000,
        "isrc": "AAAA00000001",
    }
    collection = _collection("Daft Punk", "One More Time", 210_000, isrc="BBBB00000002")

    result = classify_match(spotify, collection)

    assert result.status == "matched"


def test_exact_normalised_text_and_close_duration_auto_matches():
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("DAFT PUNK", "one more time", 211_500)

    result = classify_match(spotify, collection)

    assert result.status == "matched"
    assert result.score == 100.0


def test_exact_text_but_duration_beyond_3s_falls_to_fuzzy_tier_and_still_matches():
    # Duration diff of 5s misses tier 2's 3s window but is still within tier
    # 3's 5s penalty-free grace, so identical normalised text still matches.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("Daft Punk", "One More Time", 215_000)

    result = classify_match(spotify, collection)

    assert result.status == "matched"
    assert result.score == 100.0


def test_title_dominance_60_percent_carries_a_minor_artist_typo_to_matched():
    # rapidfuzz.fuzz.token_set_ratio("daft punk", "daft punc") == 88.888...
    # weighted 0.4*88.888... + 0.6*100 == 95.555... >= 92.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("Daft Punc", "One More Time", 210_000)

    result = classify_match(spotify, collection)

    assert result.status == "matched"
    assert round(result.score, 2) == 95.56


def test_artist_weight_40_percent_still_sinks_a_completely_different_artist():
    # rapidfuzz.fuzz.token_set_ratio("daft punk", "a totally different act") == 25.0
    # weighted 0.4*25.0 + 0.6*100 == 70.0 < 75.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("A Totally Different Act", "One More Time", 210_000)

    result = classify_match(spotify, collection)

    assert result.status == "missing"
    assert round(result.score, 2) == 70.0


def test_score_between_75_and_92_enters_review_queue():
    # Full artist match; rapidfuzz.fuzz.token_set_ratio("one more time",
    # "one more moment tonight") == 76.190...; weighted 0.4*100 + 0.6*76.19...
    # == 85.71... which is inside [75, 92).
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("Daft Punk", "One More Moment Tonight", 210_000)

    result = classify_match(spotify, collection)

    assert result.status == "review"
    assert 75 <= result.score < 92


def test_score_of_exactly_92_auto_matches():
    # Identical text (fuzzy 100) with a 9s duration diff: 4s excess * 2
    # points/s == 8 points off, landing at exactly 92 -- FR-007's "92 or
    # higher" is inclusive, so this must still auto-match, not enter review.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("Daft Punk", "One More Time", 219_000)

    result = classify_match(spotify, collection)

    assert result.score == 92.0
    assert result.status == "matched"


def test_score_of_exactly_75_enters_review_not_missing():
    # Identical text (fuzzy 100) with a 17.5s duration diff: 12.5s excess *
    # 2 points/s == 25 points off, landing at exactly 75 -- FR-007's "75 up
    # to 92" is inclusive at 75, so this must enter review, not missing.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("Daft Punk", "One More Time", 227_500)

    result = classify_match(spotify, collection)

    assert result.score == 75.0
    assert result.status == "review"


def test_duration_penalty_beyond_5s_grace_can_drop_an_otherwise_perfect_match_to_review():
    # Identical normalised text (fuzzy score 100) but a 10s difference misses
    # both tier 2 (3s) and tier 3's penalty-free grace (5s): 5s excess * 2
    # points/s == 10 points off, landing at 90 -- inside [75, 92).
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("Daft Punk", "One More Time", 220_000)

    result = classify_match(spotify, collection)

    assert result.status == "review"
    assert result.score == 90.0


def test_duration_penalty_can_drop_an_otherwise_perfect_match_to_missing():
    # 30s difference: 25s excess * 2 points/s == 50 points off, landing at 50.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = _collection("Daft Punk", "One More Time", 240_000)

    result = classify_match(spotify, collection)

    assert result.status == "missing"
    assert result.score == 50.0


def test_remix_marker_veto_forces_review_even_above_the_auto_match_bar():
    # Same case as the golden set's stub-remix-marker-veto (T019): "Example
    # Song (Club Mix)" normalises to identical text as "Example Song" (the
    # marker is extracted, not left in the comparison text), which would
    # otherwise clear both tier 2 and tier 3's auto-match bar.
    spotify = {
        "artist": "Example Artist",
        "title": "Example Song (Club Mix)",
        "duration_ms": 300_000,
    }
    collection = _collection("Example Artist", "Example Song", 300_000)

    result = classify_match(spotify, collection)

    assert result.status == "review"


def test_remix_marker_veto_leaves_a_sub_review_bar_pair_missing():
    # ADR 0019: the veto only demotes. A remix-marked Spotify track that simply
    # isn't in the Collection must stay "missing" so it becomes a Missing Track
    # and reaches the US4 purchase flow (FR-007, scenario 5). Promoting it to
    # "review" on the strength of the marker alone made it unbuyable, and
    # attached candidates that mean nothing.
    spotify = {
        "artist": "Some Artist",
        "title": "Some Song (Club Mix)",
        "duration_ms": 300_000,
    }
    collection = _collection("Wholly Unrelated Band", "Nothing Like It", 300_000)

    result = classify_match(spotify, collection)

    assert result.score < 75
    assert result.status == "missing"


def test_remix_marker_veto_does_not_apply_when_isrc_matches():
    # Tier 1 is an identifier match, definitionally the same recording, so
    # the veto does not second-guess it even if title text superficially
    # carries a remix marker on one side.
    spotify = {
        "artist": "Example Artist",
        "title": "Example Song (Club Mix)",
        "duration_ms": 300_000,
        "isrc": "USRC17607839",
    }
    collection = _collection("Example Artist", "Example Song", 300_000, isrc="USRC17607839")

    result = classify_match(spotify, collection)

    assert result.status == "matched"


def test_below_75_becomes_missing():
    spotify = {
        "artist": "Completely Different Artist",
        "title": "Completely Different Title",
        "duration_ms": 180_000,
    }
    collection = _collection("Example Artist", "Example Song", 210_000)

    result = classify_match(spotify, collection)

    assert result.status == "missing"


# --- find_best_match: the search/ranking step over many Collection entries,
# a gap identified while building T028 (POST /api/sync/sessions), not pinned
# by any task text -- see the function's own docstring in engine.py.


def test_find_best_match_returns_missing_and_no_candidates_for_an_empty_collection():
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}

    result, rb_content_id, candidates = find_best_match(spotify, [])

    assert result.status == "missing"
    assert rb_content_id is None
    assert candidates == []


def test_find_best_match_picks_the_highest_scoring_entry():
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = [
        _collection(
            "Completely Different Artist",
            "Completely Different Title",
            180_000,
            rb_content_id="rb-wrong",
        ),
        _collection("Daft Punk", "One More Time", 210_000, rb_content_id="rb-right"),
    ]

    result, rb_content_id, candidates = find_best_match(spotify, collection)

    assert result.status == "matched"
    assert rb_content_id == "rb-right"
    assert candidates == []


def test_find_best_match_returns_no_rb_content_id_for_a_review_result():
    # A "review" result (score in [75, 92)) must not hand back a confident
    # rb_content_id -- the DJ picks from candidates instead.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = [_collection("Daft Punk", "One More Moment Tonight", 210_000)]

    result, rb_content_id, candidates = find_best_match(spotify, collection)

    assert result.status == "review"
    assert rb_content_id is None
    assert len(candidates) == 1
    assert candidates[0]["rb_content_id"] == "rb1"
    assert candidates[0]["score"] == result.score


def test_find_best_match_returns_up_to_3_candidates_sorted_best_first():
    # Same review-tier title on three entries, differentiated purely by the
    # duration penalty (0s/8s/10s diff -> 85.71/79.71/75.71, all in [75, 92)),
    # plus one clearly-missing entry that must not make the top 3.
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = [
        _collection("Daft Punk", "One More Moment Tonight", 210_000, rb_content_id="rb-a"),
        _collection("Daft Punk", "One More Moment Tonight", 218_000, rb_content_id="rb-b"),
        _collection("Daft Punk", "One More Moment Tonight", 220_000, rb_content_id="rb-c"),
        _collection("Nobody At All", "Nothing Similar", 180_000, rb_content_id="rb-d"),
    ]

    result, rb_content_id, candidates = find_best_match(spotify, collection)

    assert result.status == "review"
    assert rb_content_id is None
    assert [c["rb_content_id"] for c in candidates] == ["rb-a", "rb-b", "rb-c"]
    scores = [c["score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_find_best_match_returns_no_candidates_for_a_missing_result():
    spotify = {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000}
    collection = [_collection("Nobody At All", "Nothing Similar", 180_000)]

    result, rb_content_id, candidates = find_best_match(spotify, collection)

    assert result.status == "missing"
    assert rb_content_id is None
    assert candidates == []


# --- find_best_matches: the batched, T097-perf-motivated rewrite of
# find_best_match for scoring many Spotify tracks against one Collection at
# once (rapidfuzz.process.cdist instead of a classify_match-per-entry Python
# loop). Proven equivalent to calling find_best_match once per track, not
# just independently plausible -- a differential test, not a duplicate of
# find_best_match's own tests above.


def _mixed_collection():
    return [
        _collection(
            "Example Artist", "Example Song", 210_000, isrc="USRC17607839", rb_content_id="rb-isrc"
        ),
        _collection("Daft Punk", "One More Time", 211_000, rb_content_id="rb-tier2"),
        _collection("Daft Punk", "One More Moment Tonight", 210_000, rb_content_id="rb-review-a"),
        _collection("Daft Punk", "One More Moment Tonight", 218_000, rb_content_id="rb-review-b"),
        _collection("Daft Punk", "One More Minute Tonight", 210_000, rb_content_id="rb-review-c"),
        _collection("Example Artist", "Example Song (Club Mix)", 300_000, rb_content_id="rb-remix"),
        _collection("Nobody At All", "Nothing Similar", 180_000, rb_content_id="rb-missing"),
    ]


def _mixed_tracks():
    return [
        # Tier 1: ISRC exact match.
        {"artist": "Anything", "title": "Anything", "duration_ms": 1, "isrc": "USRC17607839"},
        # Tier 2: exact normalised text, duration within 3s.
        {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 210_000},
        # Tier 3: review band (multiple close-scoring candidates).
        {"artist": "Daft Punk", "title": "One More Time", "duration_ms": 400_000},
        # Remix veto: would otherwise clear the auto-match bar via tier 2.
        {"artist": "Example Artist", "title": "Example Song", "duration_ms": 300_000},
        # Missing: nothing scores anywhere close.
        {"artist": "Totally Unrelated", "title": "Totally Unrelated", "duration_ms": 999_000},
        # Remix-marked and absent from the Collection: the veto must not lift it
        # out of "missing" (ADR 0019), or it can never become a Missing Track.
        {"artist": "Some Artist", "title": "Some Song (Club Mix)", "duration_ms": 300_000},
    ]


def test_find_best_matches_matches_find_best_match_for_the_same_inputs():
    collection = _mixed_collection()
    tracks = _mixed_tracks()

    batched = find_best_matches(tracks, collection)
    individually = [find_best_match(track, collection) for track in tracks]

    assert len(batched) == len(individually)
    for (batch_result, batch_rb_id, batch_candidates), (
        single_result,
        single_rb_id,
        single_candidates,
    ) in zip(batched, individually, strict=True):
        assert batch_result.status == single_result.status
        assert round(batch_result.score, 2) == round(single_result.score, 2)
        assert batch_rb_id == single_rb_id
        assert {c["rb_content_id"] for c in batch_candidates} == {
            c["rb_content_id"] for c in single_candidates
        }


def test_find_best_matches_matches_find_best_match_when_a_vetoed_tier2_entry_precedes_isrc():
    # Phase-7 review finding: the differential fixture above
    # (_mixed_collection/_mixed_tracks) never placed a vetoed tier-2 entry
    # (remix marker differs, forced to "review" at score 100.0) AHEAD of a
    # genuine ISRC match (also score 100.0) in collection order -- the one
    # ordering that exposed find_best_match ranking by score alone: a stable
    # sort on tied scores lets collection order, not tier, decide the
    # winner, so the earlier vetoed entry won instead of the ISRC match.
    # find_best_matches never had this bug (its ISRC lane is checked before
    # any tier-2/3 ranking, independent of collection order).
    spotify = {
        "artist": "Example Artist",
        "title": "Example Song",
        "duration_ms": 300_000,
        "isrc": "USRC17607839",
    }
    collection = [
        _collection(
            "Example Artist", "Example Song (Club Mix)", 300_000, rb_content_id="rb-vetoed"
        ),
        _collection(
            "Example Artist", "Example Song", 300_000, isrc="USRC17607839", rb_content_id="rb-isrc"
        ),
    ]
    tracks = [spotify]

    batched = find_best_matches(tracks, collection)
    individually = [find_best_match(track, collection) for track in tracks]

    assert len(batched) == len(individually) == 1
    batch_result, batch_rb_id, batch_candidates = batched[0]
    single_result, single_rb_id, single_candidates = individually[0]

    assert batch_result.status == single_result.status == "matched"
    assert batch_rb_id == single_rb_id == "rb-isrc"
    assert batch_candidates == single_candidates == []


def test_find_best_matches_returns_missing_for_every_track_against_an_empty_collection():
    tracks = _mixed_tracks()

    results = find_best_matches(tracks, [])

    assert len(results) == len(tracks)
    assert all(result.status == "missing" for result, _, _ in results)
    assert all(rb_content_id is None for _, rb_content_id, _ in results)
    assert all(candidates == [] for _, _, candidates in results)


def test_find_best_matches_returns_an_empty_list_for_no_tracks():
    assert find_best_matches([], _mixed_collection()) == []
