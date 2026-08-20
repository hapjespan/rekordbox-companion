"""T027: playlist_link/sync_session/sync_track tables (data-model.md)."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from companion.db.models import PlaylistLink, SyncSession, SyncTrack
from companion.db.session import Base, create_session_factory


def _fresh_db():
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_local


def _playlist_link(session):
    link = PlaylistLink(
        spotify_playlist_id="37i9dQZF1DXcBWIGoYBM5M",
        rb_playlist_id=None,
        rb_playlist_name="Booking 2026",
        created_at=datetime(2026, 8, 17),
        last_applied_at=None,
    )
    session.add(link)
    session.flush()
    return link


def test_playlist_link_spotify_playlist_id_is_unique():
    session_local = _fresh_db()
    with session_local() as db:
        _playlist_link(db)
        db.commit()
        db.add(
            PlaylistLink(
                spotify_playlist_id="37i9dQZF1DXcBWIGoYBM5M",
                rb_playlist_name="Another Name",
                created_at=datetime(2026, 8, 17),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_sync_session_round_trips_and_links_to_playlist_link():
    session_local = _fresh_db()
    with session_local() as db:
        link = _playlist_link(db)
        link_id = link.id
        session = SyncSession(
            playlist_link_id=link.id,
            spotify_snapshot_id="snap-1",
            name="Booking 2026",
            status="ready",
            created_at=datetime(2026, 8, 17),
        )
        db.add(session)
        db.commit()
        session_id = session.id

    with session_local() as db:
        row = db.get(SyncSession, session_id)
        assert row.status == "ready"
        assert row.playlist_link_id == link_id


def test_sync_track_allows_the_same_spotify_track_at_two_positions():
    # Spec edge case: a Spotify playlist containing the same track twice is
    # reported once per playlist position -- no uniqueness constraint should
    # block two sync_track rows sharing spotify_track_id/isrc under one session.
    session_local = _fresh_db()
    with session_local() as db:
        link = _playlist_link(db)
        session = SyncSession(
            playlist_link_id=link.id,
            spotify_snapshot_id="snap-1",
            name="Booking 2026",
            status="matching",
            created_at=datetime(2026, 8, 17),
        )
        db.add(session)
        db.flush()

        for position in (1, 2):
            db.add(
                SyncTrack(
                    sync_session_id=session.id,
                    position=position,
                    spotify_track_id="sp1",
                    isrc="USRC17607839",
                    artist="Example Artist",
                    title="Example Song",
                    duration_ms=210_000,
                    status="matched",
                    rb_content_id="rb1",
                    match_score=100.0,
                    candidates=[],
                    matched_at=None,
                )
            )
        db.commit()
        session_id = session.id

    with session_local() as db:
        tracks = db.query(SyncTrack).filter_by(sync_session_id=session_id).all()
        assert {t.position for t in tracks} == {1, 2}


def test_sync_track_candidates_round_trips_as_json():
    session_local = _fresh_db()
    candidates = [
        {"rb_content_id": "rb1", "score": 80.0, "reason": "fuzzy"},
        {"rb_content_id": "rb2", "score": 78.0, "reason": "fuzzy"},
    ]
    with session_local() as db:
        link = _playlist_link(db)
        session = SyncSession(
            playlist_link_id=link.id,
            spotify_snapshot_id="snap-1",
            name="Booking 2026",
            status="matching",
            created_at=datetime(2026, 8, 17),
        )
        db.add(session)
        db.flush()
        db.add(
            SyncTrack(
                sync_session_id=session.id,
                position=1,
                spotify_track_id="sp1",
                isrc=None,
                artist="Example Artist",
                title="Example Song",
                duration_ms=210_000,
                status="review",
                rb_content_id=None,
                match_score=80.0,
                candidates=candidates,
                matched_at=None,
            )
        )
        db.commit()
        session_id = session.id

    with session_local() as db:
        track = db.query(SyncTrack).filter_by(sync_session_id=session_id).one()
        assert track.candidates == candidates
