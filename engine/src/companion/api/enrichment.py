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

`app.state.enrichment_running` guards against a double run (review finding):
a page reload mid-run, a second tab, or a stale enabled button all used to
be able to fire a second `POST /run` while the first was still going,
racing two background runs on the same SQLite file (`apply_genres` is
delete-then-insert with no unique constraint, so a race can leave duplicate
`enriched_genre` rows). The flag is set synchronously before the background
task is scheduled and always cleared in `_run_and_release`'s `finally`, so
it can never wedge `/run` shut after a run ends -- however it ends (drained,
circuit-broken, or raising). `GET /status` exposes the same flag so the
frontend derives its disabled state from server truth on load, not only
from local `useState`.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from companion import security
from companion.api import events
from companion.db.models import EnrichedGenre, EnrichmentState
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
        with security.build_allowlisted_client(timeout=15.0) as client:
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


def _is_running(app) -> bool:
    # `app.state` is a plain Starlette `State`; nothing pre-initialises
    # this attribute (a fresh app -- including every test's `create_app()`
    # -- has never had a run), so `getattr` with a default stands in for
    # that initial "no run yet" state.
    return getattr(app.state, "enrichment_running", False)


def _run_and_release(app, background_runner, artists_by_id: dict[str, str]) -> None:
    """Runs the background job, then always clears the in-progress flag --
    on a normal drain, a circuit-broken early exit, or an exception -- so a
    stuck flag can never permanently lock `POST /run` shut."""
    try:
        background_runner(artists_by_id)
    finally:
        app.state.enrichment_running = False


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
    # Server-side double-run guard (review finding): a page reload mid-run,
    # a second tab, or a run started before this page loaded all used to
    # present an enabled button with nothing behind it stopping a second
    # concurrent run. Refusing here, rather than only in the UI, is the
    # actual guard -- the UI disabled-state is just a courtesy derived from
    # GET /status's own "running" field.
    if _is_running(request.app):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "enrichment_already_running",
                "message": "an enrichment run is already in progress",
            },
        )
    artists_by_id = _artists_by_id(request)
    queued = runner.enqueue_pending(db, list(artists_by_id))
    db.commit()
    request.app.state.enrichment_running = True
    background_tasks.add_task(_run_and_release, request.app, background_runner, artists_by_id)
    return {"queued": queued}


@router.get("/enrichment/status")
def enrichment_status(request: Request, db: Session = Depends(get_db)):
    counts = dict(
        db.execute(
            select(EnrichmentState.status, func.count()).group_by(EnrichmentState.status)
        ).all()
    )
    pending = counts.get("pending", 0)
    done = counts.get("done", 0)
    none_found = counts.get("none_found", 0)
    failed = counts.get("failed", 0)

    # SC-008 is "% of Collection Tracks with at least one Enriched Genre" --
    # not "% of tracks that ever got an enrichment_state row". A track with
    # a manual override set before any enqueue never gets a state row
    # (enqueue_pending skips it) and an artist-less track never gets
    # enqueued at all (_artists_by_id filters blanks), so both used to fall
    # out of the old state-row-only denominator, silently inflating the
    # number the owner judges SC-008 by. The denominator is the full
    # collection index; the numerator counts distinct `enriched_genre`
    # tracks (manual counts too -- FR-028's override IS the DJ's Enriched
    # Genre for that track).
    collection_size = len(request.app.state.collection_index.entries)
    enriched_tracks = db.scalar(select(func.count(func.distinct(EnrichedGenre.rb_content_id))))
    coverage_pct = round(100 * enriched_tracks / collection_size, 1) if collection_size else 0.0
    return {
        "pending": pending,
        "done": done,
        "none_found": none_found,
        "failed": failed,
        "coverage_pct": coverage_pct,
        "running": _is_running(request.app),
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
