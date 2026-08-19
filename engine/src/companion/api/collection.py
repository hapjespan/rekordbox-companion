"""POST /api/collection/reindex: rebuilds the in-memory index (R6/ADR 0012).
GET /api/collection: search/sort/paginate over it (T062, FR-024, US5), plus
an `?ids=` filter for resolving a bounded set of known rb_content_ids without
a paged sweep (e.g. the Structure builder's phase rows, the review queue's
candidate cards).
GET /api/playlists, GET /api/playlists/{rb_playlist_id}/tracks: the Rekordbox
playlist tree, and one playlist's tracks in the same page shape as
GET /api/collection.
"""

import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from companion.db.models import EnrichedGenre
from companion.db.session import get_db
from companion.matching.normalize import normalize
from companion.rb.index import IndexEntry
from companion.rb.reader import (
    open_database,
    read_collection_snapshot,
    read_playlist_track_refs,
    read_playlist_tree,
)

router = APIRouter()

# Review finding: an unbounded `limit` lets a page of ~40k rows reach
# `_genres_by_track`'s `IN` clause, past SQLite's default bound-variable limit
# (SQLITE_MAX_VARIABLE_NUMBER, historically 999) -- an unhandled 500, not a
# documented error. This cap is well above any real page size the UI ever
# requests (TrackTable's PAGE_SIZE is 50) but far below that limit.
_MAX_LIMIT = 200

# Same defect, same fix, for `?ids=`: a caller resolving a batch of known
# rb_content_ids (the Structure builder's phase rows, the review queue's
# candidate cards) must not be able to hand this endpoint an unbounded id
# list that then feeds `_genres_by_track`'s `IN` clause past SQLite's
# bound-variable limit. Kept equal to `_MAX_LIMIT`: neither caller needs more
# than a page's worth of ids resolved in one call, and it lets a caller
# always fetch every id it sent back in a single page by setting `limit` to
# match.
_MAX_IDS = _MAX_LIMIT


def get_database():
    """FastAPI dependency wrapping `open_database` so tests can override it
    with a fake database (rather than needing a real master.db) and so its
    FileNotFoundError becomes the documented error shape (contracts/api.md
    conventions: `{code, message, field?}`), not an unhandled 500.

    A `yield` dependency (not a plain `return`): `Rekordbox6Database` opens a
    SQLCipher connection that must be closed at the end of the request, or
    every reindex/playlists call leaks one (review finding).
    """
    try:
        db = open_database()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "rekordbox_not_found", "message": str(exc)},
        ) from exc
    try:
        yield db
    finally:
        db.close()


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


def _invalid_sort(allowed: set[str]) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "invalid_sort",
            "message": f"sort must be one of {sorted(allowed)}, "
            "optionally prefixed with '-' for descending",
            "field": "sort",
        },
    )


def _sort_entries(entries: list[IndexEntry], sort_param: str) -> list[IndexEntry]:
    descending = sort_param.startswith("-")
    field = sort_param[1:] if descending else sort_param
    key_fn = _SORT_FIELDS.get(field)
    if key_fn is None:
        raise _invalid_sort(set(_SORT_FIELDS))
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


def _too_many_ids(count: int) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "too_many_ids",
            "message": f"ids accepts at most {_MAX_IDS} values per request, got {count}",
            "field": "ids",
        },
    )


def _filter_by_ids(entries: list[IndexEntry], ids: list[str] | None) -> list[IndexEntry]:
    """`ids` is a filter, applied before `query`/`sort`/`limit`/`offset` --
    the same position `query` already occupies in this pipeline. An id that
    doesn't exist in the index is simply absent from the result, never an
    error: the caller compares the ids it sent against `items` to see which
    ones came back."""
    if not ids:
        return entries
    wanted = set(ids)
    return [e for e in entries if e.rb_content_id in wanted]


