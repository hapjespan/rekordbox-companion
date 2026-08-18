"""T073/T068/T069: the incremental, resumable enrichment runner
(data-model.md `enrichment_state`, ADR 0013)."""

import shutil
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from companion.db.models import EnrichedGenre, EnrichmentState
from companion.db.session import Base, create_session_factory
from companion.enrichment.runner import (
    MAX_CONSECUTIVE_FAILED_BATCHES,
    enqueue_pending,
    run,
    run_until_drained,
)
from companion.rb.reader import open_database, read_collection_snapshot

FIXTURE_MASTER_DB = Path(__file__).resolve().parent.parent / "fixtures" / "master.db"


def _fresh_db():
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_local


class _FakeSource:
    name = "fake"

    def __init__(self, genres_by_artist: dict[str, list[str]]):
        self._genres_by_artist = genres_by_artist
        self.calls: list[str] = []

    def genres_for(self, artist: str) -> list[str]:
        self.calls.append(artist)
        return self._genres_by_artist.get(artist, [])


class _FailingSource:
    name = "fake"

    def genres_for(self, artist: str) -> list[str]:
        raise RuntimeError("simulated network failure")


def test_enqueue_pending_creates_state_rows_for_new_tracks():
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1", "2"])
        db.commit()
        states = db.execute(select(EnrichmentState)).scalars().all()
        assert {s.rb_content_id for s in states} == {"1", "2"}
        assert all(s.status == "pending" for s in states)


def test_enqueue_pending_skips_tracks_with_a_manual_override():
    session_local = _fresh_db()
    with session_local() as db:
        db.add(
            EnrichedGenre(
                rb_content_id="1", genre="house", source="manual", updated_at=datetime(2026, 8, 18)
            )
        )
        db.commit()
        enqueue_pending(db, ["1", "2"])
        db.commit()
        states = {s.rb_content_id for s in db.execute(select(EnrichmentState)).scalars().all()}
        assert states == {"2"}


def test_run_writes_genres_and_marks_tracks_done():
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1"])
        db.commit()
        source = _FakeSource({"Daft Punk": ["house", "electronic"]})
        progress = run(db, source, {"1": "Daft Punk"}, budget=10)
        db.commit()

        assert progress.done == 1
        assert progress.none_found == 0
        assert progress.remaining == 0
        genres = {g.genre for g in db.query(EnrichedGenre).filter_by(rb_content_id="1").all()}
        assert genres == {"house", "electronic"}
        state = db.get(EnrichmentState, "1")
        assert state.status == "done"
        assert state.last_source == "fake"


def test_run_marks_no_match_as_none_found():
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1"])
        db.commit()
        progress = run(db, _FakeSource({}), {"1": "Obscure Artist"}, budget=10)
        db.commit()

        assert progress.none_found == 1
        state = db.get(EnrichmentState, "1")
        assert state.status == "none_found"


def test_run_marks_a_source_failure_as_failed_and_retryable():
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1"])
        db.commit()
        progress = run(db, _FailingSource(), {"1": "Daft Punk"}, budget=10)
        db.commit()

        assert progress.failed == 1
        state = db.get(EnrichmentState, "1")
        assert state.status == "failed"


def test_run_skips_a_track_that_gained_a_manual_override_after_enqueue():
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1"])
        db.add(
            EnrichedGenre(
                rb_content_id="1",
                genre="deep house",
                source="manual",
                updated_at=datetime(2026, 8, 18),
            )
        )
        db.commit()

        source = _FakeSource({"Daft Punk": ["house"]})
        run(db, source, {"1": "Daft Punk"}, budget=10)
        db.commit()

        assert source.calls == []  # never called the external source at all
        genres = db.query(EnrichedGenre).filter_by(rb_content_id="1").all()
        assert len(genres) == 1
        assert genres[0].source == "manual"


def test_run_respects_a_budget_and_never_reprocesses_done_tracks():
    """T069: an interrupted enrichment run resumes without redoing done
    tracks -- run() with a budget smaller than the queue, called twice."""
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1", "2", "3"])
        db.commit()
        source = _FakeSource({"A": ["house"], "B": ["techno"], "C": ["disco"]})
        artists = {"1": "A", "2": "B", "3": "C"}

        first = run(db, source, artists, budget=2)
        db.commit()
        assert first.processed == 2
        assert first.remaining == 1

        second = run(db, source, artists, budget=2)
        db.commit()
        assert second.processed == 1  # only the one remaining track
        assert second.remaining == 0
        # each artist looked up exactly once across both calls
        assert sorted(source.calls) == ["A", "B", "C"]


def test_run_leaves_master_db_byte_for_byte_unchanged(tmp_path):
    """T068 (FR-030, Principle III): enrichment only ever reads master.db."""
    if not FIXTURE_MASTER_DB.exists():
        pytest.skip("no fixture master.db available")
    db_copy = tmp_path / "master.db"
    shutil.copy(FIXTURE_MASTER_DB, db_copy)
    before = db_copy.read_bytes()

    tracks = [t for t in read_collection_snapshot(open_database(db_copy)) if t.artist]
    artists_by_id = {t.rb_content_id: t.artist for t in tracks}

    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, list(artists_by_id))
        db.commit()
        run(db, _FakeSource({}), artists_by_id, budget=len(artists_by_id))
        db.commit()

    assert db_copy.read_bytes() == before


def test_run_until_drained_processes_every_track_in_small_chunks():
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1", "2", "3"])
        db.commit()
        source = _FakeSource({"A": ["house"], "B": ["techno"], "C": ["disco"]})
        artists = {"1": "A", "2": "B", "3": "C"}
        progress_calls = []

        run_until_drained(db, source, artists, budget=1, on_progress=progress_calls.append)

        assert len(progress_calls) == 3  # one per chunk of 1
        assert all(db.get(EnrichmentState, i).status == "done" for i in ["1", "2", "3"])


def test_run_until_drained_stops_after_persistent_failures_instead_of_spinning_forever():
    """A source that is unreachable (e.g. no network) must not spin the loop
    forever with zero backoff -- a genuine, plausible failure mode for a
    local-first app that goes offline mid-run."""
    session_local = _fresh_db()
    with session_local() as db:
        enqueue_pending(db, ["1"])
        db.commit()

        run_until_drained(db, _FailingSource(), {"1": "Daft Punk"}, budget=10)

        state = db.get(EnrichmentState, "1")
        assert state.status == "failed"  # still retryable by a later call
        assert state.attempted_at is not None


def test_run_until_drained_resets_the_failure_counter_on_real_progress():
    class _FlakySource:
        name = "fake"
        calls = 0

        def genres_for(self, artist: str) -> list[str]:
            self.calls += 1
            if self.calls % 2 == 0:
                raise RuntimeError("simulated intermittent failure")
            return ["house"]

    session_local = _fresh_db()
    with session_local() as db:
        # more tracks than MAX_CONSECUTIVE_FAILED_BATCHES so a naive counter
        # that never resets would give up long before the queue drains
        ids = [str(i) for i in range(MAX_CONSECUTIVE_FAILED_BATCHES * 2 + 2)]
        enqueue_pending(db, ids)
        db.commit()
        artists = dict.fromkeys(ids, "Daft Punk")

        run_until_drained(db, _FlakySource(), artists, budget=1)

        done_count = sum(1 for i in ids if db.get(EnrichmentState, i).status == "done")
        assert done_count > 0  # succeeded between the failures, not given up early
