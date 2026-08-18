"""MusicBrainz GenreSource adapter (ADR 0013's rate limit, ADR 0018's source
decision): reads the community `tags` field ranked by count, not the
curated `genres` field, which is too sparse to use in practice (verified
live during T066's spike: even Daft Punk resolves to zero curated genres).

`sleep`/`max_retries` are constructor parameters, not module constants, so
tests can run instantly (`sleep=lambda _: None`) without weakening the real
1 req/s rate limit or the retry-on-503 behaviour they exercise.
"""

import time

import httpx

MUSICBRAINZ_BASE = "https://musicbrainz.org/ws/2"
USER_AGENT = "rekordbox-companion/0.1 (github.com/hapjespan/rekordbox-companion)"
REQUEST_INTERVAL_SECONDS = 1.1  # a hair over MusicBrainz's 1 req/s limit
MIN_TAG_COUNT = 2  # drop one-off/noise tags a single user applied once
MAX_TAGS_PER_ARTIST = 3  # coarse genre tags only, per Booking Profile's own grain
DEFAULT_MAX_RETRIES = 5  # MusicBrainz's shared public instance returns 503 under load routinely


class MusicBrainzGenreSource:
    name = "musicbrainz"

    def __init__(
        self,
        client: httpx.Client,
        sleep=time.sleep,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self._client = client
        self._sleep = sleep
        self._max_retries = max_retries

    def _get_with_retry(self, url: str, params: dict) -> httpx.Response:
        for attempt in range(self._max_retries):
            response = self._client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            if response.status_code != 503:
                response.raise_for_status()
                return response
            self._sleep(REQUEST_INTERVAL_SECONDS * (2**attempt))
        response.raise_for_status()
        return response

    def genres_for(self, artist: str) -> list[str]:
        """Top `MAX_TAGS_PER_ARTIST` community tags for the best name match,
        filtered to `MIN_TAG_COUNT`+. `[]` on no match or no qualifying tags
        -- both a normal "not found" outcome for this source, never raised.
        Rekordbox joins collaborating artists into one comma-separated
        `Artist.Name`; MusicBrainz has no artist by the combined name, so
        only the first credited artist is looked up.
        """
        primary_artist = artist.split(",")[0].strip()
        # Lucene query syntax: a literal `"` would otherwise end the quoted
        # phrase early and malform the query.
        escaped_name = primary_artist.replace('"', '\\"')
        search = self._get_with_retry(
            f"{MUSICBRAINZ_BASE}/artist/",
            {"query": f'artist:"{escaped_name}"', "fmt": "json", "limit": 1},
        )
        artists = search.json().get("artists", [])
        if not artists:
            return []
        mbid = artists[0]["id"]

        self._sleep(REQUEST_INTERVAL_SECONDS)
        lookup = self._get_with_retry(
            f"{MUSICBRAINZ_BASE}/artist/{mbid}", {"fmt": "json", "inc": "tags"}
        )
        tags = lookup.json().get("tags", [])
        ranked = sorted(tags, key=lambda t: t["count"], reverse=True)
        return [t["name"] for t in ranked if t["count"] >= MIN_TAG_COUNT][:MAX_TAGS_PER_ARTIST]
