"""T016: POST /api/collection/reindex -- rebuilds the in-memory index (R6)."""

from fastapi.testclient import TestClient

from companion.api.collection import get_database
from companion.main import create_app
from companion.rb.reader import CollectionTrack, PlaylistNode


class _FakeDatabase:
    def get_content(self):
        return []

    def get_playlist(self):
        return []


def test_reindex_returns_503_when_rekordbox_is_not_found():
    # Real assertion, no mocking: this dev container genuinely has no
    # Rekordbox install, so the real get_database dependency raises.
    client = TestClient(create_app())

    response = client.post("/api/collection/reindex")

    assert response.status_code == 503
    # Flat {code, message, field?} per contracts/api.md's error convention,
    # not FastAPI's default {"detail": {...}} envelope (T016 review finding).
    body = response.json()
    assert body["code"] == "rekordbox_not_found"
    assert "message" in body


def test_reindex_returns_indexed_count_and_took_ms(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_database] = lambda: _FakeDatabase()
    client = TestClient(app)

    monkeypatch.setattr(
        "companion.api.collection.read_collection_snapshot",
        lambda db: [
            CollectionTrack(
                rb_content_id="1",
                artist="Example",
                title="Track",
                duration_ms=1000,
                bpm=120.0,
                isrc=None,
                play_count=0,
                location=None,
            )
        ],
    )

    response = client.post("/api/collection/reindex")

    assert response.status_code == 200
    body = response.json()
    assert body["indexed_count"] == 1
    assert isinstance(body["took_ms"], int)
    assert body["took_ms"] >= 0


def test_reindex_actually_rebuilds_the_apps_shared_index(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_database] = lambda: _FakeDatabase()
    monkeypatch.setattr(
        "companion.api.collection.read_collection_snapshot",
        lambda db: [
            CollectionTrack(
                rb_content_id="1",
                artist="Example",
                title="Track",
                duration_ms=None,
                bpm=None,
                isrc=None,
                play_count=0,
                location=None,
            )
        ],
    )
    client = TestClient(app)

    client.post("/api/collection/reindex")

    assert len(app.state.collection_index.entries) == 1


def test_playlists_returns_503_when_rekordbox_is_not_found():
    # Real assertion, no mocking: same shared get_database dependency as
    # reindex, so it fails the same way in this Rekordbox-less container.
    client = TestClient(create_app())

    response = client.get("/api/playlists")

    assert response.status_code == 503
    assert response.json()["code"] == "rekordbox_not_found"


def _patch_moved_db_path(monkeypatch, tmp_path):
    # T105: Rekordbox installed and pinned, but its configured database file
    # has moved or been deleted -- distinct from "never installed" (the
    # other 503 tests above), which is the only case those exercise.
    missing_path = tmp_path / "master.db"
    monkeypatch.setattr(
        "companion.rb.reader.rb_config.get_config",
        lambda section: {"version": "7.2.17", "db_path": missing_path},
    )


def test_reindex_returns_503_when_the_db_file_has_moved_or_been_deleted(monkeypatch, tmp_path):
    _patch_moved_db_path(monkeypatch, tmp_path)
    client = TestClient(create_app())

    response = client.post("/api/collection/reindex")

    assert response.status_code == 503
    assert response.json()["code"] == "rekordbox_not_found"


def test_playlists_returns_503_when_the_db_file_has_moved_or_been_deleted(monkeypatch, tmp_path):
    _patch_moved_db_path(monkeypatch, tmp_path)
    client = TestClient(create_app())

    response = client.get("/api/playlists")

    assert response.status_code == 503
    assert response.json()["code"] == "rekordbox_not_found"


def test_playlists_returns_the_tree_from_reader(monkeypatch):
    app = create_app()
    app.dependency_overrides[get_database] = lambda: _FakeDatabase()
    monkeypatch.setattr(
        "companion.api.collection.read_playlist_tree",
        lambda db: [
            PlaylistNode(
                rb_playlist_id="root",
                name="Bookings",
                parent_id=None,
                is_folder=True,
                position=1,
            ),
            PlaylistNode(
                rb_playlist_id="child",
                name="Horeca",
                parent_id="root",
                is_folder=False,
                position=2,
            ),
        ],
    )
    client = TestClient(app)

    response = client.get("/api/playlists")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["rb_playlist_id"] == "root"
    assert body[0]["is_folder"] is True
    assert body[1]["parent_id"] == "root"
