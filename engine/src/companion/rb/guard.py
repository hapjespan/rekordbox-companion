"""The write-refusal gate for the Rekordbox database (FR-015).

`check()` runs BEFORE any backup or write is attempted (spec.md US3
scenario 2: "the write is refused before anything is touched"). It is the
sole gate protecting the DJ's irreplaceable Rekordbox library from a bad
write, so a check that silently passes when it should fail is unacceptable.

Three conditions, evaluated in the order FR-015 lists them (and the order
the API contract tests exercise): Rekordbox running, installed version off
the pinned 7.2.17, and insufficient disk headroom (2x `master.db`'s size,
phase 4 grilling / D16). The first failing condition wins and names itself
in the result so the caller can tell the DJ exactly what blocked the write.

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
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from companion.config import PINNED_REKORDBOX_VERSION
from companion.rb import reader

# Free space required before a write, as a multiple of master.db's current
# size (D16, phase 4 grilling): enough headroom for the pre-write backup
# copy plus the database's own growth during the write.
DISK_HEADROOM_MULTIPLIER = 2


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    code: str | None
    message: str | None


def check(db_path: Path) -> GuardResult:
    """Decide whether a write to `db_path` may proceed.

    Returns `GuardResult(ok=True, code=None, message=None)` when all three
    checks pass, otherwise the first failing condition with its `code`
    (`"rekordbox_running"`, `"version_mismatch"`, or `"insufficient_disk"`)
    and a plain-English message naming the fix.
    """
    if reader.is_rekordbox_running():
        return GuardResult(
            ok=False,
            code="rekordbox_running",
            message="Rekordbox is running. Close Rekordbox and retry.",
        )

    detection = reader.detect_rekordbox()
    if not detection.version_pin_ok:
        return GuardResult(
            ok=False,
            code="version_mismatch",
            message=(
                f"Installed Rekordbox version is {detection.version}, "
                f"but {PINNED_REKORDBOX_VERSION} is required."
            ),
        )

    required = DISK_HEADROOM_MULTIPLIER * db_path.stat().st_size
    free = shutil.disk_usage(db_path.parent).free
    if free < required:
        return GuardResult(
            ok=False,
            code="insufficient_disk",
            message=(
                f"Not enough free disk space: {required} bytes required, "
                f"{free} bytes available. Free up disk space and retry."
            ),
        )

    return GuardResult(ok=True, code=None, message=None)
