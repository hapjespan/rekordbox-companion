"""T061 (FR-026, US5 scenario 5): a missing or unreadable audio file
reports `file_missing` instead of failing silently.

The API-level 404 mapping and the "location is None"/"file was deleted"
cases are already covered in `engine/tests/api/test_player_stream.py`
(T038). This file adds the case that's genuinely new to US5: a `location`
that resolves to something that exists on disk but is NOT a readable
audio file -- a directory, not a permission-bit test (root, which this
sandbox runs as, bypasses permission bits -- the same lesson already
applied to `rb/backup.py`'s tests).
"""

from pathlib import Path

import pytest

from companion.audio.stream import FileMissingError, resolve_local_file
from companion.rb.index import CollectionIndex
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


def test_a_location_that_is_a_directory_reports_file_missing_not_a_crash(tmp_path: Path):
    # A real "unreadable" case: the path exists but isn't a file at all
    # (e.g. the DJ's music folder got reorganised and FolderPath now
    # points at a directory) -- `is_file()` catches this the same way it
    # catches an absent path, so this must not raise anything unexpected.
    not_a_file = tmp_path / "not-a-file"
    not_a_file.mkdir()
    index = CollectionIndex()
    index.rebuild([_track("1", str(not_a_file))])

    with pytest.raises(FileMissingError):
        resolve_local_file(index, "1")


def test_a_broken_symlink_reports_file_missing(tmp_path: Path):
    # Another real "unreadable" shape: the FolderPath resolves to a
    # symlink whose target no longer exists.
    target = tmp_path / "gone.mp3"
    link = tmp_path / "link.mp3"
    link.symlink_to(target)
    index = CollectionIndex()
    index.rebuild([_track("1", str(link))])

    with pytest.raises(FileMissingError):
        resolve_local_file(index, "1")
