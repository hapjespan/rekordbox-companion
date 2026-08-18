"""T070/T067: the GenreSource seam (ADR 0013) and FR-028's manual-override
precedence -- a manual genre override is never touched by an enrichment run."""

from datetime import datetime

from companion.db.models import EnrichedGenre, EnrichmentState
from companion.db.session import Base, create_session_factory
from companion.enrichment.source import apply_genres, has_manual_override, set_manual_override


def _fresh_db():
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_local


def test_has_manual_override_false_when_no_rows_exist():
    session_local = _fresh_db()
    with session_local() as db:
        assert has_manual_override(db, "123") is False


def test_has_manual_override_true_when_a_manual_row_exists():
    session_local = _fresh_db()
    with session_local() as db:
        db.add(
            EnrichedGenre(
                rb_content_id="123", genre="house", source="manual", updated_at=datetime.now()
            )
        )
        db.commit()
        assert has_manual_override(db, "123") is True


def test_has_manual_override_false_for_automated_rows_only():
    session_local = _fresh_db()
    with session_local() as db:
        db.add(
            EnrichedGenre(
                rb_content_id="123",
                genre="house",
                source="musicbrainz",
                updated_at=datetime.now(),
            )
        )
        db.commit()
        assert has_manual_override(db, "123") is False


def test_apply_genres_writes_rows_for_an_untouched_track():
    session_local = _fresh_db()
    with session_local() as db:
        apply_genres(db, "123", ["house", "techno"], source="musicbrainz")
        db.commit()
        rows = db.query(EnrichedGenre).filter_by(rb_content_id="123").all()
        assert {r.genre for r in rows} == {"house", "techno"}
        assert all(r.source == "musicbrainz" for r in rows)


def test_apply_genres_never_overwrites_a_manual_override():
    """FR-028: a manual genre override is never overwritten by a later
    enrichment run. Simulates a manual edit landing after an automated run
    already enriched the track, then a later run trying to enrich it again."""
    session_local = _fresh_db()
    with session_local() as db:
        db.add(
            EnrichedGenre(
                rb_content_id="123", genre="deep house", source="manual", updated_at=datetime.now()
            )
        )
        db.commit()

        apply_genres(db, "123", ["techno", "electro"], source="musicbrainz")
        db.commit()

        rows = db.query(EnrichedGenre).filter_by(rb_content_id="123").all()
        assert len(rows) == 1
        assert rows[0].genre == "deep house"
        assert rows[0].source == "manual"


def test_apply_genres_replaces_prior_automated_rows_from_a_previous_run():
    session_local = _fresh_db()
    with session_local() as db:
        apply_genres(db, "123", ["house"], source="musicbrainz")
        db.commit()

        apply_genres(db, "123", ["techno", "electro"], source="musicbrainz")
        db.commit()

        rows = db.query(EnrichedGenre).filter_by(rb_content_id="123").all()
        assert {r.genre for r in rows} == {"techno", "electro"}


def test_set_manual_override_resolves_a_none_found_enrichment_state():
    """FR-029: a manually-fixed track must stop appearing in the manual
    work list, which reads enrichment_state, not enriched_genre."""
    session_local = _fresh_db()
    with session_local() as db:
        db.add(EnrichmentState(rb_content_id="123", status="none_found"))
        db.commit()

        set_manual_override(db, "123", ["deep house"])
        db.commit()

        state = db.get(EnrichmentState, "123")
        assert state.status == "done"
        assert state.last_source == "manual"


def test_set_manual_override_with_no_existing_enrichment_state_is_a_noop_there():
    session_local = _fresh_db()
    with session_local() as db:
        set_manual_override(db, "123", ["deep house"])
        db.commit()  # must not raise for a track never enqueued

        assert db.get(EnrichmentState, "123") is None


def test_clearing_a_manual_override_returns_the_track_to_pending():
    session_local = _fresh_db()
    with session_local() as db:
        db.add(EnrichmentState(rb_content_id="123", status="none_found"))
        db.commit()
        set_manual_override(db, "123", ["deep house"])
        db.commit()

        set_manual_override(db, "123", [])
        db.commit()

        state = db.get(EnrichmentState, "123")
        assert state.status == "pending"
        assert state.last_source is None
        assert db.query(EnrichedGenre).filter_by(rb_content_id="123").count() == 0
