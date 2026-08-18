"""GET /api/player/stream/{rb_content_id} -- local audio streaming.

T038 built native-format Range streaming and the id-only security boundary
(ASVS V6/V12). T063 (US5) added the ffmpeg transcode fallback for non-native
formats (ALAC-coded `.m4a`, `.aiff`), replacing T038's 501 seam with a live
pipe; those tests live under "Non-native format" and "the escalated concurrency
risk" below.

The native Range tests use tiny synthetic byte files in tmp_path -- the bytes
need not be real audio to slice them by range, which is all those tests prove.
The transcode tests instead build real (ffmpeg-generated) audio fixtures, since
a live subprocess must decode genuine audio; both keep real owner-supplied
fixtures gitignored (kickoff.md).
"""

import subprocess
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from fastapi.testclient import TestClient

from companion.audio.stream import (
    FileMissingError,
    TrackNotFoundError,
    _is_native,
    _iter_transcode,
    _m4a_codec,
    _parse_range_header,
    resolve_local_file,
)
from companion.main import create_app
from companion.rb.reader import CollectionTrack

# --- Real synthetic audio fixtures (T063) -----------------------------------
#
# The transcode fallback exercises a live ffmpeg subprocess, so these fixtures
# must be genuinely decodable audio, not the arbitrary byte blobs the native
# Range tests use. ffmpeg's own lavfi sine generator produces tiny (~1s) files;
# real audio fixtures stay owner-supplied and gitignored (kickoff.md), so the
# tests build their own here rather than committing any.


def _ffmpeg_make(tmp_path: Path, name: str, codec_args: list[str]) -> str:
    path = tmp_path / name
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            *codec_args,
            str(path),
        ],
        check=True,
    )
    return str(path)


def _alac_m4a(tmp_path: Path, name: str = "lossless.m4a") -> str:
    # ALAC-coded .m4a: same container as an AAC .m4a, NOT browser-playable.
    return _ffmpeg_make(tmp_path, name, ["-c:a", "alac"])


def _aac_m4a(tmp_path: Path, name: str = "aac.m4a") -> str:
    # AAC-coded .m4a: browser-native; must stay on the passthrough path.
    return _ffmpeg_make(tmp_path, name, ["-c:a", "aac"])


def _aiff(tmp_path: Path, name: str = "lossless.aiff") -> str:
    return _ffmpeg_make(tmp_path, name, [])


