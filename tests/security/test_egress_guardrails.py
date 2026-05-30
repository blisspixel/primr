"""Egress guardrail invariant: no outbound fetch reaches internal services.

primr builds outbound URLs from data the LLM and discovery influence — gap-query
results, sister-subdomains, careers pages, fallback sources. The invariant is
that *every* fetch entry point runs the SSRF guard (`is_safe_url`) on the URL
(and the post-redirect final URL) before touching the network, so an
attacker-controlled page/redirect can't pivot primr into loopback / RFC1918 /
link-local / cloud-metadata endpoints — even though the original company URL
passed the MCP validator.

These tests pin that guard across all three real egress helpers. Literal
blocked IPs are used so the guard rejects them deterministically without any DNS
or network call.
"""

from __future__ import annotations

import pytest

# Loopback, RFC1918, and the cloud-metadata endpoint — all must be refused.
BLOCKED_URLS = [
    "http://169.254.169.254/latest/meta-data/",  # AWS/GCP metadata
    "http://127.0.0.1:8080/admin",  # loopback
    "http://10.0.0.5/internal",  # RFC1918
    "http://[::1]/internal",  # IPv6 loopback
]


class TestEgressGuardrails:
    @pytest.mark.parametrize("url", BLOCKED_URLS)
    def test_httpclient_get_raises_on_ssrf(self, url):
        from primr.data.http_client import HTTPClient

        client = HTTPClient()
        with pytest.raises(ValueError, match=r"SSRF|URL"):
            client.get(url)

    @pytest.mark.parametrize("url", BLOCKED_URLS)
    def test_fallback_http_get_blocks_ssrf(self, url):
        from primr.data.fallback_sources import _http_get

        status, body, final = _http_get(url, timeout=5)
        assert (status, body, final) == (None, None, None)

    @pytest.mark.parametrize("url", BLOCKED_URLS)
    def test_hiring_signals_http_get_blocks_ssrf(self, url):
        from primr.data.hiring_signals import _http_get

        status, body, final = _http_get(url, timeout=5)
        assert (status, body, final) == (None, None, None)

    def test_public_url_is_not_blocked_by_the_guard(self):
        """Sanity: the guard itself accepts a normal public URL (so the blocks
        above are real SSRF rejections, not the guard refusing everything)."""
        from primr.utils.security import is_safe_url

        safe, _reason = is_safe_url("https://example.com/page")
        assert safe is True
