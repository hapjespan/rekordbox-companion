"""The single, guarded write path into the Rekordbox database (FR-016..FR-018).

This is the ONLY module in the codebase permitted to write to the DJ's real,
irreplaceable Rekordbox library (project rule 2). A backup already exists and
the guard has already passed by the time `apply_playlist` is called: this
module's job starts at "write to `db_path`" and ends at "readback confirms it".
Backup creation (`rb/backup.py`, T047) and the write-refusal guard
(`rb/guard.py`, T046) are separate modules run before this one in the apply
flow (the API endpoint, T050).

The three safety invariants this module upholds (FR-017/FR-018, Principle
II/III):

- **Write only playlists.** It creates and appends to playlists, and never
  edits track metadata, cues or beat grids.
- **Add-only.** On re-apply it appends only content ids not already present as
  a `DjmdSongPlaylist` row for the target playlist, and never removes or
  reorders anything it did not just add. A content id already in the playlist is
  counted as already-present and left untouched.
- **Readback-verified.** After committing and closing the write session, a
  brand-new `Rekordbox6Database` is opened against the same file to confirm the
  playlist exists with every intended content id present. This proves the write
  reached disk, not just an in-memory session. A failed readback is *reported*
  (`readback_ok=False`), never raised, so the caller can tell the DJ which
  backup to restore (spec.md US3 scenario 7) instead of crashing.

`Rekordbox6Database` is imported directly from `pyrekordbox.db6.database` and
referenced as a module global on purpose: the readback-failure test monkeypatches
`companion.rb.writer.Rekordbox6Database` to simulate a write that did not
persist, and both the write-session open and the readback open must resolve
through that patchable name.

`configure_logging()` (T018) is called at import, after the `pyrekordbox`
import, following `rb/reader.py`'s precedent: `pyrekordbox/logger.py` attaches
its own raw, non-redacting handler as an import side effect, so redaction must
be (re)installed afterwards, before this module ever drives pyrekordbox. It is
idempotent.
"""

from dataclasses import dataclass
from pathlib import Path

from pyrekordbox.db6.database import Rekordbox6Database

from companion.logging import configure_logging, get_logger

configure_logging()

_logger = get_logger(__name__)


@dataclass(frozen=True)
class WriteResult:
    """The outcome of one `apply_playlist` call.

    `rb_playlist_id` is the id of the created-or-updated Target Playlist (a new
    id when `created` is True, the reused id otherwise). `tracks_added` counts
    genuinely new `DjmdSongPlaylist` rows written; `tracks_already_present`
    counts intended content ids skipped because they were already in the
    playlist (add-only). `readback_ok` is the verdict of the post-write reopen:
    True only when the playlist and every intended content id were found.
    """

    rb_playlist_id: str
    created: bool
    tracks_added: int
    tracks_already_present: int
    readback_ok: bool


def _dedupe_preserving_order(content_ids: list[str]) -> list[str]:
    """The intended content ids with duplicates removed, first occurrence kept.

    A content id repeated in the caller's list must only ever be added once
    (US3: a track accepted twice is still one playlist entry)."""
    seen: set[str] = set()
    unique: list[str] = []
    for content_id in content_ids:
        if content_id not in seen:
            seen.add(content_id)
            unique.append(content_id)
    return unique


def apply_playlist(
    db_path: Path,
    rb_playlist_id: str | None,
    playlist_name: str,
    rb_content_ids: list[str],
) -> WriteResult:
    """Ensure the Target Playlist named `playlist_name` contains every id in
    `rb_content_ids`, add-only, then verify by readback.

    `rb_playlist_id` is `None` on first apply (a new playlist is created at the
    root of the tree) or the previously-known id on re-apply. If a known id no
    longer resolves to a playlist (the DJ deleted the Target Playlist inside
    Rekordbox since the last apply, spec.md US3 scenario 5), it is treated as a
    first apply: a new playlist is created and `created` is True, so the caller
    can report that it was recreated.

    Never raises on a failed readback: returns `WriteResult(readback_ok=False)`
    so the caller can surface it to the DJ (spec.md US3 scenario 7)."""
    intended_ids = _dedupe_preserving_order(rb_content_ids)

    db = Rekordbox6Database(path=str(db_path))
    try:
        existing_playlist = (
            db.get_playlist(ID=rb_playlist_id) if rb_playlist_id is not None else None
        )
        created = existing_playlist is None

        if created:
            playlist = db.create_playlist(playlist_name, parent=None)
            already_present_ids: set[str] = set()
        else:
            playlist = existing_playlist
            already_present_ids = {song.ContentID for song in playlist.Songs}

        tracks_added = 0
        tracks_already_present = 0
        for content_id in intended_ids:
            if content_id in already_present_ids:
                tracks_already_present += 1
                continue
            db.add_to_playlist(playlist, content_id)
            already_present_ids.add(content_id)
            tracks_added += 1

        db.commit()
        result_playlist_id = str(playlist.ID)
    finally:
        db.close()

    readback_ok = _readback_ok(db_path, result_playlist_id, intended_ids)

    _logger.info(
        "rekordbox playlist write applied",
        # Nested under one field: `created` (and other names) collide with
        # reserved `LogRecord` attributes if passed as top-level `extra` keys.
        extra={
            "write": {
                "rb_playlist_id": result_playlist_id,
                "created": created,
                "tracks_added": tracks_added,
                "tracks_already_present": tracks_already_present,
                "readback_ok": readback_ok,
            }
        },
    )

    return WriteResult(
        rb_playlist_id=result_playlist_id,
        created=created,
        tracks_added=tracks_added,
        tracks_already_present=tracks_already_present,
        readback_ok=readback_ok,
    )


def _readback_ok(db_path: Path, rb_playlist_id: str, intended_ids: list[str]) -> bool:
    """Open a fresh database against the same file and confirm the playlist
    exists with every intended content id present.

    The brand-new instance is the whole point: it reads from disk, proving the
    committed write persisted rather than lingering only in the write session's
    memory."""
    reopened = Rekordbox6Database(path=str(db_path))
    try:
        playlist = reopened.get_playlist(ID=rb_playlist_id)
        if playlist is None:
            return False
        present_ids = {song.ContentID for song in playlist.Songs}
        return set(intended_ids).issubset(present_ids)
    finally:
        reopened.close()
