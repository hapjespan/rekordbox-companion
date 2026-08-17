"""In-memory collection index (R6/ADR 0012): a cache of master.db, rebuilt
on demand from rb/reader.py's snapshot, serving matching, search and
suggestions.

`norm_artist`/`norm_title`/`remix_tokens` use a placeholder normalisation
(lowercase + strip, empty tokens) until T024's FR-004 pipeline exists
(tasks.md T013 note). Replace `_placeholder_normalize` with
`matching.normalize`'s real functions once that lands.
"""

from dataclasses import dataclass

from companion.rb.reader import CollectionTrack


@dataclass(frozen=True)
class IndexEntry:
    rb_content_id: str
    artist: str
    title: str
    norm_artist: str
    norm_title: str
    remix_tokens: tuple[str, ...]
    duration_ms: int | None
    bpm: float | None
    isrc: str | None
    play_count: int
    location: str | None


def _placeholder_normalize(text: str) -> str:
    return text.strip().lower()


def _build_entry(track: CollectionTrack) -> IndexEntry:
    return IndexEntry(
        rb_content_id=track.rb_content_id,
        artist=track.artist,
        title=track.title,
        norm_artist=_placeholder_normalize(track.artist),
        norm_title=_placeholder_normalize(track.title),
        remix_tokens=(),
        duration_ms=track.duration_ms,
        bpm=track.bpm,
        isrc=track.isrc,
        play_count=track.play_count,
        location=track.location,
    )


class CollectionIndex:
    """Holds the current snapshot; `rebuild()` replaces it wholesale.

    A class, not module-level globals, so tests get independent instances
    instead of mutating shared process state (same lesson as
    db/session.py's `create_session_factory` design, T009 review)."""

    def __init__(self) -> None:
        self._entries: list[IndexEntry] = []

    @property
    def entries(self) -> list[IndexEntry]:
        return list(self._entries)

    def rebuild(self, tracks: list[CollectionTrack]) -> int:
        """Replace the index wholesale from a fresh reader.py snapshot.
        Returns the number of entries indexed."""
        self._entries = [_build_entry(track) for track in tracks]
        return len(self._entries)
