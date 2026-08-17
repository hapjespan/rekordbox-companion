"""T007: the golden matching-set fixture exists with a documented schema.

The real >=50-case set (>=10 hard cases, FR-009/SC-003) is an owner-supplied
input still owed (grilling D10, quickstart.md) and not required for phase 5
or the start of phase 6. This only proves the schema stub is well-formed;
the loader that gates matching changes on it is built in T019 (US1).
"""

from pathlib import Path

import yaml

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "matching_golden.yaml"

REQUIRED_CASE_FIELDS = {
    "id",
    "description",
    "hard_case",
    "spotify",
    "collection",
    "expected_status",
}
VALID_STATUSES = {"matched", "review", "missing"}


def _load():
    return yaml.safe_load(FIXTURE_PATH.read_text())


def test_fixture_file_exists():
    assert FIXTURE_PATH.exists()


def test_fixture_is_valid_yaml_with_a_cases_list():
    data = _load()
    assert isinstance(data, dict)
    assert isinstance(data["cases"], list)
    assert len(data["cases"]) >= 1  # illustrative stub only, real set is owner-supplied


def test_every_case_declares_the_required_fields():
    for case in _load()["cases"]:
        missing = REQUIRED_CASE_FIELDS - case.keys()
        assert not missing, f"case {case.get('id')!r} missing fields: {missing}"


def test_every_case_has_a_valid_expected_status():
    for case in _load()["cases"]:
        assert case["expected_status"] in VALID_STATUSES


def test_every_case_is_marked_as_a_stub_example():
    # Distinguishes illustrative cases from the real, owner-supplied set so
    # T019's loader can refuse to run "for real" against stub data only.
    for case in _load()["cases"]:
        assert case.get("stub_example") is True
