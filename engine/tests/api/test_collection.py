"""T016: POST /api/collection/reindex -- rebuilds the in-memory index (R6).
T062: GET /api/collection -- search/sort/paginate over it (FR-024, US5).
GET /api/playlists/{rb_playlist_id}/tracks -- the same page, one playlist.
"""

from datetime import datetime

from fastapi.testclient import TestClient

from companion.api.collection import get_database
from companion.db.models import EnrichedGenre
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb.reader import CollectionTrack, PlaylistNode, PlaylistTrackRef


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


# rb1 carries both a musical key and a label, rb2 neither, rb3 a key only:
# both fields are optional in Rekordbox and absent for most tracks.
_INDEXED_TRACKS = [
    CollectionTrack(
        rb_content_id="rb1",
        artist="Daft Punk",
        title="One More Time",
        duration_ms=210_000,
        bpm=123.0,
        isrc=None,
        play_count=50,
        location="/music/one-more-time.mp3",
        musical_key="8m",
        label="Virgin",
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
        musical_key="G m",
    ),
]


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
    app.state.collection_index.rebuild(_INDEXED_TRACKS)
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
        "musical_key": "8m",
        "label": "Virgin",
    }


def test_collection_item_reports_an_absent_key_and_label_as_null():
    # Both come straight from Rekordbox and are absent for most tracks, so
    # null is the normal answer, never a reason to omit the field.
    client = _seeded_client()

    item = client.get("/api/collection", params={"query": "get lucky"}).json()["items"][0]

    assert item["musical_key"] is None
    assert item["label"] is None


def test_collection_item_keeps_the_key_verbatim_including_classical_notation():
    # No normalisation, no Camelot conversion: the DJ recognises their own
    # notation and a lossy conversion is worse than none.
    client = _seeded_client()

    item = client.get("/api/collection", params={"query": "rolling"}).json()["items"][0]

    assert item["musical_key"] == "G m"


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


# --- ids filter (resolving known ids without a paged sweep) -----------------
#
# Two views need BPM/key/title for a handful of known rb_content_ids (the
# Structure builder's phase rows, the review queue's candidate cards) and
# previously had to sweep pages of GET /api/collection until every wanted id
# turned up, capping out at `_MAX_LIMIT` on a large collection.


def test_collection_ids_filter_returns_exactly_the_requested_tracks():
    client = _seeded_client()

    response = client.get("/api/collection", params={"ids": ["rb1", "rb3"]})

    body = response.json()
    assert body["total"] == 2
    assert {item["rb_content_id"] for item in body["items"]} == {"rb1", "rb3"}


def test_collection_ids_filter_silently_drops_unknown_ids():
    # No error for an id the collection doesn't have -- the caller compares
    # the ids it sent against `items` to see which ones came back.
    client = _seeded_client()

    response = client.get("/api/collection", params={"ids": ["rb1", "does-not-exist"]})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["rb_content_id"] == "rb1"


def test_collection_ids_filter_applies_before_query_sort_and_paging():
    # `ids` narrows the set first; `query`, `sort` and `limit`/`offset` still
    # apply on top of that narrowed set, same as they do for every other page.
    client = _seeded_client()

    response = client.get("/api/collection", params={"ids": ["rb1", "rb2", "rb3"], "query": "daft"})

    body = response.json()
    assert {item["rb_content_id"] for item in body["items"]} == {"rb1", "rb2"}


def test_collection_ids_filter_returns_the_full_collection_track_shape():
    client = _seeded_client()

    item = client.get("/api/collection", params={"ids": ["rb1"]}).json()["items"][0]

    assert item == {
        "rb_content_id": "rb1",
        "artist": "Daft Punk",
        "title": "One More Time",
        "duration_ms": 210_000,
        "bpm": 123.0,
        "play_count": 50,
        "genres": [],
        "format": "mp3",
        "musical_key": "8m",
        "label": "Virgin",
    }


def test_collection_ids_filter_rejects_more_ids_than_the_bound():
    client = _seeded_client()

    response = client.get("/api/collection", params={"ids": [f"rb{i}" for i in range(201)]})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "too_many_ids"
    assert body["field"] == "ids"


def test_collection_ids_filter_accepts_the_max_allowed_count():
    client = _seeded_client()

    response = client.get("/api/collection", params={"ids": [f"rb{i}" for i in range(200)]})

    assert response.status_code == 200


def test_collection_without_ids_behaves_exactly_as_before():
    # Omitting `ids` entirely must not change the existing default-page
    # behaviour (no regression on the untouched code path).
    client = _seeded_client()

    response = client.get("/api/collection")

    assert response.status_code == 200
    assert response.json()["total"] == 3


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


# --- GET /api/playlists/{rb_playlist_id}/tracks ------------------------------
#
# The Collection view filtered to one Rekordbox playlist: the same
# `{total, items: [CollectionTrack]}` body as GET /api/collection, so the
# frontend reuses its table without a second row type. Membership comes from
# master.db (the playlist-to-content relation lives there and nowhere else);
# every track field comes from the in-memory index (ADR 0012), which is why an
# unindexed collection is a documented refusal rather than an empty page.


def _playlist_client(monkeypatch, refs_by_playlist, indexed_tracks=_INDEXED_TRACKS, genre_rows=()):
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

    monkeypatch.setattr(
        "companion.api.collection.read_playlist_track_refs",
        lambda db, rb_playlist_id: refs_by_playlist.get(rb_playlist_id),
    )
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_database] = lambda: _FakeDatabase()
    app.state.collection_index.rebuild(indexed_tracks)
    return TestClient(app)


