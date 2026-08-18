"""T055: iTunes Search API integration -- Store Link lookup (FR-020).

Outbound HTTP is mocked with `httpx.MockTransport` for the lookup-logic
unit tests, matching `test_spotify_integration.py`'s established pattern.
"""

import httpx
import pytest

from companion.integrations import itunes


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _result(artist: str, title: str, track_id: int, url: str) -> dict:
    return {
        "trackId": track_id,
        "artistName": artist,
        "trackName": title,
        "trackViewUrl": url,
    }


def test_find_store_link_hits_the_fixed_itunes_host_with_nl_storefront():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"resultCount": 0, "results": []})

    itunes.find_store_link(_client(handler), "Daft Punk", "One More Time")

    assert captured["url"].startswith("https://itunes.apple.com/search?")
    assert "country=NL" in captured["url"]
    assert "entity=song" in captured["url"]
    assert "Daft" in captured["url"] or "Daft+Punk" in captured["url"]


def test_find_store_link_returns_the_top_exact_match():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "resultCount": 1,
                "results": [
                    _result(
                        "Daft Punk",
                        "One More Time",
                        697195462,
                        "https://music.apple.com/nl/album/one-more-time/697194953?i=697195462",
                    )
                ],
            },
        )

    result = itunes.find_store_link(_client(handler), "Daft Punk", "One More Time")

    assert result.itunes_track_id == "697195462"
    assert result.url == "https://music.apple.com/nl/album/one-more-time/697194953?i=697195462"


def test_find_store_link_picks_the_best_fuzzy_match_among_several_results():
    # Apple's own ranking sometimes leads with a live version, remix, or
    # cover; the exact-title/artist match should still win the auto-pick.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "resultCount": 3,
                "results": [
                    _result("Daft Punk", "One More Time (Live)", 1, "https://example.com/1"),
                    _result("Daft Punk", "One More Time", 2, "https://example.com/2"),
                    _result("Some Cover Band", "One More Time (Cover)", 3, "https://example.com/3"),
                ],
            },
        )

    result = itunes.find_store_link(_client(handler), "Daft Punk", "One More Time")

    assert result.itunes_track_id == "2"


def test_find_store_link_returns_none_none_when_nothing_is_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"resultCount": 0, "results": []})

    result = itunes.find_store_link(_client(handler), "Nonexistent Artist", "Nonexistent Track")

    assert result.itunes_track_id is None
    assert result.url is None


# Review finding: `find_store_link` used to let `response.raise_for_status()`
# raise a raw `httpx.HTTPStatusError` straight out, unlike
# `integrations/spotify.py`'s typed `*Error` family -- a caller had no way
# to catch just this failure mode without also swallowing programming
# errors.
def test_find_store_link_raises_store_lookup_error_on_a_non_2xx_response():
    # e.g. the free-tier ~20/min rate limit's 403.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"errorMessage": "rate limited"})

    with pytest.raises(itunes.StoreLookupError):
        itunes.find_store_link(_client(handler), "Daft Punk", "One More Time")


def test_find_store_link_raises_store_lookup_error_on_a_network_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(itunes.StoreLookupError):
        itunes.find_store_link(_client(handler), "Daft Punk", "One More Time")
