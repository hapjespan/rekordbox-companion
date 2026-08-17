"""T016: POST /api/collection/reindex -- rebuilds the in-memory index (R6)."""

from fastapi.testclient import TestClient

from companion.api.collection import get_database
from companion.main import create_app
from companion.rb.reader import CollectionTrack


class _FakeDatabase:
    def get_content(self):
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
