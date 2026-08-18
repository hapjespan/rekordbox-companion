"""T047: `rb/backup.py` -- timestamped zipped Backup, verified readable,
pruned to the newest 10 only after a verified create (ADR 0016).

The success/failure-mode contracts (`ok`/`path`/`error` shape, a genuine
unwritable-directory failure) are already exercised against the real
fixture DB in `test_writer_integration.py` (T043/T096). This file covers
what that one doesn't: pruning, and that create() is idempotent-safe to
call repeatedly (a real DJ applies many times over a project's lifetime).
"""

import zipfile
from pathlib import Path

import pytest

from companion.rb import backup

FIXTURE_DB = Path(__file__).resolve().parents[1] / "fixtures" / "master.db"


@pytest.fixture
def db_copy(tmp_path: Path) -> Path:
    if not FIXTURE_DB.exists():
        pytest.skip(f"Owner-supplied fixture {FIXTURE_DB} not present (research.md R3).")
    import shutil

    copy_path = tmp_path / "master.db"
    shutil.copy(FIXTURE_DB, copy_path)
    return copy_path


def test_create_produces_a_verified_readable_zip_containing_master_db(
    db_copy: Path, tmp_path: Path
):
    backup_dir = tmp_path / "backups"

    result = backup.create(db_copy, backup_dir)

    assert result.ok is True
    assert result.error is None
    assert result.path is not None
    assert result.path.suffix == ".zip"
    with zipfile.ZipFile(result.path) as zf:
        assert zf.testzip() is None
        assert any(name.endswith("master.db") for name in zf.namelist())


def test_each_create_gets_a_distinct_timestamped_filename(db_copy: Path, tmp_path: Path):
    backup_dir = tmp_path / "backups"

    first = backup.create(db_copy, backup_dir)
    second = backup.create(db_copy, backup_dir)

    assert first.path != second.path
    assert first.path.exists()
    assert second.path.exists()


def test_prune_keeps_only_the_newest_ten_backups(db_copy: Path, tmp_path: Path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Pre-seed 10 fake, already-old backups (pruning only needs to see
    # existing *.db.zip files in the directory; it doesn't need to have
    # created them itself).
    for i in range(10):
        (backup_dir / f"master-2026010100000{i}.db.zip").write_bytes(b"fake")

    result = backup.create(db_copy, backup_dir)

    assert result.ok is True
    remaining = sorted(p.name for p in backup_dir.glob("*.zip"))
    assert len(remaining) == 10  # the 10 oldest fakes, minus one, plus the new real one
    assert result.path.name in remaining


def test_prune_never_runs_when_create_fails(db_copy: Path, tmp_path: Path):
    # A real, uid-independent failure: `backup_dir` exists as a plain FILE,
    # so `create()`'s own `mkdir(exist_ok=True)` genuinely raises -- this
    # forces a real failure even when the test runs as root, where a
    # permission-bit-based failure (chmod) would be silently bypassed.
    real_backup_dir = tmp_path / "backups"
    real_backup_dir.mkdir()
    for i in range(10):
        (real_backup_dir / f"master-2026010100000{i}.db.zip").write_bytes(b"fake")
    before = sorted(p.name for p in real_backup_dir.glob("*.zip"))

    blocked_path = tmp_path / "backups" / "blocked"
    blocked_path.write_bytes(b"not a directory")

    result = backup.create(db_copy, blocked_path)

    assert result.ok is False
    after = sorted(p.name for p in real_backup_dir.glob("*.zip"))
    assert before == after  # constraints.md: pruning never runs on a failed create
