"""GET /api/player/stream/{rb_content_id}: local audio preview (US2, FR-013).

Thin router over `audio/stream.py` (one-router-file-per-feature convention,
mirroring `api/collection.py` over `rb/reader.py`). All streaming and Range
logic lives in `audio/stream.py`; this module only maps that module's typed
domain exceptions onto the flat `{code, message}` HTTP error envelope
(contracts/api.md), so a bad id or a missing file becomes a documented error
shape, never an unhandled 500.

The security boundary lives entirely in `resolve_local_file`: `rb_content_id`
is the sole client input and is only ever matched as an index key.
"""

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from companion.audio.stream import (
    FileMissingError,
    RangeNotSatisfiableError,
    TrackNotFoundError,
    TranscodeNotImplementedError,
    build_stream_response,
)

router = APIRouter()


@router.get("/player/stream/{rb_content_id}")
def stream_track(rb_content_id: str, request: Request) -> Response:
    index = request.app.state.collection_index
    try:
        return build_stream_response(index, rb_content_id, request.headers.get("range"))
    except TrackNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "track_not_found",
                "message": f"no Collection Track with id {rb_content_id!r}",
            },
        ) from exc
    except FileMissingError as exc:
        # 404, per contracts/api.md: distinguished from track_not_found by
        # `code`, not status -- the id resolves, but nothing is servable at
        # it, so the player can still report "file missing on disk"
        # specifically (spec.md US5 scenario 5) without a non-standard status.
        raise HTTPException(
            status_code=404,
            detail={
                "code": "file_missing",
                "message": f"audio file for track {rb_content_id!r} is not on disk",
            },
        ) from exc
    except TranscodeNotImplementedError as exc:
        # 501: this format needs the ffmpeg transcode fallback, which is T063
        # (US5), not T038. Honest interim state until that task lands.
        raise HTTPException(
            status_code=501,
            detail={
                "code": "transcode_not_implemented",
                "message": (
                    "non-native format needs the transcode fallback "
                    "(not yet implemented; tracked as T063)"
                ),
            },
        ) from exc
    except RangeNotSatisfiableError as exc:
        raise HTTPException(
            status_code=416,
            detail={
                "code": "range_not_satisfiable",
                "message": "requested range not satisfiable",
            },
            headers={
                "Content-Range": f"bytes */{exc.file_size}",
                "Accept-Ranges": "bytes",
            },
        ) from exc
