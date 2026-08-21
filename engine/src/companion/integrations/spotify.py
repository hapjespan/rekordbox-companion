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

from companion import security
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

# Spotify's maximum page size for `/me/playlists` (half the items limit; the
# endpoint refuses anything above 50).
_MY_PLAYLISTS_PAGE_LIMIT = 50

# The narrowest cover art still sharp enough for a sidebar thumbnail on a
# retina display. Spotify returns three sizes per playlist (typically 640/300/
# 64 px); the smallest one at or above this width is picked, so a sidebar of
# ~100 playlists does not pull 100 x 640px originals.
_MIN_COVER_WIDTH = 160

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


class SessionExpiredError(SpotifyError):
    """A previously-connected Spotify session is no longer usable: the
    refresh token was rejected (revoked at Spotify's end, or otherwise
    invalid), so the access token cannot be renewed. Distinct from
    `NotConnectedError` (no session ever existed) so a caller can message
    the difference -- both need the same fix (reconnect), which is what
    spec.md's edge case asks for: "the Spotify session expires mid Sync
    Session: the session fails with a re-connect prompt and no partial
    report is presented as complete" (T104 build finding: this used to let
    the refresh call's `httpx.HTTPStatusError` bubble up uncaught)."""


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


class PlaylistsUnavailableError(SpotifyError):
    """Spotify would not list this account's own playlists (`/me/playlists`).

    A separate type from `PlaylistUnreachableError`, which is about one named
    playlist: this one says "the listing itself failed". It exists so a
    refusal can never be mistaken for an account that owns no playlists --
    the same phase 7 finding that made an unreadable playlist's contents an
    error rather than an empty match report.
    """


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
    `db.session.create_session_factory`). Routed through
    `security.build_allowlisted_client` (T090): a defense-in-depth backstop
    that refuses any request whose host isn't `api.spotify.com` or
    `accounts.spotify.com`, on top of this module already only ever
    building URLs from those two fixed constants.
    """
    return security.build_allowlisted_client(timeout=15.0)


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
    if response.status_code in (400, 401):
        # Spotify rejects a revoked/invalid refresh token this way (spec.md
        # edge case: session expires mid Sync Session).
        raise SessionExpiredError("Spotify rejected the refresh token; reconnect the account")
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


def get_player_token(db, client: httpx.Client) -> dict:
    """`{access_token, expires_in}` for the Web Playback SDK (T099,
    contracts/api.md "player-token", R2). Reuses `_get_valid_access_token`'s
    refresh-if-needed logic -- the SDK gets the same live token every other
    Spotify API call in this module would use, not a separate credential."""
    access_token = _get_valid_access_token(db, client)
    row = db.get(SpotifyAuth, 1)
    expires_in = max(0, int((row.token_expires_at - _utcnow()).total_seconds()))
    return {"access_token": access_token, "expires_in": expires_in}


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
# The operator's own playlists
# --------------------------------------------------------------------------- #
def _cover_image_url(images: list | None) -> str | None:
    """The best sidebar-sized cover URL among Spotify's three sizes, or None.

    Spotify orders `images` widest first and can report a `width` of null, so
    this picks the smallest image at or above `_MIN_COVER_WIDTH`, falls back to
    the widest known size when every image is smaller, and to the first URL
    when no width is given at all. A playlist without cover art has no image,
    which is a normal state and not an error.
    """
    candidates = [
        (image.get("width"), image.get("url")) for image in images or [] if image.get("url")
    ]
    if not candidates:
        return None
    sized = [(width, url) for width, url in candidates if isinstance(width, int)]
    if not sized:
        return candidates[0][1]
    big_enough = sorted(pair for pair in sized if pair[0] >= _MIN_COVER_WIDTH)
    return big_enough[0][1] if big_enough else max(sized)[1]


def _my_playlists_page(client: httpx.Client, url: str, headers: dict, params: dict | None) -> dict:
    """One `/me/playlists` page, with every refusal turned into a typed error.

    No non-2xx may become an empty list here: a 403 (this app may not read the
    account's playlists), a 429 (rate limited) and a 5xx all mean "we do not
    know what you own", which the caller must be able to say out loud.
    """
    response = client.get(url, headers=headers, params=params)
    if response.status_code == 401:
        raise SessionExpiredError("Spotify rejected the access token; reconnect the account")
    if not response.is_success:
        raise PlaylistsUnavailableError(
            "Spotify would not list this account's playlists "
            f"(HTTP {response.status_code}); it did not say the account has none"
        )
    return response.json()


def list_my_playlists(db, client: httpx.Client) -> list[dict]:
    """Every playlist on the operator's own account, as
    `{spotify_playlist_id, name, image_url, owner_display_name}` dicts.

    Paginates over Spotify's own `next` cursor to gather the whole account
    (101 playlists for the owner's), through the same allowlisted client and
    refresh-if-needed token path as every other call in this module.

    There is deliberately NO track count: Spotify strips the `tracks` object
    from `/me/playlists` items for this application, so any count would be
    invented. `description` is available but not returned -- nothing consumes
    it, and an unused field is a field that drifts.
    """
    access_token = _get_valid_access_token(db, client)
    headers = {"Authorization": f"Bearer {access_token}"}

    playlists: list[dict] = []
    body = _my_playlists_page(
        client,
        f"{API_BASE}/me/playlists",
        headers,
        {"limit": _MY_PLAYLISTS_PAGE_LIMIT},
    )
    while True:
        for item in body.get("items") or []:
            if not isinstance(item, dict):
                continue
            playlists.append(
                {
                    "spotify_playlist_id": item.get("id"),
                    "name": item.get("name") or "",
                    "image_url": _cover_image_url(item.get("images")),
                    "owner_display_name": (item.get("owner") or {}).get("display_name") or None,
                }
            )
        next_url = body.get("next")
        if not next_url:
            break
        # `next` is a Spotify-issued absolute URL on api.spotify.com: the API's
        # own cursor, never user input (and the allowlisted client refuses any
        # other host regardless).
        body = _my_playlists_page(client, next_url, headers, None)

    logger.info("spotify_playlists_listed", extra={"count": len(playlists)})
    return playlists


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
    with null identifiers rather than being dropped (spec.md edge case).

    Spotify's March 2026 API migration renamed the wrapped track/episode field
    from `track` to `item` on every entry (and, one level up, the playlist's
    own `tracks` object to `items`) without changing anything else about the
    shape. `_fetch_tracks_page` and `fetch_playlist_tracks` below read the new
    names; this is the one place that reads the per-entry wrapper."""
    is_local = bool(item.get("is_local"))
    track = item.get("item")
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


def _fetch_tracks_page(client: httpx.Client, headers: dict, playlist_id: str) -> dict:
    """First page of a playlist's items from the dedicated items endpoint.

    The fallback for a playlist response that carries no embedded `items`
    object. Spotify answers this endpoint with a bare 403 when it will not give
    an app a playlist's contents, and the caller must hear about that rather
    than see an empty playlist, so every non-2xx becomes an error here.

    `/playlists/{id}/tracks` itself is gone: Spotify's March 2026 migration
    renamed it to `/playlists/{id}/items`, and development-mode apps may only
    call it for a playlist they own or collaborate on -- calling the old path
    now answers a 403 unconditionally, which is what surfaced this rename.
    """
    response = client.get(
        f"{API_BASE}/playlists/{playlist_id}/items",
        headers=headers,
        params={"limit": _PAGE_LIMIT},
    )
    if response.status_code == 401:
        raise SessionExpiredError("Spotify rejected the access token; reconnect the account")
    if response.status_code in (403, 404):
        raise PlaylistUnreachableError(
            f"Spotify will not return the tracks of playlist {playlist_id!r}. The playlist "
            "itself is readable, so this is a permission on the Spotify app rather than the "
            "playlist: check that the app may read playlist contents for this account"
        )
    response.raise_for_status()
    return response.json()


def fetch_playlist_tracks(
    db, client: httpx.Client, playlist_url_or_id: str
) -> SpotifyPlaylistFetch:
    """Fetch a playlist's tracks, paginating, with the 999-cap short-circuit.

    The first request returns `items.total`; if that exceeds the cap the
    function raises `PlaylistTooLargeError` immediately, WITHOUT fetching any
    further page (T022 review finding). Only within the cap does it follow
    `items.next` to completion. (Spotify's March 2026 migration renamed the
    embedded `tracks` object to `items`; see `_fetch_tracks_page`.)
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
    if first.status_code == 401:
        # The access token passed our local expiry check but Spotify
        # rejected it anyway -- e.g. access revoked mid-session (T104
        # build finding, spec.md's "session expires mid Sync Session").
        raise SessionExpiredError("Spotify rejected the access token; reconnect the account")
    first.raise_for_status()
    body = first.json()

    # Spotify does not always embed the items object in the playlist response:
    # a playlist this app may not read the contents of comes back with no
    # `items` key at all, and a bare 403 on the dedicated items endpoint.
    # Reading a MISSING object as an empty playlist is the difference between
    # "you own none of these" and "we could not read the playlist", and the
    # app used to report the first while meaning the second: a session went
    # `ready` with zero tracks and no error. An absent object is therefore an
    # error, while an object that is present and says zero is a genuinely
    # empty playlist and stays fine.
    if "items" not in body:
        tracks_page = _fetch_tracks_page(client, headers, playlist_id)
    else:
        tracks_page = body.get("items") or {}
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
        if page.status_code == 401:
            raise SessionExpiredError("Spotify rejected the access token; reconnect the account")
        page.raise_for_status()
        page_body = page.json()
        tracks.extend(_extract_track(item) for item in page_body.get("items", []))
        next_url = page_body.get("next")

    return SpotifyPlaylistFetch(
        name=body.get("name") or "",
        snapshot_id=body.get("snapshot_id") or "",
        tracks=tracks,
    )
