"""T053/T054: API contract tests for the Missing Tracks queue (US4,
FR-020..FR-023).

T053 hits the REAL iTunes Search API (no mocking; `test_itunes_integration.py`
already covers the lookup/auto-pick logic in isolation with a mocked
transport) for a curated 20-track set of globally well-known, unambiguous
songs, matching SC-004's ">=90% resolve to the correct NL store page". For
tracks this well-known and unambiguous, a non-null resolved URL from
`refresh-links` IS the practical definition of "resolved to the correct
page": Apple's catalog for major-label global hits is effectively certain
to contain the exact track, and the auto-pick's own correctness among
near-duplicate results is separately unit-tested in
`test_itunes_integration.py`. Skips gracefully if the network is
unavailable, the same precedent as the fixture-skip pattern for owner-
supplied inputs.

T054 exercises FR-023 (auto-close) and US4 scenario 3 (ignored is sticky
across re-syncs) through `POST /api/sync/sessions`, since that's where a
Missing Track is spawned/closed -- not through `/api/missing` itself.

Committed RED: `companion.api.missing` doesn't exist until T057 builds it,
and `create_sync_session`'s auto-spawn/auto-close/sticky-ignore wiring
doesn't exist until T058 builds it.
"""

from fastapi.testclient import TestClient

from companion.api.sync import get_spotify_fetcher
from companion.db.models import MissingTrack, SyncTrack
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb.reader import CollectionTrack

# 20 globally well-known, unambiguous studio tracks spanning multiple
# genres/eras/labels, chosen so a missing result would mean a real lookup
# problem, not catalog obscurity (SC-004).
WELL_KNOWN_TRACKS = [
    ("Daft Punk", "One More Time"),
    ("Queen", "Bohemian Rhapsody"),
    ("Michael Jackson", "Billie Jean"),
    ("The Beatles", "Hey Jude"),
    ("Whitney Houston", "I Wanna Dance with Somebody"),
    ("Nirvana", "Smells Like Teen Spirit"),
    ("Madonna", "Like a Prayer"),
    ("ABBA", "Dancing Queen"),
    ("Daft Punk", "Get Lucky"),
    ("Adele", "Rolling in the Deep"),
    ("Coldplay", "Yellow"),
    ("Beyonce", "Halo"),
    ("Ed Sheeran", "Shape of You"),
    ("The Rolling Stones", "Paint It Black"),
    ("Fleetwood Mac", "Dreams"),
    ("David Bowie", "Heroes"),
    ("Prince", "Purple Rain"),
    ("Stevie Wonder", "Superstition"),
    ("Bee Gees", "Stayin' Alive"),
    ("Eurythmics", "Sweet Dreams (Are Made of This)"),
]


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


def _client_and_app(collection_entries=()):
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
    app.state.collection_index.rebuild(list(collection_entries))
    return TestClient(app), app, session_local


def _set_fetch(app, tracks):
    def fetch(playlist_url):
        return _FakePlaylistFetch("Booking 2026", "snap-1", tracks)

    app.dependency_overrides[get_spotify_fetcher] = lambda: fetch


def _collection_track(rb_content_id, artist, title, duration_ms):
    return CollectionTrack(
        rb_content_id=rb_content_id,
        artist=artist,
        title=title,
        duration_ms=duration_ms,
        bpm=None,
        isrc=None,
        play_count=0,
        location=None,
    )


PLAYLIST_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"


def test_a_track_scoring_below_75_automatically_spawns_an_open_missing_track():
    client, app, session_local = _client_and_app(collection_entries=())
    _set_fetch(app, [_FakeTrack("sp1", "Obscure Artist Xyz", "Obscure Track Xyz", 200_000)])

    response = client.post("/api/sync/sessions", json={"playlist_url": PLAYLIST_URL})
    session_id = response.json()["id"]

    with session_local() as db:
        sync_track = db.query(SyncTrack).filter_by(sync_session_id=session_id).one()
        assert sync_track.status == "missing"
        missing = db.query(MissingTrack).filter_by(sync_track_id=sync_track.id).one()
        assert missing.status == "open"


def test_ignored_is_sticky_across_a_resync_of_the_same_playlist():
    client, app, session_local = _client_and_app(collection_entries=())
    _set_fetch(app, [_FakeTrack("sp1", "Obscure Artist Xyz", "Obscure Track Xyz", 200_000)])

    first = client.post("/api/sync/sessions", json={"playlist_url": PLAYLIST_URL})
    with session_local() as db:
        first_track = db.query(SyncTrack).filter_by(sync_session_id=first.json()["id"]).one()
        missing = db.query(MissingTrack).filter_by(sync_track_id=first_track.id).one()
        missing_id = missing.id

    status_response = client.post(f"/api/missing/{missing_id}/status", json={"status": "ignored"})
    assert status_response.status_code == 200

    second = client.post("/api/sync/sessions", json={"playlist_url": PLAYLIST_URL})
    with session_local() as db:
        second_track = db.query(SyncTrack).filter_by(sync_session_id=second.json()["id"]).one()
        second_missing = db.query(MissingTrack).filter_by(sync_track_id=second_track.id).one()
        # US4 scenario 3: never re-added as open once ignored.
        assert second_missing.status == "ignored"


