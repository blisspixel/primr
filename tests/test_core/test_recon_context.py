"""
Property-based tests for the recon context formatter module.

Tests cover:
- Property 3: Formatter section presence corresponds to non-empty data
- Property 4: Formatter determinism

Feature: recon-platform-integration
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from primr.core.recon_context import (
    SECTION_DETECTED_SERVICES,
    SECTION_EMAIL_SECURITY,
    SECTION_IDENTITY_AUTH,
    SECTION_INFRASTRUCTURE,
    SECTION_SIGNAL_INTELLIGENCE,
    format_recon_context,
)
from primr.recon.models import ConfidenceLevel, TenantInfo

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Realistic service names
_SAMPLE_SERVICES = [
    "Microsoft 365",
    "Salesforce",
    "Google Workspace",
    "Slack",
    "Zoom",
    "AWS SES",
    "Cloudflare CDN",
    "Okta SSO",
    "CrowdStrike Falcon",
    "Snowflake",
    "Databricks",
    "SPF complexity: large (8+ includes)",
    "DNS: Cloudflare",
    "CDN: Akamai",
    "Email: Exchange Online",
]

# Realistic slug names
_SAMPLE_SLUGS = [
    "aws-route53",
    "aws-cloudfront",
    "azure-dns",
    "microsoft365",
    "gcp-dns",
    "google-workspace",
    "okta",
    "crowdstrike",
    "cloudflare",
    "sendgrid",
    "proofpoint",
]

# Realistic insight strings (various categories)
_SIGNAL_INSIGHTS = [
    "AI Adoption: anthropic, openai",
    "Enterprise Security Stack: crowdstrike, okta",
    "Sales-Led Growth: salesforce, hubspot",
    "Infrastructure: Cloudflare, AWS",
    "Security stack: CrowdStrike (endpoint), Okta (identity)",
    "PKI: Let's Encrypt",
]

_EMAIL_INSIGHTS = [
    "Email security 3/5 good (DMARC reject, DKIM, SPF strict)",
    "Email security 0/5 weak (no protections detected)",
    "DMARC: none — email spoofing protection not enforced",
    "No DKIM selectors — email signing not configured",
]

_AUTH_INSIGHTS = [
    "Federated identity via Okta",
    "Federated identity (likely ADFS/Okta/Ping — enterprise SSO)",
    "Cloud-managed identity (Entra ID native)",
]

_INFRA_INSIGHTS = [
    "Infrastructure: Cloudflare, AWS CloudFront",
    "DNS: Route53",
]

_ALL_INSIGHTS = _SIGNAL_INSIGHTS + _EMAIL_INSIGHTS + _AUTH_INSIGHTS + _INFRA_INSIGHTS


# Strategy for generating valid TenantInfo instances
confidence_levels = st.sampled_from(list(ConfidenceLevel))

safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Pd", "Zs")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

domain_text = st.from_regex(r"[a-z][a-z0-9\-]{1,15}\.(com|org|net|io)", fullmatch=True)

tenant_info_strategy = st.builds(
    TenantInfo,
    tenant_id=st.one_of(st.none(), st.uuids().map(str)),
    display_name=safe_text,
    default_domain=domain_text,
    queried_domain=domain_text,
    confidence=confidence_levels,
    region=st.one_of(st.none(), st.sampled_from(["US", "EU", "APAC"])),
    sources=st.tuples(*[st.just(s) for s in ["dns", "oidc"]]).map(tuple) | st.just(()),
    services=st.lists(st.sampled_from(_SAMPLE_SERVICES), min_size=0, max_size=8, unique=True).map(
        tuple
    ),
    slugs=st.lists(st.sampled_from(_SAMPLE_SLUGS), min_size=0, max_size=8, unique=True).map(tuple),
    auth_type=st.one_of(st.none(), st.sampled_from(["Federated", "Managed"])),
    dmarc_policy=st.one_of(st.none(), st.sampled_from(["reject", "quarantine", "none"])),
    domain_count=st.integers(min_value=0, max_value=100),
    tenant_domains=st.just(()),
    related_domains=st.just(()),
    insights=st.lists(st.sampled_from(_ALL_INSIGHTS), min_size=0, max_size=8, unique=True).map(
        tuple
    ),
)

# Strategy for TenantInfo with guaranteed empty fields (for section omission tests)
empty_tenant_info_strategy = st.builds(
    TenantInfo,
    tenant_id=st.none(),
    display_name=domain_text,  # same as queried_domain to skip Organization line
    default_domain=domain_text,
    queried_domain=domain_text,
    confidence=confidence_levels,
    region=st.none(),
    sources=st.just(()),
    services=st.just(()),
    slugs=st.just(()),
    auth_type=st.none(),
    dmarc_policy=st.none(),
    domain_count=st.just(0),
    tenant_domains=st.just(()),
    related_domains=st.just(()),
    insights=st.just(()),
)


def _extract_section_headers(text: str) -> list[str]:
    """Extract --- Section Name --- headers from formatted output."""
    return re.findall(r"^--- (.+?) ---$", text, re.MULTILINE)


# ===========================================================================
# Property 3: Formatter section presence corresponds to non-empty data
# **Validates: Requirements 8.2, 8.1, 8.3, 8.4**
# ===========================================================================


class TestFormatterSectionPresence:
    """Property 3: Formatter section presence corresponds to non-empty data."""

    @given(info=tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_returns_non_empty_string(self, info: TenantInfo):
        """format_recon_context always returns a non-empty string.

        **Validates: Requirements 8.1**
        """
        result = format_recon_context(info)
        assert isinstance(result, str)
        assert len(result) > 0

    @given(info=tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_domain_always_present(self, info: TenantInfo):
        """Domain line is always present in output.

        **Validates: Requirements 8.1**
        """
        result = format_recon_context(info)
        assert f"Domain: {info.queried_domain}" in result

    @given(info=tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_confidence_always_present(self, info: TenantInfo):
        """Confidence line is always present in output.

        **Validates: Requirements 8.1**
        """
        result = format_recon_context(info)
        assert f"Confidence: {info.confidence.value}" in result

    @given(info=tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_detected_services_present_iff_services_non_empty(self, info: TenantInfo):
        """'Detected Services' header present iff info.services is non-empty.

        **Validates: Requirements 8.2, 8.3**
        """
        result = format_recon_context(info)
        has_header = SECTION_DETECTED_SERVICES in _extract_section_headers(result)
        if info.services:
            assert has_header, (
                f"Expected '{SECTION_DETECTED_SERVICES}' header for services={info.services}"
            )
        else:
            assert not has_header, (
                f"'{SECTION_DETECTED_SERVICES}' should be absent when services is empty"
            )

    @given(info=empty_tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_sections_omitted_when_data_empty(self, info: TenantInfo):
        """All optional sections are omitted when their data is empty.

        **Validates: Requirements 8.3, 8.4**
        """
        result = format_recon_context(info)
        headers = _extract_section_headers(result)
        assert SECTION_DETECTED_SERVICES not in headers
        assert SECTION_SIGNAL_INTELLIGENCE not in headers
        assert SECTION_EMAIL_SECURITY not in headers
        assert SECTION_IDENTITY_AUTH not in headers
        assert SECTION_INFRASTRUCTURE not in headers

    @given(info=tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_signal_intelligence_present_iff_signal_insights_exist(self, info: TenantInfo):
        """'Signal Intelligence' header present iff insights contain signal-type entries.

        **Validates: Requirements 8.2, 8.4**
        """
        result = format_recon_context(info)
        has_header = SECTION_SIGNAL_INTELLIGENCE in _extract_section_headers(result)
        signal_insights = [
            i for i in info.insights if ":" in i and not i.startswith("Email security")
        ]
        if signal_insights:
            assert has_header, (
                f"Expected '{SECTION_SIGNAL_INTELLIGENCE}' header for insights={info.insights}"
            )
        else:
            assert not has_header, (
                f"'{SECTION_SIGNAL_INTELLIGENCE}' should be absent when no signal insights"
            )


# ===========================================================================
# Property 4: Formatter determinism
# **Validates: Requirements 8.5**
# ===========================================================================


class TestFormatterDeterminism:
    """Property 4: Formatter determinism."""

    @given(info=tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_identical_output_on_repeated_calls(self, info: TenantInfo):
        """Calling format_recon_context twice produces identical output strings.

        **Validates: Requirements 8.5**
        """
        result1 = format_recon_context(info)
        result2 = format_recon_context(info)
        assert result1 == result2, "Formatter produced different output on repeated calls"

    @given(info=tenant_info_strategy)
    @settings(deadline=None, max_examples=200)
    def test_section_headers_identical_across_calls(self, info: TenantInfo):
        """Section headers extracted from output are identical across calls.

        **Validates: Requirements 8.5**
        """
        result1 = format_recon_context(info)
        result2 = format_recon_context(info)
        headers1 = _extract_section_headers(result1)
        headers2 = _extract_section_headers(result2)
        assert headers1 == headers2, f"Section headers differ: {headers1} vs {headers2}"
