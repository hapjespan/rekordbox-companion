"""GET/POST /api/missing* (US4, FR-020..FR-022, FR-041, contracts/api.md).

Every route joins through `SyncTrack` for `artist`/`title`: `MissingTrack`
itself only carries the Store Link/status columns (data-model.md), the
identifying fields live on the `sync_track` row it was spawned from.
"""

import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from companion.db.models import MissingTrack, SyncTrack
from companion.db.session import get_db
from companion.integrations import itunes

router = APIRouter()

_VALID_STATUSES = {"open", "acquired", "ignored"}

# ADR 0011: the free-tier iTunes Search API allows roughly 20 requests per
# minute. One refresh-links call processes at most this many rows, so a
# single call's worst-case wall-clock time (~batch size *
# itunes.REQUEST_INTERVAL_SECONDS) stays bounded; a larger queue is finished
# incrementally over repeat clicks (same "run within free-tier limits"
# discipline as `enrichment/runner.py`'s budgeted `run()`), not one bulk pass
# that inevitably outruns the limit.
REFRESH_BATCH_SIZE = 20


def get_itunes_client():
    """FastAPI dependency yielding a request-scoped httpx client (same
    seam-isolation pattern as `api.auth.get_spotify_client`): tests override
    this with an `httpx.MockTransport` client instead of hitting the real
    iTunes Search API."""
    client = itunes.build_client()
    try:
        yield client
    finally:
        client.close()


def get_store_link_lookup(client: httpx.Client = Depends(get_itunes_client)):
    """Production `(artist, title) -> itunes.StoreLinkResult`, raising
    `itunes.StoreLookupError` on failure. Its own dependency so tests can
    override it with a fake that fails for chosen rows, to exercise
    `refresh_links`' partial-progress/skip handling without a real network
    dependency (review finding's required regression test)."""

    def lookup(artist: str, title: str) -> itunes.StoreLinkResult:
        return itunes.find_store_link(client, artist, title)

    return lookup


def get_itunes_sleep():
    """FastAPI dependency for the throttle between iTunes calls (ADR 0011).
    Tests override this with a no-op so they don't pay
    `REQUEST_INTERVAL_SECONDS * batch size` of real wall-clock time -- the
    same reasoning as `enrichment/musicbrainz.py`'s injectable `sleep`
    constructor parameter."""
    return time.sleep


def _missing_dict(missing: MissingTrack, track: SyncTrack) -> dict:
    effective_url = missing.itunes_url_chosen or missing.itunes_url_auto
    return {
        "id": missing.id,
        "artist": track.artist,
        "title": track.title,
        "status": missing.status,
        "itunes_url_auto": missing.itunes_url_auto,
        "itunes_url_chosen": missing.itunes_url_chosen,
        "effective_url": effective_url,
        "no_link_found": effective_url is None,
        # ADR 0022: every Missing Track originates in a Spotify playlist
        # track, so this rides along on the same `sync_track` join as
        # artist/title above -- never a second lookup. Nullable because
        # `SyncTrack.spotify_track_id` itself is (NULL for a local/
        # unavailable Spotify track); the buy queue falls back to the store
        # preview when it is absent.
        "spotify_track_id": track.spotify_track_id,
        # FR-041: the preview and the price of the automatically picked
        # store page, each independently nullable -- a track can have no
        # preview, and a streaming-only or album-only track has no
        # single-track price. The UI renders "no preview available" and
        # simply no price rather than a dead control or a fake amount.
        "itunes_preview_url": missing.itunes_preview_url,
        "itunes_price": missing.itunes_price,
        "itunes_currency": missing.itunes_currency,
    }


def _store_store_link(missing: MissingTrack, result: itunes.StoreLinkResult) -> None:
    """Persist one resolved lookup onto the row.

    The single place a `StoreLinkResult` becomes columns, so the link and
    FR-041's preview/price can never drift apart: every field is written
    from the same result, including when that result is empty (a re-lookup
    that now finds nothing must clear a stale preview and price, not leave
    yesterday's price beside today's absent link).
    """
    missing.itunes_track_id = result.itunes_track_id
    missing.itunes_url_auto = result.url
    missing.itunes_preview_url = result.preview_url
    missing.itunes_price = result.price
    missing.itunes_currency = result.currency


