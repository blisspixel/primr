"""Tests for portable URL component extraction."""

from __future__ import annotations

import pytest

from primr.utils.url_helpers import (
    hostname_is_same_or_subdomain,
    normalized_hostname,
    normalized_web_origin,
    public_web_url,
    safe_hostname_token,
    web_url_is_external,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://Example.COM:8443/path", "example.com"),
        ("https://user:secret@example.com/path", "example.com"),
        ("example.com:8443/path", "example.com"),
        ("https://[2001:db8::1]:8443/path", "2001:db8::1"),
        ("https://example.com./path", "example.com"),
        ("", ""),
        ("https://[invalid", ""),
        ("https://example.com:bad/path", ""),
        ("javascript:alert(1)", ""),
    ],
)
def test_normalized_hostname_excludes_authority_metadata(url: str, expected: str) -> None:
    assert normalized_hostname(url) == expected


def test_normalized_hostname_strips_only_leading_www() -> None:
    assert normalized_hostname("https://www.example.com", strip_www=True) == "example.com"
    assert normalized_hostname("https://notwww.example.com", strip_www=True) == "notwww.example.com"


def test_normalized_hostname_uses_idna_without_casefold_collision() -> None:
    assert normalized_hostname("https://faß.de") == "xn--fa-hia.de"
    assert normalized_hostname("https://fass.de") == "fass.de"


def test_normalized_web_origin_removes_userinfo_and_preserves_valid_port() -> None:
    assert (
        normalized_web_origin("https://user:secret@example.com:8443/private")
        == "https://example.com:8443"
    )


def test_public_web_url_removes_userinfo_but_preserves_resource_components() -> None:
    assert (
        public_web_url("https://user:secret@faß.de:8443/a?q=1#part")
        == "https://xn--fa-hia.de:8443/a?q=1#part"
    )


@pytest.mark.parametrize(
    "url",
    [
        "mailto:user@example.com",
        "ftp:user@example.com",
        "data:text@example.com",
        "javascript:80",
        "ftp:21",
        "foo.bar:user@example.com",
        "custom+scheme:80",
    ],
)
def test_public_web_url_rejects_non_web_schemes_without_slashes(url: str) -> None:
    assert public_web_url(url) == ""


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("example.com:8443/path", "https://example.com:8443/path"),
        ("localhost:8080/health", "https://localhost:8080/health"),
    ],
)
def test_public_web_url_accepts_unambiguous_scheme_less_host_ports(url: str, expected: str) -> None:
    assert public_web_url(url) == expected


def test_hostname_boundary_match_rejects_lookalike_domain() -> None:
    assert hostname_is_same_or_subdomain("https://news.acme.com", "acme.com")
    assert not hostname_is_same_or_subdomain("https://notacme.com", "acme.com")


def test_hostname_boundary_match_does_not_widen_www_specific_parent() -> None:
    assert hostname_is_same_or_subdomain("https://docs.www.acme.com", "www.acme.com")
    assert not hostname_is_same_or_subdomain("https://news.acme.com", "www.acme.com")


@pytest.mark.parametrize(
    "candidate",
    [
        "http://www.acme.com/article",
        "https://acme.com/article",
        "https://news.acme.com/article",
    ],
)
def test_external_web_url_rejects_same_site_variants(candidate: str) -> None:
    assert not web_url_is_external(candidate, "https://www.acme.com")


def test_external_web_url_accepts_distinct_hostname_boundary() -> None:
    assert web_url_is_external("https://notacme.com/article", "https://acme.com")


@pytest.mark.parametrize("candidate", ["", "not a URL", "javascript:alert(1)"])
def test_external_web_url_rejects_invalid_candidates(candidate: str) -> None:
    assert not web_url_is_external(candidate, "https://acme.com")


def test_safe_hostname_token_excludes_ipv6_separators() -> None:
    token = safe_hostname_token("https://[2001:db8::1]:8443/path")

    assert token == "2001_db8_1"
