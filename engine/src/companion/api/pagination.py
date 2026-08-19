"""The `{total, items: [CollectionTrack]}` page shape shared by every endpoint
that pages over `IndexEntry` rows: `GET /api/collection`,
`GET /api/playlists/{rb_playlist_id}/tracks` (both `api/collection.py`) and
`GET /api/structures/{id}/nodes/{node_id}/tracks` (`api/structures.py`).

These three deliberately return identical rows -- the frontend renders all of
them through one `TrackTable` component (T064/T087 build findings) -- so the
paging math and the row conversion live here once, as a small contract
between two routers, rather than three times with three chances to drift.
Nothing here may change shape without checking all three callers.
"""

from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from companion.db.models import EnrichedGenre
from companion.rb.index import IndexEntry

# Review finding: an unbounded `limit` lets a page of ~40k rows reach
# `_genres_by_track`'s `IN` clause, past SQLite's default bound-variable limit
# (SQLITE_MAX_VARIABLE_NUMBER, historically 999) -- an unhandled 500, not a
# documented error. This cap is well above any real page size the UI ever
# requests (TrackTable's PAGE_SIZE is 50) but far below that limit.
MAX_LIMIT = 200


def _format_from_location(location: str | None) -> str | None:
    if not location:
        return None
    return Path(location).suffix.lstrip(".").lower() or None


def _entry_to_collection_track(entry: IndexEntry, genres: list[dict]) -> dict:
    return {
        "rb_content_id": entry.rb_content_id,
        "artist": entry.artist,
        "title": entry.title,
        "duration_ms": entry.duration_ms,
        "bpm": entry.bpm,
        "play_count": entry.play_count,
        "genres": genres,
        "format": _format_from_location(entry.location),
        # Rekordbox's own key and label, verbatim and independently nullable:
        # `musical_key` (not `key`, which reads as an identifier in a row
        # object) carries Camelot notation like "8m" exactly as the DJ's
        # Rekordbox shows it, never normalised or converted.
        "musical_key": entry.musical_key,
        "label": entry.label,
    }


def _genres_by_track(db: Session, entries: list[IndexEntry]) -> dict[str, list[dict]]:
    """One batched query for the whole page, not one per track (US5's
    100ms/page budget, contracts/api.md)."""
    ids = [e.rb_content_id for e in entries]
    rows = db.execute(select(EnrichedGenre).where(EnrichedGenre.rb_content_id.in_(ids))).scalars()
    genres_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        genres_by_id[row.rb_content_id].append({"genre": row.genre, "source": row.source})
    return genres_by_id


def page_body(db: Session, entries: list[IndexEntry], limit: int, offset: int) -> dict:
    """`{total, items: [CollectionTrack]}` for one page of `entries`.

    Shared by `GET /api/collection`, `GET /api/playlists/{id}/tracks` and
    `GET /api/structures/{id}/nodes/{node_id}/tracks` so the three can never
    drift into different row shapes -- the frontend reuses one table for all
    of them."""
    total = len(entries)
    page = entries[offset : offset + limit]
    genres_by_id = _genres_by_track(db, page)
    return {
        "total": total,
        "items": [
            _entry_to_collection_track(e, genres_by_id.get(e.rb_content_id, [])) for e in page
        ],
    }
