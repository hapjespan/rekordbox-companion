"""T075/T076: POST /api/enrichment/run, GET /api/enrichment/status,
GET /api/enrichment/unenriched, PUT /api/collection/{rb_content_id}/genres
(contracts/api.md), plus the enrichment_progress SSE event (R4)."""

import threading

from fastapi.testclient import TestClient

from companion.api import events
from companion.api.enrichment import get_background_runner
from companion.db.models import EnrichedGenre, EnrichmentState
from companion.db.session import Base, create_session_factory, get_db
from companion.enrichment import runner as enrichment_runner
from companion.main import create_app
from companion.rb.reader import CollectionTrack


class _FakeSource:
    name = "fake"

    def __init__(self, genres_by_artist: dict[str, list[str]] | None = None):
        self._genres_by_artist = genres_by_artist or {}

    def genres_for(self, artist: str) -> list[str]:
        return self._genres_by_artist.get(artist, [])


def _track(rb_content_id: str, artist: str, title: str = "Title") -> CollectionTrack:
    return CollectionTrack(
        rb_content_id=rb_content_id,
        artist=artist,
        title=title,
        duration_ms=200_000,
        bpm=128.0,
        isrc=None,
        play_count=0,
        location=f"/music/{rb_content_id}.mp3",
    )


def _client(tracks=(), source=None):
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    fake_source = source or _FakeSource()

    def _publish(progress):
        events.publish(
            "enrichment_progress",
            {
                "done": progress.done,
                "none_found": progress.none_found,
                "failed": progress.failed,
                "remaining": progress.remaining,
            },
        )

    def test_background_runner(artists_by_id):
        with session_local() as db:
            enrichment_runner.run_until_drained(
                db, fake_source, artists_by_id, budget=1000, on_progress=_publish
            )

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_background_runner] = lambda: test_background_runner
    app.state.collection_index.rebuild(list(tracks))
    return TestClient(app), session_local


def test_run_enqueues_every_named_artist_track_and_returns_queued_count():
    client, _ = _client(tracks=[_track("1", "Daft Punk"), _track("2", "")])

    response = client.post("/api/enrichment/run")

    assert response.status_code == 200
    assert response.json() == {"queued": 1}  # the blank-artist track is never enqueued


def test_run_processes_the_queue_synchronously_and_writes_genres():
    client, session_local = _client(
        tracks=[_track("1", "Daft Punk")],
        source=_FakeSource({"Daft Punk": ["house", "electronic"]}),
    )

    client.post("/api/enrichment/run")

    with session_local() as db:
        genres = {g.genre for g in db.query(EnrichedGenre).filter_by(rb_content_id="1").all()}
        assert genres == {"house", "electronic"}
        assert db.get(EnrichmentState, "1").status == "done"


def test_run_never_reenqueues_a_track_with_a_manual_override():
    client, session_local = _client(tracks=[_track("1", "Daft Punk")])
    client.put("/api/collection/1/genres", json={"genres": ["deep house"]})

    response = client.post("/api/enrichment/run")

    assert response.json() == {"queued": 0}
    with session_local() as db:
        assert db.get(EnrichmentState, "1") is None


def test_status_reports_counts_and_coverage_pct():
    client, _ = _client(
        tracks=[_track("1", "Daft Punk"), _track("2", "Obscure Artist")],
        source=_FakeSource({"Daft Punk": ["house"]}),
    )
    client.post("/api/enrichment/run")

    response = client.get("/api/enrichment/status")

    assert response.status_code == 200
    body = response.json()
    assert body["done"] == 1
    assert body["none_found"] == 1
    assert body["pending"] == 0
    assert body["failed"] == 0
    assert body["coverage_pct"] == 50.0
    assert body["running"] is False


def test_status_is_all_zero_before_any_run():
    client, _ = _client()

    response = client.get("/api/enrichment/status")

    assert response.json() == {
        "pending": 0,
        "done": 0,
        "none_found": 0,
        "failed": 0,
        "coverage_pct": 0.0,
        "running": False,
    }


def test_coverage_pct_counts_the_full_collection_not_only_tracks_with_state_rows():
    """Finding: an artist-less track (never enqueued -- _artists_by_id
    filters blanks) and a track with a manual override set BEFORE any
    enqueue (enqueue_pending skips a track that already has one, so it
    never gets an enrichment_state row either) both used to fall outside
    the old state-row-only denominator, silently inflating coverage_pct.
    SC-008 is measured over the whole collection instead."""
    client, _ = _client(
        tracks=[
            _track("1", "Daft Punk"),  # enqueued, resolves -> done
            _track("2", "Obscure Artist"),  # enqueued, no match -> none_found
            _track("3", ""),  # blank artist, never enqueued at all
            _track("4", "Manual Artist"),  # override set before any run below
            _track("5", "Another Obscure"),  # enqueued, no match -> none_found
        ],
        source=_FakeSource({"Daft Punk": ["house"]}),
    )
    client.put("/api/collection/4/genres", json={"genres": ["deep house"]})

    client.post("/api/enrichment/run")
    response = client.get("/api/enrichment/status")

    body = response.json()
    # numerator: distinct enriched_genre tracks = {"1" (musicbrainz), "4" (manual)} = 2
    # denominator: the full collection index = 5, not the 3 tracks that got a state row
    assert body["coverage_pct"] == 40.0


