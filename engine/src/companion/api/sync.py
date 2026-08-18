"""POST/GET /api/sync/sessions (contracts/api.md "Sync sessions", US1).

Fetches a Spotify playlist, matches every track against the in-memory
Collection index, and persists one `sync_track` row per playlist position
(T028). `get_spotify_fetcher` is the seam T022's contract test already fixed
(`(playlist_url: str) -> object with .name/.snapshot_id/.tracks`, tracks
exposing `.spotify_track_id/.isrc/.artist/.title/.duration_ms`) -- this
module's production implementation wraps `integrations.spotify` behind that
exact shape, so the router's own matching/persistence code stays identical
whether it runs against T022's fake or the real Spotify client.

The 999-track cap (spec edge case, FR-026/D12) is enforced twice on purpose:
`integrations.spotify.fetch_playlist_tracks` raises `PlaylistTooLargeError`
using Spotify's own `total` before pagination completes (T026), but this
router ALSO checks `len(fetch_result.tracks)` after any successful fetch --
a fake fetcher (T022's test, or any future one) that returns every track in
one call without raising still gets refused correctly.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from companion.api import events
from companion.api.auth import get_spotify_client
from companion.db.models import MissingTrack, PlaylistLink, SyncSession, SyncTrack
from companion.db.session import get_db
from companion.integrations import spotify
from companion.matching.engine import find_best_matches
from companion.rb.index import IndexEntry

router = APIRouter()

PLAYLIST_TRACK_CAP = 999

_STATUSES = ("matched", "review", "missing", "rejected", "unmatchable")

# T097 review finding: chunk size for _classify_tracks calls within one
# create_sync_session run -- large enough that each rapidfuzz.process.cdist
# call still batches efficiently, small enough that sync_progress events
# (R4) keep flowing throughout a long run instead of bursting at the end.
_PROGRESS_CHUNK_SIZE = 50


def _utcnow() -> datetime:
    # Naive UTC: one clock, one machine (same convention as
    # integrations.spotify._utcnow -- kept local rather than importing a
    # private cross-module helper).
    return datetime.now(UTC).replace(tzinfo=None)


class CreateSyncSessionBody(BaseModel):
    # Optional at the schema level, required by the manual check below: a
    # required Pydantic field would 422 via FastAPI's own validation-error
    # shape (`{"detail": [...]}`), breaking contracts/api.md's flat
    # `{code, message, field}` envelope every other error in this router
    # uses (T028 review finding: the body was untyped `dict` before, so
    # `playlist_url` was invisible in the generated OpenAPI schema entirely).
    playlist_url: str | None = None


@dataclass
class _FetchedTrack:
    spotify_track_id: str | None
    isrc: str | None
    artist: str
    title: str
    duration_ms: int | None
    # Defaults False so T022's fake `_FakeTrack` fixture (no such attribute)
    # stays a valid stand-in via `getattr(track, "is_local", False)` in
    # `_is_unmatchable` below -- only the production wrapper below ever sets
    # it True.
    is_local: bool = False


@dataclass
class _FetchedPlaylist:
    name: str
    snapshot_id: str
    tracks: list[_FetchedTrack]


def get_spotify_fetcher(db: Session = Depends(get_db), client=Depends(get_spotify_client)):
    """Production `(playlist_url) -> _FetchedPlaylist` -- the shape T022's
    contract test already pins. Tests override this dependency entirely with
    their own fake, so this function's body never runs under test."""

    def fetch(playlist_url: str) -> _FetchedPlaylist:
        result = spotify.fetch_playlist_tracks(db, client, playlist_url)
        tracks = [
            _FetchedTrack(
                spotify_track_id=track["spotify_track_id"],
                isrc=track["isrc"],
                artist=track["artist"],
                title=track["title"],
                duration_ms=track["duration_ms"] or None,
                is_local=track["is_local"],
            )
            for track in result.tracks
        ]
        return _FetchedPlaylist(name=result.name, snapshot_id=result.snapshot_id, tracks=tracks)

    return fetch


