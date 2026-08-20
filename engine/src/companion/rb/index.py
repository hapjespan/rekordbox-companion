"""In-memory collection index (R6/ADR 0012): a cache of master.db, rebuilt
on demand from rb/reader.py's snapshot, serving matching, search and
suggestions.

`norm_artist`/`norm_title`/`remix_tokens` are PRECOMPUTED here via
`matching.normalize` (FR-004) so `matching.engine.classify_match`'s hot loop
never re-normalises the collection side per comparison (data-model.md's
"Matching engine seam" note, ADR 0012).
"""

from dataclasses import dataclass

from companion.matching.normalize import extract_remix_tokens, normalize
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
    # Rekordbox's own KeyName/LabelName, carried through verbatim and
    # optional: absent for most tracks, and the key is never normalised or
    # converted (see `CollectionTrack`).
    musical_key: str | None = None
    label: str | None = None


def _build_entry(track: CollectionTrack) -> IndexEntry:
    return IndexEntry(
        rb_content_id=track.rb_content_id,
        artist=track.artist,
        title=track.title,
        norm_artist=normalize(track.artist),
        norm_title=normalize(track.title),
        remix_tokens=extract_remix_tokens(track.title),
        duration_ms=track.duration_ms,
        bpm=track.bpm,
        isrc=track.isrc,
        play_count=track.play_count,
        location=track.location,
        musical_key=track.musical_key,
        label=track.label,
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
