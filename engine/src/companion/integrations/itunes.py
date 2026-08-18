"""iTunes Search API integration: Store Link lookup for Missing Tracks
(T055, US4, FR-020).

* **Fixed outbound host only** (ASVS V10/V14, SSRF). Every request targets
  `ITUNES_HOST` via the fixed `/search` path; artist/title are passed as
  the `term` query parameter's VALUE, never used to build the host or
  path -- the same "fixed endpoint, user data only ever a parameter value"
  discipline `integrations/spotify.py` establishes. `build_client()` routes
  through `security.build_allowlisted_client` (T090), the process-wide
  outbound allowlist backstop that refuses this module's own request if it
  were ever built with the wrong host.
* **No auth, no secrets.** The Search API is public and unauthenticated;
  nothing here needs redaction.
* **Best-effort auto-pick.** Apple's own relevance ranking is a reasonable
  prior, but a `rapidfuzz` score against the query (artist/title) picks
  among the top few results rather than blindly trusting result order --
  consistent with this project's fuzzy-matching-first philosophy (ADR
  0003). Deliberately NOT `matching/normalize.py`'s `normalize()`: that
  function strips bracketed content unconditionally (by design, for
  FR-004's remix-agnostic Spotify/Rekordbox comparison), which would make
  "One More Time" and "One More Time (Live)" compare as identical here --
  exactly the wrong outcome when picking a Store Link, where a live/cover
  version IS the wrong track page. This module's own light-touch
  comparison keeps bracketed words in play instead.
"""

import re
from dataclasses import dataclass

import httpx
from rapidfuzz import fuzz

from companion import security

ITUNES_HOST = "itunes.apple.com"
SEARCH_URL = f"https://{ITUNES_HOST}/search"
STOREFRONT_COUNTRY = "NL"  # FR-020: Dutch storefront
RESULT_LIMIT = 5

# ADR 0011: the free-tier iTunes Search API allows roughly 20 requests per
# minute. A hair over the resulting 3s-per-call cadence, the same margin
# `enrichment/musicbrainz.py`'s REQUEST_INTERVAL_SECONDS keeps over its own
# documented limit. Callers that issue more than one lookup per request
# cycle (api/missing.py's refresh_links) must sleep this long between calls.
REQUEST_INTERVAL_SECONDS = 3.1


def build_client() -> httpx.Client:
    """A short-lived httpx client for one request cycle, matching
    `integrations/spotify.py`'s factory-not-global pattern (test
    injection via `httpx.MockTransport`). Routed through
    `security.build_allowlisted_client` (T090), the outbound allowlist
    backstop this module's own docstring already commits to."""
    return security.build_allowlisted_client(timeout=15.0)


class StoreLookupError(Exception):
    """A `find_store_link` call failed: a non-2xx response (including the
    free-tier rate limit's 403) or a network-level failure. Mirrors
    `integrations/spotify.py`'s `*Error` family (e.g.
    `PlaylistUnreachableError`) so a caller (api/missing.py) can catch one
    typed exception instead of letting a raw `httpx.HTTPError` reach FastAPI
    as an unhandled 500 -- exactly what `response.raise_for_status()` used
    to do here (review finding: a queue of open Missing Tracks large enough
    to hit the rate limit mid-loop turned into one uncaught exception)."""


@dataclass(frozen=True)
class StoreLinkResult:
    itunes_track_id: str | None
    url: str | None


def find_store_link(client: httpx.Client, artist: str, title: str) -> StoreLinkResult:
    """Look up the NL Apple Music / iTunes Store page for `artist`/`title`.

    Returns `StoreLinkResult(None, None)` when nothing is found (spec.md
    US4 scenario 5: "no link was found", not an error) -- this is a normal
    outcome for an obscure or mistagged track, never raised as an
    exception. A failed REQUEST (rate limit, network error) raises
    `StoreLookupError` instead, distinct from "found nothing".
    """
    try:
        response = client.get(
            SEARCH_URL,
            params={
                "term": f"{artist} {title}",
                "country": STOREFRONT_COUNTRY,
                "entity": "song",
                "limit": RESULT_LIMIT,
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # httpx.HTTPError is the shared base of both raise_for_status()'s
        # HTTPStatusError and a network-level RequestError (DNS, timeout,
        # connection refused) -- one except clause covers every way this
        # request can fail.
        raise StoreLookupError(f"iTunes Search API request failed: {exc}") from exc
    results = response.json().get("results", [])
    best = _pick_best(artist, title, results)
    if best is None:
        return StoreLinkResult(itunes_track_id=None, url=None)
    return StoreLinkResult(itunes_track_id=str(best["trackId"]), url=best["trackViewUrl"])


_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9\s]")
_EXTRA_WHITESPACE = re.compile(r"\s+")


def _comparison_key(text: str) -> str:
    """Lowercase, punctuation-light text for scoring candidates.

    Unlike `matching/normalize.py`'s `normalize()`, bracket CHARACTERS are
    dropped but their contents are kept as ordinary words -- "(Live)"
    becomes "live", not nothing -- so a live/cover/remix annotation the
    query doesn't have still lowers the fuzzy score against it.
    """
    result = text.replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ")
    result = _NON_ALPHANUMERIC.sub("", result.lower())
    return _EXTRA_WHITESPACE.sub(" ", result).strip()


def _pick_best(artist: str, title: str, results: list[dict]) -> dict | None:
    if not results:
        return None
    # token_sort_ratio, not token_set_ratio: token_set_ratio is deliberately
    # lenient about one side having *extra* words, which is exactly wrong
    # here -- a candidate with an extra "live"/"cover"/"remix" word must
    # score lower than an exact match, not tie with it.
    query = _comparison_key(f"{artist} {title}")
    scored = [
        (
            fuzz.token_sort_ratio(
                query, _comparison_key(f"{r.get('artistName', '')} {r.get('trackName', '')}")
            ),
            r,
        )
        for r in results
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]
