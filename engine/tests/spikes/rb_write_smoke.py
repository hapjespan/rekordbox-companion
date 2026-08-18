"""T042 (R3 spike, research.md unknown #1): pyrekordbox write smoke test.

This spike gates every subsequent Rekordbox write-path task (T046 rb/guard.py,
T047 rb/backup.py, T048 rb/writer.py). Its single job is to prove that
pyrekordbox's documented write API (create folder, create playlist, add track,
commit) actually works end-to-end against a *real* Rekordbox-format master.db
of this exact schema/version, in this Linux dev container with no Rekordbox
install, and that the file still opens cleanly after a full close/reopen cycle.
A failure here is not a test bug to work around: per the task, it stops phase 6
and reopens phase 4.

What this spike proves: pyrekordbox's write mechanics are structurally sound
against a real file of this database's schema/version (Rekordbox 7.2.17 keeps
the v6 master.db format, ADR 0002).

What it does NOT and CANNOT prove here: that Rekordbox 7.2.17 itself, launched
for real, reads back the folder/playlist/track exactly as pyrekordbox wrote
them. That final check is explicitly deferred to the owner's own Mac
(quickstart.md, research.md R3: "What cannot be verified here is Rekordbox
itself reading the result").

SAFETY (project rule 2, and the T042 dispatch): the fixture
`tests/fixtures/master.db` is the owner's own real, irreplaceable Rekordbox
database, gitignored and never committed. It is NEVER mutated in place. Every
write happens against a per-test `shutil.copy` of it into pytest's `tmp_path`;
the fixture itself is only ever opened read-only or used as a copy *source*,
exactly as the future rb/backup.py must copy before rb/writer.py touches the
live DB. Verify by inspection: every reference to the fixture below is a
`shutil.copy(...)` source or a read-only existence check, never a write target.

Note on project rule 1 ("never import pyrekordbox outside rb/"): this spike is
the one deliberate, task-directed exception. Its entire purpose is to
characterize pyrekordbox itself before the production writer (T048, rb/writer.py)
exists to route through; the T042 dispatch explicitly instructs calling
`Rekordbox6Database`, `create_playlist_folder`, `create_playlist` and
`add_to_playlist` directly here. In production, rb/writer.py remains the only
importer of the write API.

Quirks discovered here that the later write-path tasks must account for:

- commit() raises RuntimeError("Rekordbox is running...") if it detects a live
  Rekordbox process (via get_rekordbox_pid()). rb/guard.py (T046) must still do
  its own closed-Rekordbox check *before* the copy/backup, but pyrekordbox
  provides this as a last-line backstop at commit time.
- commit() auto-increments the local + row USN (update-sequence numbers) that
  Rekordbox uses to detect external changes (autoinc=True by default). This is
  desirable: it is how Rekordbox notices the new playlist. rb/writer.py should
  keep the default.
- masterPlaylists6.xml: on open, pyrekordbox looks for this file next to
  master.db. Our tmp copy contains only master.db, so pyrekordbox logs
  "No masterPlaylists6.xml found ..." and sets playlist_xml=None; commit() then
  SKIPS the XML sync. On the real Mac install the XML file IS present, and
  commit() updates it (playlist add + updated_at sync). rb/backup.py (T047)
  must therefore back up / copy masterPlaylists6.xml alongside master.db, and
  the Mac-side verification must confirm the XML side too. Creating playlists
  via create_playlist()/create_playlist_folder() keeps the XML in sync; hand-
  inserting DjmdPlaylist rows would not (pyrekordbox warns about exactly that).
- create_playlist_folder() sets Attribute=1 (folder); create_playlist() sets
  Attribute=0 (normal playlist). add_to_playlist() refuses anything with
  Attribute != 0 (folders/smart lists) with ValueError, so writer.py must add
  tracks to the leaf playlist, never the folder.
- pyrekordbox logs "OS linux not supported!" on every open here (config
  auto-detection). Harmless in this container; absent on macOS.

The IDs of the two playlists that already exist in this fixture
('200000' CUE Analysis Playlist, '280900474' DEMO) and the 119 Collection
tracks are treated as the add-only baseline (ADR 0006): the spike asserts they
survive the write untouched, which is the first evidence point rb/writer.py
must also uphold (companion writes are add-only; never remove/reorder).
"""

import shutil
from pathlib import Path

import pytest
from pyrekordbox.db6.database import Rekordbox6Database

