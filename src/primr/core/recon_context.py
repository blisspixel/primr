"""
Recon context formatter: converts TenantInfo into a structured text block
for injection into strategy prompts.

Pure function module with no side effects or I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from recon_tool.models import TenantInfo

__all__ = [
    "SECTION_DETECTED_SERVICES",
    "SECTION_EMAIL_SECURITY",
    "SECTION_IDENTITY_AUTH",
    "SECTION_INFRASTRUCTURE",
    "SECTION_SIGNAL_INTELLIGENCE",
    "format_recon_context",
]

# Section headers used in the formatted output
SECTION_DETECTED_SERVICES = "Detected Services"
SECTION_SIGNAL_INTELLIGENCE = "Signal Intelligence"
SECTION_EMAIL_SECURITY = "Email Security"
SECTION_IDENTITY_AUTH = "Identity & Auth"
SECTION_INFRASTRUCTURE = "Infrastructure"


def format_recon_context(info: TenantInfo) -> str:
    """Format TenantInfo into a structured text block for strategy prompts.

    Produces a human-readable, strategy-oriented text block with labeled sections.
    Omits sections when the underlying data is empty.
    Written to be consumed by Deep Research as additional context alongside
    the strategic report and vendor research.

    Args:
        info: TenantInfo from resolve_tenant()

    Returns:
        Formatted string suitable for Deep Research prompt injection.
    """
    sections: list[str] = []

    # Header is always present.
    sections.append("=== Domain Intelligence (DNS Reconnaissance) ===")
    sections.append("")
    sections.append(
        "This section contains observed public configuration signals from DNS records "
        "and Microsoft endpoints. A signal can support a hypothesis that a service is "
        "configured, integrated, evaluated, or recently used. It does not by itself "
        "prove an active contract, production adoption, primary platform, workload "
        "placement, maturity, or spend. Preserve the stated confidence, corroborate "
        "with other evidence, and name what must be validated."
    )
    sections.append("")
    sections.append(f"Domain: {info.queried_domain}")
    if info.display_name and info.display_name != info.queried_domain:
        sections.append(f"Organization: {info.display_name}")
    sections.append(f"Confidence: {info.confidence.value}")
    sections.append("")

    # Detected services, categorized for strategic relevance.
    if info.services:
        sections.append(f"--- {SECTION_DETECTED_SERVICES} ---")
        sections.append(
            "These services were detected via DNS TXT, SPF, MX, CNAME, and NS records. "
            "Treat each as a service indicator, not proof of an active vendor relationship."
        )
        for svc in info.services:
            sections.append(f"  - {svc}")
        sections.append("")

    # AI and productivity intelligence is the key strategic signal.
    ai_slugs = {"openai", "anthropic", "mistral", "perplexity", "glean"}
    detected_ai = [s for s in info.slugs if s in ai_slugs]
    m365_detected = "microsoft365" in info.slugs
    gws_detected = "google-workspace" in info.slugs

    if detected_ai or m365_detected or gws_detected:
        sections.append("--- AI & Productivity Posture ---")
        if m365_detected:
            sections.append(
                "  Microsoft 365 domain configuration detected. Treat Microsoft as a likely "
                "productivity ecosystem to validate. Evaluate Microsoft 365 Copilot and "
                "adjacent Microsoft services for integration fit, while comparing credible "
                "alternatives and avoiding assumptions about licenses or active use."
            )
        if gws_detected:
            sections.append(
                "  Google Workspace domain configuration detected. Treat Google as a likely "
                "productivity ecosystem to validate. Evaluate Gemini for Workspace and "
                "adjacent Google services for integration fit, while comparing credible "
                "alternatives and avoiding assumptions about licenses or active use."
            )
        if detected_ai:
            ai_names = {
                "openai": "OpenAI (ChatGPT Enterprise)",
                "anthropic": "Anthropic (Claude)",
                "mistral": "Mistral AI",
                "perplexity": "Perplexity Enterprise",
                "glean": "Glean (Enterprise AI Search)",
            }
            ai_list = [ai_names.get(s, s) for s in detected_ai]
            sections.append(
                f"  AI provider or product indicators detected: {', '.join(ai_list)}. "
                "These may reflect domain verification, evaluation, integration, or active use. "
                "Validate scope and ownership before treating them as deployed capabilities."
            )
        sections.append("")

    # Signal intelligence for strategic patterns.
    signal_insights = [i for i in info.insights if ":" in i and not i.startswith("Email security")]
    if signal_insights:
        sections.append(f"--- {SECTION_SIGNAL_INTELLIGENCE} ---")
        sections.append(
            "These signals are derived from cross-referencing detected services. "
            "They are interpretations to corroborate, not direct observations of operating practice."
        )
        for insight in signal_insights:
            sections.append(f"  - Recon-derived interpretation to validate: {insight}")
        sections.append("")

    # Email Security
    email_insights = [
        i for i in info.insights if i.startswith("Email security") or "DMARC" in i or "DKIM" in i
    ]
    if email_insights or info.dmarc_policy:
        sections.append(f"--- {SECTION_EMAIL_SECURITY} ---")
        if info.dmarc_policy:
            sections.append(f"  DMARC Policy: {info.dmarc_policy}")
        for insight in email_insights:
            sections.append(f"  - {insight}")
        sections.append("")

    # Identity & Auth
    if info.auth_type:
        sections.append(f"--- {SECTION_IDENTITY_AUTH} ---")
        sections.append(f"  Auth Type: {info.auth_type}")
        auth_insights = [
            i
            for i in info.insights
            if "identity" in i.lower() or "federated" in i.lower() or "managed" in i.lower()
        ]
        for insight in auth_insights:
            sections.append(f"  - {insight}")
        sections.append("")

    # Infrastructure with strategic interpretation.
    infra_insights = [
        i
        for i in info.insights
        if i.startswith("Infrastructure:") or "cloud" in i.lower() or "DNS:" in i
    ]
    if infra_insights or info.slugs:
        sections.append(f"--- {SECTION_INFRASTRUCTURE} ---")
        # Interpret cloud platform from slugs
        azure_slugs = {"azure-dns", "azure-cdn", "azure-appservice", "azure-tm"}
        aws_slugs = {"aws-route53", "aws-cloudfront", "aws-ses", "aws-acm"}
        gcp_slugs = {"gcp-dns", "google-trust"}
        detected_azure = [s for s in info.slugs if s in azure_slugs]
        detected_aws = [s for s in info.slugs if s in aws_slugs]
        detected_gcp = [s for s in info.slugs if s in gcp_slugs]
        if detected_azure:
            sections.append(f"  Azure infrastructure detected: {', '.join(detected_azure)}")
        if detected_aws:
            sections.append(f"  AWS infrastructure detected: {', '.join(detected_aws)}")
        if detected_gcp:
            sections.append(f"  GCP infrastructure detected: {', '.join(detected_gcp)}")
        if detected_azure and detected_aws:
            sections.append(
                "  Multiple public-cloud infrastructure signals observed: Azure and AWS. "
                "Evaluate an integrated multicloud or hybrid posture, but do not infer that "
                "all workloads or control planes actively use both."
            )
        for insight in infra_insights:
            sections.append(f"  - {insight}")
        sections.append("")

    # Security stack summary for security strategy
    security_slugs = {
        "crowdstrike",
        "sentinelone",
        "knowbe4",
        "proofpoint",
        "mimecast",
        "zscaler",
        "netskope",
        "paloalto",
        "wiz",
        "sophos",
        "okta",
        "duo",
        "1password",
        "jamf",
        "kandji",
        "barracuda",
        "trendmicro",
        "trellix",
        "ping-identity",
        "cyberark",
        "cato",
        "lakera",
    }
    detected_security = [s for s in info.slugs if s in security_slugs]
    if detected_security:
        sections.append("--- Security Stack ---")
        sections.append(
            "These security service indicators were detected via DNS. Use them as "
            "integration clues, not as a standalone measure of security maturity."
        )
        for slug in sorted(detected_security):
            sections.append(f"  - {slug}")
        sections.append("")

    # Data & analytics for data fabric strategy
    data_slugs = {
        "databricks",
        "snowflake",
        "mongodb",
        "dynatrace",
        "segment",
        "datadog",
        "newrelic",
        "pagerduty",
    }
    detected_data = [s for s in info.slugs if s in data_slugs]
    if detected_data:
        sections.append("--- Data & Analytics Stack ---")
        sections.append(
            "These data and observability service indicators were detected. Validate "
            "their scope before using them to assess data maturity or architecture."
        )
        for slug in sorted(detected_data):
            sections.append(f"  - {slug}")
        sections.append("")

    # CRM & GTM for CX strategy
    crm_slugs = {
        "salesforce",
        "hubspot",
        "marketo",
        "pardot",
        "eloqua",
        "klaviyo",
        "6sense",
        "outreach",
        "salesloft",
        "clearbit",
        "demandbase",
        "drift",
        "gong",
        "intercom",
        "apollo",
    }
    detected_crm = [s for s in info.slugs if s in crm_slugs]
    if detected_crm:
        sections.append("--- CRM & Go-to-Market Stack ---")
        sections.append(
            "These CRM and sales or marketing service indicators were detected. Validate "
            "their active scope before drawing conclusions about the go-to-market model."
        )
        for slug in sorted(detected_crm):
            sections.append(f"  - {slug}")
        sections.append("")

    # HR & Operations
    hr_slugs = {"workday", "sap", "ukg", "rippling", "deel"}
    detected_hr = [s for s in info.slugs if s in hr_slugs]
    if detected_hr:
        sections.append("--- HR & Operations Stack ---")
        sections.append(
            "These HR and operations service indicators were detected. Validate active "
            "use and ownership before drawing workforce-management conclusions."
        )
        for slug in sorted(detected_hr):
            sections.append(f"  - {slug}")
        sections.append("")

    # File Sharing & Collaboration
    file_slugs = {"box", "egnyte", "dropbox"}
    detected_file = [s for s in info.slugs if s in file_slugs]
    if detected_file:
        sections.append("--- File Sharing & Collaboration ---")
        sections.append(
            "These file sharing platforms were detected. Multiple platforms may "
            "reflect intentional segmentation, migration, overlap, or dormant configuration. "
            "Treat the explanation as a question to validate."
        )
        for slug in sorted(detected_file):
            sections.append(f"  - {slug}")
        sections.append("")

    return "\n".join(sections)
