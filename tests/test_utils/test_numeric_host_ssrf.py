"""Tests for platform-independent numeric-IP SSRF canonicalization.

The crux of the SSRF hardening: obfuscated IPv4 literals (octal/hex/decimal/
short forms) must canonicalize identically on every OS, real domain names must
never be misread as numeric IPs, and only non-public literals get blocked.
"""

from __future__ import annotations

import pytest

from primr.utils.security import (
    canonicalize_numeric_host,
    is_safe_url,
    numeric_host_block_reason,
)


class TestCanonicalizeNumericHost:
    @pytest.mark.parametrize(
        "host,expected",
        [
            # Dotted decimal (already canonical)
            ("127.0.0.1", "127.0.0.1"),
            ("10.0.0.1", "10.0.0.1"),
            ("8.8.8.8", "8.8.8.8"),
            # Octal dotted-quad (the macOS-divergent case)
            ("0177.0.0.1", "127.0.0.1"),
            ("0177.0.0.01", "127.0.0.1"),
            # Hex dotted
            ("0x7f.0.0.1", "127.0.0.1"),
            ("0x7f.0x0.0x0.0x1", "127.0.0.1"),
            # Bare 32-bit integer
            ("2130706433", "127.0.0.1"),  # 127.0.0.1
            ("2852039166", "169.254.169.254"),  # AWS metadata
            # inet_aton short forms (last part absorbs remaining bytes)
            ("127.1", "127.0.0.1"),
            ("127.0.1", "127.0.0.1"),
            ("0", "0.0.0.0"),
            # Mixed radix
            ("0x0a.0.0.1", "10.0.0.1"),
        ],
    )
    def test_decodes_numeric_forms(self, host, expected):
        assert canonicalize_numeric_host(host) == expected

    @pytest.mark.parametrize(
        "host",
        [
            "acme.example",
            "example.com",
            "sub.domain.co.uk",
            "dead.beef",  # all-hex labels but no 0x prefix -> not numeric
            "cafe.com",
            "localhost",
            "::1",  # IPv6
            "[::1]",
            "",
            "...",
            "1.2.3.4.5",  # too many parts
            "08.0.0.1",  # invalid octal digit
            "999.0.0.1",  # leading part > 255
            "0x100.0.0.1",  # leading part > 255 (hex)
        ],
    )
    def test_returns_none_for_non_numeric_or_invalid(self, host):
        assert canonicalize_numeric_host(host) is None

    def test_short_form_overflow_rejected(self):
        # Two parts: last absorbs 24 bits; 2**24 is out of range.
        assert canonicalize_numeric_host("127.16777216") is None


class TestNumericHostBlockReason:
    @pytest.mark.parametrize(
        "host",
        [
            "0177.0.0.1",  # octal loopback
            "0x7f.0.0.1",  # hex loopback
            "2130706433",  # decimal loopback
            "127.1",  # short loopback
            "2852039166",  # decimal AWS metadata
            "0xa.0.0.1",  # hex private (10.0.0.1)
            "0",  # unspecified 0.0.0.0
            "0300.0250.0.1",  # octal 192.168.0.1 (private)
        ],
    )
    def test_blocks_obfuscated_non_public(self, host):
        assert numeric_host_block_reason(host) is not None

    @pytest.mark.parametrize(
        "host",
        [
            "8.8.8.8",  # public, plain
            "0x08080808",  # public 8.8.8.8 in hex, but genuinely public -> allowed
            "acme.example",  # domain -> not numeric -> None
            "example.com",
        ],
    )
    def test_allows_public_or_domains(self, host):
        assert numeric_host_block_reason(host) is None


class TestIsSafeUrlNumericBackstop:
    @pytest.mark.parametrize(
        "url",
        [
            "http://0177.0.0.1/",
            "http://2130706433/",
            "http://127.1/",
            "http://2852039166/",
        ],
    )
    def test_blocks_obfuscated_loopback_metadata(self, url):
        safe, reason = is_safe_url(url)
        assert safe is False
        assert reason
