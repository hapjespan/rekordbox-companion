"""T038: GET /api/player/stream/{rb_content_id} -- local audio streaming with
HTTP Range support and the id-only security boundary (ASVS V6/V12).

Scope note (tasks.md): T038 builds native-format Range streaming and the
security boundary. The ffmpeg transcode pipe for non-native formats is T063
(US5), a deliberately separate task, so a non-native format here resolves to a
documented 501 seam rather than a live transcode. These tests assert that seam,
not a working transcode.

Real audio fixtures are owner-supplied and gitignored; these tests use tiny
synthetic byte files in tmp_path, which is sufficient to prove the HTTP Range
mechanics, status codes and the security boundary (the bytes need not be real
audio to slice them by range).
"""

from urllib.parse import quote

from fastapi.testclient import TestClient

from companion.audio.stream import (
    FileMissingError,
    TrackNotFoundError,
    _parse_range_header,
    resolve_local_file,
)
from companion.main import create_app
from companion.rb.reader import CollectionTrack


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


def test_id_known_but_location_none_returns_410_file_missing():
    client = _app_with_tracks(_track("7", None))

    response = client.get("/api/player/stream/7")

    assert response.status_code == 410
    assert response.json()["code"] == "file_missing"


def test_id_known_but_file_gone_from_disk_returns_410_file_missing(tmp_path):
    gone = str(tmp_path / "was-here.mp3")  # never created
    client = _app_with_tracks(_track("7", gone))

    response = client.get("/api/player/stream/7")

    assert response.status_code == 410
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


# --- Non-native format routes to the T063 transcode seam (501) --------------


def test_non_native_extension_returns_501_transcode_not_implemented(tmp_path):
    # An existing, resolvable file whose format is NOT browser-native. T038
    # detects it and routes to the transcode seam; the actual ffmpeg pipe is
    # T063 (US5), so the honest interim state is 501, never a wrong file or a
    # crash.
    location = _native_file(tmp_path, name="lossless.aiff", size=500)
    client = _app_with_tracks(_track("9", location))

    response = client.get("/api/player/stream/9")

    assert response.status_code == 501
    assert response.json()["code"] == "transcode_not_implemented"


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
