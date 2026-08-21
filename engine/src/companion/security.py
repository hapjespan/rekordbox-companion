"""Process-wide outbound HTTP allowlist (ASVS V10/V14, SSRF) and sensitive-
file permission checks (ASVS V6/V12) -- T090, the polish-phase security
pass `integrations/itunes.py` already names as owing this.

Every integration module (`integrations/spotify.py`, `integrations/itunes.py`,
`enrichment/musicbrainz.py`) already only ever builds request URLs from its
own fixed host constant, with user data interpolated solely into query
parameters or path segments after that fixed prefix -- never the host. This
module is the defense-in-depth backstop for that discipline: a transport-
level check that refuses any request whose host isn't on the fixed
allowlist, so a future bug (a typo'd f-string, a dependency that builds a
URL from unexpected input) fails loudly and immediately, before any real
network I/O, rather than quietly reaching an arbitrary host.
"""

import os
import stat
from pathlib import Path

import httpx

# Every outbound host this app is ever allowed to reach. Extends
# constraints.md/plan.md's own ASVS V10/V14 answer (api.spotify.com,
# itunes.apple.com, musicbrainz.org) with accounts.spotify.com, which those
# documents omit but integrations/spotify.py's OAuth token exchange and
# refresh genuinely need -- without it, login/refresh would be broken, not
# more secure.
ALLOWED_HOSTS = frozenset(
    {
        "api.spotify.com",
        "accounts.spotify.com",
        "itunes.apple.com",
        "musicbrainz.org",
    }
)


class OutboundHostNotAllowedError(Exception):
    """Raised when code attempts an outbound HTTP request to a host outside
    `ALLOWED_HOSTS`. Should never fire in production -- if it does, some
    caller built a request from the wrong host, and the request must not
    proceed."""


class _AllowlistTransport(httpx.BaseTransport):
    """Wraps a real transport, checking the host before ever delegating to
    it. Exact set-membership, not a prefix/suffix check: immune to the
    classic SSRF trick of a hostname that merely contains or is
    prefixed/suffixed by an allowed one (`api.spotify.com.evil.com`).

    Scope: checks the hostname string in the request URL, not a resolved
    IP address -- it constrains which name gets contacted, not what that
    name resolves to (DNS rebinding is out of scope). A deliberate,
    correctly-sized limitation for this app's actual threat model (a
    local-first, single-user desktop app on a trusted network), not an
    oversight.
    """

    def __init__(self, wrapped: httpx.BaseTransport):
        self._wrapped = wrapped

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host not in ALLOWED_HOSTS:
            raise OutboundHostNotAllowedError(
                f"outbound request to {request.url.host!r} is not on the allowlist "
                f"{sorted(ALLOWED_HOSTS)}"
            )
        return self._wrapped.handle_request(request)


def build_allowlisted_client(
    *, transport: httpx.BaseTransport | None = None, **kwargs
) -> httpx.Client:
    """An `httpx.Client` whose every request is checked against
    `ALLOWED_HOSTS` before it reaches the real transport. `transport`
    defaults to a real `httpx.HTTPTransport()`; tests inject an
    `httpx.MockTransport` the same way the integration modules' own
    `build_client()` factories already do."""
    inner = transport if transport is not None else httpx.HTTPTransport()
    return httpx.Client(transport=_AllowlistTransport(inner), **kwargs)


def check_file_not_group_or_world_readable(path: Path) -> bool:
    """ASVS V6/V12: a secrets-bearing file (`.env`, a token file) must not
    be readable or writable by anyone but its owner. Returns True (nothing
    to flag) for a file that doesn't exist -- a missing file can leak
    nothing, and "does this file exist" is a separate, config-level
    concern from this check's job."""
    if not path.exists():
        return True
    mode = stat.S_IMODE(os.stat(path).st_mode)
    return mode & 0o077 == 0
