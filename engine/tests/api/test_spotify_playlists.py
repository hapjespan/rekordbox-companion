"""GET /api/spotify/playlists: the operator's own Spotify playlists, each
carrying the app's own sync status.

Follows `test_auth.py`'s conventions: `TestClient`, an isolated in-memory DB via
`dependency_overrides[get_db]`, and an overridden `get_spotify_client` backed by
`httpx.MockTransport` so no test contacts real Spotify.

The sync status is derived from `playlist_link` + the latest `sync_session` for
that link -- our own data, never Spotify's -- and is returned as a state plus
counts, never a pre-rendered sentence: UI copy is Dutch and belongs in the
frontend (contracts/api.md).
"""

from datetime import datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from companion.api.auth import get_spotify_client
from companion.db.models import PlaylistLink, SpotifyAuth, SyncSession, SyncTrack
from companion.db.session import Base, create_session_factory, get_db
from companion.integrations.spotify import _utcnow
from companion.main import create_app


def _app_with_db():
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
    return app, session_local


def _connect(session_local, *, expires_in_seconds=3600):
    with session_local() as db:
        db.add(
            SpotifyAuth(
                id=1,
                access_token="good-access",
                refresh_token="r",
                token_expires_at=_utcnow() + timedelta(seconds=expires_in_seconds),
                account_id="acc",
                display_name="DJ Test",
                product="premium",
            )
        )
        db.commit()


def _playlist_item(playlist_id, name):
    return {
        "id": playlist_id,
        "name": name,
        "description": "",
        "owner": {"display_name": "DJ Test"},
        "images": [{"url": f"https://i.scdn.co/image/{playlist_id}", "width": 300, "height": 300}],
    }


def _client_returning(items):
    def handler(request):
        assert request.url.path == "/v1/me/playlists"
        return httpx.Response(200, json={"items": items, "next": None})

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def _client_answering(status_code):
    def handler(request):
        return httpx.Response(status_code, json={"error": {"status": status_code}})

    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def _seed_session(session_local, *, spotify_playlist_id, status, statuses=(), last_applied_at=None):
    """One playlist_link plus one sync_session with `statuses` as its tracks."""
    with session_local() as db:
        link = PlaylistLink(
            spotify_playlist_id=spotify_playlist_id,
            rb_playlist_id=None,
            rb_playlist_name="Bruiloft",
            created_at=datetime(2026, 8, 17),
            last_applied_at=last_applied_at,
        )
        db.add(link)
        db.flush()
        sync_session = SyncSession(
            playlist_link_id=link.id,
            spotify_snapshot_id="snap-1",
            name="Bruiloft",
            status=status,
            created_at=datetime(2026, 8, 18),
        )
        db.add(sync_session)
        db.flush()
        for position, track_status in enumerate(statuses, start=1):
            db.add(
                SyncTrack(
                    sync_session_id=sync_session.id,
                    position=position,
                    spotify_track_id=f"t{position}",
                    isrc=None,
                    artist="A",
                    title="T",
                    duration_ms=1000,
                    status=track_status,
                    rb_content_id=None,
                    match_score=None,
                    candidates=[],
                    matched_at=None,
                )
            )
        db.commit()
        return sync_session.id


def test_playlists_returns_id_name_cover_and_owner():
    app, session_local = _app_with_db()
    _connect(session_local)
    app.dependency_overrides[get_spotify_client] = _client_returning(
        [_playlist_item("p1", "Bruiloft")]
    )
    client = TestClient(app)

    response = client.get("/api/spotify/playlists")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["spotify_playlist_id"] == "p1"
    assert body[0]["name"] == "Bruiloft"
    assert body[0]["image_url"] == "https://i.scdn.co/image/p1"
    assert body[0]["owner_display_name"] == "DJ Test"
    # No track count anywhere in the body: Spotify strips it for this app.
    assert "track_count" not in body[0]


def test_a_never_synced_playlist_reports_not_scanned_with_no_counts():
    app, session_local = _app_with_db()
    _connect(session_local)
    app.dependency_overrides[get_spotify_client] = _client_returning(
        [_playlist_item("p1", "Bruiloft")]
    )
    client = TestClient(app)

    sync = client.get("/api/spotify/playlists").json()[0]["sync"]

    assert sync == {
        "state": "not_scanned",
        "session_id": None,
        "session_created_at": None,
        "last_applied_at": None,
        "totals": None,
    }


