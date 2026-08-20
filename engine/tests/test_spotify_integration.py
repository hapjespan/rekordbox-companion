"""T026: unit tests for `companion.integrations.spotify`.

The load-bearing case, per the T022 review finding, is the pagination
short-circuit: the 999-track cap must stop fetching further pages the moment
`total` is known to exceed it, which T022's router-level fake (all tracks in
one call) cannot exercise. The rest cover the security boundary itself: PKCE
challenge derivation, callback state rejection, token refresh before an
expired-token call, and disconnect actually deleting the row.

Outbound HTTP is mocked with `httpx.MockTransport` (no new dependency; httpx is
already pinned) so no test ever contacts real Spotify.
"""

import base64
import hashlib
from datetime import timedelta

import httpx
import pytest

from companion.db.models import SpotifyAuth
from companion.db.session import Base, create_session_factory
from companion.integrations import spotify
from companion.integrations.spotify import (
    InvalidPlaylistUrlError,
    NotConnectedError,
    PlaylistTooLargeError,
    PlaylistUnreachableError,
    SessionExpiredError,
    StateMismatchError,
    _utcnow,
)

PLAYLIST_ID = "PLAYLISTID0000000000AB"


@pytest.fixture
def session():
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = session_local()
    try:
        yield db
    finally:
        db.close()


def _store_auth(db, *, expires_in_seconds: int, access_token: str = "old-access"):
    db.add(
        SpotifyAuth(
            id=1,
            access_token=access_token,
            refresh_token="refresh-1",
            token_expires_at=_utcnow() + timedelta(seconds=expires_in_seconds),
            account_id="acc-1",
            display_name="DJ Test",
            product="premium",
        )
    )
    db.commit()


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _track_item(track_id, name, artist, isrc=None, duration_ms=200_000):
    return {
        "is_local": False,
        "track": {
            "id": track_id,
            "name": name,
            "artists": [{"name": artist}],
            "duration_ms": duration_ms,
            "external_ids": {"isrc": isrc} if isrc else {},
        },
    }


# --------------------------------------------------------------------------- #
# PKCE
# --------------------------------------------------------------------------- #
def test_code_challenge_is_unpadded_base64url_sha256_of_verifier():
    verifier = spotify.generate_code_verifier()
    challenge = spotify.code_challenge_for(verifier)

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert challenge == expected
    assert "=" not in challenge  # S256 requires padding stripped


def test_generate_code_verifier_is_high_entropy_and_unique():
    assert spotify.generate_code_verifier() != spotify.generate_code_verifier()
    assert len(spotify.generate_code_verifier()) >= 43  # RFC 7636 minimum


def test_start_login_builds_s256_authorize_url_and_stores_verifier(monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")

    url, state = spotify.start_login()

    assert url.startswith("https://accounts.spotify.com/authorize?")
    assert "code_challenge_method=S256" in url
    assert "client_id=test-client-id" in url
    assert "client_secret" not in url  # public client, no secret anywhere
    assert f"state={state}" in url
    # The verifier is retained server-side, keyed by state, for the callback.
    assert spotify._pending_verifiers.get(state) is not None


def test_start_login_without_client_id_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    with pytest.raises(spotify.SpotifyNotConfiguredError):
        spotify.start_login()


# --------------------------------------------------------------------------- #
# Callback / state
# --------------------------------------------------------------------------- #
def test_complete_login_rejects_unknown_state(session):
    # No pending verifier for this state -> refuse before any HTTP happens.
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("no HTTP call should happen on a state mismatch")

    with pytest.raises(StateMismatchError):
        spotify.complete_login(session, _client(handler), code="x", state="never-issued")


def test_complete_login_exchanges_code_and_persists_session(session, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    _, state = spotify.start_login()

    seen = {}

    def handler(request):
        if request.url.path == "/api/token":
            seen["token_body"] = request.content
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                },
            )
        if request.url.path == "/v1/me":
            seen["auth_header"] = request.headers.get("Authorization")
            return httpx.Response(
                200,
                json={"id": "acc-1", "display_name": "DJ Test", "product": "premium"},
            )
        raise AssertionError(f"unexpected {request.url}")

    row = spotify.complete_login(session, _client(handler), code="auth-code", state=state)

    assert row.access_token == "new-access"
    assert row.refresh_token == "new-refresh"
    assert row.account_id == "acc-1"
    assert row.display_name == "DJ Test"
    assert row.product == "premium"
    # PKCE token exchange carries the verifier and no client secret.
    assert b"code_verifier=" in seen["token_body"]
    assert b"client_secret" not in seen["token_body"]
    assert seen["auth_header"] == "Bearer new-access"


