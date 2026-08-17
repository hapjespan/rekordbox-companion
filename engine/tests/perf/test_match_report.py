"""T097: performance test -- SC-001 (100-track playlist against the
40.000-entry Collection index produces a complete match report within 30
seconds) and the 999-track cap (D12) within 5 minutes (plan.md
constraint-to-decision map). Gate-review finding B3.

Exercises the real `POST /api/sync/sessions` router end to end (fetch via a
fake, batch-match against a real 40k-entry `CollectionIndex`, persist,
publish SSE progress) -- the most direct evidence for "produces a complete
match report" within budget, not just the matching engine in isolation.

The naive per-track `find_best_match` (one `classify_match` call per
Collection entry, in a Python loop) cannot meet this budget at this scale:
benchmarked at ~10us/call, 100 tracks x 40k entries is ~4M calls (~41s,
already over the 30s bar), and 999 x 40k is ~40M calls (~400s, over the
5-minute bar). `api/sync.py`'s `_classify_tracks` batches every matchable
track through `matching.engine.find_best_matches`
(`rapidfuzz.process.cdist`) instead, which is what actually makes these
budgets achievable -- this test is what caught the naive version failing
them, and now guards the batched version staying fast enough (T097 finding
that led to that rewrite).
"""

import time

from fastapi.testclient import TestClient

from companion.api.sync import get_spotify_fetcher
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb.reader import CollectionTrack

COLLECTION_SIZE = 40_000


class _FakeTrack:
    def __init__(self, spotify_track_id, artist, title, duration_ms, isrc=None):
        self.spotify_track_id = spotify_track_id
        self.isrc = isrc
        self.artist = artist
        self.title = title
        self.duration_ms = duration_ms
        self.is_local = False


class _FakePlaylistFetch:
    def __init__(self, name, snapshot_id, tracks):
        self.name = name
        self.snapshot_id = snapshot_id
        self.tracks = tracks


def _build_app_with_large_collection():
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

    collection_tracks = [
        CollectionTrack(
            rb_content_id=f"rb{i}",
            artist=f"Artist {i % 5000}",
            title=f"Track Title Number {i}",
            duration_ms=180_000 + (i % 120) * 1000,
            bpm=120.0,
            isrc=f"USRC{i:08d}" if i % 10 == 0 else None,
            play_count=0,
            location=None,
        )
        for i in range(COLLECTION_SIZE)
    ]
    app.state.collection_index.rebuild(collection_tracks)
    return app


def _playlist_tracks(count: int) -> list[_FakeTrack]:
    # A realistic mix across tiers, not every track hitting the cheap ISRC
    # fast lane -- that would understate the fuzzy tier's real cost.
    tracks = []
    for i in range(count):
        if i % 3 == 0:
            source_idx = (i * 10) % COLLECTION_SIZE
            tracks.append(
                _FakeTrack(
                    f"sp{i}",
                    f"Artist {source_idx % 5000}",
                    f"Track Title Number {source_idx}",
                    180_000 + (source_idx % 120) * 1000,
                    isrc=f"USRC{source_idx:08d}",
                )
            )
        elif i % 3 == 1:
            tracks.append(
                _FakeTrack(f"sp{i}", f"Unknown Artist {i}", f"Unknown Title {i}", 200_000)
            )
        else:
            source_idx = (i * 7) % COLLECTION_SIZE
            tracks.append(
                _FakeTrack(
                    f"sp{i}",
                    f"Artist {source_idx % 5000}",
                    f"Track Title Number {source_idx} Extended",
                    180_000 + (source_idx % 120) * 1000,
                )
            )
    return tracks


def _post_playlist(app, tracks, playlist_url):
    def fetch(playlist_url):
        return _FakePlaylistFetch("Booking Set", "snap-1", tracks)

    app.dependency_overrides[get_spotify_fetcher] = lambda: fetch
    client = TestClient(app)

    started = time.perf_counter()
    response = client.post("/api/sync/sessions", json={"playlist_url": playlist_url})
    elapsed = time.perf_counter() - started
    return response, elapsed


def test_100_track_playlist_against_40k_index_completes_within_30_seconds():
    app = _build_app_with_large_collection()
    tracks = _playlist_tracks(100)

    response, elapsed = _post_playlist(app, tracks, "https://open.spotify.com/playlist/perf100")

    assert response.status_code == 200
    assert sum(response.json()["totals"].values()) == 100
    assert elapsed < 30, f"took {elapsed:.1f}s, SC-001's budget is 30s"


def test_999_track_playlist_against_40k_index_completes_within_5_minutes():
    app = _build_app_with_large_collection()
    tracks = _playlist_tracks(999)

    response, elapsed = _post_playlist(app, tracks, "https://open.spotify.com/playlist/perf999")

    assert response.status_code == 200
    assert sum(response.json()["totals"].values()) == 999
    assert elapsed < 300, f"took {elapsed:.1f}s, the 999-track cap's budget is 5 minutes (D12)"