def _entry_to_dict(entry: IndexEntry) -> dict:
    return {
        "rb_content_id": entry.rb_content_id,
        "norm_artist": entry.norm_artist,
        "norm_title": entry.norm_title,
        "remix_tokens": entry.remix_tokens,
        "duration_ms": entry.duration_ms,
        "isrc": entry.isrc,
    }


def _is_unmatchable(track) -> bool:
    # spec.md edge case: a local file or unavailable track is reported
    # unmatchable and counted separately, never silently dropped or fuzzy-
    # matched. Two signals, either sufficient on its own (T028 review
    # finding): no usable identifiers at all, OR the fetcher's own
    # `is_local` flag -- a local file can carry real artist/title ID3 tags
    # (so "no usable identifiers" alone would miss it) but never a Spotify
    # id/ISRC to match on. `getattr` defaults False so fetchers that don't
    # know about `is_local` (T022's fake fixture) still behave correctly.
    no_identifiers = (
        not track.spotify_track_id and not track.isrc and not track.artist and not track.title
    )
    return no_identifiers or getattr(track, "is_local", False)


def _classify_tracks(
    tracks: list, collection: list[dict]
) -> list[tuple[str, float | None, str | None, list]]:
    """One batched call for every matchable track (T097 perf finding):
    `find_best_matches` scores all of them against `collection` in a
    handful of `rapidfuzz.process.cdist` calls, not one `find_best_match`
    (and its O(collection) Python loop) per track -- the difference between
    meeting SC-001's time budget at Collection scale (~40k entries) and not.
    """
    unmatchable_positions = {i for i, track in enumerate(tracks) if _is_unmatchable(track)}
    matchable_positions = [i for i in range(len(tracks)) if i not in unmatchable_positions]
    matchable_dicts = [
        {
            "artist": tracks[i].artist,
            "title": tracks[i].title,
            "duration_ms": tracks[i].duration_ms,
            "isrc": tracks[i].isrc,
        }
        for i in matchable_positions
    ]
    batch_results = find_best_matches(matchable_dicts, collection)
    results_by_position = dict(zip(matchable_positions, batch_results, strict=True))

    output = []
    for i in range(len(tracks)):
        if i in unmatchable_positions:
            output.append(("unmatchable", None, None, []))
        else:
            result, rb_content_id, candidates = results_by_position[i]
            output.append((result.status, result.score, rb_content_id, candidates))
    return output


def _get_or_create_playlist_link(db: Session, spotify_playlist_id: str, name: str) -> PlaylistLink:
    link = db.query(PlaylistLink).filter_by(spotify_playlist_id=spotify_playlist_id).first()
    if link is None:
        link = PlaylistLink(
            spotify_playlist_id=spotify_playlist_id,
            rb_playlist_id=None,
            rb_playlist_name=name,
            created_at=_utcnow(),
            last_applied_at=None,
        )
        db.add(link)
        db.flush()
    return link


def _totals_for(db: Session, session_id: int) -> dict:
    totals = dict.fromkeys(_STATUSES, 0)
    rows = db.query(SyncTrack.status).filter_by(sync_session_id=session_id).all()
    for (status,) in rows:
        totals[status] += 1
    return totals


def _session_dict(db: Session, session: SyncSession) -> dict:
    return {
        "id": session.id,
        "playlist_link_id": session.playlist_link_id,
        "spotify_snapshot_id": session.spotify_snapshot_id,
        "name": session.name,
        "status": session.status,
        "created_at": session.created_at,
        "totals": _totals_for(db, session.id),
    }


