"""T013: in-memory collection index (R6/ADR 0012), rebuilt from reader.py.

norm_artist/norm_title/remix_tokens use a placeholder normalisation until
T024's FR-004 pipeline exists (tasks.md T013 note) -- these tests pin the
placeholder's current behaviour so replacing it with the real pipeline is a
deliberate, visible change here, not a silent one.
"""

from companion.rb.index import CollectionIndex
from companion.rb.reader import CollectionTrack


def _track(**overrides):
    defaults = dict(
        rb_content_id="1",
        artist="Example Artist",
        title="Example Title",
        duration_ms=210_000,
        bpm=128.0,
        isrc="USRC17607839",
        play_count=42,
        location="/music/example.mp3",
    )
    return CollectionTrack(**{**defaults, **overrides})


def test_starts_empty():
    index = CollectionIndex()
    assert index.entries == []


def test_rebuild_populates_entries_from_tracks():
    index = CollectionIndex()
    count = index.rebuild([_track()])

    assert count == 1
    assert len(index.entries) == 1
    entry = index.entries[0]
    assert entry.rb_content_id == "1"
    assert entry.artist == "Example Artist"
    assert entry.duration_ms == 210_000
    assert entry.bpm == 128.0
    assert entry.isrc == "USRC17607839"
    assert entry.play_count == 42
    assert entry.location == "/music/example.mp3"


def test_rebuild_replaces_the_index_wholesale():
    index = CollectionIndex()
    index.rebuild([_track(rb_content_id="1")])
    index.rebuild([_track(rb_content_id="2")])

    assert [e.rb_content_id for e in index.entries] == ["2"]


def test_placeholder_normalization_lowercases_and_strips():
    index = CollectionIndex()
    index.rebuild([_track(artist="  Daft Punk  ", title="One More Time")])

    entry = index.entries[0]
    assert entry.norm_artist == "daft punk"
    assert entry.norm_title == "one more time"


def test_placeholder_remix_tokens_are_always_empty():
    index = CollectionIndex()
    index.rebuild([_track(title="Track (Club Mix)")])

    assert index.entries[0].remix_tokens == ()


def test_entries_returns_a_copy_not_the_live_list():
    index = CollectionIndex()
    index.rebuild([_track()])

    snapshot = index.entries
    snapshot.clear()

    assert len(index.entries) == 1


def test_independent_instances_do_not_share_state():
    a = CollectionIndex()
    b = CollectionIndex()
    a.rebuild([_track()])

    assert a.entries != []
    assert b.entries == []