def _filter_by_query(entries: list[IndexEntry], query: str | None) -> list[IndexEntry]:
    if not query:
        return entries
    normalized_query = normalize(query)
    return [
        e for e in entries if normalized_query in e.norm_artist or normalized_query in e.norm_title
    ]


def _page_body(db: Session, entries: list[IndexEntry], limit: int, offset: int) -> dict:
    """`{total, items: [CollectionTrack]}` for one page of `entries`.

    Shared by `GET /api/collection` and `GET /api/playlists/{id}/tracks` so the
    two can never drift into two different row shapes -- the frontend reuses
    one table for both."""
    total = len(entries)
    page = entries[offset : offset + limit]
    genres_by_id = _genres_by_track(db, page)
    return {
        "total": total,
        "items": [
            _entry_to_collection_track(e, genres_by_id.get(e.rb_content_id, [])) for e in page
        ],
    }


@router.get("/collection")
def get_collection(
    request: Request,
    query: str | None = None,
    ids: list[str] | None = Query(default=None),
    sort: str = "artist",
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if ids is not None and len(ids) > _MAX_IDS:
        raise _too_many_ids(len(ids))
    entries = _filter_by_ids(request.app.state.collection_index.entries, ids)
    entries = _filter_by_query(entries, query)
    entries = _sort_entries(entries, sort)
    return _page_body(db, entries, limit, offset)


@router.get("/playlists")
def get_playlists(db=Depends(get_database)):
    return read_playlist_tree(db)


# The Collection view filtered to one Rekordbox playlist. `position` is this
# endpoint's own extra sort field and its default: the order the DJ built
# inside Rekordbox, which no field of the index can reconstruct.
_PLAYLIST_SORT_FIELDS = {"position", *_SORT_FIELDS}


def _sort_playlist_entries(entries: list[IndexEntry], sort_param: str) -> list[IndexEntry]:
    descending = sort_param.startswith("-")
    field = sort_param[1:] if descending else sort_param
    if field not in _PLAYLIST_SORT_FIELDS:
        raise _invalid_sort(_PLAYLIST_SORT_FIELDS)
    if field == "position":
        # `entries` already arrives in playlist order (rb/reader.py sorts by
        # the membership row's TrackNo), so this only has to honour direction.
        return list(reversed(entries)) if descending else list(entries)
    return _sort_entries(entries, sort_param)


@router.get("/playlists/{rb_playlist_id}/tracks")
def get_playlist_tracks(
    rb_playlist_id: str,
    request: Request,
    query: str | None = None,
    sort: str = "position",
    limit: int = Query(default=50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    rekordbox=Depends(get_database),
):
    """The tracks of one Rekordbox playlist, in the same
    `{total, items: [CollectionTrack]}` shape as `GET /api/collection`.

    Only the playlist's membership comes from `master.db` (that relation exists
    nowhere else); every track field is served from the in-memory index (ADR
    0012), so this never re-reads 30.000+ content rows per request. That is
    also why an unindexed collection is a documented refusal
    (`collection_not_indexed`) rather than an empty page: "scan first" and
    "this playlist is empty" must not look the same (phase 7 lesson).
    """
    refs = read_playlist_track_refs(rekordbox, rb_playlist_id)
    if refs is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "rekordbox_playlist_not_found",
                "message": f"no Rekordbox playlist {rb_playlist_id!r}",
            },
        )

    entries_by_id = {e.rb_content_id: e for e in request.app.state.collection_index.entries}
    if not entries_by_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "collection_not_indexed",
                "message": "the collection has not been indexed yet; "
                "run POST /api/collection/reindex first",
            },
        )

    # A member the index no longer knows (the track was removed from
    # Rekordbox since the last scan) is skipped rather than rendered as a row
    # with an empty artist and title.
    entries = [
        entries_by_id[ref.rb_content_id] for ref in refs if ref.rb_content_id in entries_by_id
    ]
    entries = _filter_by_query(entries, query)
    entries = _sort_playlist_entries(entries, sort)
    return _page_body(db, entries, limit, offset)
