"""Spotify integration: OAuth PKCE session + playlist fetch (T026, US1).

This is the security boundary that exchanges and stores the operator's Spotify
credentials, so every rule below is load-bearing, not decoration:

* **Public-client PKCE, no secret** (constraints.md ASVS V2). The flow uses a
  loopback redirect and an S256 code challenge; there is NO client secret in
  the repository or in `.env`. Only a public `SPOTIFY_CLIENT_ID` (the
  operator's own Spotify Developer Dashboard app) is needed.
* **Tokens are never logged** (ASVS V3, NIS2). This module logs account
  identity and event summaries via named fields, never a raw token; the
  redacting formatter (`companion.logging`) is the backstop, not the plan.
* **Fixed outbound hosts only** (ASVS V10/V14, SSRF). Every request targets a
  URL built from the module constants below (`accounts.spotify.com`,
  `api.spotify.com`); nothing here is ever pointed at a host taken from user
  input. The pasted playlist URL is parsed to a base62 id (ASVS V5) that is
  interpolated into a fixed API path -- the raw URL is never fetched.

Naming: `SpotifyPlaylistFetch` mirrors the seam T028's `get_spotify_fetcher`
dependency wraps (`.name`, `.snapshot_id`, `.tracks`), but this task does not
depend on T028's exact DI shape -- it only makes the fetch function exist and
behave correctly.
"""

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

import httpx

from companion.db.models import SpotifyAuth
from companion.logging import get_logger

logger = get_logger(__name__)

# --- Fixed outbound endpoints (ASVS V10/V14). Never derived from user input. --
ACCOUNTS_HOST = "accounts.spotify.com"
API_HOST = "api.spotify.com"
AUTHORIZE_URL = f"https://{ACCOUNTS_HOST}/authorize"
TOKEN_URL = f"https://{ACCOUNTS_HOST}/api/token"
API_BASE = f"https://{API_HOST}/v1"

# The app binds to 127.0.0.1:8787 and nowhere else (main.py / kickoff §5), so
# the loopback callback is a constant derived from that fixed binding rather
# than its own env var. Spotify permits plain http ONLY for loopback redirect
# URIs, which is why this is http, not https.
REDIRECT_URI = "http://127.0.0.1:8787/api/auth/spotify/callback"

# Scopes: playlist read (US1 fetch) plus the Web Playback SDK set that US2's
# T099 player-token task will need (streaming + the account-read scopes Spotify
# requires alongside it). Requesting them once here avoids a re-consent later.
SCOPES = (
    "playlist-read-private playlist-read-collaborative streaming user-read-email user-read-private"
)

# The Sync input bound (constraints.md D12, edge case): a playlist larger than
# this is refused BEFORE the Sync Session starts. Enforced here, on the first
# page's `total`, so pagination short-circuits instead of fetching everything
# and counting afterwards (T022 review finding, the reason the cap lives here).
PLAYLIST_TRACK_CAP = 999

# Spotify's maximum page size for playlist items.
_PAGE_LIMIT = 100

# Refresh a little before the token actually expires, so a call that starts
# just under the wire does not race the expiry.
_EXPIRY_SKEW = timedelta(seconds=60)

# PKCE verifiers awaiting their callback, keyed by `state`. In-memory is correct
# here, not a shortcut: one operator on one localhost process, and the value is
# ephemeral (seconds between /login redirect and /callback). A process restart
# mid-flow just means re-clicking login; nothing durable is lost, and keeping a
# short-lived secret out of the database is the safer default.
_pending_verifiers: dict[str, str] = {}


class SpotifyError(Exception):
    """Base class for this module's expected, caller-handled failures."""


class SpotifyNotConfiguredError(SpotifyError):
    """`SPOTIFY_CLIENT_ID` is not set, so no PKCE flow can start."""


class StateMismatchError(SpotifyError):
    """Callback `state` did not match a pending login (CSRF guard, ASVS V5)."""


