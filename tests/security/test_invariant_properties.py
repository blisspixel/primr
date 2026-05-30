"""Property-based invariant for the SSRF guard's result shape.

`is_safe_url` is a security boundary: callers branch on `(safe, reason)`. The
invariant is that the result is *always* well-formed — `(True, None)` for a safe
URL or `(False, <non-empty message>)` for a blocked one, never `(False, None)`
(which would log/raise with no reason) or `(True, <message>)`. This locks the
shape across all the early-return paths so a future edit can't introduce a
reason-less rejection.

DNS is mocked to a fixed public IP so the test is deterministic and never makes
a real network call; literal private/metadata IPs are still rejected by the
pre-DNS checks.
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from primr.utils.security import is_safe_url

_SCHEMES = st.sampled_from(["http", "https", "ftp", "file", "javascript", "gopher", ""])
_HOSTS = st.sampled_from(
    [
        "example.com",
        "sub.example.org",
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "metadata.google.internal",
        "localhost",
        "[::1]",
        "0.0.0.0",
        "192.168.1.1",
        "",
    ]
)
_PATHS = st.sampled_from(["", "/", "/path", "/a/b?q=1#frag"])


@st.composite
def _urls(draw) -> str:
    return f"{draw(_SCHEMES)}://{draw(_HOSTS)}{draw(_PATHS)}"


class TestIsSafeUrlWellFormed:
    @given(_urls())
    def test_result_is_always_well_formed(self, url):
        # Resolve any hostname to a fixed public IP — no real DNS / network.
        fake = [(2, 1, 6, "", ("93.184.216.34", 0))]
        with patch("socket.getaddrinfo", return_value=fake):
            safe, reason = is_safe_url(url)

        assert isinstance(safe, bool)
        if safe:
            assert reason is None
        else:
            assert isinstance(reason, str)
            assert reason  # non-empty