@router.post("/sync/sessions")
def create_sync_session(
    body: CreateSyncSessionBody,
    request: Request,
    db: Session = Depends(get_db),
    fetcher=Depends(get_spotify_fetcher),
):
    playlist_url = body.playlist_url
    if not playlist_url:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "missing_field",
                "message": "playlist_url is required",
                "field": "playlist_url",
            },
        )

    try:
        fetch_result = fetcher(playlist_url)
    except spotify.PlaylistTooLargeError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "playlist_too_large",
                "message": f"playlist has more than {PLAYLIST_TRACK_CAP} tracks",
            },
        ) from exc
    except spotify.InvalidPlaylistUrlError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_playlist_url", "message": str(exc), "field": "playlist_url"},
        ) from exc
    except spotify.PlaylistUnreachableError as exc:
        # T031/T032 review finding: this used to bubble up as an unhandled
        # httpx.HTTPStatusError -> a raw 500, for spec.md's own named edge
        # case ("playlist is private").
        raise HTTPException(
            status_code=404,
            detail={"code": "playlist_unreachable", "message": str(exc), "field": "playlist_url"},
        ) from exc
    except spotify.NotConnectedError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "spotify_not_connected", "message": str(exc)},
        ) from exc
    except spotify.SessionExpiredError as exc:
        # T104: "the Spotify session expires mid Sync Session: the session
        # fails with a re-connect prompt and no partial report is presented
        # as complete." Nothing has been persisted yet at this point (the
        # SyncSession row is only created after a successful fetch, below),
        # so failing here already satisfies "no partial report."
        raise HTTPException(
            status_code=409,
            detail={"code": "spotify_session_expired", "message": str(exc)},
        ) from exc

    if len(fetch_result.tracks) > PLAYLIST_TRACK_CAP:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "playlist_too_large",
                "message": f"playlist has more than {PLAYLIST_TRACK_CAP} tracks",
            },
        )

    playlist_id = spotify.parse_playlist_id(playlist_url)
    link = _get_or_create_playlist_link(db, playlist_id, fetch_result.name)

    session = SyncSession(
        playlist_link_id=link.id,
        spotify_snapshot_id=fetch_result.snapshot_id,
        name=fetch_result.name,
        status="matching",
        created_at=_utcnow(),
    )
    db.add(session)
    db.flush()

    collection = [_entry_to_dict(entry) for entry in request.app.state.collection_index.entries]
    total = len(fetch_result.tracks)
    position = 0
    # T097 review finding: `_classify_tracks` batches the expensive fuzzy
    # scoring (rapidfuzz.process.cdist) for speed, but one single call for
    # the whole playlist would run the entire match in one uninterrupted
    # burst -- for a 999-track run near the 5-minute budget, that's several
    # minutes with zero sync_progress events, then all of them firing at
    # once at the very end, defeating R4's live-progress purpose for
    # exactly the workload it exists to cover. Classifying in chunks keeps
    # each `cdist` call batched (still ~150x faster than one classify_match
    # call per Collection entry) while letting progress flow every chunk
    # instead of once at the end.
    for chunk_start in range(0, total, _PROGRESS_CHUNK_SIZE):
        chunk_tracks = fetch_result.tracks[chunk_start : chunk_start + _PROGRESS_CHUNK_SIZE]
        chunk_classifications = _classify_tracks(chunk_tracks, collection)
        for track, (status, score, rb_content_id, candidates) in zip(
            chunk_tracks, chunk_classifications, strict=True
        ):
            position += 1
            db.add(
                SyncTrack(
                    sync_session_id=session.id,
                    position=position,
                    spotify_track_id=track.spotify_track_id,
                    isrc=track.isrc,
                    artist=track.artist,
                    title=track.title,
                    duration_ms=track.duration_ms,
                    status=status,
                    rb_content_id=rb_content_id,
                    match_score=score,
                    candidates=candidates,
                    matched_at=_utcnow() if status == "matched" else None,
                )
            )
            # T030: one sync_progress event per track. This handler stays a
            # plain sync `def`, run in FastAPI's threadpool -- NOT `async
            # def` -- so the event loop stays free to flush already-queued
            # SSE bytes to a listening client while this loop is still
            # running (an `async def` version with no `await` inside this
            # loop would starve the event loop for the whole run instead,
            # T030 review finding). `events.publish` is safe to call from
            # this worker thread because it hands off via
            # `call_soon_threadsafe`, not a direct queue put.
            # Known gap (T030 review): this fires before the final
            # db.commit() below, so a listener could see done=N before
            # track N is durable. If a later chunk raised, the whole
            # request would fail and nothing would persist despite earlier
            # "progress"; `_classify_tracks` is pure local computation with
            # nothing that plausibly raises mid-chunk, so this is accepted
            # as-is rather than adding a compensating "sync_failed" event
            # type, which is outside this task's scope.
            events.publish(
                "sync_progress", {"session_id": session.id, "done": position, "total": total}
            )

    session.status = "ready"
    db.commit()

    return _session_dict(db, session)


