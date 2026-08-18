"""GET/POST /api/missing* (US4, FR-020..FR-022, contracts/api.md).

Every route joins through `SyncTrack` for `artist`/`title`: `MissingTrack`
itself only carries the Store Link/status columns (data-model.md), the
identifying fields live on the `sync_track` row it was spawned from.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from companion.db.models import MissingTrack, SyncTrack
from companion.db.session import get_db
from companion.integrations import itunes

router = APIRouter()

_VALID_STATUSES = {"open", "acquired", "ignored"}


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
    }


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
def refresh_links(db: Session = Depends(get_db)):
    """Re-runs the iTunes lookup for every OPEN row (SC-004).

    `acquired`/`ignored` rows are left alone: a resolved or dismissed
    Missing Track has no remaining use for a fresher auto-pick.
    """
    open_rows = (
        db.query(MissingTrack, SyncTrack)
        .join(SyncTrack, MissingTrack.sync_track_id == SyncTrack.id)
        .filter(MissingTrack.status == "open")
        .all()
    )
    client = itunes.build_client()
    try:
        for missing, track in open_rows:
            result = itunes.find_store_link(client, track.artist, track.title)
            missing.itunes_track_id = result.itunes_track_id
            missing.itunes_url_auto = result.url
    finally:
        client.close()
    db.commit()
    return {"refreshed": len(open_rows)}
