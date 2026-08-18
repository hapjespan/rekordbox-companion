"""POST /api/collection/reindex: rebuilds the in-memory index (R6/ADR 0012).
GET /api/collection: search/sort/paginate over it (T062, FR-024, US5).
"""

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from companion.matching.normalize import normalize
from companion.rb.index import IndexEntry
from companion.rb.reader import open_database, read_collection_snapshot, read_playlist_tree

router = APIRouter()


def get_database():
    """FastAPI dependency wrapping `open_database` so tests can override it
    with a fake database (rather than needing a real master.db) and so its
    FileNotFoundError becomes the documented error shape (contracts/api.md
    conventions: `{code, message, field?}`), not an unhandled 500."""
    try:
        return open_database()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "rekordbox_not_found", "message": str(exc)},
        ) from exc


@router.post("/collection/reindex")
def reindex(request: Request, db=Depends(get_database)):
    started = time.monotonic()
    tracks = read_collection_snapshot(db)
    indexed_count = request.app.state.collection_index.rebuild(tracks)
    took_ms = round((time.monotonic() - started) * 1000)
    return {"indexed_count": indexed_count, "took_ms": took_ms}


# FR-024: search over artist/title, sort over artist/title/BPM/Play Count.
# `sort`'s "-field" prefix for descending is this task's own design choice
# (contracts/api.md documents the `?sort=` param but not its direction
# syntax) -- a plain, well-known REST convention rather than a second
# query param.
_SORT_FIELDS = {
    "artist": lambda e: e.norm_artist,
    "title": lambda e: e.norm_title,
    "bpm": lambda e: e.bpm,
    "play_count": lambda e: e.play_count,
}


def _sort_entries(entries: list[IndexEntry], sort_param: str) -> list[IndexEntry]:
    descending = sort_param.startswith("-")
    field = sort_param[1:] if descending else sort_param
    key_fn = _SORT_FIELDS.get(field)
    if key_fn is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_sort",
                "message": f"sort must be one of {sorted(_SORT_FIELDS)}, "
                "optionally prefixed with '-' for descending",
                "field": "sort",
            },
        )
    if field == "bpm":
        # A missing BPM always sorts last, regardless of direction -- an
        # entry with no BPM isn't "the lowest BPM", it's unranked.
        with_bpm = sorted((e for e in entries if e.bpm is not None), key=key_fn, reverse=descending)
        without_bpm = [e for e in entries if e.bpm is None]
        return with_bpm + without_bpm
    return sorted(entries, key=key_fn, reverse=descending)


def _format_from_location(location: str | None) -> str | None:
    if not location:
        return None
    return Path(location).suffix.lstrip(".").lower() or None


def _entry_to_collection_track(entry: IndexEntry) -> dict:
    return {
        "rb_content_id": entry.rb_content_id,
        "artist": entry.artist,
        "title": entry.title,
        "duration_ms": entry.duration_ms,
        "bpm": entry.bpm,
        "play_count": entry.play_count,
        # US6 (T067+) wires real enriched-genre data in here; genre
        # enrichment doesn't exist yet, so every track reports none, the
        # same stub-and-replace forward-reference T013 already established
        # for norm_artist/norm_title before T024's pipeline landed.
        "genres": [],
        "format": _format_from_location(entry.location),
    }


@router.get("/collection")
def get_collection(
    request: Request,
    query: str | None = None,
    sort: str = "artist",
    limit: int = 50,
    offset: int = 0,
):
    entries = request.app.state.collection_index.entries

    if query:
        normalized_query = normalize(query)
        entries = [
            e
            for e in entries
            if normalized_query in e.norm_artist or normalized_query in e.norm_title
        ]

    entries = _sort_entries(entries, sort)

    total = len(entries)
    page = entries[offset : offset + limit]
    return {"total": total, "items": [_entry_to_collection_track(e) for e in page]}


@router.get("/playlists")
def get_playlists(db=Depends(get_database)):
    return read_playlist_tree(db)