# --------------------------------------------------------------------------- #
# Token refresh
# --------------------------------------------------------------------------- #
def test_expired_token_is_refreshed_before_the_api_call(session, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    _store_auth(session, expires_in_seconds=-10, access_token="stale-access")

    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/token":
            assert b"grant_type=refresh_token" in request.content
            return httpx.Response(200, json={"access_token": "fresh-access", "expires_in": 3600})
        if request.url.path == f"/v1/playlists/{PLAYLIST_ID}":
            assert request.headers.get("Authorization") == "Bearer fresh-access"
            return httpx.Response(
                200,
                json={"name": "P", "snapshot_id": "s", "tracks": {"total": 0, "items": []}},
            )
        raise AssertionError(f"unexpected {request.url}")

    spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)

    assert ("POST", "/api/token") in calls  # refresh happened first
    session.refresh(db_row := session.get(SpotifyAuth, 1))
    assert db_row.access_token == "fresh-access"


def test_valid_token_is_not_refreshed(session):
    _store_auth(session, expires_in_seconds=3600, access_token="good-access")

    def handler(request):
        assert request.url.path != "/api/token", "must not refresh a valid token"
        return httpx.Response(
            200,
            json={"name": "P", "snapshot_id": "s", "tracks": {"total": 0, "items": []}},
        )

    spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)


def test_fetch_without_a_session_raises_not_connected(session):
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("no HTTP call without a stored session")

    with pytest.raises(NotConnectedError):
        spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)


def test_expired_token_whose_refresh_token_was_revoked_raises_session_expired(session, monkeypatch):
    # T104, spec.md edge case: "the Spotify session expires mid Sync
    # Session" -- the access token is expired locally, the refresh attempt
    # itself is what Spotify rejects (revoked at Spotify's end).
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    _store_auth(session, expires_in_seconds=-10)

    def handler(request):
        if request.url.path == "/api/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        raise AssertionError("must not fetch the playlist with no valid token")

    with pytest.raises(SessionExpiredError):
        spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)


def test_access_token_rejected_mid_fetch_raises_session_expired(session):
    # The token passed the local expiry check but Spotify rejects it anyway.
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(401, json={"error": {"status": 401}})

    with pytest.raises(SessionExpiredError):
        spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)


def test_access_token_rejected_mid_pagination_raises_session_expired(session):
    _store_auth(session, expires_in_seconds=3600)
    tracks_path = f"/v1/playlists/{PLAYLIST_ID}/tracks"

    def handler(request):
        if request.url.path == f"/v1/playlists/{PLAYLIST_ID}":
            return httpx.Response(
                200,
                json={
                    "name": "P",
                    "snapshot_id": "s",
                    "tracks": {
                        "total": 150,
                        "items": [_track_item(f"t{i}", f"T{i}", "A") for i in range(100)],
                        "next": f"https://api.spotify.com{tracks_path}?offset=100",
                    },
                },
            )
        if request.url.path == tracks_path:
            return httpx.Response(401, json={"error": {"status": 401}})
        raise AssertionError(f"unexpected {request.url}")

    with pytest.raises(SessionExpiredError):
        spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)


# --------------------------------------------------------------------------- #
# Player token (T099, R2)
# --------------------------------------------------------------------------- #
def test_get_player_token_returns_the_access_token_and_seconds_remaining(session):
    _store_auth(session, expires_in_seconds=1800, access_token="good-access")

    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("a valid token needs no HTTP call")

    result = spotify.get_player_token(session, _client(handler))

    assert result["access_token"] == "good-access"
    # Allow a little slack for wall-clock time elapsed during the test.
    assert 1790 <= result["expires_in"] <= 1800


def test_get_player_token_refreshes_an_expired_token_first(monkeypatch, session):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    _store_auth(session, expires_in_seconds=-10, access_token="stale-access")

    def handler(request):
        if request.url.path == "/api/token":
            return httpx.Response(200, json={"access_token": "fresh-access", "expires_in": 3600})
        raise AssertionError(f"unexpected {request.url}")

    result = spotify.get_player_token(session, _client(handler))

    assert result["access_token"] == "fresh-access"
    assert 3590 <= result["expires_in"] <= 3600


def test_get_player_token_without_a_session_raises_not_connected(session):
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("no HTTP call without a stored session")

    with pytest.raises(NotConnectedError):
        spotify.get_player_token(session, _client(handler))


