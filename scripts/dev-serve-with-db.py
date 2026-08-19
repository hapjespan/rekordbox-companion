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
    # Delete the SQLite sidecars before copying, or the copy is not fresh. Found
    # the hard way: a `-wal` left by yesterday's run sat beside a newly copied
    # base file, SQLite replayed it, and a playlist an earlier apply had written
    # reappeared in what was supposed to be a clean database. Copying only
    # `master.db` is exactly the mistake `rb/backup.py` makes on the way out,
    # which is what makes this worth a comment rather than a silent unlink.
    for sidecar in ("master.db-wal", "master.db-shm"):
        (db_dir / sidecar).unlink(missing_ok=True)
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


def install_search_fetcher(app, query: str, count: int) -> None:
    """Make every pasted playlist URL resolve to a real Spotify SEARCH result.

    Spotify currently refuses this app's account all track-level data: listing
    playlists and reading a playlist's metadata both succeed, while the playlist's
    tracks, and the account's saved tracks, answer a bare 403, and the metadata
    comes back with its `tracks` object stripped. That is a permission on the
    Spotify application, not something the code can fix, and it leaves the match
    report, the review queue and the buy queue with nothing to show.

    Search still works, so this substitutes it: the tracks are real Spotify
    tracks with real artists, titles, durations and ISRCs, and everything
    downstream of the fetch is the app's genuine behaviour, matcher and
    missing-track spawn included. Only where the track list came from differs,
    which is why this lives in a dev script behind an explicit flag and prints a
    loud line saying so.
    """
    import httpx

    from companion.api.sync import _FetchedPlaylist, _FetchedTrack, get_spotify_fetcher
    from companion.db.session import get_db
    from companion.integrations import spotify

    # This account's search is capped at 10 results per request (a limit of 12
    # already answers "Invalid limit", where Spotify documents 50), and an
    # occasional page answers 502, so gathering more than ten means paging with
    # a retry. Another symptom of the same restricted application.
    page_size = 10

    def fetcher_override():
        db = next(get_db())
        items: list = []
        try:
            with httpx.Client(timeout=20.0) as client:
                token = spotify._get_valid_access_token(db, client)
                headers = {"Authorization": f"Bearer {token}"}
                offset = 0
                while len(items) < count:
                    page = None
                    for _attempt in range(3):
                        response = client.get(
                            "https://api.spotify.com/v1/search",
                            headers=headers,
                            params={
                                "q": query,
                                "type": "track",
                                "limit": page_size,
                                "offset": offset,
                            },
                        )
                        if response.status_code == 200:
                            page = response.json().get("tracks", {}).get("items", [])
                            break
                    if not page:
                        break
                    items.extend(page)
                    offset += page_size
        finally:
            db.close()
        items = items[:count]

        tracks = [
            _FetchedTrack(
                spotify_track_id=item.get("id"),
                isrc=(item.get("external_ids") or {}).get("isrc"),
                artist=", ".join(a["name"] for a in item.get("artists", [])),
                title=item.get("name") or "",
                duration_ms=item.get("duration_ms"),
            )
            for item in items
            if item
        ]

        def fetch(_playlist_url: str) -> _FetchedPlaylist:
            return _FetchedPlaylist(
                name=f"DEMO: {query}", snapshot_id=f"demo-{query}", tracks=tracks
            )

        return fetch

    app.dependency_overrides[get_spotify_fetcher] = fetcher_override


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="master.db to serve a copy of")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--demo-tracks-from-search",
        metavar="QUERY",
        help=(
            "dev demo: resolve any pasted playlist URL to real Spotify search "
            "results for QUERY, because Spotify refuses this account's playlist "
            "tracks (see install_search_fetcher)"
        ),
    )
    parser.add_argument("--demo-count", type=int, default=25)
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

    from companion.main import create_app

    app = create_app()
    if args.demo_tracks_from_search:
        install_search_fetcher(app, args.demo_tracks_from_search, args.demo_count)
        print(
            f"DEMO MODE: any playlist URL resolves to {args.demo_count} Spotify search "
            f"results for {args.demo_tracks_from_search!r}, because Spotify refuses this "
            "account's playlist tracks"
        )

    uvicorn.run(app, host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