@router.get("/sync/sessions")
def list_sync_sessions(db: Session = Depends(get_db)):
    sessions = db.query(SyncSession).order_by(SyncSession.created_at.desc()).all()
    return [_session_dict(db, session) for session in sessions]


def _track_dict(track: SyncTrack) -> dict:
    return {
        "id": track.id,
        "position": track.position,
        "spotify_track_id": track.spotify_track_id,
        "isrc": track.isrc,
        "artist": track.artist,
        "title": track.title,
        "duration_ms": track.duration_ms,
        "status": track.status,
        "rb_content_id": track.rb_content_id,
        "match_score": track.match_score,
        "candidates": track.candidates,
        "matched_at": track.matched_at,
    }


@router.get("/sync/sessions/{session_id}")
def get_sync_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(SyncSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "sync_session_not_found", "message": f"no session {session_id}"},
        )
    tracks = (
        db.query(SyncTrack).filter_by(sync_session_id=session_id).order_by(SyncTrack.position).all()
    )
    body = _session_dict(db, session)
    body["tracks"] = [_track_dict(track) for track in tracks]
    return body


def _get_review_track(db: Session, session_id: int, track_id: int) -> SyncTrack:
    """Shared lookup for accept/reject (T037): 404 for an unknown track (or
    one belonging to a different session), 409 `not_in_review` for a track
    that exists but isn't currently `review` -- accept/reject only ever
    apply from that one status (data-model.md's sync_track transition note,
    T036 build finding: `matched` never transitions away, and no other
    status lists an accept/reject transition either)."""
    track = db.get(SyncTrack, track_id)
    if track is None or track.sync_session_id != session_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "sync_track_not_found", "message": f"no track {track_id}"},
        )
    if track.status != "review":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "not_in_review",
                "message": f"track {track_id} is {track.status!r}, not review",
            },
        )
    return track


class AcceptTrackBody(BaseModel):
    # Optional at the schema level, required by the manual check below --
    # same reasoning as CreateSyncSessionBody above: a required Pydantic
    # field would 422 via FastAPI's own validation-error shape instead of
    # this router's flat {code, message, field} envelope (T037 review
    # finding: this endpoint had drifted from that established pattern).
    rb_content_id: str | None = None


@router.post("/sync/sessions/{session_id}/tracks/{track_id}/accept")
def accept_track(
    session_id: int, track_id: int, body: AcceptTrackBody, db: Session = Depends(get_db)
):
    """FR-012/FR-014: the selected candidate becomes the accepted Match,
    persisted immediately."""
    if not body.rb_content_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "missing_field",
                "message": "rb_content_id is required",
                "field": "rb_content_id",
            },
        )
    track = _get_review_track(db, session_id, track_id)
    track.status = "matched"
    track.rb_content_id = body.rb_content_id
    track.matched_at = _utcnow()
    db.commit()
    return _track_dict(track)


@router.post("/sync/sessions/{session_id}/tracks/{track_id}/reject")
def reject_track(session_id: int, track_id: int, db: Session = Depends(get_db)):
    """FR-012: reject means "wrong match" -- the Spotify Track becomes a
    Missing Track (a real row, never silently dropped), persisted
    immediately (FR-014)."""
    track = _get_review_track(db, session_id, track_id)
    track.status = "rejected"
    db.add(MissingTrack(sync_track_id=track.id, status="open"))
    db.commit()
    return _track_dict(track)
