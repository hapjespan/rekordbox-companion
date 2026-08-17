"""Spotify auth endpoints (contracts/api.md "Spotify auth"): the PKCE
login/callback/status/disconnect flow (T026, US1).

`GET /api/auth/spotify/player-token` is deliberately absent: it is a separate
later task (T099, US2). The heavy lifting (PKCE, token exchange, HTTP) lives in
`companion.integrations.spotify`; this router is a thin HTTP adapter that maps
the integration's typed errors onto the contract's `{code, message, field?}`
envelope.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from companion.db.session import get_db
from companion.integrations import spotify

router = APIRouter()


def get_spotify_client():
    """FastAPI dependency yielding a request-scoped httpx client, so tests
    override it with an `httpx.MockTransport` client instead of hitting the
    real Spotify API (the same seam-isolation pattern as `get_database`)."""
    client = spotify.build_client()
    try:
        yield client
    finally:
        client.close()


@router.get("/auth/spotify/login")
def login():
    """Start PKCE and 307-redirect the browser to Spotify's consent page."""
    try:
        authorize_url, _state = spotify.start_login()
    except spotify.SpotifyNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "spotify_not_configured", "message": str(exc)},
        ) from exc
    return RedirectResponse(authorize_url, status_code=307)


@router.get("/auth/spotify/callback")
def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    client=Depends(get_spotify_client),
):
    """Complete PKCE, then redirect back to the SPA root regardless of outcome
    (the SPA reads `/status` to render connected/disconnected). A `state`
    mismatch is a hard 400 (CSRF guard), not a silent redirect."""
    if error is not None or code is None or state is None:
        # User denied consent, or Spotify returned no code: nothing to store.
        return RedirectResponse("/", status_code=307)
    try:
        spotify.complete_login(db, client, code, state)
    except spotify.StateMismatchError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "state_mismatch", "message": str(exc), "field": "state"},
        ) from exc
    except spotify.SpotifyNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "spotify_not_configured", "message": str(exc)},
        ) from exc
    return RedirectResponse("/", status_code=307)


@router.get("/auth/spotify/status")
def status(db: Session = Depends(get_db)):
    """`{connected, display_name, product}` from the stored session row."""
    return spotify.connection_status(db)


@router.post("/auth/spotify/disconnect")
def disconnect(db: Session = Depends(get_db)):
    """Delete the stored Spotify session (the AVG/GDPR deletion path)."""
    spotify.disconnect(db)
    return spotify.connection_status(db)
