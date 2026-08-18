"""T080 (US7): integration test for applying a whole Structure (folders +
nested playlists) through the same guard/backup/writer path as US3, against
the owner-supplied fixture `master.db` -- proving `rb/writer.py`'s
structure-apply extension (T086) actually writes a real nested tree, not
just a single flat playlist (`test_writer_integration.py`'s job).

SAFETY (same contract as test_writer_integration.py): `tests/fixtures/master.db`
is the owner's own real, irreplaceable Rekordbox database, gitignored and
never committed, never mutated in place. Every write happens against a
per-test `shutil.copy` into pytest's `tmp_path`.

Committed RED: `writer.apply_structure`/`NodeSpec`/`NodeWriteResult` don't
exist until T086 builds them.
"""

import shutil
from pathlib import Path

import pytest
from pyrekordbox.db6.database import Rekordbox6Database

from companion.rb import writer
from companion.rb.writer import NodeSpec

FIXTURE_DB = Path(__file__).resolve().parents[1] / "fixtures" / "master.db"
FOLDER_NAME = "Companion Structure Test"
PLAYLIST_NAME = "Vooravond"


@pytest.fixture
def db_copy(tmp_path: Path) -> Path:
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


def test_apply_writes_a_folder_with_a_nested_playlist(db_copy: Path):
    (content_id,) = _content_ids(db_copy, 1)
    nodes = [
        NodeSpec(
            node_id=1,
            kind="folder",
            name=FOLDER_NAME,
            parent_node_id=None,
            rb_ref=None,
            rb_content_ids=[],
        ),
        NodeSpec(
            node_id=2,
            kind="playlist",
            name=PLAYLIST_NAME,
            parent_node_id=1,
            rb_ref=None,
            rb_content_ids=[content_id],
        ),
    ]

    results = writer.apply_structure(db_copy, nodes)

    by_node = {r.node_id: r for r in results}
    assert by_node[1].created is True
    assert by_node[2].created is True
    assert by_node[2].tracks_added == 1
    assert by_node[2].readback_ok is True

    reopened = Rekordbox6Database(path=str(db_copy))
    folder = reopened.get_playlist(ID=by_node[1].rb_ref)
    playlist = reopened.get_playlist(ID=by_node[2].rb_ref)
    assert folder is not None
    assert playlist is not None
    assert str(playlist.ParentID) == str(by_node[1].rb_ref)
    assert {song.ContentID for song in playlist.Songs} == {content_id}
    reopened.close()


def test_reapply_after_edits_is_add_only(db_copy: Path):
    """FR-018, scenario 6: re-apply after edits adds the new track without
    duplicating or disturbing the one already there."""
    first_id, second_id = _content_ids(db_copy, 2)
    first_nodes = [
        NodeSpec(
            node_id=1,
            kind="folder",
            name=FOLDER_NAME,
            parent_node_id=None,
            rb_ref=None,
            rb_content_ids=[],
        ),
        NodeSpec(
            node_id=2,
            kind="playlist",
            name=PLAYLIST_NAME,
            parent_node_id=1,
            rb_ref=None,
            rb_content_ids=[first_id],
        ),
    ]
    first_results = {r.node_id: r for r in writer.apply_structure(db_copy, first_nodes)}

    second_nodes = [
        NodeSpec(
            node_id=1,
            kind="folder",
            name=FOLDER_NAME,
            parent_node_id=None,
            rb_ref=first_results[1].rb_ref,
            rb_content_ids=[],
        ),
        NodeSpec(
            node_id=2,
            kind="playlist",
            name=PLAYLIST_NAME,
            parent_node_id=1,
            rb_ref=first_results[2].rb_ref,
            rb_content_ids=[first_id, second_id],
        ),
    ]
    second_results = {r.node_id: r for r in writer.apply_structure(db_copy, second_nodes)}

    assert second_results[1].created is False
    assert second_results[1].rb_ref == first_results[1].rb_ref
    assert second_results[2].created is False
    assert second_results[2].tracks_added == 1
    assert second_results[2].tracks_already_present == 1

    reopened = Rekordbox6Database(path=str(db_copy))
    playlist = reopened.get_playlist(ID=second_results[2].rb_ref)
    song_ids = [song.ContentID for song in playlist.Songs]
    assert sorted(song_ids) == sorted([first_id, second_id])
    assert len(song_ids) == 2  # never duplicated
    reopened.close()


def test_a_playlist_two_levels_deep_resolves_its_grandparent_folder(db_copy: Path):
    (content_id,) = _content_ids(db_copy, 1)
    nodes = [
        NodeSpec(
            node_id=1,
            kind="folder",
            name="Run of Show",
            parent_node_id=None,
            rb_ref=None,
            rb_content_ids=[],
        ),
        NodeSpec(
            node_id=2,
            kind="folder",
            name="Prime Time",
            parent_node_id=1,
            rb_ref=None,
            rb_content_ids=[],
        ),
        NodeSpec(
            node_id=3,
            kind="playlist",
            name="Moment 1",
            parent_node_id=2,
            rb_ref=None,
            rb_content_ids=[content_id],
        ),
    ]

    results = writer.apply_structure(db_copy, nodes)

    by_node = {r.node_id: r for r in results}
    reopened = Rekordbox6Database(path=str(db_copy))
    playlist = reopened.get_playlist(ID=by_node[3].rb_ref)
    assert str(playlist.ParentID) == str(by_node[2].rb_ref)
    reopened.close()