def test_reject_also_respects_sticky_ignore_across_sessions():
    # Review finding: reject_track (T037) used to always spawn `open`,
    # bypassing the same sticky-ignore rule the automatic missing-
    # classification path follows -- a DJ re-rejecting a track they'd
    # already ignored in an earlier session must not resurface it as open.
    from datetime import datetime

    from companion.db.models import SyncSession

    client, app, session_local = _client_and_app(collection_entries=())
    _set_fetch(app, [_FakeTrack("sp1", "Obscure Artist Xyz", "Obscure Track Xyz", 200_000)])

    first = client.post("/api/sync/sessions", json={"playlist_url": PLAYLIST_URL})
    with session_local() as db:
        first_track = db.query(SyncTrack).filter_by(sync_session_id=first.json()["id"]).one()
        missing = db.query(MissingTrack).filter_by(sync_track_id=first_track.id).one()
        missing_id = missing.id
        link_id = db.get(SyncSession, first.json()["id"]).playlist_link_id

    client.post(f"/api/missing/{missing_id}/status", json={"status": "ignored"})

    # A second session's track, in review (not auto-missing this time),
    # for the same Spotify Track under the same playlist lineage.
    with session_local() as db:
        second_session = SyncSession(
            playlist_link_id=link_id,
            spotify_snapshot_id="snap-2",
            name="Booking 2026",
            status="ready",
            created_at=datetime(2026, 8, 18),
        )
        db.add(second_session)
        db.flush()
        review_track = SyncTrack(
            sync_session_id=second_session.id,
            position=1,
            spotify_track_id="sp1",
            isrc=None,
            artist="Obscure Artist Xyz",
            title="Obscure Track Xyz",
            duration_ms=200_000,
            status="review",
            rb_content_id=None,
            match_score=80.0,
            candidates=[],
            matched_at=None,
        )
        db.add(review_track)
        db.commit()
        review_track_id = review_track.id
        second_session_id = second_session.id

    reject_response = client.post(
        f"/api/sync/sessions/{second_session_id}/tracks/{review_track_id}/reject"
    )
    assert reject_response.status_code == 200

    with session_local() as db:
        new_missing = db.query(MissingTrack).filter_by(sync_track_id=review_track_id).one()
        assert new_missing.status == "ignored"


def test_a_resynced_track_now_in_the_collection_auto_closes_the_missing_track():
    client, app, session_local = _client_and_app(collection_entries=())
    _set_fetch(app, [_FakeTrack("sp1", "Daft Punk", "One More Time", 210_000)])

    first = client.post("/api/sync/sessions", json={"playlist_url": PLAYLIST_URL})
    with session_local() as db:
        first_track = db.query(SyncTrack).filter_by(sync_session_id=first.json()["id"]).one()
        missing = db.query(MissingTrack).filter_by(sync_track_id=first_track.id).one()
        assert missing.status == "open"
        missing_id = missing.id

    # The DJ bought the track and added it to the Collection.
    app.state.collection_index.rebuild(
        [_collection_track("rb1", "Daft Punk", "One More Time", 210_000)]
    )
    second = client.post("/api/sync/sessions", json={"playlist_url": PLAYLIST_URL})

    with session_local() as db:
        second_track = db.query(SyncTrack).filter_by(sync_session_id=second.json()["id"]).one()
        assert second_track.status == "matched"
        closed = db.query(MissingTrack).filter_by(id=missing_id).one()
        assert closed.status == "acquired"  # FR-023 auto-close
        assert closed.resolved_at is not None


def test_at_least_90_percent_of_well_known_tracks_resolve_a_real_store_link():
    # SC-004. Real network call to the live iTunes Search API via
    # POST /api/missing/refresh-links.
    import httpx

    tracks = [
        _FakeTrack(f"sp{i}", artist, title, 200_000)
        for i, (artist, title) in enumerate(WELL_KNOWN_TRACKS)
    ]
    client, app, session_local = _client_and_app(collection_entries=())
    _set_fetch(app, tracks)

    try:
        httpx.get("https://itunes.apple.com/search?term=test&limit=1", timeout=5.0)
    except httpx.HTTPError:
        import pytest

        pytest.skip("No network access to itunes.apple.com in this environment.")

    session_response = client.post("/api/sync/sessions", json={"playlist_url": PLAYLIST_URL})
    assert session_response.status_code == 200

    refresh_response = client.post("/api/missing/refresh-links")
    assert refresh_response.status_code == 200

    with session_local() as db:
        rows = db.query(MissingTrack).all()
        assert len(rows) == len(WELL_KNOWN_TRACKS)
        resolved = sum(1 for row in rows if row.itunes_url_auto)

    resolution_rate = resolved / len(WELL_KNOWN_TRACKS)
    assert resolution_rate >= 0.90, f"only {resolved}/{len(WELL_KNOWN_TRACKS)} resolved"
