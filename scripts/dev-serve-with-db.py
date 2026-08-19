#!/usr/bin/env python
"""Dev-only: serve the whole app on one port against a chosen master.db.

On the DJ's Mac none of this is needed. pyrekordbox finds the real Rekordbox 7
install by itself, `make build && make run` serves the SPA from FastAPI, and
`/api/health` reports the real version. This script exists for the development
container, which has no Rekordbox install at all, so every Rekordbox-backed
endpoint answers a documented 503 and the UI is nothing but error states.

It builds a minimal fake Pioneer directory tree that pyrekordbox's own
detection is happy with, points it at a COPY of the database you name, and then
serves the app in-process so the detection override survives (pyrekordbox reads
its config at import time and offers no environment hook, and `--reload` would
re-import in a child process that never ran this file).

Working on a copy is the point, not an accident: applying a session or a
structure writes to the database, and no demo should be able to touch the
original. The copy still goes through the full guard and backup path, so a
write here is the real write path, not a simulation.

    python scripts/dev-serve-with-db.py engine/tests/fixtures/master.db

Run `make build` first, so there is an SPA to serve. Set DEV_HOST=0.0.0.0 to
make the process reachable from outside the container; the default stays
127.0.0.1, matching every other entry point in this repo (FR-037).

Reaching it from a laptop: the container sits on a Docker bridge the host is
also on, so the SSH tunnel can target the container directly and does not need
the port to be published at all.

    # on the host, to read the container's address
    docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \\
        rekordbox-companion-dev

    # from the laptop
    ssh -L 8787:<that address>:8787 root@<host>

Then open http://127.0.0.1:8787. Tunnelling to 127.0.0.1 on the host only works
if the port happens to be published (`docker port rekordbox-companion-dev`); the
container address always works, but changes when the container is recreated.
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FAKE_ROOT = REPO_ROOT / "data" / "dev-rekordbox"
PINNED_VERSION = "7.2.17"  # ADR 0002; the dir name is what pyrekordbox reads


def build_fake_install(source_db: Path) -> Path:
    """Lay out what `pyrekordbox.config` expects, around a copy of `source_db`.

    The shape is dictated by pyrekordbox: an install directory holding a
    `rekordbox <version>` folder, an app directory holding `rekordbox6/` with a
    `rekordbox3.settings` XML naming the database directory, and
    `rekordboxAgent/storage/options.json` naming the database file. The two
    must agree exactly, because `_get_rb7_config` asserts they do.
    """
    install_dir = FAKE_ROOT / "install"
    app_dir = FAKE_ROOT / "app"
    db_dir = FAKE_ROOT / "db"
    for path in (
        install_dir / f"rekordbox {PINNED_VERSION}",
        app_dir / "rekordbox6",
        app_dir / "rekordboxAgent" / "storage",
        db_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    db_copy = db_dir / "master.db"
    shutil.copy(source_db, db_copy)

    (app_dir / "rekordbox6" / "rekordbox3.settings").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<PIONEER>\n"
        f'  <VALUE name="masterDbDirectory" val="{db_dir.resolve()}"/>\n'
        "</PIONEER>\n"
    )
    (app_dir / "rekordboxAgent" / "storage" / "options.json").write_text(
        json.dumps({"options": [["db-path", str(db_copy.resolve())]]})
    )
    return db_copy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="master.db to serve a copy of")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    source_db = args.database if args.database.is_absolute() else REPO_ROOT / args.database
    if not source_db.is_file():
        return f"no such database: {source_db}"

    db_copy = build_fake_install(source_db)

    from pyrekordbox import config as rb_config

    rb_config.update_config(
        pioneer_install_dir=FAKE_ROOT / "install",
        pioneer_app_dir=FAKE_ROOT / "app",
    )

    from companion.rb.reader import detect_rekordbox

    detection = detect_rekordbox()
    if not detection.db_file_exists:
        return f"pyrekordbox did not accept the fake install tree: {detection}"

    host = os.environ.get("DEV_HOST", "127.0.0.1")
    print(f"serving a copy of {source_db} at {db_copy}")
    print(f"Rekordbox {detection.version}, version_pin_ok={detection.version_pin_ok}")
    print(f"http://{host}:{args.port}")

    import uvicorn

    uvicorn.run("companion.main:app", host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
