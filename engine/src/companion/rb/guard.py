"""The write-refusal gate for the Rekordbox database (FR-015).

`check()` runs BEFORE any backup or write is attempted (spec.md US3
scenario 2: "the write is refused before anything is touched"). It is the
sole gate protecting the DJ's irreplaceable Rekordbox library from a bad
write, so a check that silently passes when it should fail is unacceptable.

Four conditions, evaluated in this order (matching the order the API
contract tests exercise, FR-015's own two plus the two operational ones
constraints.md adds): Rekordbox running, the database file missing or
unresolved (reader.py's own documented edge case -- pyrekordbox's config
can resolve a path from install-time settings without the file still being
there), installed version off the pinned 7.2.17, and insufficient disk
headroom (2x `master.db`'s size, phase 4 grilling / D16). The first failing
condition wins and names itself in the result so the caller can tell the DJ
exactly what blocked the write. A missing/moved database file is reported
under `version_mismatch` -- the codebase has no distinct fifth refusal code
(contracts/api.md), and both cases mean the same thing to the DJ: the
pinned Rekordbox installation isn't in the state a safe write needs
(review finding, phase 6: this check's absence let `db_path.stat()` crash
with an unhandled FileNotFoundError instead of refusing cleanly).

`reader` is imported as a module and its functions are reached through
attribute access (`reader.is_rekordbox_running()`, not a `from ... import`
of the names) on purpose: the API-level refusal tests monkeypatch
`companion.rb.reader.is_rekordbox_running` / `.detect_rekordbox`, and a
bound name captured at import time would bypass those patches. This also
routes every pyrekordbox-touching call through `rb/reader.py`, whose
import-time `configure_logging()` side effect (T018) must run before
pyrekordbox is used on any code path -- this module never imports
pyrekordbox directly (project rule 1).

`shutil` is imported as a module and `shutil.disk_usage(...)` is called
through it for the same monkeypatch reason: the disk-headroom test patches
`companion.rb.guard.shutil.disk_usage`.

Every refusal is logged (constraints.md's NIS2 logging plan names "guard
refusals" explicitly); the all-clear path is not, since it carries no
information a later log line (backup, write) doesn't already imply.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from companion.config import PINNED_REKORDBOX_VERSION
from companion.logging import configure_logging, get_logger
from companion.rb import reader

configure_logging()

_logger = get_logger(__name__)

# Free space required before a write, as a multiple of master.db's current
# size (D16, phase 4 grilling): enough headroom for the pre-write backup
# copy plus the database's own growth during the write.
DISK_HEADROOM_MULTIPLIER = 2


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    code: str | None
    message: str | None


def _refuse(code: str, message: str) -> GuardResult:
    _logger.info("write refused", extra={"guard": {"code": code, "message": message}})
    return GuardResult(ok=False, code=code, message=message)


def check(db_path: Path | None) -> GuardResult:
    """Decide whether a write to `db_path` may proceed.

    `db_path` may be `None` (Rekordbox not installed at all, per
    `reader.detect_rekordbox()`) -- this function still refuses cleanly
    rather than requiring the caller to special-case it first.

    Returns `GuardResult(ok=True, code=None, message=None)` when every
    check passes, otherwise the first failing condition with its `code`
    (`"rekordbox_running"`, `"version_mismatch"`, or `"insufficient_disk"`)
    and a plain-English message naming the fix.
    """
    if reader.is_rekordbox_running():
        return _refuse("rekordbox_running", "Rekordbox is running. Close Rekordbox and retry.")

    detection = reader.detect_rekordbox()
    if not detection.version_pin_ok:
        return _refuse(
            "version_mismatch",
            f"Installed Rekordbox version is {detection.version}, "
            f"but {PINNED_REKORDBOX_VERSION} is required.",
        )

    if db_path is None or not db_path.is_file():
        return _refuse(
            "version_mismatch",
            "Rekordbox database not found. Check the Rekordbox installation.",
        )

    required = DISK_HEADROOM_MULTIPLIER * db_path.stat().st_size
    free = shutil.disk_usage(db_path.parent).free
    if free < required:
        return _refuse(
            "insufficient_disk",
            (
                f"Not enough free disk space: {required} bytes required, "
                f"{free} bytes available. Free up disk space and retry."
            ),
        )

    return GuardResult(ok=True, code=None, message=None)
