"""T090: ASVS-mapped security pass -- outbound HTTP allowlist enforcement
(ASVS V10/V14, SSRF) and sensitive-file permission checks (ASVS V6/V12).
"""

import stat
from pathlib import Path

import httpx
import pytest

from companion.security import (
    ALLOWED_HOSTS,
    OutboundHostNotAllowedError,
    build_allowlisted_client,
    check_file_not_group_or_world_readable,
)


def test_allowed_hosts_matches_the_documented_allowlist():
    # constraints.md / plan.md's own ASVS V10/V14 answer: exactly these
    # three services, nothing else, ever.
    assert ALLOWED_HOSTS == {
        "api.spotify.com",
        "accounts.spotify.com",
        "itunes.apple.com",
        "musicbrainz.org",
    }


def _mock_transport(status_code: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status_code))  # noqa: ARG005


@pytest.mark.parametrize("host", sorted(ALLOWED_HOSTS))
def test_a_request_to_an_allowed_host_passes_through(host: str):
    client = build_allowlisted_client(transport=_mock_transport())
    response = client.get(f"https://{host}/some/path")
    assert response.status_code == 200


def test_a_request_to_a_disallowed_host_is_refused_before_any_network_io():
    # The whole point of a defense-in-depth backstop: this must raise
    # *before* the wrapped transport (which would otherwise really connect)
    # ever runs -- verified by a wrapped transport that fails the test if
    # it's ever invoked.
    def fail_if_called(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("the wrapped transport must never be reached for a disallowed host")

    client = build_allowlisted_client(transport=httpx.MockTransport(fail_if_called))

    with pytest.raises(OutboundHostNotAllowedError, match="evil.com"):
        client.get("https://evil.com/steal")


def test_a_request_to_a_disallowed_host_is_refused_even_when_it_looks_like_an_allowed_one():
    # A classic SSRF trick: a hostname that merely *contains* or is
    # prefixed/suffixed by an allowed one is not the same host.
    client = build_allowlisted_client(transport=_mock_transport())
    for sneaky_host in (
        "api.spotify.com.evil.com",
        "evil-api.spotify.com.evil.net",
        "notapi.spotify.com",
    ):
        with pytest.raises(OutboundHostNotAllowedError):
            client.get(f"https://{sneaky_host}/")


def test_check_file_permissions_flags_a_group_or_world_readable_file(tmp_path: Path):
    path = tmp_path / "secret"
    path.write_text("SPOTIFY_CLIENT_ID=x")
    path.chmod(0o644)  # group/world readable -- must be flagged

    assert check_file_not_group_or_world_readable(path) is False


def test_check_file_permissions_accepts_an_owner_only_file(tmp_path: Path):
    path = tmp_path / "secret"
    path.write_text("SPOTIFY_CLIENT_ID=x")
    path.chmod(0o600)

    assert check_file_not_group_or_world_readable(path) is True


def test_check_file_permissions_is_true_for_a_missing_file():
    # No file, nothing to leak -- not a permissions problem this check
    # should report (a missing .env is a config problem, a separate concern).
    assert check_file_not_group_or_world_readable(Path("/nonexistent/path/.env")) is True


def test_the_real_env_file_is_not_group_or_world_readable():
    # Real evidence, not just the check function's own unit test: the
    # actual .env this project runs against, checked directly.
    from companion.config import REPO_ROOT

    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        pytest.skip(".env not present in this environment")
    mode = stat.S_IMODE(env_path.stat().st_mode)
    assert mode & 0o077 == 0, f".env is readable/writable beyond its owner: {oct(mode)}"


# Every real test of spotify.py/itunes.py's own request-building logic
# constructs its own httpx.Client(transport=MockTransport(...)) directly,
# bypassing build_client() entirely -- so nothing else would catch a
# regression that reverted build_client() back to a bare httpx.Client().
# The check itself fires before any real transport delegation (see
# _AllowlistTransport.handle_request), so this is safe to run for real: a
# disallowed-host request never reaches the network.
def test_spotify_build_client_routes_through_the_allowlist():
    from companion.integrations import spotify

    with spotify.build_client() as client, pytest.raises(OutboundHostNotAllowedError):
        client.get("https://evil.com/")


def test_itunes_build_client_routes_through_the_allowlist():
    from companion.integrations import itunes

    with itunes.build_client() as client, pytest.raises(OutboundHostNotAllowedError):
        client.get("https://evil.com/")
