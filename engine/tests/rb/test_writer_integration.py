"""T043/T045/T096 (US3): integration tests for `rb/backup.py` + `rb/writer.py`
against the owner-supplied fixture `master.db`, proving the two modules that
guard the write path actually cooperate against a real file -- not the API
orchestration (that's `test_sync_apply.py`'s job, T044/T096/T106), and not
pyrekordbox's raw write mechanics in isolation (already proven by T042's
`tests/spikes/rb_write_smoke.py`).

SAFETY (same contract as T042): `tests/fixtures/master.db` is the owner's own
real, irreplaceable Rekordbox database, gitignored and never committed, never
mutated in place. Every write happens against a per-test `shutil.copy` into
pytest's `tmp_path`; the fixture itself is only ever a `shutil.copy` source or
a read-only existence check.

Committed RED: `companion.rb.backup` and `companion.rb.writer` don't exist
until T046 (guard, used transitively)/T047 (backup)/T048 (writer) build them.
"""

import shutil
from pathlib import Path

import pytest
from pyrekordbox.db6.database import Rekordbox6Database

from companion.rb import backup, writer

FIXTURE_DB = Path(__file__).resolve().parents[1] / "fixtures" / "master.db"
EXPECTED_CONTENT_COUNT = 119
EXPECTED_EXISTING_PLAYLISTS = 2

PLAYLIST_NAME = "Companion Apply Test"


@pytest.fixture
def db_copy(tmp_path: Path) -> Path:
    """A writable throwaway copy of the fixture DB inside `tmp_path`; see the
    module docstring's safety contract. Skips (not fails) if the owner-
    supplied fixture isn't present, matching `test_reader.py`'s and T042's
    precedent: real-file evidence runs wherever the fixture exists."""
    if not FIXTURE_DB.exists():
        pytest.skip(f"Owner-supplied fixture {FIXTURE_DB} not present (research.md R3).")
    copy_path = tmp_path / "master.db"
    shutil.copy(FIXTURE_DB, copy_path)
    return copy_path


def _content_ids(db_path: Path, n: int) -> list[str]:
    db = Rekordbox6Database(path=str(db_path))
    ids = [c.ID for c in db.get_content().limit(n)]
    db.close()
    return ids


def test_backup_is_taken_before_the_write_and_readback_verifies_every_track(
    db_copy: Path, tmp_path: Path
):
    backup_dir = tmp_path / "backups"
    content_ids = _content_ids(db_copy, 2)

    backup_result = backup.create(db_copy, backup_dir)
    assert backup_result.ok
    assert backup_result.path is not None
    assert backup_result.path.exists()

    # The backup predates the write: opening a copy of the *backup* (never
    # the backup file itself, same never-mutate-in-place discipline) must
    # show the pre-write baseline, not the playlist about to be created.
    pre_write_check = tmp_path / "from_backup.db"
    _extract_backup(backup_result.path, pre_write_check)
    pre_write_db = Rekordbox6Database(path=str(pre_write_check))
    assert pre_write_db.get_playlist(Name=PLAYLIST_NAME).count() == 0
    pre_write_db.close()

    result = writer.apply_playlist(db_copy, None, PLAYLIST_NAME, content_ids)

    assert result.created is True
    assert result.tracks_added == 2
    assert result.tracks_already_present == 0
    assert result.readback_ok is True

    reopened = Rekordbox6Database(path=str(db_copy))
    playlist = reopened.get_playlist(ID=result.rb_playlist_id)
    assert playlist is not None
    assert {song.ContentID for song in playlist.Songs} == set(content_ids)
    reopened.close()


def test_second_apply_after_resync_adds_only_new_tracks(db_copy: Path, tmp_path: Path):
    first_id, second_id = _content_ids(db_copy, 2)

    first = writer.apply_playlist(db_copy, None, PLAYLIST_NAME, [first_id])
    assert first.created is True
    assert first.tracks_added == 1
    assert first.tracks_already_present == 0

    # Re-sync brought back the same track plus one newly-accepted one
    # (ADR 0006: add-only -- the already-present track must not be
    # duplicated or re-added, only the genuinely new one).
    second = writer.apply_playlist(
        db_copy, first.rb_playlist_id, PLAYLIST_NAME, [first_id, second_id]
    )
    assert second.created is False
    assert second.rb_playlist_id == first.rb_playlist_id
    assert second.tracks_added == 1
    assert second.tracks_already_present == 1

    reopened = Rekordbox6Database(path=str(db_copy))
    playlist = reopened.get_playlist(ID=first.rb_playlist_id)
    song_content_ids = [song.ContentID for song in playlist.Songs]
    assert sorted(song_content_ids) == sorted([first_id, second_id])
    assert len(song_content_ids) == 2  # never duplicated
    reopened.close()


