"""T047: `rb/backup.py` -- timestamped zipped Backup, verified readable,
pruned to the newest 10 only after a verified create (ADR 0016).

The success/failure-mode contracts (`ok`/`path`/`error` shape, a genuine
unwritable-directory failure) are already exercised against the real
fixture DB in `test_writer_integration.py` (T043/T096). This file covers
what that one doesn't: pruning, that create() is idempotent-safe to call
repeatedly (a real DJ applies many times over a project's lifetime), and
(backlog B2) that a backup taken while committed data sits only in a
`-wal` actually captures it.
"""

import shutil
import zipfile
from pathlib import Path

import pytest
from pyrekordbox.db6.database import Rekordbox6Database

from companion.rb import backup

FIXTURE_DB = Path(__file__).resolve().parents[1] / "fixtures" / "master.db"


@pytest.fixture
def db_copy(tmp_path: Path) -> Path:
    if not FIXTURE_DB.exists():
        pytest.skip(f"Owner-supplied fixture {FIXTURE_DB} not present (research.md R3).")

    copy_path = tmp_path / "master.db"
    shutil.copy(FIXTURE_DB, copy_path)
    return copy_path


def _wal_path(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + "-wal")


def _commit_playlist_leaving_it_only_in_the_wal(db_path: Path, name: str) -> str:
    """Create a real playlist against `db_path` and commit it, WITHOUT
    checkpointing -- the same real mechanism backlog B2 observed: pyrekordbox
    opens `master.db` in WAL mode (proven earlier against this fixture), and
    `Rekordbox6Database.close()` never checkpoints, so a small committed
    transaction routinely sits only in `-wal` until SQLite's own
    `wal_autocheckpoint` (default: every 1000 pages) eventually catches up.
    Returns the new playlist's id so the caller can look for it later.
    """
    db = Rekordbox6Database(path=str(db_path))
    try:
        playlist = db.create_playlist(name, parent=None)
        db.commit()
        playlist_id = str(playlist.ID)
    finally:
        db.close()

    wal = _wal_path(db_path)
    assert wal.exists() and wal.stat().st_size > 0, (
        "test setup didn't actually produce a pending -wal -- this test would "
        "pass vacuously against any backup.create() implementation"
    )
    return playlist_id


def _extract_member(zip_path: Path, member: str, dest: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(member) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out)
    return dest


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


def test_create_captures_committed_data_that_only_lives_in_the_wal(db_copy: Path, tmp_path: Path):
    """Backlog B2, made concrete: build the exact real state that was
    observed in the wild (a committed transaction sitting only in `-wal`),
    then prove the backup contains it -- not just that create() succeeds.

    This must fail against the pre-fix implementation, which zipped
    `db_path` directly: a zip made from the base file alone, opened with no
    `-wal` beside it, would simply not have the playlist.
    """
    backup_dir = tmp_path / "backups"
    playlist_id = _commit_playlist_leaving_it_only_in_the_wal(db_copy, "WAL-only playlist")

    result = backup.create(db_copy, backup_dir)
    assert result.ok is True, result.error

    # Extract ONLY the zip's master.db member -- no sidecar exists in the zip
    # at all (asserted below) -- and open it completely on its own, exactly
    # as a real restore would, to prove the committed data survived without
    # needing a `-wal` alongside it.
    restored = tmp_path / "restored.db"
    _extract_member(result.path, "master.db", restored)
    assert not _wal_path(restored).exists()

    db = Rekordbox6Database(path=str(restored))
    try:
        playlist = db.get_playlist(ID=playlist_id)
    finally:
        db.close()
    assert playlist is not None
    assert playlist.Name == "WAL-only playlist"


def test_create_never_puts_wal_or_shm_sidecars_in_the_zip(db_copy: Path, tmp_path: Path):
    """The checkpoint-a-copy fix (backlog B2) means the zip is always a
    single self-contained base file -- never a base file plus sidecars a
    restore would have to put back together correctly."""
    backup_dir = tmp_path / "backups"
    _commit_playlist_leaving_it_only_in_the_wal(db_copy, "another WAL-only playlist")

    result = backup.create(db_copy, backup_dir)

    assert result.ok is True, result.error
    with zipfile.ZipFile(result.path) as zf:
        names = zf.namelist()
    assert names.count("master.db") == 1
    assert not any(name.endswith(("-wal", "-shm")) for name in names)


def test_create_never_opens_a_live_connection_against_the_real_db_path(
    db_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Project rule 2: no write to the real `master.db` outside `rb/writer.py`.
    `create()`'s checkpoint must run against a disposable staging copy, never
    against `db_path` itself.

    Proven directly (a `Rekordbox6Database` is never even constructed with
    `db_path` as its target) rather than by diffing the file's bytes before
    and after: pyrekordbox's own SQLAlchemy connection pool can trigger
    SQLite's automatic checkpoint-on-last-close for an *earlier, unrelated*
    connection to `db_path` on its own schedule (observed directly: closing a
    session leaves the pooled DBAPI connection open, and disposing the engine
    triggers an immediate checkpoint) -- so the file's bytes can legitimately
    change for reasons that have nothing to do with `create()`. "Never opened"
    is the reliable signal; "byte-identical" is not.
    """
    backup_dir = tmp_path / "backups"
    _commit_playlist_leaving_it_only_in_the_wal(db_copy, "untouched-source playlist")

    opened_paths: list[str] = []
    real_cls = backup.Rekordbox6Database

    class _SpyingRekordbox6Database(real_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            opened_paths.append(str(kwargs.get("path") or args[0]))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(backup, "Rekordbox6Database", _SpyingRekordbox6Database)

    result = backup.create(db_copy, backup_dir)

    assert result.ok is True, result.error
    assert str(db_copy) not in opened_paths
    assert len(opened_paths) >= 2  # the staging checkpoint open, and the verify-readable open


def test_prune_keeps_only_the_newest_ten_backups_with_a_wal_pending(db_copy: Path, tmp_path: Path):
    """Rotation (ADR 0016) must keep holding even when the checkpoint step
    added by the B2 fix is actually exercised, not just on a quiescent DB."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for i in range(10):
        (backup_dir / f"master-2026010100000{i}.db.zip").write_bytes(b"fake")
    _commit_playlist_leaving_it_only_in_the_wal(db_copy, "rotation-check playlist")

    result = backup.create(db_copy, backup_dir)

    assert result.ok is True, result.error
    remaining = sorted(p.name for p in backup_dir.glob("*.zip"))
    assert len(remaining) == 10
    assert result.path.name in remaining
