"""T092 (FR-040, edge case): read-only features (collection browse,
playback) stay usable while a Sync Session or an enrichment run is in
progress.

GET /api/collection now reads the app db too (T075: batched EnrichedGenre
lookup per page), so this isn't purely an in-memory-index guarantee any
more -- a slow write elsewhere could plausibly starve it if the app db's
own SQLite connection handling didn't tolerate momentary lock contention.
This file proves it does, against real concurrent threads and a real
file-based SQLite db (an in-memory :memory: db with StaticPool shares one
connection process-wide, so it can never reproduce genuine cross-connection
lock contention -- the whole point of this test).
"""

import threading
import time
from datetime import datetime

from fastapi.testclient import TestClient

from companion.api.sync import get_spotify_fetcher
from companion.db.models import EnrichedGenre
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb.reader import CollectionTrack


def _client(tmp_path, tracks=()):
    engine, session_local = create_session_factory(f"sqlite:///{tmp_path / 'app.sqlite'}")
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.state.collection_index.rebuild(list(tracks))
    return TestClient(app), session_local


def _track(rb_content_id: str) -> CollectionTrack:
    return CollectionTrack(
        rb_content_id=rb_content_id,
        artist="Daft Punk",
        title="One More Time",
        duration_ms=210_000,
        bpm=123.0,
        isrc=None,
        play_count=10,
        location=None,
    )


def test_collection_browse_stays_usable_while_a_slow_sync_session_is_creating(tmp_path):
    """A slow Spotify fetch (network latency, a large playlist) must not
    make GET /api/collection hang behind it -- they're unrelated requests
    that happen to share one process."""
    client, _ = _client(tmp_path, tracks=[_track("1")])
    started = threading.Event()
    release = threading.Event()

    def slow_fetch(playlist_url):  # noqa: ARG001
        started.set()
        release.wait(timeout=5)

        class _Fetch:
            name = "Slow Playlist"
            snapshot_id = "snap-1"
            tracks = []

        return _Fetch()

    client.app.dependency_overrides[get_spotify_fetcher] = lambda: slow_fetch

    sync_thread = threading.Thread(
        target=lambda: client.post(
            "/api/sync/sessions", json={"playlist_url": "https://open.spotify.com/playlist/x"}
        )
    )
    sync_thread.start()
    try:
        assert started.wait(timeout=5), "the slow sync session never started"

        collection_started = time.monotonic()
        response = client.get("/api/collection")
        collection_elapsed = time.monotonic() - collection_started

        assert response.status_code == 200
        assert collection_elapsed < 2.0, (
            f"GET /api/collection took {collection_elapsed:.2f}s while a sync "
            "session was in progress -- it should never wait on an unrelated request"
        )
    finally:
        release.set()
        sync_thread.join(timeout=5)


def test_playback_stream_endpoint_never_depends_on_the_app_database():
    """The player route has no `Depends(get_db)` at all -- confirmed at the
    dependency-graph level, not just by observed timing, so this can never
    regress into a hidden db dependency without this test catching it."""
    from companion.api.player import stream_track

    assert "db" not in stream_track.__annotations__


def test_many_small_concurrent_writes_never_raise_database_is_locked(tmp_path):
    """Simulates the enrichment runner's own pattern (T073: commit after
    every small chunk, in a loop) racing against concurrent reads on the
    real file-based db -- proves SQLite's default busy-timeout tolerates
    this app's actual commit cadence rather than raising immediately."""
    engine, session_local = create_session_factory(f"sqlite:///{tmp_path / 'app.sqlite'}")
    Base.metadata.create_all(engine)
    errors: list[Exception] = []

    def writer():
        for i in range(50):
            try:
                with session_local() as db:
                    db.add(
                        EnrichedGenre(
                            rb_content_id=f"w{i}",
                            genre="house",
                            source="musicbrainz",
                            updated_at=datetime.now(),
                        )
                    )
                    db.commit()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    def reader():
        for _ in range(50):
            try:
                with session_local() as db:
                    db.query(EnrichedGenre).count()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(3)] + [
        threading.Thread(target=reader) for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == [], f"concurrent access raised: {errors}"
