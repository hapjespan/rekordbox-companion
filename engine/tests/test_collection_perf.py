"""T060 (SC-005, FR-024): GET /api/collection responds within 100ms/keystroke
at 40.000 indexed tracks -- tested above the 30k target constraints.md names.

Synthetic entries, not a real fixture: SC-005 is about the search/sort path's
own algorithmic performance at scale, not about real Collection data: a
40k-track fixture Collection isn't something the project has (or needs) to
own for this to be genuine evidence.
"""

import time

from fastapi.testclient import TestClient

from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app
from companion.rb.reader import CollectionTrack

TRACK_COUNT = 40_000
BUDGET_MS = 100


def _synthetic_tracks(count: int) -> list[CollectionTrack]:
    artists = ["Daft Punk", "Adele", "Coldplay", "Beyonce", "Ed Sheeran", "Queen", "ABBA"]
    return [
        CollectionTrack(
            rb_content_id=str(i),
            artist=f"{artists[i % len(artists)]} {i}",
            title=f"Track Title {i}",
            duration_ms=180_000 + (i % 600) * 1000,
            bpm=float(60 + (i % 120)),
            isrc=None,
            play_count=i % 500,
            location=f"/music/track-{i}.mp3",
        )
        for i in range(count)
    ]


def _client_with_index() -> TestClient:
    # An empty in-memory database with the schema applied, same pattern as
    # tests/api/test_collection.py: the endpoint joins `enriched_genre`, so a
    # client built on the ambient dev database only works where that database
    # already exists and is migrated (it did locally, not in CI).
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
    app.state.collection_index.rebuild(_synthetic_tracks(TRACK_COUNT))
    return TestClient(app)


def test_unfiltered_listing_responds_within_budget_at_40k_entries():
    client = _client_with_index()

    started = time.monotonic()
    response = client.get("/api/collection", params={"limit": 50})
    elapsed_ms = (time.monotonic() - started) * 1000

    assert response.status_code == 200
    assert response.json()["total"] == TRACK_COUNT
    assert elapsed_ms < BUDGET_MS, f"took {elapsed_ms:.1f}ms, budget is {BUDGET_MS}ms"


def test_search_responds_within_budget_at_40k_entries():
    client = _client_with_index()

    started = time.monotonic()
    response = client.get("/api/collection", params={"query": "coldplay", "limit": 50})
    elapsed_ms = (time.monotonic() - started) * 1000

    assert response.status_code == 200
    assert response.json()["total"] > 0
    assert elapsed_ms < BUDGET_MS, f"took {elapsed_ms:.1f}ms, budget is {BUDGET_MS}ms"


def test_sort_by_play_count_responds_within_budget_at_40k_entries():
    client = _client_with_index()

    started = time.monotonic()
    response = client.get("/api/collection", params={"sort": "-play_count", "limit": 50})
    elapsed_ms = (time.monotonic() - started) * 1000

    assert response.status_code == 200
    assert elapsed_ms < BUDGET_MS, f"took {elapsed_ms:.1f}ms, budget is {BUDGET_MS}ms"


def test_sort_by_bpm_responds_within_budget_at_40k_entries():
    # The algorithmically distinct path (review finding): _sort_entries
    # splits into a with-BPM/without-BPM pass for this field specifically,
    # unlike the single-pass sorted() the other three fields use.
    client = _client_with_index()

    started = time.monotonic()
    response = client.get("/api/collection", params={"sort": "-bpm", "limit": 50})
    elapsed_ms = (time.monotonic() - started) * 1000

    assert response.status_code == 200
    assert elapsed_ms < BUDGET_MS, f"took {elapsed_ms:.1f}ms, budget is {BUDGET_MS}ms"
