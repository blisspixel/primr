"""
Coverage-focused tests for primr.core.recon_context.

Targets the branch-heavy sections that the existing property tests do not
exercise deterministically: AI & Productivity posture, multi-cloud
interpretation, and the security / data / CRM / HR / file-sharing stacks.
"""

from __future__ import annotations

from recon_tool.models import ConfidenceLevel, TenantInfo

from primr.core.recon_context import format_recon_context


def _tenant(**overrides) -> TenantInfo:
    """Build a minimal TenantInfo, overriding only the fields under test."""
    base = {
        "tenant_id": None,
        "display_name": "example.com",
        "default_domain": "example.com",
        "queried_domain": "example.com",
        "confidence": ConfidenceLevel.HIGH,
        "region": None,
        "sources": (),
        "services": (),
        "slugs": (),
        "auth_type": None,
        "dmarc_policy": None,
        "domain_count": 0,
        "tenant_domains": (),
        "related_domains": (),
        "insights": (),
    }
    base.update(overrides)
    return TenantInfo(**base)


def test_header_always_present():
    result = format_recon_context(_tenant())
    assert "Domain Intelligence (DNS Reconnaissance)" in result
    assert "Domain: example.com" in result
    assert "Confidence: high" in result


def test_organization_line_when_display_name_differs():
    info = _tenant(display_name="Acme Corp")
    result = format_recon_context(info)
    assert "Organization: Acme Corp" in result


def test_organization_line_omitted_when_matches_domain():
    result = format_recon_context(_tenant(display_name="example.com"))
    assert "Organization:" not in result


def test_detected_services_section():
    info = _tenant(services=("Microsoft 365", "Salesforce"))
    result = format_recon_context(info)
    assert "--- Detected Services ---" in result
    assert "- Microsoft 365" in result
    assert "- Salesforce" in result


def test_ai_posture_m365():
    info = _tenant(slugs=("microsoft365",))
    result = format_recon_context(info)
    assert "AI & Productivity Posture" in result
    assert "Microsoft 365 domain configuration detected" in result
    assert "Copilot" in result


def test_ai_posture_google_workspace():
    info = _tenant(slugs=("google-workspace",))
    result = format_recon_context(info)
    assert "Google Workspace domain configuration detected" in result
    assert "Gemini for Workspace" in result


def test_ai_posture_detected_ai_tools():
    info = _tenant(slugs=("openai", "anthropic", "glean"))
    result = format_recon_context(info)
    assert "AI provider or product indicators detected" in result
    assert "OpenAI Enterprise" in result
    assert "Anthropic (Claude)" in result
    assert "Glean (Enterprise AI Search)" in result


def test_ai_posture_detects_agent_frameworks_and_llm_tooling():
    """AI slugs beyond the classic providers must surface, not hide in Detected Services."""
    info = _tenant(slugs=("n8n", "dify", "autogen", "crewai-aid", "langsmith", "mcp-discovery"))
    result = format_recon_context(info)
    assert "AI provider or product indicators detected" in result
    for name in ("n8n", "Dify", "AutoGen", "CrewAI", "LangSmith", "Model Context Protocol"):
        assert name in result, name


def test_stack_coverage_rollup_names_the_whole_mixed_stack():
    """A Google-Workspace + AWS + Claude company must have all three surfaced up front."""
    info = _tenant(
        slugs=("google-workspace", "aws-route53", "aws-cloudfront", "anthropic", "okta"),
        auth_type="Federated",
    )
    result = format_recon_context(info)
    assert "Observed Vendor Stack the Strategy Must Address" in result
    assert "not only the email or the primary cloud provider" in " ".join(result.split())
    coverage = result.split("--- AI & Productivity Posture ---")[0]
    assert "Google Workspace" in coverage
    assert "Amazon Web Services (AWS)" in coverage
    assert "Anthropic (Claude)" in coverage
    assert "Okta" in coverage


def test_stack_coverage_rollup_absent_when_nothing_detected():
    result = format_recon_context(_tenant())
    assert "Observed Vendor Stack the Strategy Must Address" not in result


