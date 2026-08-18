"""Enrichment endpoints (contracts/api.md "Enrichment (US6)"): kick off a
run, report status, list the manual work list, and set a manual override.

`PUT /api/collection/{rb_content_id}/genres` lives here, not in
`api/collection.py`, despite its path: it's a manual-override write, the
same feature area as the rest of this module, not a collection browse/search
concern (`api/collection.py` stays read-only over the in-memory index).

`POST /api/enrichment/run` returns as soon as the queue is seeded; the run
itself continues via `BackgroundTasks` (Starlette runs a sync callable
through its threadpool, same as `create_sync_session`'s plain `def`
pattern, `api/events.py`) so a run that genuinely takes hours (30.000+
tracks against MusicBrainz's 1 req/s limit, ADR 0013) never blocks the HTTP
response or the event loop. Progress streams over the existing
`enrichment_progress` SSE event (R4); the run is resumable by construction
(`enrichment_state`, ADR 0013) -- restarting the server and calling `/run`
again simply continues, no special "resume" endpoint needed.

The background run is its own dependency (`get_background_runner`), not the
genre source: it needs its own db session and httpx client, independent of
this request's -- reusing the request-scoped session would pin a pooled
connection open for however long the run takes (potentially hours), so a
fresh one is opened inside the real implementation instead.

`runner.run_until_drained` (not a bare loop here) is what actually processes
the queue: a source that is persistently unreachable (no network, DNS
failure) must not spin this background task in an unthrottled infinite loop
with zero backoff -- see its own docstring for the circuit breaker.
"""

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from companion.api import events
from companion.db.models import EnrichmentState
from companion.db.session import SessionLocal, get_db
from companion.enrichment import runner, source
from companion.enrichment.musicbrainz import MusicBrainzGenreSource

router = APIRouter()

_RUN_CHUNK_SIZE = 25  # SSE progress granularity, not a hard stop -- runs to completion


def _publish_progress(progress) -> None:
    events.publish(
        "enrichment_progress",
        {
            "done": progress.done,
            "none_found": progress.none_found,
            "failed": progress.failed,
            "remaining": progress.remaining,
        },
    )


def _run_to_completion(artists_by_id: dict[str, str]) -> None:
    db = SessionLocal()
    try:
        with httpx.Client(timeout=15.0) as client:
            genre_source = MusicBrainzGenreSource(client)
            runner.run_until_drained(
                db,
                genre_source,
                artists_by_id,
                budget=_RUN_CHUNK_SIZE,
                on_progress=_publish_progress,
            )
    finally:
        db.close()


def get_background_runner():
    """FastAPI dependency yielding the callable `BackgroundTasks` invokes to
    process the queue. Tests override this with a version that runs against
    the test's own in-memory db and a fake genre source, instead of opening
    a real MusicBrainzGenreSource and a fresh production db session."""
    return _run_to_completion


def _artists_by_id(request: Request) -> dict[str, str]:
    return {
        e.rb_content_id: e.artist for e in request.app.state.collection_index.entries if e.artist
    }


@router.post("/enrichment/run")
def run_enrichment(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    background_runner=Depends(get_background_runner),
):
    # Known gap (review finding): calling this twice in quick succession
    # starts two concurrent background runs racing on the same SQLite file
    # (lock contention, no guard here). Acceptable for now -- there is no UI
    # trigger yet (T077) -- but T077's "start" control should disable itself
    # while a run is in progress rather than this endpoint gaining a lock.
    artists_by_id = _artists_by_id(request)
    queued = runner.enqueue_pending(db, list(artists_by_id))
    db.commit()
    background_tasks.add_task(background_runner, artists_by_id)
    return {"queued": queued}


@router.get("/enrichment/status")
def enrichment_status(db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(EnrichmentState.status, func.count()).group_by(EnrichmentState.status)
        ).all()
    )
    pending = counts.get("pending", 0)
    done = counts.get("done", 0)
    none_found = counts.get("none_found", 0)
    failed = counts.get("failed", 0)
    total = pending + done + none_found + failed
    coverage_pct = round(100 * done / total, 1) if total else 0.0
    return {
        "pending": pending,
        "done": done,
        "none_found": none_found,
        "failed": failed,
        "coverage_pct": coverage_pct,
    }


@router.get("/enrichment/unenriched")
def unenriched(request: Request, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    ids = (
        db.execute(
            select(EnrichmentState.rb_content_id).where(EnrichmentState.status == "none_found")
        )
        .scalars()
        .all()
    )
    entries_by_id = {e.rb_content_id: e for e in request.app.state.collection_index.entries}
    items = [entries_by_id[i] for i in ids if i in entries_by_id]
    page = items[offset : offset + limit]
    return {
        "total": len(items),
        "items": [
            {"rb_content_id": e.rb_content_id, "artist": e.artist, "title": e.title} for e in page
        ],
    }


class GenresBody(BaseModel):
    # No default: contracts/api.md's `{genres: [text]}` is a required field.
    # An empty list is a legitimate value (clearing an override); an
    # entirely missing key should 422, not silently wipe every genre.
    genres: list[str]


@router.put("/collection/{rb_content_id}/genres")
def put_genres(
    rb_content_id: str, body: GenresBody, request: Request, db: Session = Depends(get_db)
):
    index = request.app.state.collection_index
    if not any(e.rb_content_id == rb_content_id for e in index.entries):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "track_not_found",
                "message": f"no Collection Track with id {rb_content_id!r}",
            },
        )
    source.set_manual_override(db, rb_content_id, body.genres)
    db.commit()
    return {
        "rb_content_id": rb_content_id,
        "genres": [{"genre": g, "source": "manual"} for g in body.genres],
    }
