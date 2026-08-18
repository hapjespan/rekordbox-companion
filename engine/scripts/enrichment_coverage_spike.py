"""T066 (US6, research.md R1): measure Enriched Genre coverage over the
fixture Collection before building the enrichment feature.

Run manually (not part of the app or the test suite): `uv run python
scripts/enrichment_coverage_spike.py <path-to-master.db>`.

ADR 0018 supersedes ADR 0013's source ordering: Spotify artist genres are
unavailable to this app in practice (verified live: `GET /v1/search`'s artist
objects and `GET /v1/artists/{id}` both omit `genres` entirely, and
`GET /v1/artists?ids=...` returns 403), so this spike measures MusicBrainz
only. MusicBrainz's curated `genres` field is itself too sparse to use
(verified live: Daft Punk returns zero); this measures the community `tags`
field instead, ranked by count, which is where the real genre signal lives.

MusicBrainz's hard rate limit (ADR 0013: 1 request/second) is respected with
a fixed sleep between calls, and a transient 503 (routine on MusicBrainz's
shared public instance) is retried with backoff. This is a one-off spike,
not the resumable runner (T073): there is no persisted queue state, so a
run that's interrupted for any other reason starts over from artist 1,
which is fine at this scale and would not be at 30.000+ tracks.
"""

import sys
import time
from pathlib import Path

import httpx

from companion.rb.reader import open_database, read_collection_snapshot

MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
USER_AGENT = "rekordbox-companion-spike/0.1 (T066 research spike)"
REQUEST_INTERVAL_SECONDS = 1.1  # a hair over the 1 req/s limit, not exactly at it
MIN_TAG_COUNT = 2  # drop one-off/noise tags a single user applied once
MAX_TAGS_PER_ARTIST = 3  # coarse genre tags only, per Booking Profile's own grain
SAMPLE_SIZE = 50
MAX_RETRIES = 5  # MusicBrainz's shared public instance returns 503 under load routinely


def _get_with_retry(client: httpx.Client, url: str, params: dict) -> httpx.Response:
    for attempt in range(MAX_RETRIES):
        response = client.get(url, params=params, headers={"User-Agent": USER_AGENT})
        if response.status_code != 503:
            response.raise_for_status()
            return response
        time.sleep(REQUEST_INTERVAL_SECONDS * (2**attempt))
    response.raise_for_status()
    return response


def fetch_artist_tags(client: httpx.Client, artist_name: str) -> list[str]:
    """Top `MAX_TAGS_PER_ARTIST` community tags for the best name match,
    filtered to `MIN_TAG_COUNT`+ so a single stray tag isn't treated as a
    genre. Returns [] on no match or no qualifying tags -- both are a normal
    "not found" outcome for this data source, never an error."""
    # Lucene query syntax: a literal `"` in the name would otherwise end the
    # quoted phrase early and malform the query.
    escaped_name = artist_name.replace('"', '\\"')
    search = _get_with_retry(
        client,
        f"{MUSICBRAINZ_BASE}/artist/",
        {"query": f'artist:"{escaped_name}"', "fmt": "json", "limit": 1},
    )
    artists = search.json().get("artists", [])
    if not artists:
        return []
    mbid = artists[0]["id"]

    time.sleep(REQUEST_INTERVAL_SECONDS)
    lookup = _get_with_retry(
        client, f"{MUSICBRAINZ_BASE}/artist/{mbid}", {"fmt": "json", "inc": "tags"}
    )
    tags = lookup.json().get("tags", [])
    ranked = sorted(tags, key=lambda t: t["count"], reverse=True)
    return [t["name"] for t in ranked if t["count"] >= MIN_TAG_COUNT][:MAX_TAGS_PER_ARTIST]


def main(db_path: Path) -> None:
    tracks = [t for t in read_collection_snapshot(open_database(db_path)) if t.artist]
    unique_artists = sorted({t.artist for t in tracks})
    print(f"{len(tracks)} tracks with a named artist, {len(unique_artists)} unique artists")

    genres_by_artist: dict[str, list[str]] = {}
    with httpx.Client(timeout=15.0) as client:
        for i, artist in enumerate(unique_artists, start=1):
            genres_by_artist[artist] = fetch_artist_tags(client, artist)
            time.sleep(REQUEST_INTERVAL_SECONDS)
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