# --------------------------------------------------------------------------- #
# Pagination + 999 cap short-circuit (the T022 review finding)
# --------------------------------------------------------------------------- #
def test_pagination_short_circuits_once_total_exceeds_cap(session):
    _store_auth(session, expires_in_seconds=3600)

    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == f"/v1/playlists/{PLAYLIST_ID}":
            return httpx.Response(
                200,
                json={
                    "name": "Huge",
                    "snapshot_id": "s",
                    "tracks": {
                        "total": 2000,
                        "items": [_track_item(f"t{i}", f"T{i}", "A") for i in range(100)],
                        # A next page exists; the cap check must fire before it.
                        "next": f"https://api.spotify.com/v1/playlists/{PLAYLIST_ID}/tracks?offset=100",
                    },
                },
            )
        raise AssertionError("paginated past the cap: next page was fetched")

    with pytest.raises(PlaylistTooLargeError) as excinfo:
        spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)

    assert excinfo.value.total == 2000
    # Exactly one HTTP call: the first page, whose `total` short-circuits. A
    # 2000-track playlist would otherwise cost ~20 page fetches.
    assert calls == [f"/v1/playlists/{PLAYLIST_ID}"]


@pytest.mark.parametrize("status_code", [403, 404])
def test_private_or_deleted_playlist_raises_a_typed_error_not_httpx_status_error(
    session, status_code
):
    # T031/T032 review finding: this used to let httpx.HTTPStatusError
    # bubble up uncaught for spec.md's own named edge case ("playlist is
    # private"), surfacing as a raw 500 with no {code, message, field}.
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(status_code, json={"error": {"status": status_code}})

    with pytest.raises(PlaylistUnreachableError):
        spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)


def test_within_cap_playlist_follows_pagination_to_completion(session):
    _store_auth(session, expires_in_seconds=3600)

    calls = []
    tracks_path = f"/v1/playlists/{PLAYLIST_ID}/tracks"

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == f"/v1/playlists/{PLAYLIST_ID}":
            return httpx.Response(
                200,
                json={
                    "name": "Set",
                    "snapshot_id": "snap-9",
                    "tracks": {
                        "total": 3,
                        "items": [
                            _track_item("t1", "One", "Artist A", isrc="USABC1234567"),
                            _track_item("t2", "Two", "Artist B"),
                        ],
                        "next": f"https://api.spotify.com{tracks_path}?offset=2",
                    },
                },
            )
        if request.url.path == tracks_path:
            return httpx.Response(
                200,
                json={"items": [_track_item("t3", "Three", "Artist C")], "next": None},
            )
        raise AssertionError(f"unexpected {request.url}")

    result = spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)

    assert result.name == "Set"
    assert result.snapshot_id == "snap-9"
    assert [t["spotify_track_id"] for t in result.tracks] == ["t1", "t2", "t3"]
    assert result.tracks[0]["isrc"] == "USABC1234567"
    assert result.tracks[0]["artist"] == "Artist A"
    assert result.tracks[0]["duration_ms"] == 200_000
    # First page + one follow of `next`.
    assert calls == [f"/v1/playlists/{PLAYLIST_ID}", tracks_path]


def test_local_and_unavailable_tracks_are_kept_as_unmatchable_rows(session):
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(
            200,
            json={
                "name": "Mixed",
                "snapshot_id": "s",
                "tracks": {
                    "total": 3,
                    "items": [
                        _track_item("t1", "Real", "Artist"),
                        {"is_local": True, "track": None},  # local file
                        {"is_local": False, "track": None},  # unavailable
                    ],
                    "next": None,
                },
            },
        )

    result = spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)

    assert len(result.tracks) == 3  # nothing silently dropped (spec edge case)
    assert result.tracks[1]["spotify_track_id"] is None
    assert result.tracks[1]["isrc"] is None
    assert result.tracks[1]["is_local"] is True
    assert result.tracks[2]["is_local"] is True


# --------------------------------------------------------------------------- #
# URL parsing (ASVS V5)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}",
        f"https://open.spotify.com/playlist/{PLAYLIST_ID}?si=abc123",
        f"spotify:playlist:{PLAYLIST_ID}",
        PLAYLIST_ID,
    ],
)
def test_parse_playlist_id_accepts_url_uri_and_bare_id(value):
    assert spotify.parse_playlist_id(value) == PLAYLIST_ID


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example.com/playlist/PLAYLISTID0000000000AB",
        "https://open.spotify.com/track/PLAYLISTID0000000000AB",
        "not a url at all!",
        "../../etc/passwd",
        "",
    ],
)
def test_parse_playlist_id_rejects_non_playlist_input(value):
    with pytest.raises(InvalidPlaylistUrlError):
        spotify.parse_playlist_id(value)