class NotConnectedError(SpotifyError):
    """An API call needs a token but no Spotify session is stored."""


class InvalidPlaylistUrlError(SpotifyError):
    """The pasted value did not parse to a Spotify playlist id (ASVS V5)."""


class PlaylistUnreachableError(SpotifyError):
    """The playlist id parsed but Spotify refused or couldn't find it --
    private, deleted, or otherwise inaccessible to this account (spec.md
    edge case). Distinct from `InvalidPlaylistUrlError` (bad input) so a
    caller (api/sync.py) can name the actual problem: a T031/T032 review
    finding -- `fetch_playlist_tracks` previously let Spotify's 403/404
    bubble up as an unhandled `httpx.HTTPStatusError`, surfacing as a raw
    500 with no `{code, message, field}` for a scenario spec.md itself
    names ("playlist is private")."""


class PlaylistTooLargeError(SpotifyError):
    """The playlist exceeds `PLAYLIST_TRACK_CAP`; refused before any session.

    Carries `total` so the caller (T028's router) can name the limit and the
    actual size in its 422, and is a distinct type so a caller cleanly tells
    "too large" from a normal successful fetch.
    """

    def __init__(self, total: int) -> None:
        self.total = total
        super().__init__(f"playlist has {total} tracks, cap is {PLAYLIST_TRACK_CAP}")


@dataclass
class SpotifyPlaylistFetch:
    """A fetched playlist: metadata plus one track dict per playlist position.

    `tracks` items carry `{spotify_track_id, isrc, artist, title, duration_ms,
    is_local}`. Local/unavailable tracks keep their row (never silently
    dropped, spec.md edge case) with `spotify_track_id`/`isrc` set to None and
    `is_local` True, so a caller classifies them `unmatchable`.
    """

    name: str
    snapshot_id: str
    tracks: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def _client_id() -> str:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    if not client_id:
        raise SpotifyNotConfiguredError(
            "SPOTIFY_CLIENT_ID is not set; add the client id of your own "
            "Spotify Developer Dashboard app to .env (no secret is needed for PKCE)."
        )
    return client_id


def build_client() -> httpx.Client:
    """A short-lived httpx client for one request cycle.

    A factory, not a module global, so tests inject an `httpx.MockTransport`
    client and no real network client leaks between them (same reasoning as
    `db.session.create_session_factory`).
    """
    return httpx.Client(timeout=15.0)


def _utcnow() -> datetime:
    """Naive UTC 'now'. One clock on one machine, so a single naive-UTC
    convention avoids aware/naive comparison bugs against SQLite reads."""
    return datetime.now(UTC).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# PKCE
# --------------------------------------------------------------------------- #
def generate_code_verifier() -> str:
    """A high-entropy PKCE verifier (RFC 7636: 43-128 unreserved chars)."""
    return secrets.token_urlsafe(64)


