"""T012: rb/reader.py — collection snapshot, playlist tree, playlist contents,
RB detection.

The collection/playlist mapping tests inject a fake object satisfying the
same duck-typed interface as pyrekordbox's Rekordbox6Database, so they
verify reader.py's own field-mapping logic without needing a real
master.db. The real fixture (owner-supplied, quickstart.md) is required to
verify pyrekordbox's own file reading, not this module's logic — that
verification happens on the owner's Mac (research.md R3 precedent).
"""

import logging
import shutil
from pathlib import Path

import pytest

import companion.rb.reader as reader_module
from companion.rb.reader import (
    detect_rekordbox,
    is_rekordbox_running,
    open_database,
    read_collection_snapshot,
    read_playlist_track_refs,
    read_playlist_tree,
)


def test_importing_this_module_alone_configures_logging_redaction():
    # T018's guarantee must hold for every code path that uses pyrekordbox,
    # not only ones that also happen to build the FastAPI app -- this
    # module is where pyrekordbox is actually imported (rule 1), so it must
    # be the one guaranteeing configure_logging() has already run (second-
    # round adversarial gate-review finding, T018). reader_module is
    # already imported by the time this test file's own top-level import
    # runs, so this checks the *effect* rather than re-importing.
    from companion.logging import RedactingJsonFormatter

    assert reader_module  # module loaded without error, imports order intact
    root = logging.getLogger()
    assert any(isinstance(h.formatter, RedactingJsonFormatter) for h in root.handlers)
    assert logging.getLogger("pyrekordbox").propagate is False


def test_detect_rekordbox_reports_not_installed_in_this_dev_container():
    # Real assertion, no mocking: this Linux dev container genuinely has no
    # Rekordbox install (pyrekordbox itself warns "OS not supported" and
    # returns no config), matching production's negative case exactly.
    detection = detect_rekordbox()
    assert detection.installed is False
    assert detection.version is None
    assert detection.version_pin_ok is False
    assert detection.db_path is None
    assert detection.db_file_exists is False


def test_detect_rekordbox_reports_db_file_exists_false_when_path_resolved_but_missing(
    monkeypatch, tmp_path
):
    # Spec edge case: the database moved or was deleted since Rekordbox was
    # configured -- pyrekordbox's config can still resolve a path even
    # though nothing is there (T015 review finding: this was previously
    # unchecked, so a moved/deleted master.db would have read as "ok").
    missing_path = tmp_path / "master.db"
    monkeypatch.setattr(
        "companion.rb.reader.rb_config.get_config",
        lambda section: {"version": "7.2.17", "db_path": missing_path},
    )

    detection = detect_rekordbox()

    assert detection.db_path == missing_path
    assert detection.db_file_exists is False


def test_detect_rekordbox_reports_db_file_exists_true_when_the_file_is_there(monkeypatch, tmp_path):
    real_path = tmp_path / "master.db"
    real_path.write_bytes(b"")
    monkeypatch.setattr(
        "companion.rb.reader.rb_config.get_config",
        lambda section: {"version": "7.2.17", "db_path": real_path},
    )

    detection = detect_rekordbox()

    assert detection.db_file_exists is True


def test_is_rekordbox_running_is_false_in_this_dev_container():
    # Real assertion, no mocking: no process named Rekordbox runs here, and
    # guard.py (T046) will reuse this exact function rather than reimplement
    # its own process-running check, avoiding duplication (tasks.md T015).
    assert is_rekordbox_running() is False


def test_open_database_raises_file_not_found_for_a_missing_path():
    try:
        open_database(Path("/nonexistent/master.db"))
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


def test_open_database_raises_file_not_found_when_no_path_and_none_detected():
    # No-argument branch: falls back to detect_rekordbox().db_path, which is
    # None in this dev container (review finding: this branch was untested).
    try:
        open_database()
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError:
        pass


class _FakeArtist:
    def __init__(self, name):
        self.Name = name


class _FakeContent:
    def __init__(self, **kwargs):
        self.ID = kwargs["ID"]
        self.Artist = _FakeArtist(kwargs["artist_name"]) if kwargs.get("artist_name") else None
        self.Title = kwargs.get("title")
        self.Length = kwargs.get("length_seconds")
        self.BPM = kwargs.get("bpm_hundredths")
        self.ISRC = kwargs.get("isrc")
        self.DJPlayCount = kwargs.get("play_count_str")
        self.FolderPath = kwargs.get("folder_path")
        # Verified live against the fixture master.db: pyrekordbox exposes the
        # musical key as `KeyName` (Camelot notation, e.g. '8m') and the record
        # label as `LabelName`, both None whenever Rekordbox has no value.
        self.KeyName = kwargs.get("key_name")
        self.LabelName = kwargs.get("label_name")


class _FakeSong:
    """One `DjmdSongPlaylist` row: the playlist-to-content relation, whose
    `TrackNo` carries the position inside the playlist."""

    def __init__(self, content_id, track_no):
        self.ContentID = content_id
        self.TrackNo = track_no


