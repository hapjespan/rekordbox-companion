"""T016: POST /api/collection/reindex -- rebuilds the in-memory index (R6).
T062: GET /api/collection -- search/sort/paginate over it (FR-024, US5).
"""

from datetime import datetime

from fastapi.testclient import TestClient

from companion.api.collection import get_database
from companion.db.models import EnrichedGenre
from companion.db.session import Base, create_session_factory, get_db
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


def _seeded_client(genre_rows=()):
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    if genre_rows:
        with session_local() as db:
            db.add_all(genre_rows)
            db.commit()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.state.collection_index.rebuild(
        [
            CollectionTrack(
                rb_content_id="rb1",
                artist="Daft Punk",
                title="One More Time",
                duration_ms=210_000,
                bpm=123.0,
                isrc=None,
                play_count=50,
                location="/music/one-more-time.mp3",
            ),
            CollectionTrack(
                rb_content_id="rb2",
                artist="Daft Punk",
                title="Get Lucky",
                duration_ms=240_000,
                bpm=116.0,
                isrc=None,
                play_count=10,
                location="/music/get-lucky.M4A",
            ),
            CollectionTrack(
                rb_content_id="rb3",
                artist="Adele",
                title="Rolling in the Deep",
                duration_ms=228_000,
                bpm=None,
                isrc=None,
                play_count=30,
                location=None,
            ),
        ]
    )
    return TestClient(app)


def test_collection_lists_everything_by_default_sorted_by_artist():
    client = _seeded_client()

    response = client.get("/api/collection")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["artist"] for item in body["items"]] == ["Adele", "Daft Punk", "Daft Punk"]


def test_collection_search_matches_artist_or_title_case_insensitively():
    client = _seeded_client()

    response = client.get("/api/collection", params={"query": "LUCKY"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["rb_content_id"] == "rb2"


def test_collection_search_over_artist_finds_both_daft_punk_tracks():
    client = _seeded_client()

    response = client.get("/api/collection", params={"query": "daft"})

    body = response.json()
    assert body["total"] == 2
    assert {item["rb_content_id"] for item in body["items"]} == {"rb1", "rb2"}


def test_collection_sorts_by_play_count_descending():
    client = _seeded_client()

    response = client.get("/api/collection", params={"sort": "-play_count"})

    body = response.json()
    assert [item["rb_content_id"] for item in body["items"]] == ["rb1", "rb3", "rb2"]


def test_collection_sorts_by_bpm_with_missing_bpm_always_last():
    client = _seeded_client()

    ascending = client.get("/api/collection", params={"sort": "bpm"}).json()
    descending = client.get("/api/collection", params={"sort": "-bpm"}).json()

    assert [item["rb_content_id"] for item in ascending["items"]] == ["rb2", "rb1", "rb3"]
    assert [item["rb_content_id"] for item in descending["items"]] == ["rb1", "rb2", "rb3"]


def test_collection_pagination_slices_items_but_reports_the_full_total():
    client = _seeded_client()

    response = client.get("/api/collection", params={"limit": 1, "offset": 1})

    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["items"][0]["artist"] == "Daft Punk"  # second in default artist-sorted order


def test_collection_rejects_an_unknown_sort_field_by_name():
    client = _seeded_client()

    response = client.get("/api/collection", params={"sort": "genre"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_sort"
    assert body["field"] == "sort"


def test_collection_item_shape_matches_the_contract():
    client = _seeded_client()

    response = client.get("/api/collection", params={"query": "one more time"})

    item = response.json()["items"][0]
    assert item == {
        "rb_content_id": "rb1",
        "artist": "Daft Punk",
        "title": "One More Time",
        "duration_ms": 210_000,
        "bpm": 123.0,
        "play_count": 50,
        "genres": [],
        "format": "mp3",
    }


def test_collection_item_reports_real_enriched_genres():
    client = _seeded_client(
        genre_rows=[
            EnrichedGenre(
                rb_content_id="rb1",
                genre="house",
                source="musicbrainz",
                updated_at=datetime(2026, 8, 18),
            ),
            EnrichedGenre(
                rb_content_id="rb1",
                genre="disco",
                source="musicbrainz",
                updated_at=datetime(2026, 8, 18),
            ),
        ]
    )

    response = client.get("/api/collection", params={"query": "one more time"})

    item = response.json()["items"][0]
    assert {(g["genre"], g["source"]) for g in item["genres"]} == {
        ("house", "musicbrainz"),
        ("disco", "musicbrainz"),
    }


def test_collection_format_is_derived_from_the_location_extension_case_insensitively():
    client = _seeded_client()

    response = client.get("/api/collection", params={"query": "get lucky"})

    assert response.json()["items"][0]["format"] == "m4a"


def test_collection_format_is_none_when_the_track_has_no_location():
    client = _seeded_client()

    response = client.get("/api/collection", params={"query": "rolling"})

    assert response.json()["items"][0]["format"] is None


# --- limit/offset bounds (review finding) ------------------------------------
#
# Unbounded values let `entries[offset:offset+limit]` produce a silently wrong
# page (negative offset) or, at scale, hand `_genres_by_track` an IN clause
# with tens of thousands of parameters -- past SQLite's default bound-variable
# limit, an unhandled 500. Both are now rejected as 422s by FastAPI's own
# `Query` validation, before the handler body ever runs.


def test_collection_rejects_a_negative_offset():
    client = _seeded_client()

    response = client.get("/api/collection", params={"offset": -5})

    assert response.status_code == 422


def test_collection_rejects_a_zero_or_negative_limit():
    client = _seeded_client()

    assert client.get("/api/collection", params={"limit": 0}).status_code == 422
    assert client.get("/api/collection", params={"limit": -1}).status_code == 422


def test_collection_rejects_a_limit_above_the_cap():
    client = _seeded_client()

    response = client.get("/api/collection", params={"limit": 100_000})

    assert response.status_code == 422


def test_collection_accepts_the_max_allowed_limit():
    client = _seeded_client()

    response = client.get("/api/collection", params={"limit": 200})

    assert response.status_code == 200


# --- get_database closes its SQLCipher connection (review finding) ----------


def test_get_database_closes_the_connection_after_the_request(monkeypatch):
    from companion.api import collection as collection_module

    closed = []

    class _TrackingFakeDatabase:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(collection_module, "open_database", lambda: _TrackingFakeDatabase())
    monkeypatch.setattr(collection_module, "read_playlist_tree", lambda db: [])
    client = TestClient(create_app())

    response = client.get("/api/playlists")

    assert response.status_code == 200
    assert closed == [True]