def _probe_codec(data: bytes, tmp_path: Path, name: str = "probe.bin") -> str:
    """Round-trip a response body back through ffprobe to prove it is a real,
    decodable audio stream of the expected codec -- genuine end-to-end evidence
    rather than a bare "some bytes came back" check."""
    path = tmp_path / name
    path.write_bytes(data)
    result = subprocess.run(
        [
            "ffprobe",
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
    )
    return result.stdout.strip().lower()


def _track(rb_content_id: str, location: str | None) -> CollectionTrack:
    return CollectionTrack(
        rb_content_id=rb_content_id,
        artist="Example",
        title="Track",
        duration_ms=1000,
        bpm=120.0,
        isrc=None,
        play_count=0,
        location=location,
    )


def _app_with_tracks(*tracks: CollectionTrack) -> TestClient:
    app = create_app()
    app.state.collection_index.rebuild(list(tracks))
    return TestClient(app)


def _native_file(tmp_path, name: str = "track.mp3", size: int = 1000) -> str:
    path = tmp_path / name
    # Deterministic, distinguishable bytes so range slices can be verified.
    path.write_bytes(bytes(i % 256 for i in range(size)))
    return str(path)


# --- Security boundary (the [complexity: high] point of T038) ---------------


def test_unknown_id_returns_404_track_not_found():
    client = _app_with_tracks()

    response = client.get("/api/player/stream/does-not-exist")

    assert response.status_code == 404
    assert response.json()["code"] == "track_not_found"


def test_traversal_shaped_id_is_treated_as_unknown_id_never_a_path(tmp_path):
    # A secret file that exists on disk but is NOT registered in the index.
    #
    # Review finding (T038): ids containing a literal or %2F-encoded slash
    # never even reach this router -- Starlette's own path-param matching
    # excludes "/" from a single {rb_content_id} segment, so those two cases
    # only prove FastAPI's routing, not this codebase's lookup logic. The
    # slash-free case (the absolute path with encoded spaces, `quote`d as a
    # whole) DOES reach `resolve_local_file` over real HTTP; the direct unit
    # test below (`test_resolve_rejects_unknown_id_with_typed_exception`)
    # additionally proves the equality-only lookup for a slash-containing
    # traversal string at the function level, where routing can't interfere.
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    allowed = _native_file(tmp_path)
    client = _app_with_tracks(_track("1", allowed))

    for evil_id in ("../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", str(secret)):
        response = client.get(f"/api/player/stream/{quote(evil_id, safe='')}")
        # Never 200, and never the secret's bytes: the client string is only
        # ever compared as an index key, never turned into a filesystem path.
        assert response.status_code != 200
        assert "TOP SECRET" not in response.text


def test_resolve_rejects_unknown_id_with_typed_exception():
    from companion.rb.index import CollectionIndex

    index = CollectionIndex()
    index.rebuild([])

    try:
        resolve_local_file(index, "../../etc/passwd")
    except TrackNotFoundError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected TrackNotFoundError")


# --- Two distinct failure modes: unknown id vs file missing on disk ---------


def test_id_known_but_location_none_returns_404_file_missing():
    client = _app_with_tracks(_track("7", None))

    response = client.get("/api/player/stream/7")

    assert response.status_code == 404
    assert response.json()["code"] == "file_missing"


def test_id_known_but_file_gone_from_disk_returns_404_file_missing(tmp_path):
    gone = str(tmp_path / "was-here.mp3")  # never created
    client = _app_with_tracks(_track("7", gone))

    response = client.get("/api/player/stream/7")

    assert response.status_code == 404
    assert response.json()["code"] == "file_missing"


def test_resolve_raises_file_missing_for_absent_file(tmp_path):
    from companion.rb.index import CollectionIndex

    index = CollectionIndex()
    index.rebuild([_track("7", str(tmp_path / "nope.mp3"))])

    try:
        resolve_local_file(index, "7")
    except FileMissingError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected FileMissingError")


# --- Native format: full download (200) and Range (206) ---------------------


def test_native_file_without_range_returns_200_full_content(tmp_path):
    location = _native_file(tmp_path, size=1000)
    client = _app_with_tracks(_track("1", location))

    response = client.get("/api/player/stream/1")

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["content-length"] == "1000"
    assert len(response.content) == 1000
    assert response.content == bytes(i % 256 for i in range(1000))


def test_native_file_with_range_returns_206_partial(tmp_path):
    location = _native_file(tmp_path, size=1000)
    client = _app_with_tracks(_track("1", location))

    response = client.get("/api/player/stream/1", headers={"Range": "bytes=0-99"})

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-99/1000"
    assert response.headers["content-length"] == "100"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == bytes(i % 256 for i in range(0, 100))


def test_range_open_ended_from_offset_to_end(tmp_path):
    location = _native_file(tmp_path, size=1000)
    client = _app_with_tracks(_track("1", location))

    response = client.get("/api/player/stream/1", headers={"Range": "bytes=900-"})

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 900-999/1000"
    assert response.headers["content-length"] == "100"
    assert response.content == bytes(i % 256 for i in range(900, 1000))


def test_range_suffix_last_n_bytes(tmp_path):
    location = _native_file(tmp_path, size=1000)
    client = _app_with_tracks(_track("1", location))

    response = client.get("/api/player/stream/1", headers={"Range": "bytes=-100"})

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 900-999/1000"
    assert response.content == bytes(i % 256 for i in range(900, 1000))


def test_unsatisfiable_range_returns_416(tmp_path):
    location = _native_file(tmp_path, size=1000)
    client = _app_with_tracks(_track("1", location))

    response = client.get("/api/player/stream/1", headers={"Range": "bytes=5000-6000"})

    assert response.status_code == 416
    assert response.headers["content-range"] == "bytes */1000"
    assert response.json()["code"] == "range_not_satisfiable"


def test_malformed_range_header_is_ignored_and_serves_full_200(tmp_path):
    location = _native_file(tmp_path, size=1000)
    client = _app_with_tracks(_track("1", location))

    response = client.get("/api/player/stream/1", headers={"Range": "kilobytes=0-9"})

    assert response.status_code == 200
    assert len(response.content) == 1000


# --- Non-native format: live ffmpeg transcode fallback (T063, US5 scen. 4) ---
#
# T063 replaces T038's 501 seam with a real ffmpeg pipe. The two named
# non-native formats (kickoff.md section 3) are ALAC and AIFF; both now stream
# transparently as transcoded MP3 (target format chosen for universal <audio>
# support and the existing audio/mpeg content type). No format still routes to
# a "not implemented" 501 after this task -- the exception and its mapping are
# gone (see the module docstrings). US5 scenario 4 states no seek requirement
# for this path, and plan.md cuts waveform/gapless/preload, so the transcode
# stream is a plain, non-seekable 200.


def test_alac_m4a_routes_to_transcode_returns_200_real_mp3(tmp_path):
    # The codec-sniffing case: an ALAC-coded .m4a shares the extension with a
    # native AAC .m4a but is NOT browser-playable, so it must transcode.
    location = _alac_m4a(tmp_path)
    client = _app_with_tracks(_track("9", location))

    response = client.get("/api/player/stream/9")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    # Not a native passthrough: no Accept-Ranges advertised on the pipe.
    assert "accept-ranges" not in response.headers
    # Real, decodable transcoded audio -- round-tripped through ffprobe.
    assert len(response.content) > 500
    assert _probe_codec(response.content, tmp_path) == "mp3"


def test_aac_m4a_stays_native_passthrough_not_transcoded(tmp_path):
    # Regression proving the codec sniff actually distinguishes AAC from ALAC:
    # this .m4a has the same extension as the ALAC one above but is native, so
    # it must be served byte-for-byte, NOT transcoded.
    location = _aac_m4a(tmp_path)
    original = Path(location).read_bytes()
    client = _app_with_tracks(_track("10", location))

    response = client.get("/api/player/stream/10")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == original


def test_aiff_routes_to_transcode_returns_200_real_mp3(tmp_path):
    location = _aiff(tmp_path)
    client = _app_with_tracks(_track("11", location))

    response = client.get("/api/player/stream/11")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 500
    assert _probe_codec(response.content, tmp_path) == "mp3"


def test_range_header_is_ignored_on_transcode_path_still_200(tmp_path):
    # US5 scenario 4 states no seek; a Range header on a non-native request
    # must NOT produce a 206 or a Content-Range, and must never be handed to
    # ffmpeg. It is simply ignored: a full 200 stream from the start.
    location = _alac_m4a(tmp_path)
    client = _app_with_tracks(_track("9", location))

    response = client.get("/api/player/stream/9", headers={"Range": "bytes=0-99"})

    assert response.status_code == 200
    assert "content-range" not in response.headers
    assert _probe_codec(response.content, tmp_path) == "mp3"


def test_m4a_codec_sniff_reports_alac_and_aac(tmp_path):
    assert _m4a_codec(Path(_alac_m4a(tmp_path))) == "alac"
    assert _m4a_codec(Path(_aac_m4a(tmp_path))) == "aac"


def test_is_native_uses_codec_not_just_extension(tmp_path):
    assert _is_native(Path(_aac_m4a(tmp_path))) is True
    assert _is_native(Path(_alac_m4a(tmp_path))) is False
    assert _is_native(Path(_aiff(tmp_path))) is False


# --- The escalated concurrency risk: the subprocess must never leak ----------


def _spy_popen():
    """Wrap the real subprocess.Popen so a test can grab the spawned process
    handle and assert on its lifecycle."""
    created: list[subprocess.Popen] = []
    real = subprocess.Popen

    def spy(*args, **kwargs):
        proc = real(*args, **kwargs)
        created.append(proc)
        return proc

    return created, spy


def test_transcode_process_exits_after_full_consumption(tmp_path):
    # Normal path: once the response body is fully read, ffmpeg has hit EOF and
    # exited -- no zombie/orphan left behind.
    location = _alac_m4a(tmp_path)
    created, spy = _spy_popen()

    with mock.patch("subprocess.Popen", side_effect=spy):
        data = b"".join(_iter_transcode(Path(location)))

    assert data
    assert len(created) == 1
    created[0].wait(timeout=5)
    assert created[0].poll() is not None


def test_transcode_process_terminated_on_early_disconnect(tmp_path):
    # The escalation flag's core risk: a client that seeks away or closes the
    # tab mid-stream closes the generator (Starlette raises GeneratorExit into
    # the suspended `yield`). The generator's finally block must then reap
    # ffmpeg rather than leaving it running against a dead pipe.
    location = _alac_m4a(tmp_path)
    created, spy = _spy_popen()

    with mock.patch("subprocess.Popen", side_effect=spy):
        gen = _iter_transcode(Path(location))
        first = next(gen)  # spawns ffmpeg, reads one chunk
        assert first
        gen.close()  # simulate early client disconnect

    assert len(created) == 1
    created[0].wait(timeout=5)
    assert created[0].poll() is not None


# --- Unit tests for the RFC 7233 range parser --------------------------------


def test_parse_range_no_header_is_full():
    assert _parse_range_header(None, 1000) == ("full", None)


def test_parse_range_explicit_bounds():
    assert _parse_range_header("bytes=0-499", 1000) == ("partial", (0, 499))


def test_parse_range_open_ended():
    assert _parse_range_header("bytes=500-", 1000) == ("partial", (500, 999))


def test_parse_range_suffix():
    assert _parse_range_header("bytes=-200", 1000) == ("partial", (800, 999))


def test_parse_range_end_clamped_to_file_size():
    assert _parse_range_header("bytes=0-100000", 1000) == ("partial", (0, 999))


def test_parse_range_unsatisfiable_beyond_end():
    assert _parse_range_header("bytes=2000-3000", 1000) == ("unsatisfiable", None)


def test_parse_range_multiple_ranges_ignored():
    assert _parse_range_header("bytes=0-9,20-29", 1000) == ("full", None)


def test_parse_range_garbage_ignored():
    assert _parse_range_header("bytes=abc-def", 1000) == ("full", None)
