"""T072: the MusicBrainz GenreSource adapter (ADR 0013 rate limit, ADR 0018
tags-by-count). Outbound HTTP is mocked with `httpx.MockTransport`, matching
`test_itunes.py`'s established pattern -- MusicBrainz's own public instance
is shared, rate-limited infrastructure, unsuitable for the regular suite
(verified live and manually, once, for T066's spike)."""

import httpx
import pytest

from companion.enrichment.musicbrainz import MusicBrainzGenreSource


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _search_response(mbid: str | None) -> httpx.Response:
    artists = [{"id": mbid}] if mbid else []
    return httpx.Response(200, json={"artists": artists})


def _tags_response(tags: list[tuple[str, int]]) -> httpx.Response:
    return httpx.Response(200, json={"tags": [{"name": n, "count": c} for n, c in tags]})


def test_genres_for_ranks_tags_by_count_above_the_minimum():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "tags" in str(request.url):
            return _tags_response([("electronic", 40), ("house", 20), ("one-off", 1), ("disco", 4)])
        return _search_response("mbid-1")

    source = MusicBrainzGenreSource(_client(handler), sleep=lambda _: None)
    genres = source.genres_for("Daft Punk")

    assert genres == ["electronic", "house", "disco"]  # top 3, "one-off" (count 1) dropped
    assert len(calls) == 2


def test_genres_for_returns_empty_list_when_artist_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return _search_response(None)

    source = MusicBrainzGenreSource(_client(handler), sleep=lambda _: None)
    assert source.genres_for("Totally Obscure Artist") == []


def test_genres_for_returns_empty_list_when_no_tags_qualify():
    def handler(request: httpx.Request) -> httpx.Response:
        if "tags" in str(request.url):
            return _tags_response([("one-off", 1)])
        return _search_response("mbid-1")

    source = MusicBrainzGenreSource(_client(handler), sleep=lambda _: None)
    assert source.genres_for("Some Artist") == []


def test_genres_for_uses_only_the_first_credited_artist_of_a_joined_name():
    captured_queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "tags" in str(request.url):
            return _tags_response([("hardstyle", 10)])
        captured_queries.append(str(request.url))
        return _search_response("mbid-1")

    source = MusicBrainzGenreSource(_client(handler), sleep=lambda _: None)
    source.genres_for("Zombie Nation, James Hype, Sean Paul")

    assert "Zombie+Nation" in captured_queries[0]
    assert "James" not in captured_queries[0]


def test_genres_for_escapes_a_literal_quote_in_the_artist_name():
    captured_queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "tags" in str(request.url):
            return _tags_response([])
        captured_queries.append(str(request.url))
        return _search_response(None)

    source = MusicBrainzGenreSource(_client(handler), sleep=lambda _: None)
    source.genres_for('Artist "Nickname" Name')

    assert '\\"Nickname\\"' in captured_queries[0] or "%5C%22Nickname%5C%22" in captured_queries[0]


def test_genres_for_retries_a_transient_503():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "tags" not in str(request.url):
            return _search_response("mbid-1")
        attempts["n"] += 1
        if attempts["n"] < 2:
            return httpx.Response(503)
        return _tags_response([("techno", 5)])

    source = MusicBrainzGenreSource(_client(handler), sleep=lambda _: None)
    assert source.genres_for("Some Artist") == ["techno"]
    assert attempts["n"] == 2


def test_genres_for_raises_after_exhausting_retries_on_persistent_503():
    def handler(request: httpx.Request) -> httpx.Response:
        if "tags" not in str(request.url):
            return _search_response("mbid-1")
        return httpx.Response(503)

    source = MusicBrainzGenreSource(_client(handler), sleep=lambda _: None, max_retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        source.genres_for("Some Artist")