def test_a_synced_playlist_reports_the_latest_sessions_state_and_counts():
    app, session_local = _app_with_db()
    _connect(session_local)
    session_id = _seed_session(
        session_local,
        spotify_playlist_id="p1",
        status="ready",
        statuses=["matched", "matched", "missing", "review"],
    )
    app.dependency_overrides[get_spotify_client] = _client_returning(
        [_playlist_item("p1", "Bruiloft"), _playlist_item("p2", "Horeca")]
    )
    client = TestClient(app)

    body = client.get("/api/spotify/playlists").json()

    synced = next(p for p in body if p["spotify_playlist_id"] == "p1")
    assert synced["sync"]["state"] == "ready"
    assert synced["sync"]["session_id"] == session_id
    assert synced["sync"]["session_created_at"].startswith("2026-08-18")
    # The counts the sidebar renders its own Dutch line from ("gematcht ·
    # 12 ontbreken"): state and numbers, never a sentence.
    assert synced["sync"]["totals"] == {
        "matched": 2,
        "review": 1,
        "missing": 1,
        "rejected": 0,
        "unmatchable": 0,
    }
    # A playlist Spotify lists but this app never synced stays not_scanned.
    assert next(p for p in body if p["spotify_playlist_id"] == "p2")["sync"]["state"] == (
        "not_scanned"
    )


def test_an_applied_playlist_reports_the_links_last_applied_at():
    app, session_local = _app_with_db()
    _connect(session_local)
    _seed_session(
        session_local,
        spotify_playlist_id="p1",
        status="applied",
        statuses=["matched"],
        last_applied_at=datetime(2026, 8, 18, 12, 30),
    )
    app.dependency_overrides[get_spotify_client] = _client_returning(
        [_playlist_item("p1", "Bruiloft")]
    )
    client = TestClient(app)

    sync = client.get("/api/spotify/playlists").json()[0]["sync"]

    assert sync["state"] == "applied"
    assert sync["last_applied_at"].startswith("2026-08-18T12:30")


def test_the_state_comes_from_the_most_recent_session_of_the_same_link():
    app, session_local = _app_with_db()
    _connect(session_local)
    _seed_session(session_local, spotify_playlist_id="p1", status="applied", statuses=["matched"])
    with session_local() as db:
        link = db.query(PlaylistLink).filter_by(spotify_playlist_id="p1").one()
        db.add(
            SyncSession(
                playlist_link_id=link.id,
                spotify_snapshot_id="snap-2",
                name="Bruiloft",
                status="ready",
                created_at=datetime(2026, 8, 19),
            )
        )
        db.commit()
    app.dependency_overrides[get_spotify_client] = _client_returning(
        [_playlist_item("p1", "Bruiloft")]
    )
    client = TestClient(app)

    sync = client.get("/api/spotify/playlists").json()[0]["sync"]

    assert sync["state"] == "ready"  # the newer session, not the applied one
    assert sync["session_created_at"].startswith("2026-08-19")


def test_playlists_without_a_spotify_session_returns_409():
    app, _ = _app_with_db()
    app.dependency_overrides[get_spotify_client] = _client_returning([])
    client = TestClient(app)

    response = client.get("/api/spotify/playlists")

    assert response.status_code == 409
    assert response.json()["code"] == "spotify_not_connected"


def test_a_rejected_token_returns_409_session_expired():
    app, session_local = _app_with_db()
    _connect(session_local)
    app.dependency_overrides[get_spotify_client] = _client_answering(401)
    client = TestClient(app)

    response = client.get("/api/spotify/playlists")

    assert response.status_code == 409
    assert response.json()["code"] == "spotify_session_expired"


def test_a_spotify_refusal_is_a_documented_error_never_an_empty_list():
    # The phase 7 finding this endpoint must not repeat: a refusal that reads
    # as "you have no playlists" sends the DJ to fix the wrong thing.
    app, session_local = _app_with_db()
    _connect(session_local)
    app.dependency_overrides[get_spotify_client] = _client_answering(403)
    client = TestClient(app)

    response = client.get("/api/spotify/playlists")

    assert response.status_code == 502
    body = response.json()
    assert body["code"] == "spotify_playlists_unavailable"
    assert "message" in body


def test_a_revoked_refresh_token_returns_409_session_expired(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    app, session_local = _app_with_db()
    _connect(session_local, expires_in_seconds=-10)

    def handler(request):
        assert request.url.path == "/api/token"
        return httpx.Response(400, json={"error": "invalid_grant"})

    app.dependency_overrides[get_spotify_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    client = TestClient(app)

    response = client.get("/api/spotify/playlists")

    assert response.status_code == 409
    assert response.json()["code"] == "spotify_session_expired"


def test_without_a_client_id_a_needed_refresh_returns_503(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    app, session_local = _app_with_db()
    _connect(session_local, expires_in_seconds=-10)
    app.dependency_overrides[get_spotify_client] = _client_returning([])
    client = TestClient(app)

    response = client.get("/api/spotify/playlists")

    assert response.status_code == 503
    assert response.json()["code"] == "spotify_not_configured"
