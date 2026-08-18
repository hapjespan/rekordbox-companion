"""The Suggestions query (T083, FR-033, ADR 0008). Suggestions are computed
fresh on every call, never stored (data-model.md): the in-memory Collection
index (ADR 0012) filtered by a profile's genre tags (against Enriched
Genres) and BPM range, ranked by Play Count.

Replaces the old generator design ADR 0008 rejected: the app's only
contribution here is this ranked candidate list, never a full Structure --
the DJ designs the tree by hand.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from companion.db.models import EnrichedGenre, StructureTrack, SuggestionDismissal
from companion.rb.index import IndexEntry


@dataclass(frozen=True)
class Suggestion:
    rb_content_id: str
    artist: str
    title: str
    bpm: float | None
    play_count: int
    already_in_playlist: bool


def suggestions_for_node(
    db: Session,
    entries: list[IndexEntry],
    node_id: int,
    genre_tags: list[str],
    bpm_min: int | None,
    bpm_max: int | None,
    limit: int | None = None,
) -> tuple[list[Suggestion], int]:
    """FR-033: Collection Tracks filtered by the profile's genre tags
    (against Enriched Genres) and BPM range, ranked by Play Count
    descending. A dismissed Suggestion (FR-034) never returns for this
    node; a track already in this node's playlist is still returned,
    flagged `already_in_playlist` (contracts/api.md) rather than hidden --
    the DJ can see what's already there, only a genuinely dismissed
    Suggestion disappears.

    Returns `(suggestions, excluded_missing_bpm_count)`: a BPM filter can't
    verify a track with no BPM value belongs in the range, so it's excluded
    from the results (T078 edge case), but the count is reported separately
    rather than the track silently vanishing with no explanation.
    """
    dismissed_ids = {
        row
        for row in db.execute(
            select(SuggestionDismissal.rb_content_id).where(SuggestionDismissal.node_id == node_id)
        ).scalars()
    }
    in_playlist_ids = {
        row
        for row in db.execute(
            select(StructureTrack.rb_content_id).where(StructureTrack.node_id == node_id)
        ).scalars()
    }

    wanted_tags = {tag.lower() for tag in genre_tags}
    genres_by_track: dict[str, set[str]] = defaultdict(set)
    if wanted_tags:
        rows = db.execute(
            select(EnrichedGenre.rb_content_id, EnrichedGenre.genre).where(
                EnrichedGenre.rb_content_id.in_([e.rb_content_id for e in entries])
            )
        ).all()
        for rb_content_id, genre in rows:
            genres_by_track[rb_content_id].add(genre.lower())

    bpm_filter_active = bpm_min is not None or bpm_max is not None
    excluded_missing_bpm = 0
    candidates: list[IndexEntry] = []
    for entry in entries:
        if entry.rb_content_id in dismissed_ids:
            continue
        if wanted_tags and not (genres_by_track.get(entry.rb_content_id, set()) & wanted_tags):
            continue
        if bpm_filter_active:
            if entry.bpm is None:
                excluded_missing_bpm += 1
                continue
            if bpm_min is not None and entry.bpm < bpm_min:
                continue
            if bpm_max is not None and entry.bpm > bpm_max:
                continue
        candidates.append(entry)

    candidates.sort(key=lambda e: e.play_count, reverse=True)
    if limit is not None:
        candidates = candidates[:limit]

    suggestions = [
        Suggestion(
            rb_content_id=entry.rb_content_id,
            artist=entry.artist,
            title=entry.title,
            bpm=entry.bpm,
            play_count=entry.play_count,
            already_in_playlist=entry.rb_content_id in in_playlist_ids,
        )
        for entry in candidates
    ]
    return suggestions, excluded_missing_bpm
