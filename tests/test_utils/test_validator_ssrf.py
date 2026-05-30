"""Tests for validate_url_for_request authority-parsing hardening.

Regression guard for the SSRF bypass via malformed authority parsing and
the IPv4-mapped IPv6 bypass: the validator must use parsed.hostname
(not netloc.split) and must unwrap ipv4_mapped before checking the IP.
"""

from __future__ import annotations

import pytest

from primr.utils.validators import validate_url_for_request


class TestUserinfoBypass:
    @pytest.mark.parametrize(
        "url",
        [
            "http://x@127.0.0.1/admin",
            "http://x@localhost:8080/",
            "https://x@169.254.169.254/latest/meta-data/",
            "http://attacker@10.0.0.1/",
        ],
    )
    def test_userinfo_does_not_mask_internal_host(self, url: str) -> None:
        # The hand-split netloc parser returned "x" as the host and let
        # these through; the hostname-based parser correctly resolves the
        # authority to the loopback/RFC1918/metadata address.
        ok, _, error = validate_url_for_request(url)
        assert ok is False
        assert error is not None


class TestIPv6BracketedHosts:
    @pytest.mark.parametrize(
        "url",
        [
            "http://[::1]/",
            "http://[fe80::1]/",
        ],
    )
    def test_bracketed_ipv6_internal_blocked(self, url: str) -> None:
        ok, _, error = validate_url_for_request(url)
        assert ok is False
        assert error is not None


class TestPublicHostnamesAccepted:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/",
            "https://example.com/path?q=1",
        ],
    )
    def test_public_urls_pass(self, url: str) -> None:
        ok, normalized, error = validate_url_for_request(url)
        assert ok is True
        assert error is None
        assert normalized.startswith("https://")


class TestDnsFailureFailsClosed:
    def test_unresolvable_host_rejected(self) -> None:
        # The prior implementation allowed unresolvable hosts through,
        # which let the HTTP client resolve the real authority. Fail closed.
        ok, _, error = validate_url_for_request("https://does-not-exist.invalid.primr-test/")
        assert ok is False
        assert error is not None
