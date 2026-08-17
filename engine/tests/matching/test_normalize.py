"""T020: Unit tests for normalisation + remix-token extraction (FR-004).

Interface pinned in data-model.md's "Matching engine seam" note (T019 review
finding) and kickoff.md section on matching:
`normalize(text: str) -> str` and `extract_remix_tokens(text: str) -> tuple[str, ...]`.
Both take a raw artist or title string; rb/index.py (T013) calls `normalize`
for both `norm_artist`/`norm_title` and `extract_remix_tokens` for `title`
only, since remix/edit markers live in the title (kickoff.md section 8).

Committed RED: `companion.matching.normalize` doesn't exist until T024
builds it, same US1 red/green split as T019 (owner-confirmed).

The remix/edit marker vocabulary isn't specified anywhere beyond "remix/edit
markers" (FR-004) and kickoff.md's examples ("radio edit", remixes). This
test file fixes a concrete, minimal vocabulary as the working definition for
T024 to implement: mix, remix, edit, dub, version, vip, bootleg, flip,
rework, extended -- the common DJ-pool naming conventions kickoff.md's own
examples draw from. Extending the vocabulary later is a normal code change,
not a spec change, as long as FR-008's veto behaviour (differing markers
never auto-match) still holds.
"""

from companion.matching.normalize import extract_remix_tokens, normalize


def test_normalize_lowercases():
    assert normalize("DAFT PUNK") == "daft punk"


def test_normalize_strips_leading_trailing_whitespace():
    assert normalize("  Daft Punk  ") == "daft punk"


def test_normalize_strips_featuring_credit_parenthetical():
    assert normalize("One More Time (feat. Romanthony)") == "one more time"


def test_normalize_strips_featuring_credit_trailing():
    assert normalize("One More Time feat. Romanthony") == "one more time"


def test_normalize_strips_ft_abbreviation():
    assert normalize("Blame It ft. T-Pain") == "blame it"


def test_normalize_strips_remaster_suffix():
    assert normalize("Voyager - 2011 Remaster") == "voyager"


def test_normalize_strips_remastered_parenthetical():
    assert normalize("Voyager (Remastered 2011)") == "voyager"


def test_normalize_strips_non_remix_bracketed_addition():
    assert normalize("Discovery (Bonus Track)") == "discovery"


def test_normalize_strips_punctuation():
    assert normalize("Don't Stop the Music!") == "dont stop the music"


def test_normalize_strips_diacritics():
    assert normalize("Café del Mar") == "cafe del mar"


def test_normalize_collapses_internal_whitespace_left_by_stripping():
    assert normalize("Voyager   - 2011 Remaster") == "voyager"


def test_normalize_removes_remix_marker_from_normalized_text():
    # The marker itself is kept aside by extract_remix_tokens, not left
    # behind in the normalized comparison text (FR-004).
    assert normalize("One More Time (Club Mix)") == "one more time"


def test_extract_remix_tokens_finds_mix_marker():
    assert extract_remix_tokens("One More Time (Club Mix)") == ("club mix",)


def test_extract_remix_tokens_finds_radio_edit():
    assert extract_remix_tokens("Voyager (Radio Edit)") == ("radio edit",)


def test_extract_remix_tokens_finds_bare_remix_word():
    assert extract_remix_tokens("Around the World (Remix)") == ("remix",)


def test_extract_remix_tokens_is_empty_when_no_marker_present():
    assert extract_remix_tokens("Discovery") == ()


def test_extract_remix_tokens_is_case_insensitive():
    assert extract_remix_tokens("Voyager (RADIO EDIT)") == ("radio edit",)


def test_extract_remix_tokens_ignores_non_remix_bracketed_addition():
    assert extract_remix_tokens("Discovery (Bonus Track)") == ()
