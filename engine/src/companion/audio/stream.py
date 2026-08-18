"""Stream a Collection track's local audio file for in-browser preview.

Serves `GET /api/player/stream/{rb_content_id}` (wired through the thin
`api/player.py` router, matching this codebase's one-router-file-per-feature
convention). This module owns the domain logic: resolving an id to a file,
parsing RFC 7233 Range requests, and building the streaming response.

Security boundary (ASVS V6/V12, T038 -- the reason this task is
[complexity: high]): `rb_content_id` is the ONLY client input. The filesystem
path is looked up server-side from the trusted in-memory Collection index
(`app.state.collection_index`, built by `rb/index.py` from Rekordbox's own
`FolderPath`). No client-supplied string ever becomes part of a path passed to
`open()`. A path-traversal-shaped id (`../../etc/passwd`) is simply an id that
is not in the index -> `TrackNotFoundError`; it is compared as a dict-style key,
never interpreted as a path.

Scope boundary (tasks.md): T038 builds native-format Range streaming and the
security boundary only. The ffmpeg transcode pipe for non-native formats
(ALAC/AIFF) is T063 (US5) -- a deliberately separate task; the gate-review
moved the pipe's interleaved-Range/subprocess concurrency risk off T038. Until
T063 lands, a resolvable-but-non-native file raises `TranscodeNotImplementedError`
(mapped to 501), never a crash, a silent failure, or a wrong file. T063 replaces
that one branch in `build_stream_response` with the real pipe.

Format detection here is by file extension (kickoff.md section 3: mp3 and
m4a/AAC stream natively). Sniffing the codec inside an `.m4a` container to tell
AAC from ALAC is deferred to T063, which does the real non-native format
handling; T038's extension check is the documented, simple split.
"""

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote, urlparse

from starlette.responses import StreamingResponse

from companion.rb.index import CollectionIndex

# Browser-native containers/codecs (kickoff.md section 3). Everything else is a
# transcode-fallback candidate, owned by T063.
NATIVE_EXTENSIONS = {".mp3", ".m4a"}

_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}
_DEFAULT_CONTENT_TYPE = "application/octet-stream"

_CHUNK_SIZE = 64 * 1024


class TrackNotFoundError(Exception):
    """No Collection Track has this `rb_content_id` (includes any
    path-traversal-shaped id: it is just an unknown key)."""


class FileMissingError(Exception):
    """The Track exists in the index but its audio file is not on disk (no
    `location`, or the path no longer resolves to a file). Distinct from
    `TrackNotFoundError` so the player can report "missing" rather than a
    generic error (spec.md US5 scenario 5)."""


class TranscodeNotImplementedError(Exception):
    """The Track's file is a resolvable non-native format that needs the
    ffmpeg transcode fallback. That fallback is T063 (US5), not T038 -- this
    is the seam T063 fills in."""


class RangeNotSatisfiableError(Exception):
    """The client's Range is syntactically valid but out of bounds (RFC 7233
    -> 416). Carries `file_size` so the router can emit the required
    `Content-Range: bytes */<size>` header."""

    def __init__(self, file_size: int) -> None:
        super().__init__(f"range not satisfiable for {file_size} bytes")
        self.file_size = file_size


def _location_to_path(location: str) -> Path:
    """Normalise a Rekordbox `FolderPath` to a filesystem `Path`.

    Rekordbox may store either a plain absolute path or a
    `file://localhost/...` URL; both normalise here. This runs only on the
    trusted `location` from the index -- never on client input -- so it is a
    convenience for the real Mac library, not a security-relevant transform.
    """
    if location.startswith("file:"):
        return Path(unquote(urlparse(location).path))
    return Path(location)


def resolve_local_file(index: CollectionIndex, rb_content_id: str) -> Path:
    """Resolve `rb_content_id` to an on-disk audio file via the trusted index.

    Raises `TrackNotFoundError` for an unknown id and `FileMissingError` when
    the Track is known but its file is absent. The `rb_content_id` is only ever
    matched as a key against index entries; it never touches the filesystem.
    """
    entry = next(
        (e for e in index.entries if e.rb_content_id == rb_content_id),
        None,
    )
    if entry is None:
        raise TrackNotFoundError(rb_content_id)
    if not entry.location:
        raise FileMissingError(rb_content_id)
    path = _location_to_path(entry.location)
    if not path.is_file():
        raise FileMissingError(rb_content_id)
    return path


def _is_native(path: Path) -> bool:
    return path.suffix.lower() in NATIVE_EXTENSIONS


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), _DEFAULT_CONTENT_TYPE)


def _parse_range_header(
    range_header: str | None, file_size: int
) -> tuple[str, tuple[int, int] | None]:
    """Parse a single-range RFC 7233 `Range: bytes=...` header.

    Returns one of:
      ("full", None)            -- no header, or unparseable/multi-range: serve 200
      ("partial", (start, end)) -- inclusive byte bounds for a 206
      ("unsatisfiable", None)   -- syntactically valid but out of range: 416

    A malformed header is ignored (200 full) rather than rejected, which RFC
    7233 explicitly permits. Multiple ranges are not supported (audio players
    request single ranges); they fall back to a full 200.
    """
    if not range_header:
        return ("full", None)

    unit, sep, spec = range_header.partition("=")
    if not sep or unit.strip().lower() != "bytes":
        return ("full", None)
    spec = spec.strip()
    if "," in spec:  # multiple ranges: unsupported, serve full
        return ("full", None)

    start_s, dash, end_s = spec.partition("-")
    if not dash:
        return ("full", None)

    try:
        if start_s == "":
            # Suffix range: the last N bytes.
            suffix = int(end_s)
            if suffix <= 0:
                return ("full", None)
            start = max(0, file_size - suffix)
            end = file_size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s != "" else file_size - 1
    except ValueError:
        return ("full", None)

    if start > end or start >= file_size:
        return ("unsatisfiable", None)
    end = min(end, file_size - 1)
    return ("partial", (start, end))


def _iter_file(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def build_stream_response(
    index: CollectionIndex, rb_content_id: str, range_header: str | None
) -> StreamingResponse:
    """Resolve the id and build the streaming response (200, 206, or 416).

    Raises the typed domain exceptions above; `api/player.py` maps those to the
    `{code, message}` HTTP error envelope. Non-native formats raise
    `TranscodeNotImplementedError` (T063 seam).
    """
    path = resolve_local_file(index, rb_content_id)
    if not _is_native(path):
        raise TranscodeNotImplementedError(path.suffix.lower())

    file_size = path.stat().st_size
    content_type = _content_type(path)
    disposition, byte_range = _parse_range_header(range_header, file_size)

    if disposition == "unsatisfiable":
        # Raised, not returned: the router maps it to a 416 in the shared
        # {code, message} error envelope, attaching the required Content-Range.
        raise RangeNotSatisfiableError(file_size)

    if disposition == "partial" and byte_range is not None:
        start, end = byte_range
        length = end - start + 1
        return StreamingResponse(
            _iter_file(path, start, length),
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
            },
            media_type=content_type,
        )

    return StreamingResponse(
        _iter_file(path, 0, file_size),
        status_code=200,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        },
        media_type=content_type,
    )
