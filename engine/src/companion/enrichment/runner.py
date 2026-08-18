"""Incremental, resumable enrichment queue (T073, ADR 0013, data-model.md
`enrichment_state`). 30.000+ tracks against a 1 req/s source is a
multi-hour job that will be interrupted, so a run only ever advances a
per-track queue by `budget` tracks and can always be called again later
without redoing `done`/`none_found` work.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from companion.db.models import EnrichmentState
from companion.enrichment.source import GenreSource, apply_genres, has_manual_override

_PENDING_STATUSES = ("pending", "failed")

# A batch where every track fails (e.g. the source is unreachable -- no
# network, DNS failure) has zero backoff between individual httpx errors, so
# without a circuit breaker `run_until_drained` would spin an unthrottled
# tight loop forever instead of giving up and leaving the rows `failed`
# (still retryable by a later call, ADR 0013's resumability).
MAX_CONSECUTIVE_FAILED_BATCHES = 3


def _utcnow() -> datetime:
    # Naive UTC: one clock, one machine (same convention as
    # integrations.spotify._utcnow -- kept local rather than importing a
    # private cross-module helper).
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class EnrichmentProgress:
    processed: int
    done: int
    none_found: int
    failed: int
    remaining: int


def enqueue_pending(db: Session, rb_content_ids: list[str]) -> int:
    """Seed queue state for tracks that don't have one yet. A track with a
    manual override is never enqueued (FR-028): it needs no automated run.
    Returns the number of tracks freshly enqueued (contracts/api.md's
    `POST /api/enrichment/run` `{queued}` response)."""
    queued = 0
    for rb_content_id in rb_content_ids:
        if has_manual_override(db, rb_content_id):
            continue
        if db.get(EnrichmentState, rb_content_id) is None:
            db.add(EnrichmentState(rb_content_id=rb_content_id, status="pending"))
            queued += 1
    return queued


def run(
    db: Session, source: GenreSource, artists_by_id: dict[str, str], budget: int
) -> EnrichmentProgress:
    """Process up to `budget` tracks whose queue state is pending or failed
    -- never `done` or `none_found` (incremental+resumable). `artists_by_id`
    is the caller's collection lookup (`rb_content_id` -> artist name)."""
    states = (
        db.execute(
            select(EnrichmentState)
            .where(EnrichmentState.status.in_(_PENDING_STATUSES))
            .limit(budget)
        )
        .scalars()
        .all()
    )

    done = none_found = failed = 0
    for state in states:
        state.attempted_at = _utcnow()
        if has_manual_override(db, state.rb_content_id):
            # Gained an override after being enqueued: already fully
            # resolved, no need to spend a rate-limited call on it (FR-028).
            state.status = "done"
            done += 1
            continue

        artist = artists_by_id.get(state.rb_content_id)
        try:
            genres = source.genres_for(artist) if artist else []
        except Exception:
            # The whole reason `failed` exists (data-model.md): an external
            # source call can fail for any reason (network, rate limit,
            # malformed response), and every such failure is retryable, not
            # a reason to abort the rest of the batch.
            state.status = "failed"
            failed += 1
            continue

        state.last_source = source.name
        if genres:
            apply_genres(db, state.rb_content_id, genres, source=source.name)
            state.status = "done"
            done += 1
        else:
            state.status = "none_found"
            none_found += 1

    # autoflush=False project-wide (db/session.py): the status changes above
    # are still only in-memory, so the remaining-count query below needs an
    # explicit flush to see them.
    db.flush()
    remaining = db.scalar(
        select(func.count())
        .select_from(EnrichmentState)
        .where(EnrichmentState.status.in_(_PENDING_STATUSES))
    )
    return EnrichmentProgress(
        processed=len(states), done=done, none_found=none_found, failed=failed, remaining=remaining
    )


def run_until_drained(
    db: Session,
    source: GenreSource,
    artists_by_id: dict[str, str],
    budget: int,
    on_progress=None,
) -> None:
    """Call `run()` in a loop, chunk by chunk, until the queue is empty --
    or until `MAX_CONSECUTIVE_FAILED_BATCHES` consecutive chunks make zero
    real progress (every track in them failed), a circuit breaker against
    a persistently unreachable source. `on_progress`, if given, is called
    with each chunk's `EnrichmentProgress` (e.g. to publish SSE events)."""
    consecutive_failed_batches = 0
    while True:
        progress = run(db, source, artists_by_id, budget=budget)
        db.commit()
        if progress.processed == 0:
            break
        if on_progress is not None:
            on_progress(progress)
        if progress.done == 0 and progress.none_found == 0:
            consecutive_failed_batches += 1
            if consecutive_failed_batches >= MAX_CONSECUTIVE_FAILED_BATCHES:
                break
        else:
            consecutive_failed_batches = 0
