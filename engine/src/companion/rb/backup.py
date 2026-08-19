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

`master.db` is opened in WAL mode (proven, not assumed: backlog B2 -- a
`master.db-wal` was found beside the owner's own fixture holding committed
data that a base-file-only backup silently dropped). `create()` therefore
never zips `db_path` directly; it first makes a disposable staging copy of
`db_path` plus any `-wal`/`-shm` sidecar and checkpoints THAT COPY
(`_checkpointed_copy`) so the file actually placed in the zip is a single,
self-contained snapshot with every committed transaction folded in, WAL or
not. See `_checkpointed_copy`'s docstring for why checkpointing a disposable
copy -- rather than checkpointing the real `db_path` in place, or shipping
the sidecars uncompacted inside the zip -- is the option that neither
touches the real database (project rule 2) nor hands a restore two sidecars
to put back correctly (backlog B2's own stated worry). The zip therefore
still contains exactly one `master.db` member, never `-wal`/`-shm` entries.

Every create (success and failure) and every prune is logged
(constraints.md's NIS2 logging plan names "backup creation/rotation"
explicitly).
"""

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from defusedxml import ElementTree
from pyrekordbox.db6.database import Rekordbox6Database

from companion.logging import configure_logging, get_logger

configure_logging()

_logger = get_logger(__name__)

MASTER_PLAYLISTS_XML = "masterPlaylists6.xml"
KEEP_NEWEST = 10
# SQLite's write-ahead-log sidecars, named `<db file name><suffix>` next to the
# base file. Only ever read from `db_path`'s pair to seed a staging copy --
# never written back next to `db_path` itself (see `_checkpointed_copy`).
WAL_SIDECAR_SUFFIXES = ("-wal", "-shm")


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

        with tempfile.TemporaryDirectory(dir=backup_dir, prefix=".staging-") as staging_dir:
            staging_db = _checkpointed_copy(db_path, Path(staging_dir))

            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(staging_db, arcname="master.db")
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
        _logger.info("backup create failed", extra={"backup": {"error": str(exc)}})
        return BackupResult(ok=False, path=None, error=str(exc))

    _logger.info("backup created", extra={"backup": {"path": str(backup_path)}})
    _prune_old_backups(backup_dir)
    return BackupResult(ok=True, path=backup_path, error=None)


def _checkpointed_copy(db_path: Path, staging_dir: Path) -> Path:
    """Copy `db_path` (and any `-wal`/`-shm` sidecar) into `staging_dir`, then
    checkpoint the COPY so it becomes one self-contained base file with every
    committed transaction folded in -- including one that landed only in a
    `-wal` and was never checkpointed on the live database (backlog B2: a
    `master.db-wal` was found beside the owner's own fixture holding committed
    data; a base-file-only backup verified readable while silently missing it).

    Two other fixes were considered and rejected:

    - Checkpointing `db_path` itself, in place, before copying it. Rejected
      because a checkpoint is a write, and project rule 2 requires
      `guard.check()` + `backup.create()` to precede every write to the real
      `master.db` -- but `backup.create()` is the very code that would be
      doing the checkpointing, so "backup before this write" is circular for
      this write specifically. Checkpointing a disposable copy instead means
      this module never writes to the real database at all, so rule 2's write
      path (guarded, backed-up writes to the DJ's actual file) is simply not
      the one exercised here -- there is no rule to bend.
    - Zipping `db_path` plus its `-wal`/`-shm` sidecars uncompacted, and
      restoring all three together. Rejected because that is exactly the
      shape that caused the original surprise (a base file plus a foreign
      sidecar, replayed by SQLite in an order the restorer doesn't control) --
      backlog B2 names this explicitly as the reason checkpointing is safer.

    Opened through `Rekordbox6Database`, the same access path `_verify_readable`
    below already uses: it handles the SQLCipher key transparently on both the
    real, encrypted Mac database and this sandbox's encrypted fixture, so
    nothing here re-derives or hardcodes that key (and nothing here imports
    pyrekordbox outside `rb/`, project rule 1). `PRAGMA wal_checkpoint(TRUNCATE)`
    both folds every committed frame back into the base file and truncates the
    copy's own `-wal` to empty, so the caller only ever needs to zip the base
    file this function returns -- never a sidecar.
    """
    staging_db = staging_dir / db_path.name
    shutil.copy(db_path, staging_db)
    for suffix in WAL_SIDECAR_SUFFIXES:
        sidecar = db_path.with_name(db_path.name + suffix)
        if sidecar.is_file():
            shutil.copy(sidecar, Path(f"{staging_db}{suffix}"))

    db = Rekordbox6Database(path=str(staging_db))
    try:
        raw_connection = db.engine.raw_connection()
        try:
            raw_connection.cursor().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            raw_connection.close()
    finally:
        db.close()

    return staging_db


def _verify_readable(backup_path: Path) -> None:
    """Raise if `backup_path` is not a genuinely restorable backup.

    Three layers: the zip itself must be structurally intact (`testzip()`),
    the `master.db` it contains must actually open as a real Rekordbox
    database -- a zip can be valid while the database inside it is garbage
    -- and, if `masterPlaylists6.xml` was included, it must at least parse
    as well-formed XML (T042 finding: a restore missing/corrupting this
    file is a real behavioural gap on the Mac, not just an empty nice-to-have).
    """
    with zipfile.ZipFile(backup_path) as zf:
        bad_file = zf.testzip()
        if bad_file is not None:
            raise ValueError(f"backup zip is corrupt: {bad_file}")

        if MASTER_PLAYLISTS_XML in zf.namelist():
            ElementTree.fromstring(zf.read(MASTER_PLAYLISTS_XML))

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
    stale_backups = backups[:-KEEP_NEWEST]
    for stale in stale_backups:
        stale.unlink(missing_ok=True)
    if stale_backups:
        _logger.info(
            "backup rotation pruned",
            extra={"backup": {"pruned": [p.name for p in stale_backups]}},
        )
