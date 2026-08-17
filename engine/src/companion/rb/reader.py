"""Read-only interface over pyrekordbox: collection snapshot, playlist tree,
and Rekordbox install/version detection.

The only module (with its `rb/` siblings) permitted to import pyrekordbox
(project rule 1). Never writes; guarded writes live in `rb/writer.py`.

`read_collection_snapshot`/`read_playlist_tree` take an already-open
database object (any object exposing `get_content()`/`get_playlist()`, the
same shape as `Rekordbox6Database`) so tests can inject a fake and callers
control connection lifetime. That keeps this module's own field-mapping
logic testable without a real `master.db`; the real file is an
owner-supplied input still owed (quickstart.md) and its bytes are only
exercised through `open_database`, verified for real on the owner's Mac
(research.md R3 precedent).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pyrekordbox import config as rb_config
from pyrekordbox.db6 import Rekordbox6Database

from companion.config import PINNED_REKORDBOX_VERSION


@dataclass(frozen=True)
class RekordboxDetection:
    installed: bool
    version: str | None
    version_pin_ok: bool
    db_path: Path | None


def detect_rekordbox() -> RekordboxDetection:
    """Facts about the local Rekordbox 7 install, from pyrekordbox's own
    config scan. Never raises: no install found (this dev container; a
    fresh Mac before Rekordbox is set up) is a normal, expected state, not
    an error (spec edge case: degraded start, not a crash)."""
    conf = rb_config.get_config("rekordbox7")
    version = conf.get("version")
    db_path = conf.get("db_path")
    return RekordboxDetection(
        installed=bool(conf),
        version=version,
        version_pin_ok=version == PINNED_REKORDBOX_VERSION,
        db_path=Path(db_path) if db_path else None,
    )


def open_database(db_path: Path | None = None) -> Rekordbox6Database:
    """Open the real Rekordbox database. Requires the SQLCipher key
    pyrekordbox extracts on the Mac; raises FileNotFoundError for a missing
    path rather than silently returning an empty database."""
    path = db_path or detect_rekordbox().db_path
    return Rekordbox6Database(path=str(path) if path else None)


@dataclass(frozen=True)
class CollectionTrack:
    rb_content_id: str
    artist: str
    title: str
    duration_ms: int | None
    bpm: float | None
    isrc: str | None
    play_count: int
    location: str | None


class _ContentSource(Protocol):
    def get_content(self): ...


def read_collection_snapshot(db: _ContentSource) -> list[CollectionTrack]:
    """Snapshot of every track in the collection."""
    tracks = []
    for content in db.get_content():
        # Rekordbox stores BPM as an integer scaled by 100 (12800 == 128.00).
        bpm = content.BPM / 100 if content.BPM is not None else None
        duration_ms = content.Length * 1000 if content.Length is not None else None
        tracks.append(
            CollectionTrack(
                rb_content_id=content.ID,
                artist=content.Artist.Name if content.Artist else "",
                title=content.Title or "",
                duration_ms=duration_ms,
                bpm=bpm,
                isrc=content.ISRC or None,
                play_count=int(content.DJPlayCount) if content.DJPlayCount else 0,
                location=content.FolderPath or None,
            )
        )
    return tracks


@dataclass(frozen=True)
class PlaylistNode:
    rb_playlist_id: str
    name: str
    parent_id: str | None
    is_folder: bool
    position: int


class _PlaylistSource(Protocol):
    def get_playlist(self): ...


def read_playlist_tree(db: _PlaylistSource) -> list[PlaylistNode]:
    """The full playlist/folder tree, flat (each node carries its parent id)."""
    return [
        PlaylistNode(
            rb_playlist_id=playlist.ID,
            name=playlist.Name or "",
            parent_id=playlist.ParentID or None,
            is_folder=playlist.is_folder,
            position=playlist.Seq or 0,
        )
        for playlist in db.get_playlist()
    ]
