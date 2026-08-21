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

Scope boundary (tasks.md): T038 built native-format Range streaming and the
security boundary. T063 (US5) adds the ffmpeg transcode fallback for the two
non-native formats named in kickoff.md section 3 (ALAC and AIFF), replacing
T038's `TranscodeNotImplementedError`/501 seam with a real subprocess pipe. The
gate-review moved the pipe's interleaved-Range/subprocess concurrency risk here,
to the task that actually builds the pipe (see `_iter_transcode`).

Format detection (T063): `.mp3` is always native; `.aiff`/`.aif` are always
non-native. `.m4a` is ambiguous -- the container holds AAC (browser-native) or
ALAC (lossless, NOT browser-playable) -- so its codec is sniffed with `ffprobe`
per request (no persistent cache in v1, CLAUDE.md/D17), and only an AAC-coded
`.m4a` stays on the native passthrough path. Everything non-native streams
through the ffmpeg pipe as transcoded MP3.

Transcode target (T063): MP3 (`-f mp3`, libmp3lame). Chosen over AAC-in-ADTS
because MP3 has the widest, most unconditional `<audio>` support and reuses the
existing `audio/mpeg` content type. Per US5 scenario 4 (which, unlike scenario
3, states no seek requirement) and plan.md's proof-of-value cut (no waveform, no
gapless, no preload), the transcode stream is a plain, non-seekable 200: a
`Range` header on a non-native request is ignored, never handed to ffmpeg.
"""

import asyncio
import subprocess
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import Request
from starlette.responses import StreamingResponse

from companion.logging import get_logger
from companion.rb.index import CollectionIndex

_logger = get_logger(__name__)

# `.m4a` audio codecs that browsers can decode natively. AAC only; ALAC (and any
# other codec ever muxed into an .m4a) routes to the transcode pipe.
_M4A_NATIVE_CODECS = {"aac"}

_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
}
_DEFAULT_CONTENT_TYPE = "application/octet-stream"

# Transcode fallback target: MP3 via libmp3lame. See the module docstring for
# why MP3 over AAC-ADTS. `-vn` drops any embedded cover-art video stream, which
# would otherwise make the mp3 muxer reject the output.
_TRANSCODE_FORMAT = "mp3"
_TRANSCODE_CONTENT_TYPE = "audio/mpeg"

_FFMPEG = "ffmpeg"
_FFPROBE = "ffprobe"
_PROBE_TIMEOUT_S = 10
_TERMINATE_TIMEOUT_S = 5

_CHUNK_SIZE = 64 * 1024


class TrackNotFoundError(Exception):
    """No Collection Track has this `rb_content_id` (includes any
    path-traversal-shaped id: it is just an unknown key)."""


class FileMissingError(Exception):
    """The Track exists in the index but its audio file is not on disk (no
    `location`, or the path no longer resolves to a file). Distinct from
    `TrackNotFoundError` so the player can report "missing" rather than a
    generic error (spec.md US5 scenario 5)."""


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


def _m4a_codec(path: Path) -> str | None:
    """Return the codec name of the first audio stream inside an `.m4a`
    container (e.g. `"aac"`, `"alac"`), or `None` if `ffprobe` cannot determine
    it (missing/damaged stream, ffprobe error or timeout).

    Runs per request with no caching (v1 cut, CLAUDE.md/D17). The path comes
    only from the trusted index (`resolve_local_file`), never client input, so
    passing it to a subprocess is not a shell-injection surface (there is no
    shell: `subprocess.run` with an argv list).
    """
    try:
        result = subprocess.run(
            [
                _FFPROBE,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip().lower() or None


def _is_native(path: Path) -> bool:
    """Whether the browser can play this file directly (no transcode).

    `.mp3` is unconditionally native. `.m4a` is native only when its actual
    audio codec is AAC -- an ALAC-coded `.m4a` has the same extension but is not
    browser-playable, so it (and an `.m4a` whose codec cannot be sniffed) routes
    to the transcode pipe. Every other extension (`.aiff`/`.aif`, ...) is
    non-native.
    """
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return True
    if suffix == ".m4a":
        return _m4a_codec(path) in _M4A_NATIVE_CODECS
    return False


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

    if start > end:
        # RFC 7233 SS2.1: last-byte-pos < first-byte-pos is an INVALID
        # byte-range-spec, which a recipient MUST ignore -- not the same as a
        # syntactically valid range that is merely out of bounds (that case,
        # `start >= file_size` below, is genuinely 416). Ignoring falls back
        # to a full 200, same as any other unparseable header.
        return ("full", None)
    if start >= file_size:
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


async def _terminate_on_disconnect(request: Request, process: asyncio.subprocess.Process) -> None:
    """Kill `process` as soon as the client disconnects.

    Review finding (T063): Starlette's `StreamingResponse` (this project's
    pinned version) does NOT reliably deliver `GeneratorExit` into a
    response-body generator on early client disconnect -- for a SYNC
    generator wrapped via `iterate_in_threadpool`, there is no `finally`
    around the wrapped iterator at all, and even for an async generator the
    only guarantee is eventual reference-counted garbage collection, not a
    bounded time. `request.is_disconnected()` (Starlette's own documented
    mechanism for exactly this problem) is polled independently here instead
    of relying on the generator ever being closed -- this is what actually
    closes the "must not deadlock/orphan the subprocess on early disconnect"
    risk this task was escalated for, not the generator's own `finally`
    (which remains as defence in depth for the normal-completion path).
    """
    poll_interval_s = 0.5
    while process.returncode is None:
        if await request.is_disconnected():
            process.terminate()
            return
        await asyncio.sleep(poll_interval_s)


async def _iter_transcode(path: Path, request: Request) -> AsyncIterator[bytes]:
    """Stream `path` transcoded to MP3 on the fly, chunk by chunk.

    The escalated [complexity: high] risk lives here: a live subprocess pipe
    read from a response-body generator. The guards, each load-bearing:

    * A genuine `asyncio` subprocess (not `subprocess.Popen`): reads are real
      `await`s that cooperate with the event loop, which is what lets
      `_terminate_on_disconnect` run concurrently alongside this generator
      via the same running loop, and is what makes this an `AsyncIterable`
      Starlette drives directly (no threadpool wrapping, see
      `build_stream_response`).
    * `stderr=DEVNULL`: ffmpeg writes progress/diagnostics to stderr
      continuously. Piping stderr without draining it would let its OS buffer
      fill and deadlock the whole subprocess (the classic two-pipe pitfall).
      We do not need those diagnostics for the proof-of-value cut (plan.md:
      rarer failures get logs + a generic toast, not bespoke UX) beyond the
      one-line warning below, so we discard them outright rather than
      draining a second pipe.
    * Fixed-size `read(_CHUNK_SIZE)`, never a bare `.read()`: reading "the whole
      thing" would buffer the entire transcode in memory, defeating the whole
      point of a streaming fallback (and re-introducing the very problem this
      task exists to avoid).
    * The disconnect watcher (`_terminate_on_disconnect`) is the primary
      cleanup path; this generator's own `finally` is a second, independent
      guard for the normal-completion case and for the (rarer) case where
      the generator itself does get closed. `.terminate()` first, then
      `.kill()` if it ignores the signal, always followed by `.wait()` so no
      zombie remains.

    No `Range`/seek handling: this is intentionally a non-seekable full stream
    (US5 scenario 4; plan.md proof-of-value cut). The caller never passes a byte
    range in.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            _FFMPEG,
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vn",
            "-f",
            _TRANSCODE_FORMAT,
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        # ffmpeg missing/unexecutable: `/api/health`'s ffmpeg_ok check is the
        # primary guard against this, but a clear log line beats a bare
        # traceback surfacing as a truncated response if it happens anyway.
        _logger.warning("could not spawn ffmpeg for transcode")
        return
    watcher = asyncio.ensure_future(_terminate_on_disconnect(request, process))
    try:
        assert process.stdout is not None  # PIPE was requested
        while True:
            chunk = await process.stdout.read(_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        watcher.cancel()
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=_TERMINATE_TIMEOUT_S)
            except TimeoutError:
                process.kill()
                await process.wait()
        else:
            await process.wait()
        if process.returncode not in (0, None, -15, -9):
            # -15/-9: SIGTERM/SIGKILL from our own cleanup above, not a real
            # transcode failure -- only a genuine nonzero ffmpeg exit is
            # worth a log line (review finding: this was previously
            # completely unobservable, stderr having been discarded).
            _logger.warning(
                "transcode process exited non-zero",
                extra={"transcode": {"returncode": process.returncode}},
            )


def build_stream_response(
    index: CollectionIndex, rb_content_id: str, range_header: str | None, request: Request
) -> StreamingResponse:
    """Resolve the id and build the streaming response.

    Native formats (`.mp3`, AAC-coded `.m4a`) get a Range-aware file stream
    (200, 206, or a 416 via `RangeNotSatisfiableError`). Non-native formats
    (ALAC-coded `.m4a`, `.aiff`/`.aif`) get a live ffmpeg transcode pipe: a
    plain, non-seekable 200 (`range_header` is ignored on this path, US5
    scenario 4). Raises the typed domain exceptions above; `api/player.py` maps
    those to the `{code, message}` HTTP error envelope.

    `request` is only used by the transcode path, to detect an early client
    disconnect and kill the ffmpeg subprocess (see `_terminate_on_disconnect`)
    -- passed through unconditionally rather than threaded in only on that
    branch, so the signature doesn't have to change again if a future format
    needs it too.
    """
    path = resolve_local_file(index, rb_content_id)
    if not _is_native(path):
        return StreamingResponse(
            _iter_transcode(path, request),
            status_code=200,
            media_type=_TRANSCODE_CONTENT_TYPE,
        )

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
