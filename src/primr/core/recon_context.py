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
    "SECTION_STACK_COVERAGE",
    "format_recon_context",
]

# Section headers used in the formatted output
SECTION_DETECTED_SERVICES = "Detected Services"
SECTION_SIGNAL_INTELLIGENCE = "Signal Intelligence"
SECTION_EMAIL_SECURITY = "Email Security"
SECTION_IDENTITY_AUTH = "Identity & Auth"
SECTION_INFRASTRUCTURE = "Infrastructure"
SECTION_STACK_COVERAGE = "Observed Vendor Stack the Strategy Must Address"

# --- Slug classification maps -------------------------------------------------
# Kept at module scope so the coverage rollup and the detailed sections classify
# every signal identically. Display names follow the recon_tool fingerprint
# catalog (data/fingerprints/*.yaml). The AI set intentionally spans model
# providers, AI-native search, agent frameworks, LLM tooling, and MCP endpoints
# so a Claude/OpenAI/agent-framework signal is never buried in the generic
# service list.
AI_PROVIDER_SLUGS: dict[str, str] = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI Enterprise",
    "mistral": "Mistral AI",
    "perplexity": "Perplexity Enterprise",
    "glean": "Glean (Enterprise AI Search)",
    "n8n": "n8n (workflow automation / AI orchestration)",
    "dify": "Dify (AI app builder)",
    "autogen": "AutoGen (agent framework)",
    "crewai-aid": "CrewAI (agent framework)",
    "langsmith": "LangSmith (LLM observability)",
    "mcp-discovery": "Model Context Protocol endpoint",
}

IDENTITY_PROVIDER_SLUGS: dict[str, str] = {
    "okta": "Okta",
    "auth0": "Auth0 (Okta)",
    "ping-identity": "Ping Identity",
    "onelogin": "OneLogin",
    "duo": "Duo Security",
    "beyond-identity": "Beyond Identity",
    "cisco-identity": "Cisco Identity",
}

AZURE_SLUGS = {"azure-dns", "azure-cdn", "azure-appservice", "azure-tm"}
# Align with platform_mapper: SES/ACM/Google Trust are email/cert signals,
# not enough to declare a primary cloud for strategy.
AWS_SLUGS = {"aws-route53", "aws-cloudfront"}
GCP_SLUGS = {"gcp-dns"}

