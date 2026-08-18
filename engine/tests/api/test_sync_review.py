"""T036: API contract tests for accept/reject (FR-012, FR-014).

Seeds a `sync_session`/`sync_track` pair directly via the DB (not through a
full POST /api/sync/sessions fetch+match run, T022) -- these tests are about
the accept/reject transition itself, not the fetch/match pipeline T022
already covers.

`MissingTrack` (data-model.md, originally T056/US4) is pinned here as a
build finding: FR-012 requires reject to spawn a real Missing Track, and
this task tests that, so the model must exist before T037 (which this test
turns green) can be built -- moved ahead of T056, the same playlist_link-
ahead-of-T049 pattern from T027.

Committed RED: `companion.db.models.MissingTrack` and the
`.../accept`/`.../reject` endpoints don't exist until T037 builds them,
same US1/US2 red/green split (owner-confirmed).
"""

from datetime import datetime

from fastapi.testclient import TestClient

from companion.db.models import MissingTrack, PlaylistLink, SyncSession, SyncTrack
from companion.db.session import Base, create_session_factory, get_db
from companion.main import create_app


def _seed_review_track(session_local, *, status="review"):
    with session_local() as db:
        link = PlaylistLink(
            spotify_playlist_id="abc123",
            rb_playlist_id=None,
            rb_playlist_name="Booking 2026",
            created_at=datetime(2026, 8, 17),
            last_applied_at=None,
        )
        db.add(link)
        db.flush()
        session = SyncSession(
            playlist_link_id=link.id,
            spotify_snapshot_id="snap-1",
            name="Booking 2026",
            status="ready",
            created_at=datetime(2026, 8, 17),
        )
        db.add(session)
        db.flush()
        track = SyncTrack(
            sync_session_id=session.id,
            position=1,
            spotify_track_id="sp1",
            isrc=None,
            artist="Daft Punk",
            title="One More Time",
            duration_ms=210_000,
            status=status,
            rb_content_id=None,
            match_score=85.0,
            candidates=[
                {"rb_content_id": "rb-a", "score": 85.0, "reason": "fuzzy"},
                {"rb_content_id": "rb-b", "score": 80.0, "reason": "fuzzy"},
            ],
            matched_at=None,
        )
        db.add(track)
        db.commit()
        return session.id, track.id


def _client():
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
    return TestClient(app), session_local


def test_accept_sets_status_matched_and_rb_content_id():
    client, session_local = _client()
    session_id, track_id = _seed_review_track(session_local)

    response = client.post(
        f"/api/sync/sessions/{session_id}/tracks/{track_id}/accept",
        json={"rb_content_id": "rb-a"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "matched"
    assert body["rb_content_id"] == "rb-a"
    assert body["matched_at"] is not None


def test_accept_persists_immediately():
    # FR-014: the resolution is visible on a fresh GET, not just in the
    # accept response itself.
    client, session_local = _client()
    session_id, track_id = _seed_review_track(session_local)

    client.post(
        f"/api/sync/sessions/{session_id}/tracks/{track_id}/accept",
        json={"rb_content_id": "rb-a"},
    )
    detail = client.get(f"/api/sync/sessions/{session_id}").json()

    track = next(t for t in detail["tracks"] if t["id"] == track_id)
    assert track["status"] == "matched"
    assert track["rb_content_id"] == "rb-a"


def test_reject_sets_status_rejected_and_spawns_a_missing_track():
    # FR-012: reject means "wrong match" -- the Spotify Track becomes a
    # Missing Track, never silently dropped.
    client, session_local = _client()
    session_id, track_id = _seed_review_track(session_local)

    response = client.post(f"/api/sync/sessions/{session_id}/tracks/{track_id}/reject")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"

    with session_local() as db:
        missing = db.query(MissingTrack).filter_by(sync_track_id=track_id).one()
        assert missing.status == "open"


def test_reject_persists_immediately():
    client, session_local = _client()
    session_id, track_id = _seed_review_track(session_local)

    client.post(f"/api/sync/sessions/{session_id}/tracks/{track_id}/reject")
    detail = client.get(f"/api/sync/sessions/{session_id}").json()

    track = next(t for t in detail["tracks"] if t["id"] == track_id)
    assert track["status"] == "rejected"


def test_accept_on_a_track_not_in_review_is_refused():
    client, session_local = _client()
    session_id, track_id = _seed_review_track(session_local, status="matched")

    response = client.post(
        f"/api/sync/sessions/{session_id}/tracks/{track_id}/accept",
        json={"rb_content_id": "rb-a"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "not_in_review"


def test_reject_on_a_track_not_in_review_is_refused():
    client, session_local = _client()
    session_id, track_id = _seed_review_track(session_local, status="missing")

    response = client.post(f"/api/sync/sessions/{session_id}/tracks/{track_id}/reject")

    assert response.status_code == 409
    assert response.json()["code"] == "not_in_review"


def test_accept_with_an_unknown_track_id_returns_404():
    client, session_local = _client()
    session_id, _track_id = _seed_review_track(session_local)

    response = client.post(
        f"/api/sync/sessions/{session_id}/tracks/999999/accept",
        json={"rb_content_id": "rb-a"},
    )

    assert response.status_code == 404