def test_second_apply_with_a_new_name_renames_the_reused_playlist(db_copy: Path):
    # Review finding: without this, PlaylistLink.rb_playlist_name (the
    # companion's own record) would drift from the real Rekordbox
    # playlist's name the moment the DJ supplies a new name on a re-apply.
    (content_id,) = _content_ids(db_copy, 1)
    first = writer.apply_playlist(db_copy, None, PLAYLIST_NAME, [content_id])

    renamed = writer.apply_playlist(db_copy, first.rb_playlist_id, "Renamed Playlist", [content_id])

    assert renamed.rb_playlist_id == first.rb_playlist_id
    reopened = Rekordbox6Database(path=str(db_copy))
    playlist = reopened.get_playlist(ID=first.rb_playlist_id)
    assert playlist.Name == "Renamed Playlist"
    reopened.close()


def test_target_playlist_deleted_in_rekordbox_is_detected_and_recreated(db_copy: Path):
    (content_id,) = _content_ids(db_copy, 1)
    first = writer.apply_playlist(db_copy, None, PLAYLIST_NAME, [content_id])

    # Simulate the DJ deleting the Target Playlist inside Rekordbox itself
    # (spec.md US3 scenario 5) between one apply and the next.
    db = Rekordbox6Database(path=str(db_copy))
    db.delete_playlist(first.rb_playlist_id)
    db.commit()
    db.close()

    second = writer.apply_playlist(db_copy, first.rb_playlist_id, PLAYLIST_NAME, [content_id])

    assert second.created is True  # detected as missing, recreated -- reported via `created`
    assert second.rb_playlist_id != first.rb_playlist_id
    assert second.readback_ok is True

    reopened = Rekordbox6Database(path=str(db_copy))
    recreated = reopened.get_playlist(ID=second.rb_playlist_id)
    assert recreated is not None
    assert recreated.Name == PLAYLIST_NAME
    assert {song.ContentID for song in recreated.Songs} == {content_id}
    reopened.close()


def test_backup_create_fails_when_the_backup_directory_is_blocked(db_copy: Path, tmp_path: Path):
    # T096: a real (not mocked) backup failure -- constraints.md: "A backup
    # that fails verification blocks the write, the same as insufficient
    # disk space." A path component that exists as a plain FILE, not a
    # directory, is a genuine, uid-independent failure mode: unlike a
    # permission-bit denial (chmod), it fails even when the process runs as
    # root, which this sandbox's tests do.
    blocked = tmp_path / "backups" / "blocked"
    blocked.parent.mkdir()
    blocked.write_bytes(b"not a directory")

    result = backup.create(db_copy, blocked)

    assert result.ok is False
    assert result.path is None
    assert result.error


def test_writer_reports_readback_failure_instead_of_claiming_success(
    db_copy: Path, monkeypatch: pytest.MonkeyPatch
):
    # T096: the write's OWN post-write readback verification fails (as
    # opposed to the pre-write backup_failed refusal above) -- spec.md US3
    # scenario 7. Simulated at writer.py's one external seam
    # (`Rekordbox6Database`): the first call is the real write, the second
    # (writer's internal readback reopen) returns a double whose playlist
    # has no songs, as if the write had not actually persisted.
    (content_id,) = _content_ids(db_copy, 1)
    real_calls: list[Rekordbox6Database] = []

    class _EmptyReadbackPlaylist:
        Songs: list = []

    class _EmptyReadbackDouble:
        def get_playlist(self, ID=None, **kwargs):  # noqa: ARG002
            return _EmptyReadbackPlaylist()

        def close(self):
            pass

    def fake_constructor(*args, **kwargs):
        if not real_calls:
            db = Rekordbox6Database(*args, **kwargs)
            real_calls.append(db)
            return db
        return _EmptyReadbackDouble()

    monkeypatch.setattr("companion.rb.writer.Rekordbox6Database", fake_constructor)

    result = writer.apply_playlist(db_copy, None, PLAYLIST_NAME, [content_id])

    assert result.readback_ok is False


def _extract_backup(zip_path: Path, dest: Path) -> None:
    import zipfile

    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.endswith("master.db")]
        assert names, f"backup zip {zip_path} has no master.db member"
        with zf.open(names[0]) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out)