def test_run_refuses_a_second_run_while_the_first_is_still_in_progress():
    """The actual race the review finding was about: a page reload, a
    second tab, or a stale button all used to be able to fire a second
    POST /run while the first genuinely hadn't finished yet."""
    started = threading.Event()
    release = threading.Event()

    class _SlowSource:
        name = "fake"

        def genres_for(self, artist):  # noqa: ARG002
            started.set()
            assert release.wait(timeout=5), "test never released the slow source"
            return ["house"]

    client, _ = _client(tracks=[_track("1", "Daft Punk")], source=_SlowSource())

    first_run = threading.Thread(target=lambda: client.post("/api/enrichment/run"))
    first_run.start()
    try:
        assert started.wait(timeout=5), "the first run never started"

        second_response = client.post("/api/enrichment/run")

        assert second_response.status_code == 409
        assert second_response.json()["code"] == "enrichment_already_running"
        assert client.get("/api/enrichment/status").json()["running"] is True
    finally:
        release.set()
        first_run.join(timeout=5)

    # cleared once the (first) background run actually finished
    assert client.get("/api/enrichment/status").json()["running"] is False


def test_unenriched_lists_none_found_tracks_for_the_manual_work_list():
    client, _ = _client(
        tracks=[_track("1", "Daft Punk", "One More Time"), _track("2", "Obscure Artist", "B-Side")],
        source=_FakeSource({"Daft Punk": ["house"]}),
    )
    client.post("/api/enrichment/run")

    response = client.get("/api/enrichment/unenriched")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"] == [{"rb_content_id": "2", "artist": "Obscure Artist", "title": "B-Side"}]


def test_unenriched_paginates():
    tracks = [_track(str(i), f"Artist {i}") for i in range(5)]
    client, _ = _client(tracks=tracks, source=_FakeSource({}))
    client.post("/api/enrichment/run")

    response = client.get("/api/enrichment/unenriched?limit=2&offset=2")

    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_put_genres_sets_a_permanent_manual_override():
    client, session_local = _client(tracks=[_track("1", "Daft Punk")])

    response = client.put("/api/collection/1/genres", json={"genres": ["deep house", "disco"]})

    assert response.status_code == 200
    assert response.json() == {
        "rb_content_id": "1",
        "genres": [
            {"genre": "deep house", "source": "manual"},
            {"genre": "disco", "source": "manual"},
        ],
    }
    with session_local() as db:
        rows = db.query(EnrichedGenre).filter_by(rb_content_id="1").all()
        assert {(r.genre, r.source) for r in rows} == {
            ("deep house", "manual"),
            ("disco", "manual"),
        }


def test_put_genres_replaces_a_prior_manual_override():
    client, _ = _client(tracks=[_track("1", "Daft Punk")])
    client.put("/api/collection/1/genres", json={"genres": ["house"]})

    response = client.put("/api/collection/1/genres", json={"genres": ["techno"]})

    assert response.json()["genres"] == [{"genre": "techno", "source": "manual"}]


def test_put_genres_returns_404_for_an_unknown_track():
    client, _ = _client(tracks=[])

    response = client.put("/api/collection/999/genres", json={"genres": ["house"]})

    assert response.status_code == 404
    assert response.json()["code"] == "track_not_found"


def test_collection_reports_real_enriched_genres():
    client, _ = _client(tracks=[_track("1", "Daft Punk")])
    client.put("/api/collection/1/genres", json={"genres": ["house"]})

    response = client.get("/api/collection")

    item = response.json()["items"][0]
    assert item["genres"] == [{"genre": "house", "source": "manual"}]


def test_run_publishes_an_enrichment_progress_event(monkeypatch):
    published = []
    monkeypatch.setattr(
        "companion.api.enrichment.events.publish",
        lambda event, data: published.append((event, data)),
    )
    client, _ = _client(
        tracks=[_track("1", "Daft Punk")], source=_FakeSource({"Daft Punk": ["house"]})
    )

    client.post("/api/enrichment/run")

    assert [event for event, _ in published] == ["enrichment_progress"]
    assert published[0][1] == {"done": 1, "none_found": 0, "failed": 0, "remaining": 0}
