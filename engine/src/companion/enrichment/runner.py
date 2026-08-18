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


def enqueue_pending(db: Session, rb_content_ids: list[str]) -> None:
    """Seed queue state for tracks that don't have one yet. A track with a
    manual override is never enqueued (FR-028): it needs no automated run."""
    for rb_content_id in rb_content_ids:
        if has_manual_override(db, rb_content_id):
            continue
        if db.get(EnrichmentState, rb_content_id) is None:
            db.add(EnrichmentState(rb_content_id=rb_content_id, status="pending"))


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