def code_challenge_for(verifier: str) -> str:
    """The S256 challenge: base64url(SHA256(verifier)), padding stripped."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def start_login() -> tuple[str, str]:
    """Begin PKCE: stash a fresh verifier under a random `state`, return the
    Spotify `/authorize` URL to redirect to and that `state`."""
    verifier = generate_code_verifier()
    challenge = code_challenge_for(verifier)
    state = secrets.token_urlsafe(32)
    _pending_verifiers[state] = verifier

    params = {
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": state,
        "scope": SCOPES,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}", state


def _take_verifier(state: str) -> str:
    verifier = _pending_verifiers.pop(state, None)
    if verifier is None:
        raise StateMismatchError("unknown or expired login state")
    return verifier


# --------------------------------------------------------------------------- #
# Token exchange / refresh
# --------------------------------------------------------------------------- #
def _persist_tokens(db, token_response: dict, existing: SpotifyAuth | None) -> SpotifyAuth:
    access_token = token_response["access_token"]
    # Spotify may or may not return a fresh refresh_token on a refresh; keep the
    # previous one when it doesn't.
    refresh_token = token_response.get("refresh_token")
    expires_in = int(token_response.get("expires_in", 3600))
    expires_at = _utcnow() + timedelta(seconds=expires_in)

    row = existing or db.get(SpotifyAuth, 1)
    if row is None:
        row = SpotifyAuth(id=1, access_token=access_token, refresh_token=refresh_token or "")
        db.add(row)
    else:
        row.access_token = access_token
        if refresh_token:
            row.refresh_token = refresh_token
    row.token_expires_at = expires_at
    return row


def complete_login(db, client: httpx.Client, code: str, state: str) -> SpotifyAuth:
    """Finish the callback: verify state, exchange code (+ verifier) for tokens,
    fetch the account profile, upsert the single `spotify_auth` row."""
    verifier = _take_verifier(state)

    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": _client_id(),
            "code_verifier": verifier,
        },
    )
    response.raise_for_status()
    tokens = response.json()

    profile = _fetch_profile(client, tokens["access_token"])

    row = _persist_tokens(db, tokens, existing=db.get(SpotifyAuth, 1))
    row.account_id = profile.get("id") or ""
    row.display_name = profile.get("display_name")
    row.product = profile.get("product")
    db.commit()

    # Identity is allowed in logs (only tokens/keys are forbidden); the token
    # itself is never referenced here.
    logger.info(
        "spotify_connected",
        extra={"account_id": row.account_id, "display_name": row.display_name},
    )
    return row


def _fetch_profile(client: httpx.Client, access_token: str) -> dict:
    response = client.get(f"{API_BASE}/me", headers={"Authorization": f"Bearer {access_token}"})
    response.raise_for_status()
    return response.json()


def _refresh(db, client: httpx.Client, row: SpotifyAuth) -> SpotifyAuth:
    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": row.refresh_token,
            "client_id": _client_id(),
        },
    )
    response.raise_for_status()
    refreshed = _persist_tokens(db, response.json(), existing=row)
    db.commit()
    logger.info("spotify_token_refreshed", extra={"account_id": row.account_id})
    return refreshed


def _get_valid_access_token(db, client: httpx.Client) -> str:
    """Return a usable access token, refreshing first if it is expired or about
    to expire. Internal helper for anything that calls the Spotify Web API."""
    row = db.get(SpotifyAuth, 1)
    if row is None:
        raise NotConnectedError("no Spotify session; connect the account first")
    if row.token_expires_at <= _utcnow() + _EXPIRY_SKEW:
        row = _refresh(db, client, row)
    return row.access_token


# --------------------------------------------------------------------------- #
# Status / disconnect
# --------------------------------------------------------------------------- #
def connection_status(db) -> dict:
    """`{connected, display_name, product}` (contracts/api.md). A stored row
    means connected; an expired token is refreshed transparently on next use."""
    row = db.get(SpotifyAuth, 1)
    if row is None:
        return {"connected": False, "display_name": None, "product": None}
    return {"connected": True, "display_name": row.display_name, "product": row.product}


def disconnect(db) -> None:
    """Delete the `spotify_auth` row. This IS the AVG/GDPR deletion path
    (pii-inventory.md): it actually removes the row, tokens and identity
    together, never merely flags it inactive."""
    row = db.get(SpotifyAuth, 1)
    if row is not None:
        db.delete(row)
        db.commit()
        logger.info("spotify_disconnected", extra={"account_id": row.account_id})


# --------------------------------------------------------------------------- #
# Playlist fetch
# --------------------------------------------------------------------------- #
def parse_playlist_id(value: str) -> str:
    """Parse a pasted playlist URL / URI / bare id into a base62 playlist id.

    ASVS V5: raw user-supplied URLs are never fetched. Only the extracted id
    (validated base62, so it can carry no path separator or scheme) is ever
    interpolated into the fixed API path.
    """
    candidate = (value or "").strip()

    if candidate.startswith("spotify:playlist:"):
        candidate = candidate.split(":", 2)[2]
    elif candidate.startswith(("http://", "https://")):
        parsed = urlparse(candidate)
        if parsed.hostname not in ("open.spotify.com", "play.spotify.com"):
            raise InvalidPlaylistUrlError(f"not a Spotify URL: {value!r}")
        parts = [segment for segment in parsed.path.split("/") if segment]
        if "playlist" not in parts or parts.index("playlist") + 1 >= len(parts):
            raise InvalidPlaylistUrlError(f"no playlist id in URL: {value!r}")
        candidate = parts[parts.index("playlist") + 1]

    candidate = candidate.split("?")[0]
    if not candidate.isalnum() or not (1 <= len(candidate) <= 40):
        raise InvalidPlaylistUrlError(f"not a valid Spotify playlist id: {value!r}")
    return candidate


def _extract_track(item: dict) -> dict:
    """One playlist item -> the track dict. Local/unavailable items keep a row
    with null identifiers rather than being dropped (spec.md edge case)."""
    is_local = bool(item.get("is_local"))
    track = item.get("track")
    if not isinstance(track, dict):
        return {
            "spotify_track_id": None,
            "isrc": None,
            "artist": "",
            "title": "",
            "duration_ms": 0,
            "is_local": True,
        }
    track_id = track.get("id")  # None for local files
    artists = track.get("artists") or []
    return {
        "spotify_track_id": track_id,
        "isrc": (track.get("external_ids") or {}).get("isrc"),
        "artist": artists[0].get("name", "") if artists else "",
        "title": track.get("name") or "",
        "duration_ms": track.get("duration_ms") or 0,
        # No id means nothing to match on -> the caller treats it as unmatchable.
        "is_local": is_local or track_id is None,
    }


def fetch_playlist_tracks(
    db, client: httpx.Client, playlist_url_or_id: str
) -> SpotifyPlaylistFetch:
    """Fetch a playlist's tracks, paginating, with the 999-cap short-circuit.

    The first request returns `tracks.total`; if that exceeds the cap the
    function raises `PlaylistTooLargeError` immediately, WITHOUT fetching any
    further page (T022 review finding). Only within the cap does it follow
    `tracks.next` to completion.
    """
    playlist_id = parse_playlist_id(playlist_url_or_id)
    access_token = _get_valid_access_token(db, client)
    headers = {"Authorization": f"Bearer {access_token}"}

    # One call gives name, snapshot_id, tracks.total and the first page. The cap
    # check happens on this single response, before any pagination.
    first = client.get(
        f"{API_BASE}/playlists/{playlist_id}",
        headers=headers,
        params={"limit": _PAGE_LIMIT},
    )
    if first.status_code in (403, 404):
        raise PlaylistUnreachableError(
            f"playlist {playlist_id!r} is private, deleted, or otherwise inaccessible"
        )
    first.raise_for_status()
    body = first.json()

    tracks_page = body.get("tracks") or {}
    total = int(tracks_page.get("total", 0))
    if total > PLAYLIST_TRACK_CAP:
        logger.info(
            "spotify_playlist_too_large",
            extra={"playlist_id": playlist_id, "total": total, "cap": PLAYLIST_TRACK_CAP},
        )
        raise PlaylistTooLargeError(total)

    tracks = [_extract_track(item) for item in tracks_page.get("items", [])]
    next_url = tracks_page.get("next")
    while next_url:
        # `next` is a Spotify-issued absolute URL on api.spotify.com; it is the
        # API's own pagination cursor, not user input.
        page = client.get(next_url, headers=headers)
        page.raise_for_status()
        page_body = page.json()
        tracks.extend(_extract_track(item) for item in page_body.get("items", []))
        next_url = page_body.get("next")

    return SpotifyPlaylistFetch(
        name=body.get("name") or "",
        snapshot_id=body.get("snapshot_id") or "",
        tracks=tracks,
    )
