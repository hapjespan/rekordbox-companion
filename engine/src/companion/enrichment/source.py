"""GenreSource seam (ADR 0013): a source-agnostic interface for genre
enrichment, plus the manual-override precedence rule (FR-028) shared by
every source and by the runner (T073).

`has_manual_override`/`apply_genres` live here rather than in the runner so
the FR-028 guarantee -- a manual genre override is never touched, in any
way, by an enrichment run -- is enforced in exactly one place, regardless of
which adapter or how many runs try to write to a track afterwards.
"""

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from companion.db.models import EnrichedGenre, EnrichmentState


def _utcnow() -> datetime:
    # Naive UTC: one clock, one machine (same convention as
    # integrations.spotify._utcnow -- kept local rather than importing a
    # private cross-module helper).
    return datetime.now(UTC).replace(tzinfo=None)


class GenreSource(Protocol):
    """One external genre data source. `name` identifies it in
    `enriched_genre.source`/`enrichment_state.last_source`."""

    name: str

    def genres_for(self, artist: str) -> list[str]:
        """Genre tags for an artist, best first. `[]` means "no match" or
        "no qualifying tags" -- both are `enrichment_state.status ==
        "none_found"` to the runner, never an error."""
        ...


def has_manual_override(db: Session, rb_content_id: str) -> bool:
    """FR-028: whether a manual genre override already exists for this
    track. The runner must skip any track this returns True for."""
    return (
        db.execute(
            select(EnrichedGenre.id).where(
                EnrichedGenre.rb_content_id == rb_content_id,
                EnrichedGenre.source == "manual",
            )
        ).first()
        is not None
    )


def set_manual_override(db: Session, rb_content_id: str, genres: list[str]) -> None:
    """A human setting the override IS the authoritative action (FR-028):
    unlike `apply_genres`, this always replaces whatever rows exist --
    manual or automated -- rather than refusing because a manual row
    already exists.

    Also resolves this track's `enrichment_state` (if it has one), so a
    manually-fixed track stops feeding the "manual work list" (FR-029) it
    might have been on -- `GET /api/enrichment/unenriched` only reads
    `enrichment_state`, never `enriched_genre` directly. Clearing an
    override (an empty `genres` list) does the reverse: the track has no
    genres again, so it goes back to `pending`, eligible for a future
    automated run.
    """
    db.query(EnrichedGenre).filter_by(rb_content_id=rb_content_id).delete()
    now = _utcnow()
    for genre in genres:
        db.add(
            EnrichedGenre(rb_content_id=rb_content_id, genre=genre, source="manual", updated_at=now)
        )
    state = db.get(EnrichmentState, rb_content_id)
    if state is not None:
        state.status = "done" if genres else "pending"
        state.attempted_at = now
        state.last_source = "manual" if genres else None


def apply_genres(db: Session, rb_content_id: str, genres: list[str], source: str) -> None:
    """Replace a track's automated genre rows from `source` with `genres`.
    No-ops entirely if a manual override exists (FR-028) -- an enriched
    track never gets automated rows alongside a manual one, or after it."""
    if has_manual_override(db, rb_content_id):
        return
    db.query(EnrichedGenre).filter_by(rb_content_id=rb_content_id).delete()
    now = _utcnow()
    for genre in genres:
        db.add(
            EnrichedGenre(rb_content_id=rb_content_id, genre=genre, source=source, updated_at=now)
        )