class _FakePlaylist:
    def __init__(self, **kwargs):
        self.ID = kwargs["ID"]
        self.Name = kwargs.get("name")
        self.ParentID = kwargs.get("parent_id")
        self.Seq = kwargs.get("seq")
        self._is_folder = kwargs.get("is_folder", False)
        self.Songs = kwargs.get("songs", [])

    @property
    def is_folder(self):
        return self._is_folder


class _FakeRekordboxDatabase:
    def __init__(self, contents, playlists):
        self._contents = contents
        self._playlists = playlists

    def get_content(self):
        return self._contents

    def get_playlist(self, **kwargs):
        # Mirrors pyrekordbox: no kwargs lists every node, `ID=` looks one up
        # and answers None when nothing matches (verified against the fixture).
        if not kwargs:
            return self._playlists
        wanted = kwargs["ID"]
        return next((p for p in self._playlists if p.ID == wanted), None)


def test_read_collection_snapshot_maps_every_field():
    db = _FakeRekordboxDatabase(
        contents=[
            _FakeContent(
                ID="1",
                artist_name="Example Artist",
                title="Example Title",
                length_seconds=210,
                bpm_hundredths=12800,
                isrc="USRC17607839",
                play_count_str="42",
                folder_path="/music/example.mp3",
                key_name="8m",
                label_name="Loopmasters",
            )
        ],
        playlists=[],
    )

    tracks = read_collection_snapshot(db)

    assert len(tracks) == 1
    track = tracks[0]
    assert track.rb_content_id == "1"
    assert track.artist == "Example Artist"
    assert track.title == "Example Title"
    assert track.duration_ms == 210_000
    assert track.bpm == 128.0
    assert track.isrc == "USRC17607839"
    assert track.play_count == 42
    assert track.location == "/music/example.mp3"
    assert track.musical_key == "8m"
    assert track.label == "Loopmasters"


def test_read_collection_snapshot_handles_missing_optional_fields():
    db = _FakeRekordboxDatabase(
        contents=[_FakeContent(ID="2", title="No Artist Track")],
        playlists=[],
    )

    tracks = read_collection_snapshot(db)

    assert tracks[0].artist == ""
    assert tracks[0].duration_ms is None
    assert tracks[0].bpm is None
    assert tracks[0].isrc is None
    assert tracks[0].play_count == 0
    assert tracks[0].location is None
    # Key and label are absent for most tracks even in a real, analysed
    # library (7 of 119 carry a key in the fixture, 4 a label), so absence is
    # the normal case, never an error.
    assert tracks[0].musical_key is None
    assert tracks[0].label is None


def test_read_collection_snapshot_keeps_the_key_verbatim_as_rekordbox_stores_it():
    # The DJ recognises their own notation; a lossy conversion is worse than
    # none, so nothing here normalises Camelot ('2d') or the classical
    # spelling ('G m') the fixture also contains.
    db = _FakeRekordboxDatabase(
        contents=[
            _FakeContent(ID="1", title="Camelot", key_name="2d"),
            _FakeContent(ID="2", title="Classical", key_name="G m"),
            _FakeContent(ID="3", title="Empty string key", key_name=""),
        ],
        playlists=[],
    )

    tracks = read_collection_snapshot(db)

    assert [track.musical_key for track in tracks] == ["2d", "G m", None]


def test_read_playlist_track_refs_returns_content_ids_in_playlist_order():
    # `Songs` comes back unordered from pyrekordbox (verified against the
    # fixture: TrackNo 76, 95, 86, ... for the first rows); TrackNo is the
    # position inside the playlist, so the reader is what orders by it.
    db = _FakeRekordboxDatabase(
        contents=[],
        playlists=[
            _FakePlaylist(
                ID="pl1",
                name="DEMO",
                songs=[
                    _FakeSong("c3", 3),
                    _FakeSong("c1", 1),
                    _FakeSong("c2", 2),
                ],
            )
        ],
    )

    refs = read_playlist_track_refs(db, "pl1")

    assert [ref.rb_content_id for ref in refs] == ["c1", "c2", "c3"]
    assert [ref.position for ref in refs] == [1, 2, 3]


def test_read_playlist_track_refs_puts_a_missing_track_no_last():
    db = _FakeRekordboxDatabase(
        contents=[],
        playlists=[
            _FakePlaylist(
                ID="pl1",
                name="DEMO",
                songs=[_FakeSong("c-unpositioned", None), _FakeSong("c1", 1)],
            )
        ],
    )

    refs = read_playlist_track_refs(db, "pl1")

    assert [ref.rb_content_id for ref in refs] == ["c1", "c-unpositioned"]


def test_read_playlist_track_refs_is_none_for_an_unknown_playlist_id():
    # None, not an empty list: "this playlist does not exist" and "this
    # playlist is empty" are different answers, and the API layer turns the
    # first into a 404 (contracts/api.md) instead of an empty page.
    db = _FakeRekordboxDatabase(contents=[], playlists=[])

    assert read_playlist_track_refs(db, "nope") is None


