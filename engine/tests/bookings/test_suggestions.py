"""T078/T083: the Suggestions query (FR-033, ADR 0008) -- filter by a
profile's genre tags and BPM range, rank by Play Count descending."""

from datetime import datetime

from companion.bookings.models import suggestions_for_node
from companion.db.models import EnrichedGenre, StructureTrack, SuggestionDismissal
from companion.db.session import Base, create_session_factory
from companion.rb.index import IndexEntry


def _fresh_db():
    engine, session_local = create_session_factory("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_local


def _entry(rb_content_id: str, artist: str, title: str, bpm: float | None, play_count: int):
    return IndexEntry(
        rb_content_id=rb_content_id,
        artist=artist,
        title=title,
        norm_artist=artist.lower(),
        norm_title=title.lower(),
        remix_tokens=(),
        duration_ms=200_000,
        bpm=bpm,
        isrc=None,
        play_count=play_count,
        location=None,
    )


def _genre(db, rb_content_id: str, genre: str):
    db.add(
        EnrichedGenre(
            rb_content_id=rb_content_id,
            genre=genre,
            source="musicbrainz",
            updated_at=datetime.now(),
        )
    )


def test_ranks_by_play_count_descending():
    entries = [
        _entry("1", "A", "Low", bpm=None, play_count=5),
        _entry("2", "B", "High", bpm=None, play_count=50),
        _entry("3", "C", "Mid", bpm=None, play_count=20),
    ]
    session_local = _fresh_db()
    with session_local() as db:
        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=None, bpm_max=None
        )

    assert [s.rb_content_id for s in suggestions] == ["2", "3", "1"]


def test_filters_by_genre_tags_against_enriched_genres():
    entries = [
        _entry("1", "A", "House Track", bpm=None, play_count=10),
        _entry("2", "B", "Techno Track", bpm=None, play_count=100),
    ]
    session_local = _fresh_db()
    with session_local() as db:
        _genre(db, "1", "house")
        _genre(db, "2", "techno")
        db.commit()

        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=["house"], bpm_min=None, bpm_max=None
        )

    assert [s.rb_content_id for s in suggestions] == ["1"]


def test_genre_matching_is_case_insensitive():
    entries = [_entry("1", "A", "House Track", bpm=None, play_count=10)]
    session_local = _fresh_db()
    with session_local() as db:
        _genre(db, "1", "house")
        db.commit()

        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=["House"], bpm_min=None, bpm_max=None
        )

    assert len(suggestions) == 1


def test_filters_by_bpm_range():
    entries = [
        _entry("1", "A", "Slow", bpm=100.0, play_count=10),
        _entry("2", "B", "Right Tempo", bpm=126.0, play_count=10),
        _entry("3", "C", "Fast", bpm=150.0, play_count=10),
    ]
    session_local = _fresh_db()
    with session_local() as db:
        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=120, bpm_max=130
        )

    assert [s.rb_content_id for s in suggestions] == ["2"]


def test_excludes_tracks_with_missing_bpm_from_a_bpm_filter_and_reports_the_count():
    """Edge case (T078): a BPM filter can't verify a track with no BPM
    value belongs in range, so it's excluded, but the count is reported
    rather than the track silently vanishing with no explanation."""
    entries = [
        _entry("1", "A", "In Range", bpm=125.0, play_count=10),
        _entry("2", "B", "No BPM", bpm=None, play_count=100),
        _entry("3", "C", "Also No BPM", bpm=None, play_count=5),
    ]
    session_local = _fresh_db()
    with session_local() as db:
        suggestions, excluded_missing_bpm = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=120, bpm_max=130
        )

    assert [s.rb_content_id for s in suggestions] == ["1"]
    assert excluded_missing_bpm == 2


def test_missing_bpm_tracks_are_not_excluded_when_no_bpm_filter_is_active():
    entries = [_entry("1", "A", "No BPM", bpm=None, play_count=10)]
    session_local = _fresh_db()
    with session_local() as db:
        suggestions, excluded_missing_bpm = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=None, bpm_max=None
        )

    assert len(suggestions) == 1
    assert excluded_missing_bpm == 0


def test_dismissed_suggestions_never_return_for_that_node():
    entries = [_entry("1", "A", "Dismissed", bpm=None, play_count=10)]
    session_local = _fresh_db()
    with session_local() as db:
        db.add(SuggestionDismissal(node_id=1, rb_content_id="1"))
        db.commit()

        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=None, bpm_max=None
        )

    assert suggestions == []


def test_a_dismissal_on_a_different_node_does_not_affect_this_one():
    entries = [_entry("1", "A", "Track", bpm=None, play_count=10)]
    session_local = _fresh_db()
    with session_local() as db:
        db.add(SuggestionDismissal(node_id=999, rb_content_id="1"))
        db.commit()

        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=None, bpm_max=None
        )

    assert len(suggestions) == 1


def test_flags_already_in_playlist_rather_than_excluding_it():
    entries = [
        _entry("1", "A", "Already Added", bpm=None, play_count=10),
        _entry("2", "B", "Not Added", bpm=None, play_count=5),
    ]
    session_local = _fresh_db()
    with session_local() as db:
        db.add(StructureTrack(node_id=1, rb_content_id="1", position=0, origin="suggestion"))
        db.commit()

        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=None, bpm_max=None
        )

    by_id = {s.rb_content_id: s for s in suggestions}
    assert len(suggestions) == 2  # still present, not subtracted
    assert by_id["1"].already_in_playlist is True
    assert by_id["2"].already_in_playlist is False


def test_genre_filter_survives_a_collection_larger_than_sqlites_variable_cap():
    """Regression (phase 7 review): the genre filter used to bind one SQL
    parameter per Collection entry, which raises `sqlite3.OperationalError:
    too many SQL variables` above SQLite's 32.766-variable cap -- inside the
    40.000-entry sizing envelope tests/test_collection_perf.py pins. The
    filter must be driven by the (small, bounded) wanted tag list instead."""
    entries = [
        _entry(str(i), f"Artist {i}", "Track", bpm=None, play_count=i) for i in range(40_000)
    ]
    session_local = _fresh_db()
    with session_local() as db:
        _genre(db, "39999", "house")
        _genre(db, "12345", "techno")
        db.commit()

        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=["house"], bpm_min=None, bpm_max=None
        )

    assert [s.rb_content_id for s in suggestions] == ["39999"]


def test_an_enriched_genre_for_a_track_outside_the_collection_is_ignored():
    """The genre filter is driven by tags now, not by the collection's ids,
    so a stale enriched_genre row for a track no longer in the Collection
    must not leak into the results."""
    entries = [_entry("1", "A", "In Collection", bpm=None, play_count=10)]
    session_local = _fresh_db()
    with session_local() as db:
        _genre(db, "1", "house")
        _genre(db, "gone", "house")
        db.commit()

        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=["house"], bpm_min=None, bpm_max=None
        )

    assert [s.rb_content_id for s in suggestions] == ["1"]


def test_respects_a_limit():
    entries = [_entry(str(i), f"Artist {i}", "Track", bpm=None, play_count=i) for i in range(5)]
    session_local = _fresh_db()
    with session_local() as db:
        suggestions, _ = suggestions_for_node(
            db, entries, node_id=1, genre_tags=[], bpm_min=None, bpm_max=None, limit=2
        )

    assert len(suggestions) == 2
    assert [s.rb_content_id for s in suggestions] == ["4", "3"]  # highest play count first
