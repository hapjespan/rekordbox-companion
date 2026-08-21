"""T019: Golden-set contract test harness (FR-009, SC-003, US1).

Loads engine/tests/fixtures/matching_golden.yaml and runs every case through
the matching engine (matching/engine.py), asserting 100% pass. The real
>=50-case set is an owner-supplied input still owed (quickstart.md); until
then this runs against the stub examples only, per that file's own header.

This test is committed RED: `companion.matching.engine` doesn't exist until
T024/T025 build it, later in this same user story. That is a deliberate,
owner-confirmed exception to the "every task lands green" default -- tests
and implementation are split into separate task groups for every user story
from here on (tasks.md's "Tests for User Story N" / "Implementation for
User Story N" sections), so a pure-test task's commit can be red until its
paired implementation task lands, as long as the full suite is green again
by the end of the user story's arc, not after every single commit within it.

`classify_match`'s `collection` argument expects the PRECOMPUTED
`norm_artist`/`norm_title`/`remix_tokens` fields of a Collection index entry,
never raw `artist`/`title` (data-model.md's "Matching engine seam" note,
corrected by T020/T021 review -- classify_match is a hot loop scored against
up to ~40k Collection entries per Spotify track, so it must not re-normalise
that side per comparison). The golden fixture stays human-authored plain
`artist`/`title` on purpose (an owner hand-writing >=50 real cases should
never have to pre-normalise them), so `_collection_dict` bridges the two
here, the same conversion a real caller would run once per Collection index
entry at build time.
"""

import hashlib
import json
from pathlib import Path

import yaml

from companion.matching.engine import classify_match
from companion.matching.normalize import extract_remix_tokens, normalize

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "matching_golden.yaml"
BASELINE_PATH = Path(__file__).resolve().parent / "fixtures" / "matching_golden_baseline.txt"


def _collection_dict(raw: dict) -> dict:
    return {
        "norm_artist": normalize(raw["artist"]),
        "norm_title": normalize(raw["title"]),
        "remix_tokens": extract_remix_tokens(raw["title"]),
        "duration_ms": raw["duration_ms"],
        "isrc": raw.get("isrc"),
    }


def _load_cases():
    data = yaml.safe_load(FIXTURE_PATH.read_text())
    return data["cases"]


def _case_signature(case: dict) -> str:
    """Content hash of everything that actually drives a case's outcome:
    `spotify`, `collection` and `expected_status` -- NOT free-text fields
    like `description`, which are free to be clarified without triggering a
    false "edited in place" failure below.
    """
    payload = {
        "spotify": case["spotify"],
        "collection": case["collection"],
        "expected_status": case["expected_status"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _load_baseline() -> dict[str, str]:
    """Return {id: content_hash}, parsed from matching_golden_baseline.txt's
    "<id> <sha256-hex>" lines (blank lines and '#'-comments ignored)."""
    lines = BASELINE_PATH.read_text().splitlines()
    baseline = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        case_id, _, digest = stripped.partition(" ")
        baseline[case_id] = digest
    return baseline


def test_golden_set_passes_100_percent():
    failures = []
    for case in _load_cases():
        result = classify_match(case["spotify"], _collection_dict(case["collection"]))
        if result.status != case["expected_status"]:
            failures.append(
                f"{case['id']}: expected {case['expected_status']!r}, "
                f"got {result.status!r} (score={result.score})"
            )
    assert not failures, "\n" + "\n".join(failures)


def test_golden_set_only_ever_grows():
    """FR-009 / project rule 7: only ever extended, never weakened.

    Every id recorded in matching_golden_baseline.txt must still exist in
    the live fixture, AND its `spotify`/`collection`/`expected_status`
    content must still hash to the value recorded there. An id check alone
    only catches removal or renaming -- it is blind to a case's inputs being
    edited or its expected_status flipped in place, which is exactly as
    real a way to weaken the set as deleting it outright (phase-7 review
    finding; the fixture history shows this already happened once, for
    stub-fuzzy-review-tier's title, before this hash existed). Adding a new
    case to the fixture without also adding its "<id> <hash>" line to the
    baseline (in the same commit) is the expected, required step for
    extending the set.
    """
    current_cases = {case["id"]: case for case in _load_cases()}
    baseline = _load_baseline()

    missing = set(baseline) - set(current_cases)
    assert not missing, f"case id(s) removed from the golden set: {sorted(missing)}"

    changed = sorted(
        case_id
        for case_id, digest in baseline.items()
        if _case_signature(current_cases[case_id]) != digest
    )
    assert not changed, (
        "case(s) edited in place (spotify/collection/expected_status no "
        f"longer matches the recorded baseline hash): {changed}"
    )


def test_every_case_id_is_unique():
    ids = [case["id"] for case in _load_cases()]
    assert len(ids) == len(set(ids)), "duplicate case ids in matching_golden.yaml"
