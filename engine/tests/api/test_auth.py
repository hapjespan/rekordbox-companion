"""T026: router tests for the Spotify auth endpoints (contracts/api.md).

Follows the `test_config_api.py` / `test_collection.py` conventions:
`TestClient`, an isolated in-memory DB via `dependency_overrides[get_db]`, and
an overridden `get_spotify_client` so the callback never touches real Spotify.
"""

from datetime import timedelta

import httpx
from fastapi.testclient import TestClient

from companion.api.auth import get_spotify_client
from companion.db.models import SpotifyAuth
from companion.db.session import Base, create_session_factory, get_db
from companion.integrations import spotify
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


def _mock_spotify_client():
    def handler(request):
        if request.url.path == "/api/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "acc-token",
                    "refresh_token": "ref-token",
                    "expires_in": 3600,
                },
            )
        if request.url.path == "/v1/me":
            return httpx.Response(
                200,
                json={"id": "acc-42", "display_name": "DJ Test", "product": "premium"},
            )
        raise AssertionError(f"unexpected {request.url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_login_redirects_to_spotify_authorize_with_pkce(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    app, _ = _app_with_db()
    client = TestClient(app)

    response = client.get("/api/auth/spotify/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.spotify.com/authorize?")
    assert "code_challenge_method=S256" in location
    assert "client_secret" not in location


def test_login_without_client_id_returns_503(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    app, _ = _app_with_db()
    client = TestClient(app)

    response = client.get("/api/auth/spotify/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["code"] == "spotify_not_configured"


def test_status_is_disconnected_without_a_stored_session():
    app, _ = _app_with_db()
    client = TestClient(app)

    response = client.get("/api/auth/spotify/status")

    assert response.status_code == 200
    assert response.json() == {"connected": False, "display_name": None, "product": None}


def test_callback_rejects_state_mismatch():
    app, _ = _app_with_db()
    app.dependency_overrides[get_spotify_client] = _mock_spotify_client
    client = TestClient(app)

    response = client.get(
        "/api/auth/spotify/callback",
        params={"code": "x", "state": "never-issued"},
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "state_mismatch"
    assert body["field"] == "state"


def test_callback_completes_flow_and_persists_session(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    app, session_local = _app_with_db()
    app.dependency_overrides[get_spotify_client] = _mock_spotify_client
    client = TestClient(app)

    # Seed a real pending state through the module the router shares.
    _, state = spotify.start_login()

    response = client.get(
        "/api/auth/spotify/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "/"

    status = client.get("/api/auth/spotify/status").json()
    assert status == {"connected": True, "display_name": "DJ Test", "product": "premium"}


def test_disconnect_deletes_the_session_row():
    app, session_local = _app_with_db()
    client = TestClient(app)
    with session_local() as db:
        db.add(
            SpotifyAuth(
                id=1,
                access_token="a",
                refresh_token="r",
                token_expires_at=_utcnow() + timedelta(seconds=3600),
                account_id="acc",
                display_name="DJ",
                product="premium",
            )
        )
        db.commit()

    response = client.post("/api/auth/spotify/disconnect")

    assert response.status_code == 200
    assert response.json()["connected"] is False
    with session_local() as db:
        assert db.get(SpotifyAuth, 1) is None


def test_player_token_returns_access_token_and_expiry():
    # T099, R2: short-lived token for the Web Playback SDK.
    app, session_local = _app_with_db()
    app.dependency_overrides[get_spotify_client] = lambda: _mock_spotify_client()
    client = TestClient(app)
    with session_local() as db:
        db.add(
            SpotifyAuth(
                id=1,
                access_token="good-access",
                refresh_token="r",
                token_expires_at=_utcnow() + timedelta(seconds=1800),
                account_id="acc",
                display_name="DJ",
                product="premium",
            )
        )
        db.commit()

    response = client.get("/api/auth/spotify/player-token")

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "good-access"
    assert 1790 <= body["expires_in"] <= 1800


def test_player_token_without_a_session_returns_409():
    app, _ = _app_with_db()
    app.dependency_overrides[get_spotify_client] = lambda: _mock_spotify_client()
    client = TestClient(app)

    response = client.get("/api/auth/spotify/player-token")

    assert response.status_code == 409
    assert response.json()["code"] == "spotify_not_connected"


def test_player_token_with_a_revoked_refresh_token_returns_409(monkeypatch):
    # T099 review finding: a stale token triggers a refresh inside
    # get_player_token; if Spotify rejects that refresh (revoked at
    # Spotify's end), this must map to the flat error envelope, not an
    # unhandled 500.
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")

    def handler(request):
        if request.url.path == "/api/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        raise AssertionError(f"unexpected {request.url}")

    app, session_local = _app_with_db()
    app.dependency_overrides[get_spotify_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    client = TestClient(app)
    with session_local() as db:
        db.add(
            SpotifyAuth(
                id=1,
                access_token="stale-access",
                refresh_token="revoked",
                token_expires_at=_utcnow() - timedelta(seconds=10),
                account_id="acc",
                display_name="DJ",
                product="premium",
            )
        )
        db.commit()

    response = client.get("/api/auth/spotify/player-token")

    assert response.status_code == 409
    assert response.json()["code"] == "spotify_session_expired"