def test_read_playlist_track_refs_is_empty_for_a_folder():
    # A folder holds no content rows of its own (verified: the fixture's
    # empty "CUE Analysis Playlist" and every folder answer with no Songs).
    db = _FakeRekordboxDatabase(
        contents=[],
        playlists=[_FakePlaylist(ID="folder1", name="Bookings", is_folder=True)],
    )

    assert read_playlist_track_refs(db, "folder1") == []


def test_read_playlist_tree_maps_folders_and_playlists():
    # The top folder's own id is deliberately NOT the literal string "root"
    # here: pyrekordbox reserves that value as the top-level sentinel (see
    # test_read_playlist_tree_maps_the_root_sentinel_parent_id_to_none
    # below), so a real folder never has "root" as its own id.
    db = _FakeRekordboxDatabase(
        contents=[],
        playlists=[
            _FakePlaylist(ID="folder1", name="Bookings", is_folder=True, seq=1),
            _FakePlaylist(ID="child", name="Horeca", parent_id="folder1", is_folder=False, seq=2),
        ],
    )

    nodes = read_playlist_tree(db)

    assert len(nodes) == 2
    root, child = nodes
    assert root.rb_playlist_id == "folder1"
    assert root.name == "Bookings"
    assert root.parent_id is None
    assert root.is_folder is True
    assert child.parent_id == "folder1"
    assert child.is_folder is False


def test_read_playlist_tree_maps_the_root_sentinel_parent_id_to_none():
    # pyrekordbox reports a top-level node's ParentID as the literal string
    # "root" (db6/database.py), not None/empty. A falsy-only check would
    # leave this node's parent_id as "root", matching no other node and
    # breaking hierarchy reconstruction (phase 7 review finding).
    db = _FakeRekordboxDatabase(
        contents=[],
        playlists=[
            _FakePlaylist(ID="1", name="Top Level", parent_id="root", is_folder=False, seq=1),
        ],
    )

    nodes = read_playlist_tree(db)

    assert nodes[0].parent_id is None


# --- against the owner-supplied fixture master.db ---------------------------
#
# The fakes above prove this module's own mapping logic; these two prove the
# pyrekordbox attribute names it depends on (`KeyName`, `LabelName`, and the
# playlist-to-content relation's `Songs`/`ContentID`/`TrackNo`) are really
# what a Rekordbox 7 database exposes. Same safety contract as
# test_writer_integration.py: the fixture is the owner's own irreplaceable
# database, never opened in place -- every test reads a `shutil.copy` in
# `tmp_path` -- and the tests skip when it isn't present.

FIXTURE_DB = Path(__file__).resolve().parents[1] / "fixtures" / "master.db"


def _fixture_copy(tmp_path):
    if not FIXTURE_DB.exists():
        pytest.skip(f"Owner-supplied fixture {FIXTURE_DB} not present (research.md R3).")
    copy_path = tmp_path / "master.db"
    shutil.copy(FIXTURE_DB, copy_path)
    return copy_path


def test_read_collection_snapshot_reads_real_key_and_label_values(tmp_path):
    db = open_database(_fixture_copy(tmp_path))
    try:
        tracks = read_collection_snapshot(db)
    finally:
        db.close()

    # 7 of the fixture's 119 tracks carry a key, 4 a label; a real analysed
    # library carries them nearly everywhere.
    assert len(tracks) == 119
    assert sum(1 for t in tracks if t.musical_key) == 7
    assert sum(1 for t in tracks if t.label) == 4
    assert "8m" in {t.musical_key for t in tracks}


def test_read_playlist_track_refs_reads_the_real_playlist_to_content_relation(tmp_path):
    db = open_database(_fixture_copy(tmp_path))
    try:
        playlists = [node for node in read_playlist_tree(db) if not node.is_folder]
        refs_by_playlist = {
            node.rb_playlist_id: read_playlist_track_refs(db, node.rb_playlist_id)
            for node in playlists
        }
    finally:
        db.close()

    # The fixture holds two playlists: "DEMO" with 107 tracks and an empty
    # "CUE Analysis Playlist".
    counts = sorted(len(refs) for refs in refs_by_playlist.values())
    assert counts == [0, 107]
    populated = max(refs_by_playlist.values(), key=len)
    assert all(ref.rb_content_id for ref in populated)
    assert [ref.position for ref in populated] == sorted(ref.position for ref in populated)


def test_an_unanalysed_track_reports_no_bpm_rather_than_zero():
    # Rekordbox stores 0 for a track it has not analysed, and 85 of the 119
    # tracks in the owner's fixture do. Carrying that through as a real value
    # made "0 BPM" a measurement: it appeared in the collection table, plotted
    # at the foot of the builder's BPM chart, turned a set's range into
    # "0-120 BPM", and let the checks bar report nothing missing a BPM while
    # most of the set had none.
    db = _FakeRekordboxDatabase(
        contents=[
            _FakeContent(ID="1", title="Unanalysed", bpm_hundredths=0),
            _FakeContent(ID="2", title="Analysed", bpm_hundredths=12_800),
        ],
        playlists=[],
    )

    unanalysed, analysed = read_collection_snapshot(db)

    assert unanalysed.bpm is None
    assert analysed.bpm == 128.0