# --------------------------------------------------------------------------- #
# Status / disconnect (AVG/GDPR deletion path)
# --------------------------------------------------------------------------- #
def test_connection_status_reflects_stored_row(session):
    assert spotify.connection_status(session) == {
        "connected": False,
        "display_name": None,
        "product": None,
    }
    _store_auth(session, expires_in_seconds=3600)
    assert spotify.connection_status(session) == {
        "connected": True,
        "display_name": "DJ Test",
        "product": "premium",
    }


def test_disconnect_deletes_the_row(session):
    _store_auth(session, expires_in_seconds=3600)
    assert session.get(SpotifyAuth, 1) is not None

    spotify.disconnect(session)

    assert session.get(SpotifyAuth, 1) is None


def test_a_playlist_response_without_a_tracks_object_falls_back_to_the_tracks_endpoint(session):
    # Spotify does not always embed the tracks object. Reading its absence as an
    # empty playlist is what made a real sync report a ready session with zero
    # tracks and no error, so the fallback must actually be taken.
    _store_auth(session, expires_in_seconds=3600)
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/tracks"):
            return httpx.Response(
                200,
                json={
                    "total": 1,
                    "items": [
                        {
                            "track": {
                                "id": "sp1",
                                "name": "One More Time",
                                "artists": [{"name": "Daft Punk"}],
                                "duration_ms": 210_000,
                                "external_ids": {"isrc": "USRC17607839"},
                            }
                        }
                    ],
                    "next": None,
                },
            )
        # The playlist itself is readable, but carries no `tracks` key at all.
        return httpx.Response(200, json={"name": "Bruiloft", "snapshot_id": "snap-1"})

    result = spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)

    assert [track["title"] for track in result.tracks] == ["One More Time"]
    assert result.name == "Bruiloft"
    assert any(path.endswith("/tracks") for path in paths)


def test_a_forbidden_tracks_endpoint_is_an_error_not_an_empty_playlist(session):
    # The failure this pairs with: the playlist reads fine, Spotify refuses its
    # contents with a bare 403, and the DJ must be told rather than shown an
    # empty match report.
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        if request.url.path.endswith("/tracks"):
            return httpx.Response(403, json={"error": {"status": 403, "message": "Forbidden"}})
        return httpx.Response(200, json={"name": "Bruiloft", "snapshot_id": "snap-1"})

    with pytest.raises(PlaylistUnreachableError) as caught:
        spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)

    # The message has to name where the permission sits, because "playlist is
    # private" sends the DJ to fix the wrong thing.
    assert "Spotify app" in str(caught.value)


def test_a_genuinely_empty_playlist_still_fetches_as_empty(session):
    # The other side of the same coin: a tracks object that is present and says
    # zero is a real, empty playlist and must not become an error.
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(
            200,
            json={
                "name": "Nog leeg",
                "snapshot_id": "snap-1",
                "tracks": {"total": 0, "items": [], "next": None},
            },
        )

    result = spotify.fetch_playlist_tracks(session, _client(handler), PLAYLIST_ID)

    assert result.tracks == []
    assert result.name == "Nog leeg"


# --------------------------------------------------------------------------- #
# The operator's own playlists (GET /v1/me/playlists)
# --------------------------------------------------------------------------- #
def _playlist_item(playlist_id, name, images=None, owner="DJ Test"):
    """One `/v1/me/playlists` item as this account really receives it.

    Verified against the live account: `id`, `name`, `images` (three sizes of
    real cover art), `owner.display_name` and `description` are present, and
    the `tracks` object is stripped for this application -- there is NO track
    count to report, so nothing here invents one.
    """
    return {
        "id": playlist_id,
        "name": name,
        "description": "",
        "owner": {"display_name": owner},
        "images": [
            {"url": "https://i.scdn.co/image/large", "width": 640, "height": 640},
            {"url": "https://i.scdn.co/image/medium", "width": 300, "height": 300},
            {"url": "https://i.scdn.co/image/small", "width": 64, "height": 64},
        ]
        if images is None
        else images,
    }


def test_list_my_playlists_paginates_over_spotifys_own_pagination(session):
    _store_auth(session, expires_in_seconds=3600)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.params.get("offset") == "50":
            return httpx.Response(
                200, json={"items": [_playlist_item("p3", "Prive")], "next": None}
            )
        return httpx.Response(
            200,
            json={
                "items": [_playlist_item("p1", "Bruiloft"), _playlist_item("p2", "Horeca")],
                "next": "https://api.spotify.com/v1/me/playlists?offset=50&limit=50",
            },
        )

    playlists = spotify.list_my_playlists(session, _client(handler))

    assert [p["spotify_playlist_id"] for p in playlists] == ["p1", "p2", "p3"]
    assert [p["name"] for p in playlists] == ["Bruiloft", "Horeca", "Prive"]
    assert len(calls) == 2  # first page + one follow of `next`


