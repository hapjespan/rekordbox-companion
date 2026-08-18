"""App-wide paths, environment loading, and the pinned Rekordbox version.

Rekordbox install/version detection is NOT here: it requires importing
pyrekordbox, which project rule 1 confines to `rb/`, and this module sits
outside `rb/`. That responsibility lives in `rb/reader.py` instead (moved
from this task during phase 6 build, see tasks.md T011/T012).

Importing this module loads `.env` immediately (see the bottom of this
file) — not deferred to first use — so anything needing `os.environ` values
from `.env` must import `companion.config` (directly or transitively)
before reading them.
"""

from pathlib import Path

from dotenv import load_dotenv

PINNED_REKORDBOX_VERSION = "7.2.17"  # ADR 0002


def find_repo_root(start: Path) -> Path:
    """Walk up from `start` to the parent of the `engine/` package root.

    Anchored on `engine/pyproject.toml` rather than a fixed parent-count, so
    this keeps working regardless of how deep the caller module sits inside
    `engine/src/companion/`.
    """
    for candidate in start.parents:
        if candidate.name == "engine" and (candidate / "pyproject.toml").exists():
            return candidate.parent
    raise RuntimeError(f"could not locate engine/pyproject.toml above {start}")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
DATA_DIR = REPO_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"  # rb/backup.py's target dir (T047, ADR 0016)

load_dotenv(REPO_ROOT / ".env")
