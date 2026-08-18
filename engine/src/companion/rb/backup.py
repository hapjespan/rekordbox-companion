"""Timestamped, verified Rekordbox database backups (FR-016, ADR 0016).

`create()` runs BEFORE `rb/writer.py` touches `db_path`, and the write must
never proceed on an unverified backup (constraints.md Retention: "A backup
that fails verification blocks the write, the same as insufficient disk
space"). Pruning to the newest 10 only ever runs immediately after a
verified-good create, never as a standalone job (ADR 0016) -- a failed
create leaves every existing backup untouched.

Zips `db_path` alongside `masterPlaylists6.xml` if present next to it (T042
spike finding: pyrekordbox looks for that file next to `master.db` and
syncs it on `commit()`; a restore missing it would be a real behavioural gap
on the Mac even though this sandbox's fixture copies never have one).

This module is in `rb/` (project rule 1) and imports pyrekordbox to verify a
backup is actually re-openable, not just a structurally valid zip -- the
whole point of "verify readability" is that the DJ could restore from this
file and have Rekordbox open it, not merely that `zipfile` didn't complain.
"""

import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pyrekordbox.db6.database import Rekordbox6Database

from companion.rb import reader  # noqa: F401 -- see rb/guard.py's ordering note (T018)

MASTER_PLAYLISTS_XML = "masterPlaylists6.xml"
KEEP_NEWEST = 10


@dataclass(frozen=True)
class BackupResult:
    ok: bool
    path: Path | None
    error: str | None


def create(db_path: Path, backup_dir: Path) -> BackupResult:
    """Create a timestamped, verified zip backup of `db_path` in `backup_dir`.

    Never raises: any failure (an unwritable directory, a corrupt zip, a
    backup that doesn't reopen) is reported as `BackupResult(ok=False, ...)`
    so the caller can refuse the write with `backup_failed`, per FR-016.
    """
    # Microsecond precision: two applies in the same wall-clock second (fully
    # possible -- e.g. a re-apply retried immediately after a refusal) must
    # never collide on the same backup filename.
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"master-{timestamp}.db.zip"

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        xml_path = db_path.parent / MASTER_PLAYLISTS_XML
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_path, arcname="master.db")
            if xml_path.is_file():
                zf.write(xml_path, arcname=MASTER_PLAYLISTS_XML)

        _verify_readable(backup_path)
    except Exception as exc:  # noqa: BLE001 -- any failure here means "not a usable backup"
        # The failure itself may mean `backup_path` was never a valid path
        # to begin with (e.g. a path component that turned out to be a
        # file, not a directory) -- cleanup must not raise a second,
        # different exception on top of the one already being reported.
        try:
            backup_path.unlink(missing_ok=True)
        except OSError:
            pass
        return BackupResult(ok=False, path=None, error=str(exc))

    _prune_old_backups(backup_dir)
    return BackupResult(ok=True, path=backup_path, error=None)


def _verify_readable(backup_path: Path) -> None:
    """Raise if `backup_path` is not a genuinely restorable backup.

    Two layers: the zip itself must be structurally intact (`testzip()`),
    and the `master.db` it contains must actually open as a real Rekordbox
    database -- a zip can be valid while the database inside it is garbage.
    """
    with zipfile.ZipFile(backup_path) as zf:
        bad_file = zf.testzip()
        if bad_file is not None:
            raise ValueError(f"backup zip is corrupt: {bad_file}")

        with zf.open("master.db") as member:
            extracted = backup_path.with_suffix(".verify.db")
            try:
                with extracted.open("wb") as out:
                    shutil.copyfileobj(member, out)
                db = Rekordbox6Database(path=str(extracted))
                try:
                    db.get_content().count()
                finally:
                    db.close()
            finally:
                extracted.unlink(missing_ok=True)


def _prune_old_backups(backup_dir: Path) -> None:
    """Keep only the newest `KEEP_NEWEST` backups (ADR 0016).

    Only ever called after `create()`'s own backup has been verified good
    (constraints.md: pruning never runs as a standalone job, and never on a
    failed create). Filenames are timestamp-prefixed and therefore sort
    chronologically as plain strings.
    """
    backups = sorted(backup_dir.glob("*.db.zip"))
    for stale in backups[:-KEEP_NEWEST]:
        stale.unlink(missing_ok=True)
