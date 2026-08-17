"""T012: rb/reader.py — collection snapshot, playlist tree, RB detection.

The collection/playlist mapping tests inject a fake object satisfying the
same duck-typed interface as pyrekordbox's Rekordbox6Database, so they
verify reader.py's own field-mapping logic without needing a real
master.db. The real fixture (owner-supplied, quickstart.md) is required to
verify pyrekordbox's own file reading, not this module's logic — that
verification happens on the owner's Mac (research.md R3 precedent).
"""

from pathlib import Path

from companion.rb.reader import (
    detect_rekordbox,
    is_rekordbox_running,
    open_database,
    read_collection_snapshot,
    read_playlist_tree,
)


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


class _FakePlaylist:
    def __init__(self, **kwargs):
        self.ID = kwargs["ID"]
        self.Name = kwargs.get("name")
        self.ParentID = kwargs.get("parent_id")
        self.Seq = kwargs.get("seq")
        self._is_folder = kwargs.get("is_folder", False)

    @property
    def is_folder(self):
        return self._is_folder


class _FakeRekordboxDatabase:
    def __init__(self, contents, playlists):
        self._contents = contents
        self._playlists = playlists

    def get_content(self):
        return self._contents

    def get_playlist(self):
        return self._playlists


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


def test_read_playlist_tree_maps_folders_and_playlists():
    db = _FakeRekordboxDatabase(
        contents=[],
        playlists=[
            _FakePlaylist(ID="root", name="Bookings", is_folder=True, seq=1),
            _FakePlaylist(ID="child", name="Horeca", parent_id="root", is_folder=False, seq=2),
        ],
    )

    nodes = read_playlist_tree(db)

    assert len(nodes) == 2
    root, child = nodes
    assert root.rb_playlist_id == "root"
    assert root.name == "Bookings"
    assert root.parent_id is None
    assert root.is_folder is True
    assert child.parent_id == "root"
    assert child.is_folder is False
