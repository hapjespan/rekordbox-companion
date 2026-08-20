"""GET /api/spotify/playlists (contracts/api.md "Spotify playlists").

The operator's own Spotify playlists, so a sync can be started by clicking one
in the sidebar instead of pasting a URL. Two sources, kept strictly apart:

* Spotify supplies id, name, cover art and owner name --
  `integrations.spotify.list_my_playlists` does that call, the pagination and
  the token refresh, and raises typed errors rather than ever returning a
  short or empty list on a refusal.
* The app's own database supplies the sync status: whether a `playlist_link`
  exists for the playlist and what the LATEST `sync_session` for that link
  reported. Never derived from anything Spotify says.

The status is returned as a state plus counts, never as a rendered sentence:
UI copy is Dutch and belongs in the frontend (contracts/api.md conventions).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from companion.api.auth import get_spotify_client
from companion.db.models import PlaylistLink, SyncSession, SyncTrack
from companion.db.session import get_db
from companion.integrations import spotify

router = APIRouter()

# The five per-track statuses of a Sync Session (data-model.md `sync_track`),
# always all present in `totals` so the caller never has to guess whether a
# missing key means zero. Kept local rather than imported from `api.sync`'s
# private constant, the same way `api.sync` keeps its own `_utcnow`.
_TRACK_STATUSES = ("matched", "review", "missing", "rejected", "unmatchable")

# SQLite's default bound-variable limit (SQLITE_MAX_VARIABLE_NUMBER,
# historically 999) applies to the `IN` clauses below, whose size grows with
# the number of playlists on the account. Chunking keeps a very large account
# from turning into an unhandled 500, the same failure GET /api/collection's
# limit cap exists to prevent.
_IN_CLAUSE_CHUNK = 500


def _chunks(values: list):
    for start in range(0, len(values), _IN_CLAUSE_CHUNK):
        yield values[start : start + _IN_CLAUSE_CHUNK]


def _links_by_spotify_id(db: Session, spotify_playlist_ids: list[str]) -> dict[str, PlaylistLink]:
    links: dict[str, PlaylistLink] = {}
    for chunk in _chunks(spotify_playlist_ids):
        rows = db.query(PlaylistLink).filter(PlaylistLink.spotify_playlist_id.in_(chunk)).all()
        links.update({row.spotify_playlist_id: row for row in rows})
    return links


def _latest_session_by_link(db: Session, link_ids: list[int]) -> dict[int, SyncSession]:
    """The most recent `sync_session` per link. A re-sync is a new session on
    the same link (data-model.md), so "what the app knows about this playlist"
    is the newest one, not the first. Ties on `created_at` break on `id`, so
    two sessions created in the same clock tick still resolve deterministically.
    """
    latest: dict[int, SyncSession] = {}
    for chunk in _chunks(link_ids):
        rows = (
            db.query(SyncSession)
            .filter(SyncSession.playlist_link_id.in_(chunk))
            .order_by(SyncSession.created_at.desc(), SyncSession.id.desc())
            .all()
        )
        for row in rows:
            latest.setdefault(row.playlist_link_id, row)
    return latest


def _totals_by_session(db: Session, session_ids: list[int]) -> dict[int, dict[str, int]]:
    """One grouped count query per chunk, not one query per playlist."""
    totals = {session_id: dict.fromkeys(_TRACK_STATUSES, 0) for session_id in session_ids}
    for chunk in _chunks(session_ids):
        rows = db.execute(
            select(SyncTrack.sync_session_id, SyncTrack.status, func.count())
            .where(SyncTrack.sync_session_id.in_(chunk))
            .group_by(SyncTrack.sync_session_id, SyncTrack.status)
        )
        for session_id, status, count in rows:
            if status in totals[session_id]:
                totals[session_id][status] = count
    return totals


def _not_scanned() -> dict:
    return {
        "state": "not_scanned",
        "session_id": None,
        "session_created_at": None,
        "last_applied_at": None,
        "totals": None,
    }


def _sync_status_for(
    link: PlaylistLink | None,
    session: SyncSession | None,
    totals: dict[str, int] | None,
) -> dict:
    """`state` is the latest session's own `sync_session.status` verbatim
    (`fetching`, `matching`, `ready`, `applied`, `failed`), or `not_scanned`
    when this app has never synced the playlist -- one field for the UI to
    switch on, with no second vocabulary invented on top of the model."""
    if link is None or session is None:
        return _not_scanned()
    return {
        "state": session.status,
        "session_id": session.id,
        "session_created_at": session.created_at,
        "last_applied_at": link.last_applied_at,
        "totals": totals,
    }


@router.get("/spotify/playlists")
def list_spotify_playlists(db: Session = Depends(get_db), client=Depends(get_spotify_client)):
    """`[{spotify_playlist_id, name, image_url, owner_display_name, sync}]`.

    No track count: Spotify strips the `tracks` object from `/me/playlists`
    items for this application, so there is none to report and none is
    invented (contracts/api.md).
    """
    try:
        playlists = spotify.list_my_playlists(db, client)
    except spotify.NotConnectedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "spotify_not_connected", "message": str(exc)},
        ) from exc
    except spotify.SessionExpiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "spotify_session_expired", "message": str(exc)},
        ) from exc
    except spotify.SpotifyNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "spotify_not_configured", "message": str(exc)},
        ) from exc
    except spotify.PlaylistsUnavailableError as exc:
        # 502, not an empty list and not a 500: Spotify answered, and what it
        # answered was a refusal (phase 7 finding -- a refusal that reads as
        # "you have no playlists" sends the DJ to fix the wrong thing).
        raise HTTPException(
            status_code=502,
            detail={"code": "spotify_playlists_unavailable", "message": str(exc)},
        ) from exc

    links = _links_by_spotify_id(db, [p["spotify_playlist_id"] for p in playlists])
    sessions = _latest_session_by_link(db, [link.id for link in links.values()])
    totals = _totals_by_session(db, [session.id for session in sessions.values()])

    for playlist in playlists:
        link = links.get(playlist["spotify_playlist_id"])
        session = sessions.get(link.id) if link is not None else None
        playlist["sync"] = _sync_status_for(
            link, session, totals.get(session.id) if session is not None else None
        )
    return playlists
