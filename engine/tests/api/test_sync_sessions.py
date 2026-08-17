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
reporting (contracts/api.md: "starts fetch+match; progress via SSE") was a
separate concern when this file was first written (T022) but landed in T030,
which made `create_sync_session` `async def` and added one `sync_progress`
`events.publish()` call per track -- see
`test_publishes_one_sync_progress_event_per_track` below.

The three behaviours tasks.md names for T022 are covered first -- exactly
one status per track (FR-003), the 999-track cap refused before the session
starts (edge case), duplicate playlist positions reported once each (edge
case, spec.md's "same track twice" case). Accept/reject/apply and SSE are
out of scope (later US1/US2 tasks).

Two more cases are added once T028 (the router implementation) actually
landed, since T028's own task text names them explicitly and T022 didn't:
local/unavailable tracks classified `unmatchable` rather than dropped or
crashing, and `playlist_link` reuse across two sessions for the same URL
(FR-010's "re-use one Sync Session lineage per Spotify playlist URL").

This file was committed RED (T022) before `companion.api.sync` existed;
T028 turned it green. Same US1 red/green split as T019-T021.
"""

from fastapi.testclient import TestClient

from companion.api.sync import get_spotify_fetcher
from companion.db.session import Base, create_session_factory, get_db
from companion.integrations import spotify as spotify_module
from companion.main import create_app
from companion.rb.reader import CollectionTrack


class _FakeTrack:
    def __init__(self, spotify_track_id, artist, title, duration_ms, isrc=None, is_local=False):
        self.spotify_track_id = spotify_track_id
        self.isrc = isrc
        self.artist = artist
        self.title = title
        self.duration_ms = duration_ms
        self.is_local = is_local


class _FakePlaylistFetch:
    def __init__(self, name, snapshot_id, tracks):
        self.name = name
        self.snapshot_id = snapshot_id
        self.tracks = tracks


def _client_with_fetch(fetch, collection_entries=()):
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_spotify_fetcher] = lambda: fetch
    app.state.collection_index.rebuild(list(collection_entries))
    return TestClient(app)


def _client(tracks, collection_entries=()):
    def fetch(playlist_url):
        return _FakePlaylistFetch("Example Playlist", "snap-1", tracks)

    return _client_with_fetch(fetch, collection_entries)


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


def test_local_or_unavailable_track_is_reported_unmatchable_not_dropped():
    # spec.md edge case: a local file / unavailable track has no usable
    # identifiers -- it must be counted separately, never silently dropped.
    tracks = [
        _FakeTrack("sp1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839"),
        _FakeTrack(None, "", "", 0, isrc=None),
    ]
    collection = [
        _collection_track("rb1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839")
    ]
    client = _client(tracks, collection)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/local"}
    )

    assert response.status_code == 200
    totals = response.json()["totals"]
    assert sum(totals.values()) == 2
    assert totals["matched"] == 1
    assert totals["unmatchable"] == 1


def test_resyncing_the_same_playlist_url_reuses_the_same_playlist_link():
    # FR-010: re-use one Sync Session lineage per Spotify playlist URL.
    tracks = [_FakeTrack("sp1", "Example Artist", "Example Song", 210_000)]
    client = _client(tracks)

    first = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/resync"}
    )
    second = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/resync"}
    )

    assert first.json()["id"] != second.json()["id"]
    assert first.json()["playlist_link_id"] == second.json()["playlist_link_id"]


def test_a_locally_tagged_track_with_real_artist_title_is_still_unmatchable():
    # T028 review finding: a local file can carry real artist/title ID3 tags
    # (so "no usable identifiers" alone would miss it) but never a Spotify
    # id/ISRC to match on -- `is_local` must be sufficient on its own.
    tracks = [
        _FakeTrack("sp1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839"),
        _FakeTrack(None, "Local Artist", "Local Track", 200_000, is_local=True),
    ]
    collection = [
        _collection_track("rb1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839")
    ]
    client = _client(tracks, collection)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/localtag"}
    )

    totals = response.json()["totals"]
    assert totals["matched"] == 1
    assert totals["unmatchable"] == 1


def test_playlist_too_large_error_from_the_fetcher_maps_to_422():
    # Production path: integrations.spotify short-circuits pagination and
    # raises before returning anything, unlike the fixed-list fake above.
    def fetch(playlist_url):
        raise spotify_module.PlaylistTooLargeError(total=5000)

    client = _client_with_fetch(fetch)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/big"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "playlist_too_large"


def test_invalid_playlist_url_maps_to_422_with_field():
    def fetch(playlist_url):
        raise spotify_module.InvalidPlaylistUrlError(f"not a Spotify URL: {playlist_url!r}")

    client = _client_with_fetch(fetch)

    response = client.post("/api/sync/sessions", json={"playlist_url": "not-a-url"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_playlist_url"
    assert body["field"] == "playlist_url"


def test_unreachable_playlist_maps_to_404_with_field():
    def fetch(playlist_url):
        raise spotify_module.PlaylistUnreachableError(f"playlist {playlist_url!r} is private")

    client = _client_with_fetch(fetch)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/private"}
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "playlist_unreachable"
    assert body["field"] == "playlist_url"


def test_not_connected_maps_to_409():
    def fetch(playlist_url):
        raise spotify_module.NotConnectedError("no Spotify session")

    client = _client_with_fetch(fetch)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/abc"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "spotify_not_connected"


def test_session_expiring_mid_sync_fails_with_a_reconnect_prompt_and_no_partial_report():
    # T104, spec.md edge case: "the Spotify session expires mid Sync
    # Session: the session fails with a re-connect prompt and no partial
    # report is presented as complete."
    def fetch(playlist_url):
        raise spotify_module.SessionExpiredError("Spotify rejected the access token")

    client = _client_with_fetch(fetch)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/expired"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "spotify_session_expired"

    sessions = client.get("/api/sync/sessions").json()
    assert sessions == []


def test_publishes_one_sync_progress_event_per_track(monkeypatch):
    published = []
    monkeypatch.setattr(
        "companion.api.sync.events.publish", lambda event, data: published.append((event, data))
    )
    tracks = [
        _FakeTrack("sp1", "Example Artist", "Example Song", 210_000, isrc="USRC17607839"),
        _FakeTrack("sp2", "Nobody At All", "Nothing Similar", 180_000),
    ]
    client = _client(tracks)

    response = client.post(
        "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/progress"}
    )
    session_id = response.json()["id"]

    assert [event for event, _ in published] == ["sync_progress", "sync_progress"]
    assert published[0][1] == {"session_id": session_id, "done": 1, "total": 2}
    assert published[1][1] == {"session_id": session_id, "done": 2, "total": 2}
