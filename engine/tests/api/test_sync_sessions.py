"""T022: API contract test for POST /api/sync/sessions (FR-003, edge cases).

Seam decision (this task's to make, since T026/integrations/spotify.py is a
separate [complexity: high] task and this test must not assume its internal
shape): `companion.api.sync` depends on `get_spotify_fetcher`, a thin
FastAPI dependency returning a `(playlist_url: str) -> SpotifyPlaylistFetch`
callable. `SpotifyPlaylistFetch` exposes `.name`, `.snapshot_id`, `.tracks`
(a list of `{spotify_track_id, isrc, artist, title, duration_ms}` dicts, one
per playlist position, duplicates included per the spec edge case below).
Tests override this dependency with a fake, the same seam-isolation pattern
`get_database` uses in test_collection.py -- `companion.api.sync` never
needs to know how `integrations/spotify.py` (OAuth, pagination, the real
Spotify Web API) is built, only that whatever calls it returns this shape.

Matching runs synchronously against `app.state.collection_index` (already
populated via the existing `/api/collection/reindex` seam, T016); this test
seeds it directly through `CollectionIndex.rebuild()`. SSE progress
reporting (contracts/api.md: "starts fetch+match; progress via SSE") is a
separate concern (a later US1 task); this test only asserts the HTTP
response once fetch+match has completed.

Only the three behaviours tasks.md names for T022 are covered here --
exactly one status per track (FR-003), the 999-track cap refused before the
session starts (edge case), duplicate playlist positions reported once each
(edge case, spec.md's "same track twice" case). Accept/reject/apply and SSE
are out of scope (later US1/US2 tasks).

Committed RED: `companion.api.sync` doesn't exist until T028 builds it
(tasks.md), same US1 red/green split as T019-T021 (owner-confirmed).
"""

from companion.api.sync import get_spotify_fetcher
from fastapi.testclient import TestClient

from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb.reader import CollectionTrack


class _FakeTrack:
    def __init__(self, spotify_track_id, artist, title, duration_ms, isrc=None):
        self.spotify_track_id = spotify_track_id
        self.isrc = isrc
        self.artist = artist
        self.title = title
        self.duration_ms = duration_ms


class _FakePlaylistFetch:
    def __init__(self, name, snapshot_id, tracks):
        self.name = name
        self.snapshot_id = snapshot_id
        self.tracks = tracks


def _client(tracks, collection_entries=()):
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    def fetch(playlist_url):
        return _FakePlaylistFetch("Example Playlist", "snap-1", tracks)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_spotify_fetcher] = lambda: fetch
    app.state.collection_index.rebuild(list(collection_entries))
    return TestClient(app)


def _collection_track(rb_content_id, artist, title, duration_ms, isrc=None):
    return CollectionTrack(
        rb_content_id=rb_content_id,
        artist=artist,
        title=title,
        duration_ms=duration_ms,
        bpm=None,
        isrc=isrc,
        play_count=0,
        location=None,
    )


def test_every_track_gets_exactly_one_status():
    tracks = [
        _FakeTrack("sp1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839"),
        _FakeTrack("sp2", "Nobody At All", "Nothing Similar", 180_000),
    ]
    collection = [
        _collection_track("rb1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839")
    ]
    client = _client(tracks, collection)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/abc"}
    )

    assert response.status_code == 200
    totals = response.json()["totals"]
    assert sum(totals.values()) == len(tracks)
    assert totals["matched"] == 1
    assert totals["missing"] == 1


def test_playlist_over_999_tracks_is_refused_before_the_session_starts():
    tracks = [_FakeTrack(f"sp{i}", "Artist", f"Track {i}", 200_000) for i in range(1000)]
    client = _client(tracks)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/big"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "playlist_too_large"

    sessions = client.get("/api/sync/sessions").json()
    assert sessions == []


def test_duplicate_track_at_two_playlist_positions_is_reported_once_each():
    tracks = [
        _FakeTrack("sp1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839"),
        _FakeTrack("sp1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839"),
    ]
    collection = [
        _collection_track("rb1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839")
    ]
    client = _client(tracks, collection)

    create_response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/dup"}
    )
    session_id = create_response.json()["id"]

    detail = client.get(f"/api/sync/sessions/{session_id}").json()

    assert len(detail["tracks"]) == 2
    assert {t["position"] for t in detail["tracks"]} == {1, 2}
    assert all(t["status"] == "matched" for t in detail["tracks"])