# Owner-supplied real fixture: tests/fixtures/master.db (gitignored, never
# committed). Resolved from this file's location so it works regardless of the
# pytest invocation cwd. Only ever a shutil.copy() SOURCE or an existence check
# below -- never opened for writing.
FIXTURE_DB = Path(__file__).resolve().parents[1] / "fixtures" / "master.db"

# Known baseline of the owner's fixture, confirmed out-of-band in the T042
# dispatch and re-asserted by the spike so a swapped/altered fixture is caught.
EXPECTED_CONTENT_COUNT = 119
EXPECTED_EXISTING_PLAYLISTS = 2

FOLDER_NAME = "Companion Spike Folder"
PLAYLIST_NAME = "Companion Spike Playlist"


@pytest.fixture
def db_copy(tmp_path: Path) -> Path:
    """A writable throwaway copy of the fixture DB inside tmp_path.

    This is the crux of the safety contract: the test operates ONLY on this
    copy. If the owner-supplied fixture is not present (e.g. CI without the
    real DB, matching the test_reader.py precedent where real-file verification
    happens on the owner's Mac), the spike skips rather than failing -- its
    durable evidence runs wherever the fixture exists (this sandbox, the Mac).
    """
    if not FIXTURE_DB.exists():
        pytest.skip(
            f"Owner-supplied fixture {FIXTURE_DB} not present; "
            "pyrekordbox write mechanics are verified where the real DB exists "
            "(this sandbox and the owner's Mac), per research.md R3."
        )
    copy_path = tmp_path / "master.db"
    shutil.copy(FIXTURE_DB, copy_path)
    return copy_path


def test_rb_write_smoke_survives_close_and_reopen(db_copy: Path) -> None:
    """Create folder + playlist + track, commit, close, reopen fresh, readback.

    The close/reopen boundary is the whole point: it proves the write was
    persisted to the file, not just an in-memory session artifact.
    """
    # -- Session 1: read baseline, write, commit, close -----------------------
    db = Rekordbox6Database(path=str(db_copy))

    # Add-only baseline (ADR 0006): capture what must survive untouched.
    baseline_content_count = db.get_content().count()
    baseline_playlists = {(p.ID, p.Name) for p in db.get_playlist()}
    assert baseline_content_count == EXPECTED_CONTENT_COUNT
    assert len(baseline_playlists) == EXPECTED_EXISTING_PLAYLISTS

    folder = db.create_playlist_folder(FOLDER_NAME)
    assert folder.is_folder  # Attribute == 1

    playlist = db.create_playlist(PLAYLIST_NAME, parent=folder)
    assert playlist.is_playlist  # Attribute == 0
    assert playlist.ParentID == folder.ID

    # Add the first real Collection track (a genuine DjmdContent row).
    content = db.get_content().first()
    assert content is not None
    song = db.add_to_playlist(playlist, content)
    assert song.ContentID == content.ID

    # Persist across a real close/reopen cycle.
    db.commit()

    folder_id = folder.ID
    playlist_id = playlist.ID
    content_id = content.ID
    db.close()

    # -- Session 2: brand-new instance against the same file, readback --------
    reopened = Rekordbox6Database(path=str(db_copy))

    # (1) The database still opens cleanly and is not corrupted: the full
    # Collection is intact and unchanged (add-only: nothing removed/altered).
    assert reopened.get_content().count() == EXPECTED_CONTENT_COUNT

    # (2) The folder survived with the expected name and folder attribute.
    folder_back = reopened.get_playlist(ID=folder_id)
    assert folder_back is not None
    assert folder_back.Name == FOLDER_NAME
    assert folder_back.is_folder

    # (3) The playlist survived inside that folder with the expected name.
    playlist_back = reopened.get_playlist(ID=playlist_id)
    assert playlist_back is not None
    assert playlist_back.Name == PLAYLIST_NAME
    assert playlist_back.ParentID == folder_id
    assert playlist_back.is_playlist

    # (4) The track was actually added to the playlist (DjmdSongPlaylist row).
    added_content_ids = {song.ContentID for song in playlist_back.Songs}
    assert added_content_ids == {content_id}

    # (5) Add-only evidence (ADR 0006): the two pre-existing playlists are still
    # present, untouched, alongside the two the spike added (total now 4).
    playlists_after = {(p.ID, p.Name) for p in reopened.get_playlist()}
    assert baseline_playlists <= playlists_after
    assert len(playlists_after) == EXPECTED_EXISTING_PLAYLISTS + 2

    reopened.close()
