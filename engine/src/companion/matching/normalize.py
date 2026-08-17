"""T024: artist/title normalisation and remix-token extraction (FR-004).

Remix/edit marker vocabulary and behaviour are pinned by T020's tests
(`engine/tests/matching/test_normalize.py`): case-insensitive; featuring
credits, remaster suffixes and non-remix bracketed additions stripped;
punctuation and diacritics stripped; remix/edit markers extracted as a
distinct token instead of being left in the normalised comparison text.
Bracketed content is recognised in both `(...)` and `[...]` (the latter a
common Beatport/DJ-pool convention) -- a T024/T025 review finding, since
FR-008's remix veto would otherwise silently miss `[Extended Mix]`-style
markers. Featuring/remaster stripping only fires mid-string, never when the
trigger word is the very first word (also a review finding: a title that
starts with a place name like "Ft. Lauderdale" or a bare year like "2011
Anthem" isn't a credits/remaster marker).
"""

import re
import unicodedata

_REMIX_KEYWORDS = {
    "mix",
    "remix",
    "edit",
    "dub",
    "version",
    "vip",
    "bootleg",
    "flip",
    "rework",
    "extended",
}

_FEATURING_TRAILING = re.compile(r"\s+\b(feat\.|featuring|ft\.)\s+.*$", re.IGNORECASE)
_REMASTER_TRAILING = re.compile(r"\s+-?\s*\d{4}\s*remaster(ed)?\b.*$", re.IGNORECASE)
_BRACKETED = re.compile(r"[(\[]([^)\]]*)[)\]]")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9\s]")
_EXTRA_WHITESPACE = re.compile(r"\s+")


def _has_remix_keyword(phrase: str) -> bool:
    words = re.findall(r"[a-z0-9]+", phrase.lower())
    return any(word in _REMIX_KEYWORDS for word in words)


def extract_remix_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        match.group(1).strip().lower()
        for match in _BRACKETED.finditer(text)
        if _has_remix_keyword(match.group(1))
    )


def normalize(text: str) -> str:
    result = _FEATURING_TRAILING.sub("", text)
    result = _REMASTER_TRAILING.sub("", result)
    result = _BRACKETED.sub("", result)
    result = result.lower()
    result = unicodedata.normalize("NFKD", result)
    result = "".join(char for char in result if not unicodedata.combining(char))
    result = _NON_ALPHANUMERIC.sub("", result)
    return _EXTRA_WHITESPACE.sub(" ", result).strip()
