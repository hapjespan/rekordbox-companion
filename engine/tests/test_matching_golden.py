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
"""

from pathlib import Path

import yaml
from companion.matching.engine import classify_match

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "matching_golden.yaml"
BASELINE_PATH = Path(__file__).resolve().parent / "fixtures" / "matching_golden_baseline.txt"


def _load_cases():
    data = yaml.safe_load(FIXTURE_PATH.read_text())
    return data["cases"]


def _load_baseline_ids():
    lines = BASELINE_PATH.read_text().splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def test_golden_set_passes_100_percent():
    failures = []
    for case in _load_cases():
        result = classify_match(case["spotify"], case["collection"])
        if result.status != case["expected_status"]:
            failures.append(
                f"{case['id']}: expected {case['expected_status']!r}, "
                f"got {result.status!r} (score={result.score})"
            )
    assert not failures, "\n" + "\n".join(failures)


def test_golden_set_only_ever_grows():
    """FR-009 / project rule 7: only ever extended, never weakened.

    Every id recorded in matching_golden_baseline.txt must still exist in
    the live fixture. Removing or renaming a case fails this; adding a new
    case to the fixture without also adding its id to the baseline (in the
    same commit) is the expected, required step for extending the set.
    """
    current_ids = {case["id"] for case in _load_cases()}
    baseline_ids = _load_baseline_ids()

    missing = baseline_ids - current_ids
    assert not missing, f"case id(s) removed from the golden set: {sorted(missing)}"


def test_every_case_id_is_unique():
    ids = [case["id"] for case in _load_cases()]
    assert len(ids) == len(set(ids)), "duplicate case ids in matching_golden.yaml"