SECURITY_SLUGS = {
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

DATA_SLUGS = {
    "databricks",
    "snowflake",
    "mongodb",
    "dynatrace",
    "segment",
    "datadog",
    "newrelic",
    "pagerduty",
}

CRM_SLUGS = {
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

HR_SLUGS = {"workday", "sap", "ukg", "rippling", "deel"}

FILE_SLUGS = {"box", "egnyte", "dropbox"}


def _stack_coverage_lines(info: TenantInfo) -> list[str]:
    """Build the up-front coverage rollup naming every observed ecosystem.

    Returns an empty list when nothing strategically relevant was detected, so
    the section is omitted for empty tenants. The rollup exists to stop the
    strategy from anchoring only on the email or the primary cloud provider: it
    names identity, cloud, AI, and key SaaS ecosystems and instructs the model
    to evaluate each one.
    """
    slugs = set(info.slugs)

    productivity: list[str] = []
    if "microsoft365" in slugs:
        productivity.append("Microsoft 365")
    if "google-workspace" in slugs:
        productivity.append("Google Workspace")

    identity = [name for slug, name in IDENTITY_PROVIDER_SLUGS.items() if slug in slugs]
    if info.auth_type and not identity:
        identity.append(f"{info.auth_type} identity (provider not fingerprinted)")

    clouds: list[str] = []
    if slugs & AWS_SLUGS:
        clouds.append("Amazon Web Services (AWS)")
    if slugs & AZURE_SLUGS:
        clouds.append("Microsoft Azure")
    if slugs & GCP_SLUGS:
        clouds.append("Google Cloud (GCP)")

    ai_providers = [name for slug, name in AI_PROVIDER_SLUGS.items() if slug in slugs]

    other: list[str] = []
    if slugs & DATA_SLUGS:
        other.append("data & analytics")
    if slugs & SECURITY_SLUGS:
        other.append("security")
    if slugs & CRM_SLUGS:
        other.append("CRM / go-to-market")
    if slugs & HR_SLUGS:
        other.append("HR & operations")
    if slugs & FILE_SLUGS:
        other.append("file sharing")

    if not any((productivity, identity, clouds, ai_providers, other)):
        return []

    lines = [f"--- {SECTION_STACK_COVERAGE} ---"]
    lines.append(
        "The AI Strategy must evaluate every ecosystem observed below, not only the "
        "email or the primary cloud provider. For each, assess integration fit, AI "
        "capabilities, governance, and at least one credible alternative. Absence of "
        "a category means no public signal was observed, not that the vendor is absent."
    )
    if productivity:
        lines.append(f"  Productivity / Email: {', '.join(productivity)}")
    if identity:
        lines.append(f"  Identity: {', '.join(sorted(identity))}")
    if clouds:
        lines.append(f"  Public cloud: {', '.join(sorted(clouds))}")
    if ai_providers:
        lines.append(f"  AI providers / tools: {', '.join(sorted(ai_providers))}")
    if other:
        lines.append(
            "  Additional detected ecosystems (detailed below): " + ", ".join(sorted(other))
        )
    lines.append("")
    return lines


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

    # Up-front coverage rollup so the strategy addresses the whole observed stack,
    # not just the email or cloud provider. Omitted when nothing was detected.
    sections.extend(_stack_coverage_lines(info))

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
    detected_ai = [s for s in info.slugs if s in AI_PROVIDER_SLUGS]
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
            ai_list = [AI_PROVIDER_SLUGS[s] for s in detected_ai]
            sections.append(
                f"  AI provider or product indicators detected: {', '.join(ai_list)}. "
                "These may reflect domain verification, evaluation, integration, or active use. "
                "Validate scope and ownership before treating them as deployed capabilities. "
                "The strategy must address the AI providers the company already touches, "
                "including how they coexist with any recommended platform."
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
    detected_identity = [s for s in info.slugs if s in IDENTITY_PROVIDER_SLUGS]
    if info.auth_type or detected_identity:
        sections.append(f"--- {SECTION_IDENTITY_AUTH} ---")
        if info.auth_type:
            sections.append(f"  Auth Type: {info.auth_type}")
        if detected_identity:
            id_names = [IDENTITY_PROVIDER_SLUGS[s] for s in detected_identity]
            sections.append(f"  Identity provider indicators: {', '.join(id_names)}")
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
        detected_azure = [s for s in info.slugs if s in AZURE_SLUGS]
        detected_aws = [s for s in info.slugs if s in AWS_SLUGS]
        detected_gcp = [s for s in info.slugs if s in GCP_SLUGS]
        if detected_azure:
            sections.append(f"  Azure infrastructure detected: {', '.join(detected_azure)}")
        if detected_aws:
            sections.append(f"  AWS infrastructure detected: {', '.join(detected_aws)}")
        if detected_gcp:
            sections.append(f"  GCP infrastructure detected: {', '.join(detected_gcp)}")
        multi_cloud = [
            name
            for name, present in (
                ("Azure", detected_azure),
                ("AWS", detected_aws),
                ("GCP", detected_gcp),
            )
            if present
        ]
        if len(multi_cloud) > 1:
            sections.append(
                f"  Multiple public-cloud infrastructure signals observed: {', '.join(multi_cloud)}. "
                "Evaluate an integrated multicloud or hybrid posture, but do not infer that "
                "all workloads or control planes actively use every one."
            )
        for insight in infra_insights:
            sections.append(f"  - {insight}")
        sections.append("")

    # Security stack summary for security strategy
    detected_security = [s for s in info.slugs if s in SECURITY_SLUGS]
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
    detected_data = [s for s in info.slugs if s in DATA_SLUGS]
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
    detected_crm = [s for s in info.slugs if s in CRM_SLUGS]
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
    detected_hr = [s for s in info.slugs if s in HR_SLUGS]
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
    detected_file = [s for s in info.slugs if s in FILE_SLUGS]
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