def test_identity_providers_surface_without_auth_type():
    info = _tenant(slugs=("okta",))
    result = format_recon_context(info)
    assert "--- Identity & Auth ---" in result
    assert "Identity provider indicators: Okta" in result


def test_signal_intelligence_section():
    info = _tenant(insights=("Sales-Led Growth: salesforce, hubspot",))
    result = format_recon_context(info)
    assert "--- Signal Intelligence ---" in result
    assert "Recon-derived interpretation to validate: Sales-Led Growth" in result


def test_email_security_with_dmarc_policy():
    info = _tenant(
        dmarc_policy="reject",
        insights=("Email security 3/5 good (DMARC reject)",),
    )
    result = format_recon_context(info)
    assert "--- Email Security ---" in result
    assert "DMARC Policy: reject" in result
    assert "Email security 3/5 good" in result


def test_email_security_from_dmarc_only():
    info = _tenant(dmarc_policy="quarantine")
    result = format_recon_context(info)
    assert "--- Email Security ---" in result
    assert "DMARC Policy: quarantine" in result


def test_identity_auth_section():
    info = _tenant(
        auth_type="Federated",
        insights=("Federated identity via Okta (enterprise SSO)",),
    )
    result = format_recon_context(info)
    assert "--- Identity & Auth ---" in result
    assert "Auth Type: Federated" in result
    assert "Federated identity via Okta" in result


def test_infrastructure_azure_only():
    info = _tenant(slugs=("azure-dns", "azure-cdn"))
    result = format_recon_context(info)
    assert "--- Infrastructure ---" in result
    assert "Azure infrastructure detected" in result


def test_infrastructure_multicloud_azure_and_aws():
    info = _tenant(slugs=("azure-dns", "aws-route53"))
    result = format_recon_context(info)
    assert "Azure infrastructure detected" in result
    assert "AWS infrastructure detected" in result
    assert "Multiple public-cloud infrastructure signals observed" in result


def test_infrastructure_gcp():
    info = _tenant(slugs=("gcp-dns", "google-trust"))
    result = format_recon_context(info)
    assert "GCP infrastructure detected" in result


def test_infrastructure_from_insight_only():
    info = _tenant(insights=("Infrastructure: Cloudflare, AWS CloudFront",))
    result = format_recon_context(info)
    assert "--- Infrastructure ---" in result
    assert "Infrastructure: Cloudflare" in result


def test_security_stack_section():
    info = _tenant(slugs=("crowdstrike", "okta", "zscaler"))
    result = format_recon_context(info)
    assert "--- Security Stack ---" in result
    # sorted output
    assert "- crowdstrike" in result
    assert "- okta" in result
    assert "- zscaler" in result


def test_data_analytics_stack_section():
    info = _tenant(slugs=("snowflake", "databricks", "datadog"))
    result = format_recon_context(info)
    assert "--- Data & Analytics Stack ---" in result
    assert "- snowflake" in result
    assert "- databricks" in result


def test_crm_gtm_stack_section():
    info = _tenant(slugs=("salesforce", "hubspot", "gong"))
    result = format_recon_context(info)
    assert "--- CRM & Go-to-Market Stack ---" in result
    assert "- salesforce" in result
    assert "- gong" in result


def test_hr_operations_stack_section():
    info = _tenant(slugs=("workday", "rippling"))
    result = format_recon_context(info)
    assert "--- HR & Operations Stack ---" in result
    assert "- workday" in result


def test_file_sharing_collaboration_section():
    info = _tenant(slugs=("box", "dropbox"))
    result = format_recon_context(info)
    assert "--- File Sharing & Collaboration ---" in result
    assert "- box" in result
    assert "- dropbox" in result


def test_all_optional_sections_omitted_when_empty():
    result = format_recon_context(_tenant())
    for header in (
        "Detected Services",
        "AI & Productivity Posture",
        "Signal Intelligence",
        "Email Security",
        "Identity & Auth",
        "Infrastructure",
        "Security Stack",
        "Data & Analytics Stack",
    ):
        assert f"--- {header} ---" not in result