def test_list_my_playlists_returns_only_fields_spotify_really_gives_this_app(session):
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(200, json={"items": [_playlist_item("p1", "Bruiloft")], "next": None})

    playlist = spotify.list_my_playlists(session, _client(handler))[0]

    # No track count: Spotify strips the `tracks` object for this application,
    # so there is nothing honest to report and nothing is invented.
    assert set(playlist) == {"spotify_playlist_id", "name", "image_url", "owner_display_name"}
    assert playlist["owner_display_name"] == "DJ Test"


def test_list_my_playlists_picks_a_sidebar_sized_cover_image(session):
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(200, json={"items": [_playlist_item("p1", "Bruiloft")], "next": None})

    playlist = spotify.list_my_playlists(session, _client(handler))[0]

    # The smallest image still wide enough for a sidebar thumbnail, not the
    # 640px original: 101 playlists render at once.
    assert playlist["image_url"] == "https://i.scdn.co/image/medium"


def test_list_my_playlists_falls_back_to_the_largest_image_and_then_to_none(session):
    _store_auth(session, expires_in_seconds=3600)
    tiny = [{"url": "https://i.scdn.co/image/tiny", "width": 60, "height": 60}]
    unsized = [{"url": "https://i.scdn.co/image/unsized", "width": None, "height": None}]

    def handler(request):
        return httpx.Response(
            200,
            json={
                "items": [
                    _playlist_item("p1", "Only tiny art", images=tiny),
                    _playlist_item("p2", "Unsized art", images=unsized),
                    _playlist_item("p3", "No art at all", images=[]),
                ],
                "next": None,
            },
        )

    playlists = spotify.list_my_playlists(session, _client(handler))

    assert [p["image_url"] for p in playlists] == [
        "https://i.scdn.co/image/tiny",
        "https://i.scdn.co/image/unsized",
        None,
    ]


def test_list_my_playlists_reports_a_missing_owner_name_as_none(session):
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(
            200,
            json={"items": [{"id": "p1", "name": "Naamloos", "owner": {}}], "next": None},
        )

    playlist = spotify.list_my_playlists(session, _client(handler))[0]

    assert playlist["owner_display_name"] is None
    assert playlist["image_url"] is None


@pytest.mark.parametrize("status_code", [403, 404, 429, 500])
def test_a_refused_playlist_listing_is_a_typed_error_not_an_empty_list(session, status_code):
    # The phase 7 lesson, applied to the listing: Spotify refusing to answer
    # must never look like "this account owns no playlists".
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(status_code, json={"error": {"status": status_code}})

    with pytest.raises(spotify.PlaylistsUnavailableError):
        spotify.list_my_playlists(session, _client(handler))


def test_a_refusal_halfway_through_pagination_is_an_error_not_a_partial_list(session):
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        if request.url.params.get("offset") == "50":
            return httpx.Response(403, json={"error": {"status": 403}})
        return httpx.Response(
            200,
            json={
                "items": [_playlist_item("p1", "Bruiloft")],
                "next": "https://api.spotify.com/v1/me/playlists?offset=50&limit=50",
            },
        )

    with pytest.raises(spotify.PlaylistsUnavailableError):
        spotify.list_my_playlists(session, _client(handler))


def test_list_my_playlists_with_a_rejected_token_raises_session_expired(session):
    _store_auth(session, expires_in_seconds=3600)

    def handler(request):
        return httpx.Response(401, json={"error": {"status": 401}})

    with pytest.raises(SessionExpiredError):
        spotify.list_my_playlists(session, _client(handler))


def test_list_my_playlists_without_a_session_raises_not_connected(session):
    def handler(request):  # pragma: no cover - must never be called
        raise AssertionError("no HTTP call without a stored session")

    with pytest.raises(NotConnectedError):
        spotify.list_my_playlists(session, _client(handler))


def test_list_my_playlists_refreshes_an_expired_token_first(session, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "test-client-id")
    _store_auth(session, expires_in_seconds=-10, access_token="stale-access")
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/api/token":
            return httpx.Response(200, json={"access_token": "fresh-access", "expires_in": 3600})
        assert request.headers.get("Authorization") == "Bearer fresh-access"
        return httpx.Response(200, json={"items": [], "next": None})

    spotify.list_my_playlists(session, _client(handler))

    assert calls == ["/api/token", "/v1/me/playlists"]