_DEMO_REFS = {
    "pl1": [
        PlaylistTrackRef(rb_content_id="rb3", position=1),
        PlaylistTrackRef(rb_content_id="rb1", position=2),
        PlaylistTrackRef(rb_content_id="rb2", position=3),
    ],
    "empty": [],
}


def test_playlist_tracks_returns_503_when_rekordbox_is_not_found():
    # Real assertion, no mocking: same shared get_database dependency as
    # reindex and /api/playlists, so it fails the same documented way.
    client = TestClient(create_app())

    response = client.get("/api/playlists/pl1/tracks")

    assert response.status_code == 503
    assert response.json()["code"] == "rekordbox_not_found"


def test_playlist_tracks_returns_the_playlist_in_playlist_order(monkeypatch):
    client = _playlist_client(monkeypatch, _DEMO_REFS)

    response = client.get("/api/playlists/pl1/tracks")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    # Rekordbox's own playlist order, not the artist sort /api/collection
    # defaults to: the DJ built that order on purpose.
    assert [item["rb_content_id"] for item in body["items"]] == ["rb3", "rb1", "rb2"]


def test_playlist_tracks_item_shape_is_identical_to_the_collection_item_shape(monkeypatch):
    client = _playlist_client(monkeypatch, _DEMO_REFS)

    item = client.get("/api/playlists/pl1/tracks", params={"query": "one more time"}).json()[
        "items"
    ][0]

    assert item == {
        "rb_content_id": "rb1",
        "artist": "Daft Punk",
        "title": "One More Time",
        "duration_ms": 210_000,
        "bpm": 123.0,
        "play_count": 50,
        "genres": [],
        "format": "mp3",
        "musical_key": "8m",
        "label": "Virgin",
    }


def test_playlist_tracks_reports_enriched_genres_like_the_collection_does(monkeypatch):
    # Genres live in the app's own database, so they must be joined in here
    # exactly as GET /api/collection joins them.
    client = _playlist_client(
        monkeypatch,
        _DEMO_REFS,
        genre_rows=[
            EnrichedGenre(
                rb_content_id="rb1",
                genre="house",
                source="musicbrainz",
                updated_at=datetime(2026, 8, 18),
            )
        ],
    )

    item = client.get("/api/playlists/pl1/tracks", params={"query": "one more"}).json()["items"][0]

    assert [(g["genre"], g["source"]) for g in item["genres"]] == [("house", "musicbrainz")]


def test_playlist_tracks_supports_the_same_search_and_sort_as_the_collection(monkeypatch):
    client = _playlist_client(monkeypatch, _DEMO_REFS)

    searched = client.get("/api/playlists/pl1/tracks", params={"query": "daft"}).json()
    sorted_desc = client.get("/api/playlists/pl1/tracks", params={"sort": "-play_count"}).json()

    assert {item["rb_content_id"] for item in searched["items"]} == {"rb1", "rb2"}
    assert [item["rb_content_id"] for item in sorted_desc["items"]] == ["rb1", "rb3", "rb2"]


def test_playlist_tracks_rejects_an_unknown_sort_field_by_name(monkeypatch):
    client = _playlist_client(monkeypatch, _DEMO_REFS)

    response = client.get("/api/playlists/pl1/tracks", params={"sort": "genre"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_sort"
    assert body["field"] == "sort"


def test_playlist_tracks_paginates_within_the_same_bounds_as_the_collection(monkeypatch):
    client = _playlist_client(monkeypatch, _DEMO_REFS)

    page = client.get("/api/playlists/pl1/tracks", params={"limit": 1, "offset": 1}).json()

    assert page["total"] == 3
    assert [item["rb_content_id"] for item in page["items"]] == ["rb1"]
    assert client.get("/api/playlists/pl1/tracks", params={"offset": -1}).status_code == 422
    assert client.get("/api/playlists/pl1/tracks", params={"limit": 0}).status_code == 422
    assert client.get("/api/playlists/pl1/tracks", params={"limit": 100_000}).status_code == 422
    assert client.get("/api/playlists/pl1/tracks", params={"limit": 200}).status_code == 200


def test_playlist_tracks_returns_404_for_an_unknown_playlist_id(monkeypatch):
    client = _playlist_client(monkeypatch, _DEMO_REFS)

    response = client.get("/api/playlists/does-not-exist/tracks")

    assert response.status_code == 404
    assert response.json()["code"] == "rekordbox_playlist_not_found"


def test_playlist_tracks_returns_an_empty_page_for_an_empty_playlist(monkeypatch):
    # A playlist that exists and holds nothing is not an error, the same
    # distinction the Spotify fetch draws between "refused" and "empty".
    client = _playlist_client(monkeypatch, _DEMO_REFS)

    response = client.get("/api/playlists/empty/tracks")

    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}


def test_playlist_tracks_refuses_when_the_collection_has_not_been_indexed(monkeypatch):
    # Every track field comes from the in-memory index; without a scan the
    # honest answer is "scan first", never an empty playlist (the phase 7
    # lesson: a refusal must never look like no results).
    client = _playlist_client(monkeypatch, _DEMO_REFS, indexed_tracks=[])

    response = client.get("/api/playlists/pl1/tracks")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "collection_not_indexed"
    assert "message" in body


def test_playlist_tracks_skips_a_member_the_index_no_longer_knows(monkeypatch):
    # A stale index (the DJ deleted a track in Rekordbox since the last scan)
    # must not fabricate a row with empty artist/title.
    refs = {
        "pl1": [
            PlaylistTrackRef(rb_content_id="rb1", position=1),
            PlaylistTrackRef(rb_content_id="gone", position=2),
        ]
    }
    client = _playlist_client(monkeypatch, refs)

    body = client.get("/api/playlists/pl1/tracks").json()

    assert body["total"] == 1
    assert [item["rb_content_id"] for item in body["items"]] == ["rb1"]