@router.get("/missing")
def list_missing(status: str | None = None, db: Session = Depends(get_db)):
    if status is not None and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_status",
                "message": f"status must be one of {sorted(_VALID_STATUSES)}",
                "field": "status",
            },
        )
    query = db.query(MissingTrack, SyncTrack).join(
        SyncTrack, MissingTrack.sync_track_id == SyncTrack.id
    )
    if status is not None:
        query = query.filter(MissingTrack.status == status)
    return [_missing_dict(missing, track) for missing, track in query.all()]


def _get_missing_or_404(db: Session, missing_id: int) -> MissingTrack:
    missing = db.get(MissingTrack, missing_id)
    if missing is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "missing_track_not_found", "message": f"no missing track {missing_id}"},
        )
    return missing


class MissingStatusBody(BaseModel):
    status: str | None = None


@router.post("/missing/{missing_id}/status")
def set_missing_status(missing_id: int, body: MissingStatusBody, db: Session = Depends(get_db)):
    """FR-021: open/acquired/ignored, persistently."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_status",
                "message": f"status must be one of {sorted(_VALID_STATUSES)}",
                "field": "status",
            },
        )
    missing = _get_missing_or_404(db, missing_id)
    missing.status = body.status
    db.commit()
    track = db.get(SyncTrack, missing.sync_track_id)
    return _missing_dict(missing, track)


class MissingLinkBody(BaseModel):
    itunes_url: str | None = None


@router.post("/missing/{missing_id}/link")
def set_missing_link(missing_id: int, body: MissingLinkBody, db: Session = Depends(get_db)):
    """FR-022: a manual override, keeping the automatic pick alongside it."""
    if not body.itunes_url:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "missing_field",
                "message": "itunes_url is required",
                "field": "itunes_url",
            },
        )
    missing = _get_missing_or_404(db, missing_id)
    missing.itunes_url_chosen = body.itunes_url
    db.commit()
    track = db.get(SyncTrack, missing.sync_track_id)
    return _missing_dict(missing, track)


@router.post("/missing/refresh-links")
def refresh_links(
    db: Session = Depends(get_db),
    lookup=Depends(get_store_link_lookup),
    sleep=Depends(get_itunes_sleep),
):
    """Re-runs the iTunes lookup for up to `REFRESH_BATCH_SIZE` OPEN rows
    (SC-004), throttled to ADR 0011's free-tier rate limit.

    This is also what fills FR-041's preview and price: they come from the
    same response as the link (`_store_store_link`), so a refresh is the one
    call that backfills rows created before those columns existed -- no
    extra request, no extra outbound host.

    `acquired`/`ignored` rows are left alone: a resolved or dismissed
    Missing Track has no remaining use for a fresher auto-pick.

    Review finding (MAJOR): this used to fire one unthrottled request per
    open row and let `response.raise_for_status()` bubble straight out of
    the loop. A queue large enough to hit the ~20/min limit mid-loop turned
    into an unhandled `httpx.HTTPStatusError` -> a raw 500 -- and because
    the single `db.commit()` sat AFTER the loop, `get_db`'s finally-block
    `db.close()` then discarded every link already fetched in that same
    call, not just the failing row's. Each row now commits immediately on
    success, so partial progress survives a later row's failure, and a
    failure is caught per row (`itunes.StoreLookupError`) and counted as
    `skipped` instead of propagating.
    """
    open_rows = (
        db.query(MissingTrack, SyncTrack)
        .join(SyncTrack, MissingTrack.sync_track_id == SyncTrack.id)
        .filter(MissingTrack.status == "open")
        .order_by(MissingTrack.id)
        .limit(REFRESH_BATCH_SIZE)
        .all()
    )
    refreshed = 0
    skipped = 0
    for index, (missing, track) in enumerate(open_rows):
        if index > 0:
            sleep(itunes.REQUEST_INTERVAL_SECONDS)
        try:
            result = lookup(track.artist, track.title)
        except itunes.StoreLookupError:
            skipped += 1
            continue
        _store_store_link(missing, result)
        db.commit()
        refreshed += 1

    remaining = (
        db.query(MissingTrack).filter(MissingTrack.status == "open").count() - refreshed - skipped
    )
    return {"refreshed": refreshed, "skipped": skipped, "remaining": max(remaining, 0)}
