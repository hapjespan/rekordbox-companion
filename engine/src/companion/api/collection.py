"""POST /api/collection/reindex: rebuilds the in-memory index (R6/ADR 0012)."""

import time

from fastapi import APIRouter, Depends, HTTPException, Request

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


@router.get("/playlists")
def get_playlists(db=Depends(get_database)):
    return read_playlist_tree(db)
