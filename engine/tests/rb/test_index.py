"""T013: in-memory collection index (R6/ADR 0012), rebuilt from reader.py.

norm_artist/norm_title/remix_tokens are built via matching.normalize's real
FR-004 pipeline (T024 landed; tasks.md T013 note), not a placeholder.
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
        musical_key="8m",
        label="Loopmasters",
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
    assert entry.musical_key == "8m"
    assert entry.label == "Loopmasters"


def test_rebuild_carries_an_absent_key_and_label_through_as_none():
    # Both are optional in Rekordbox and absent for most tracks, so the index
    # must never assume presence.
    index = CollectionIndex()
    index.rebuild([_track(musical_key=None, label=None)])

    entry = index.entries[0]
    assert entry.musical_key is None
    assert entry.label is None


def test_rebuild_replaces_the_index_wholesale():
    index = CollectionIndex()
    index.rebuild([_track(rb_content_id="1")])
    index.rebuild([_track(rb_content_id="2")])

    assert [e.rb_content_id for e in index.entries] == ["2"]


def test_normalizes_artist_and_title_via_the_real_pipeline():
    index = CollectionIndex()
    index.rebuild([_track(artist="  Daft Punk  ", title="One More Time")])

    entry = index.entries[0]
    assert entry.norm_artist == "daft punk"
    assert entry.norm_title == "one more time"


def test_extracts_remix_tokens_from_the_title_via_the_real_pipeline():
    index = CollectionIndex()
    index.rebuild([_track(title="Track (Club Mix)")])

    assert index.entries[0].remix_tokens == ("club mix",)


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
