"""T066 (US6, research.md R1): measure Enriched Genre coverage over the
fixture Collection before building the enrichment feature.

Run manually (not part of the app or the test suite): `uv run python
scripts/enrichment_coverage_spike.py <path-to-master.db>`.

ADR 0018 supersedes ADR 0013's source ordering: Spotify artist genres are
unavailable to this app in practice (verified live: `GET /v1/search`'s artist
objects and `GET /v1/artists/{id}` both omit `genres` entirely, and
`GET /v1/artists?ids=...` returns 403), so this spike measures the real
`MusicBrainzGenreSource` adapter (T072) only -- the same code the runner
(T073) uses in production, not a separate copy of its logic.
"""

import sys
from pathlib import Path

from companion.enrichment.musicbrainz import MusicBrainzGenreSource
from companion.rb.reader import open_database, read_collection_snapshot
from companion.security import build_allowlisted_client

SAMPLE_SIZE = 50


def main(db_path: Path) -> None:
    tracks = [t for t in read_collection_snapshot(open_database(db_path)) if t.artist]
    unique_artists = sorted({t.artist for t in tracks})
    print(f"{len(tracks)} tracks with a named artist, {len(unique_artists)} unique artists")

    genres_by_artist: dict[str, list[str]] = {}
    with build_allowlisted_client(timeout=15.0) as client:
        source = MusicBrainzGenreSource(client)
        for i, artist in enumerate(unique_artists, start=1):
            genres_by_artist[artist] = source.genres_for(artist)
            print(f"  [{i}/{len(unique_artists)}] {artist!r} -> {genres_by_artist[artist]}")

    covered = [t for t in tracks if genres_by_artist.get(t.artist)]
    coverage_pct = 100 * len(covered) / len(tracks) if tracks else 0.0

    print(f"\nCoverage: {len(covered)}/{len(tracks)} tracks ({coverage_pct:.1f}%)")
    print(f"\nSample (up to {SAMPLE_SIZE} covered tracks) for owner judgement against SC-008:")
    for t in covered[:SAMPLE_SIZE]:
        print(f"  {t.artist} - {t.title}: {genres_by_artist[t.artist]}")

    artist_coverage_pct = (
        100 * sum(1 for g in genres_by_artist.values() if g) / len(unique_artists)
        if unique_artists
        else 0.0
    )
    print(f"\nArtist-level coverage: {artist_coverage_pct:.1f}% of unique artists resolved")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <path-to-master.db>", file=sys.stderr)
        sys.exit(1)
    main(Path(sys.argv[1]))
