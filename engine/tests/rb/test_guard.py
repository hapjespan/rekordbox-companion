"""T046: rb/guard.py -- the write-refusal gate (FR-015).

These tests exercise `guard.check()` directly (not through the API): the
three OS-level dependencies are monkeypatched so guard's own ordering and
result logic runs against controlled inputs. The all-clear case uses a real
`tmp_path` file so a real filesystem supplies ample headroom for a
byte-sized dummy, rather than mocking `disk_usage`.

Monkeypatch targets match the module-attribute access guard.py uses:
`companion.rb.reader.is_rekordbox_running` / `.detect_rekordbox` (guard
reaches these via the `reader` module object) and
`companion.rb.guard.shutil.disk_usage`.
"""

from pathlib import Path

from companion.rb import guard
from companion.rb.reader import RekordboxDetection


def _detection(db_path: Path, *, version="7.2.17", version_pin_ok=True) -> RekordboxDetection:
    return RekordboxDetection(
        installed=True,
        version=version,
        version_pin_ok=version_pin_ok,
        db_path=db_path,
        db_file_exists=True,
    )


def _dummy_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "master.db"
    db_path.write_bytes(b"0" * 1024)
    return db_path


def test_check_passes_when_closed_version_matches_and_disk_has_headroom(monkeypatch, tmp_path):
    db_path = _dummy_db(tmp_path)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(db_path))

    result = guard.check(db_path)

    assert result.ok is True
    assert result.code is None
    assert result.message is None


def test_check_refuses_when_rekordbox_is_running(monkeypatch, tmp_path):
    db_path = _dummy_db(tmp_path)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: True)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(db_path))

    result = guard.check(db_path)

    assert result.ok is False
    assert result.code == "rekordbox_running"
    assert result.message


def test_check_refuses_when_version_does_not_match_the_pin(monkeypatch, tmp_path):
    db_path = _dummy_db(tmp_path)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr(
        "companion.rb.reader.detect_rekordbox",
        lambda: _detection(db_path, version="7.1.0", version_pin_ok=False),
    )

    result = guard.check(db_path)

    assert result.ok is False
    assert result.code == "version_mismatch"
    # Message names both the found and the required version (US3 scenario 3).
    assert "7.1.0" in result.message
    assert "7.2.17" in result.message


def test_check_refuses_when_disk_headroom_is_insufficient(monkeypatch, tmp_path):
    db_path = _dummy_db(tmp_path)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(db_path))
    # Far below 2x the 1024-byte dummy file's size.
    monkeypatch.setattr(
        "companion.rb.guard.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 1})(),
    )

    result = guard.check(db_path)

    assert result.ok is False
    assert result.code == "insufficient_disk"
    assert result.message


def test_check_refuses_exactly_at_the_headroom_boundary(monkeypatch, tmp_path):
    # Requirement is `free >= 2 * size`; one byte short must refuse.
    db_path = _dummy_db(tmp_path)
    size = db_path.stat().st_size
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(db_path))
    monkeypatch.setattr(
        "companion.rb.guard.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 2 * size - 1})(),
    )

    result = guard.check(db_path)

    assert result.ok is False
    assert result.code == "insufficient_disk"


def test_check_passes_exactly_at_the_headroom_boundary(monkeypatch, tmp_path):
    # The other half of the boundary (test above pins "one byte short
    # refuses"): exactly 2x must pass, not just "far above" (review finding).
    db_path = _dummy_db(tmp_path)
    size = db_path.stat().st_size
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(db_path))
    monkeypatch.setattr(
        "companion.rb.guard.shutil.disk_usage",
        lambda path: type("Usage", (), {"free": 2 * size})(),
    )

    result = guard.check(db_path)

    assert result.ok is True


def test_check_refuses_when_the_database_file_is_missing(monkeypatch, tmp_path):
    # reader.py's own documented edge case: pyrekordbox's config can resolve
    # a path from install-time settings without the file still being there
    # (moved/deleted since). Must refuse cleanly, not crash on `.stat()`
    # (review finding: this previously raised an unhandled FileNotFoundError).
    missing_path = tmp_path / "master.db"  # never created
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr("companion.rb.reader.detect_rekordbox", lambda: _detection(missing_path))

    result = guard.check(missing_path)

    assert result.ok is False
    assert result.code == "version_mismatch"
    assert result.message


def test_check_refuses_when_db_path_is_none(monkeypatch):
    # Rekordbox not installed at all: reader.detect_rekordbox().db_path is
    # None. The endpoint (sync.py) passes this straight through rather than
    # special-casing it -- check() itself must refuse cleanly.
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: False)
    monkeypatch.setattr(
        "companion.rb.reader.detect_rekordbox",
        lambda: RekordboxDetection(
            installed=False, version=None, version_pin_ok=False, db_path=None, db_file_exists=False
        ),
    )

    result = guard.check(None)

    assert result.ok is False
    assert result.code == "version_mismatch"


def test_running_check_wins_when_both_running_and_version_mismatch(monkeypatch, tmp_path):
    # Order of precedence (FR-015 list order): running is the first check,
    # so it must win even when the version is also wrong.
    db_path = _dummy_db(tmp_path)
    monkeypatch.setattr("companion.rb.reader.is_rekordbox_running", lambda: True)
    monkeypatch.setattr(
        "companion.rb.reader.detect_rekordbox",
        lambda: _detection(db_path, version="7.1.0", version_pin_ok=False),
    )

    result = guard.check(db_path)

    assert result.ok is False
    assert result.code == "rekordbox_running"
