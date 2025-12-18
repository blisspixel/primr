"""
AI strategy generation using Deep Research.

This module generates comprehensive AI strategy recommendations:
- Board-level AI roadmaps
- Vendor-specific technology recommendations
- ROI models and prioritization frameworks

Usage:
    from primr.core.ai_strategy import (
        generate_ai_strategy,
        CloudVendor,
        AIStrategyConfig,
    )

    # Generate AI strategy
    result = await generate_ai_strategy(
        company_name="Acme Corp",
        cloud_vendor=CloudVendor.AZURE,
        company_research_path="path/to/research.md"
    )
"""
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from primr.config.config import OUTPUT_DIR, PROJECT_ROOT
from primr.utils.console import console
from primr.utils.logging_config import get_logger

logger = get_logger("ai_strategy")


# =============================================================================
# ENUMS
# =============================================================================

class CloudVendor(Enum):
    """Supported cloud vendors for AI strategy."""
    AZURE = "azure"
    AWS = "aws"
    GCP = "gcp"
    AGNOSTIC = "agnostic"

    @property
    def display_name(self) -> str:
        """Human-readable vendor name."""
        names = {
            "azure": "Microsoft Azure",
            "aws": "Amazon Web Services (AWS)",
            "gcp": "Google Cloud Platform (GCP)",
            "agnostic": "Cloud Agnostic (Multi-Cloud)"
        }
        return names.get(self.value, self.value.upper())

    @classmethod
    def from_string(cls, value: str) -> "CloudVendor":
        """Create CloudVendor from string, case-insensitive."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.AGNOSTIC


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class AIStrategyConfig:
    """Configuration for AI strategy generation."""
    company_name: str
    cloud_vendor: CloudVendor
    company_research_path: str | None = None
    force_refresh_vendor: bool = False
    timeout_seconds: int = 1800  # 30 minutes

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.company_name or not self.company_name.strip():
            errors.append("Company name is required")
        if self.company_research_path:
            if not os.path.exists(self.company_research_path):
                errors.append(f"Company research file not found: {self.company_research_path}")
            elif os.path.getsize(self.company_research_path) == 0:
                errors.append(f"Company research file is empty: {self.company_research_path}")
        return errors


@dataclass
class AIStrategyResult:
    """Result of AI strategy generation."""
    docx_path: str | None
    md_path: str | None
    txt_path: str | None
    content: str
    duration_seconds: float
    vendor_research_paths: list[str]
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.docx_path is not None and self.error is None

    @property
    def output_paths(self) -> list[str]:
        """All generated output paths."""
        paths = []
        if self.docx_path:
            paths.append(self.docx_path)
        if self.md_path:
            paths.append(self.md_path)
        if self.txt_path:
            paths.append(self.txt_path)
        return paths


@dataclass
class StrategyPromptContext:
    """Context for building AI strategy prompts."""
    company_name: str
    cloud_vendor: CloudVendor
    current_date: str
    vendor_guidance: str
    vendor_name: str


# =============================================================================
# PROTOCOLS
# =============================================================================

class StrategyPromptBuilder(Protocol):
    """Protocol for strategy prompt construction."""

    def build(self, context: StrategyPromptContext) -> str:
        """Build the strategy prompt."""
        ...


# =============================================================================
# PUBLIC INTERFACE
# =============================================================================

def generate_ai_strategy_sync(
    company_name: str,
    cloud_vendor: str | CloudVendor,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    on_progress: Callable[[str], None] | None = None
) -> str | None:
    """
    Generate AI strategy using Deep Research (synchronous).

    Args:
        company_name: Name of the company
        cloud_vendor: Cloud vendor preference
        company_research_path: Path to company research markdown
        force_refresh_vendor: If True, regenerate vendor research
        on_progress: Optional progress callback

    Returns:
        Path to generated DOCX file, or None if failed
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(
        generate_ai_strategy(
            company_name=company_name,
            cloud_vendor=cloud_vendor,
            company_research_path=company_research_path,
            force_refresh_vendor=force_refresh_vendor,
            on_progress=on_progress
        )
    )

    return result.docx_path if result.success else None


async def generate_ai_strategy(
    company_name: str,
    cloud_vendor: str | CloudVendor,
    company_research_path: str | None = None,
    force_refresh_vendor: bool = False,
    on_progress: Callable[[str], None] | None = None
) -> AIStrategyResult:
    """
    Generate AI strategy using Deep Research (async).

    Creates comprehensive AI roadmap covering:
    - Strategic thesis and prioritization
    - Quick wins and bigger bets
    - ROI models and governance framework

    Args:
        company_name: Name of the company
        cloud_vendor: Cloud vendor preference (string or CloudVendor enum)
        company_research_path: Path to company research markdown
        force_refresh_vendor: If True, regenerate vendor research
        on_progress: Optional progress callback

    Returns:
        AIStrategyResult with output paths and metadata
    """
    import time
    start_time = time.time()

    # Normalize cloud vendor
    if isinstance(cloud_vendor, str):
        vendor = CloudVendor.from_string(cloud_vendor)
    else:
        vendor = cloud_vendor

    # Build config
    config = AIStrategyConfig(
        company_name=company_name,
        cloud_vendor=vendor,
        company_research_path=company_research_path,
        force_refresh_vendor=force_refresh_vendor
    )

    # Pre-flight validation
    preflight_errors = _validate_preflight(config)
    if preflight_errors:
        for err in preflight_errors:
            console.error(f"  - {err}")
        return AIStrategyResult(
            docx_path=None,
            md_path=None,
            txt_path=None,
            content="",
            duration_seconds=time.time() - start_time,
            vendor_research_paths=[],
            error="; ".join(preflight_errors)
        )

    console.info("Pre-flight checks passed")

    # Gather context files
    context_files, vendor_paths = await _gather_context(config, on_progress)

    # Build prompt
    prompt = build_ai_strategy_prompt(company_name, vendor)

    # Execute Deep Research
    content = await _execute_strategy_research(
        prompt=prompt,
        context_files=context_files,
        timeout=config.timeout_seconds,
        on_progress=on_progress
    )

    if not content:
        return AIStrategyResult(
            docx_path=None,
            md_path=None,
            txt_path=None,
            content="",
            duration_seconds=time.time() - start_time,
            vendor_research_paths=vendor_paths,
            error="AI Strategy research failed"
        )

    # Save outputs
    output_paths = _save_strategy_outputs(
        content=content,
        company_name=company_name,
        cloud_vendor=vendor
    )

    # Track usage
    _track_usage(company_name, content, time.time() - start_time)

    return AIStrategyResult(
        docx_path=output_paths.get("docx"),
        md_path=output_paths.get("md"),
        txt_path=output_paths.get("txt"),
        content=content,
        duration_seconds=time.time() - start_time,
        vendor_research_paths=vendor_paths
    )


def build_ai_strategy_prompt(company_name: str, cloud_vendor: CloudVendor) -> str:
    """
    Build Deep Research prompt for AI strategy.

    Args:
        company_name: Name of the company
        cloud_vendor: Cloud vendor preference

    Returns:
        Complete prompt string for Deep Research
    """
    current_date = datetime.now().strftime("%B %Y")
    vendor_guidance = _get_vendor_guidance(cloud_vendor, current_date)
    vendor_context = _build_vendor_context(cloud_vendor, current_date, vendor_guidance)

    return _build_full_prompt(company_name, current_date, vendor_context)


# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================

def _validate_preflight(config: AIStrategyConfig) -> list[str]:
    """Validate prerequisites for AI strategy generation."""
    from primr.config.settings import get_settings

    errors = config.validate()

    # Validate API key
    settings = get_settings()
    if not settings.api.gemini_key:
        errors.append("GEMINI_API_KEY not configured")

    # Check output directory is writable
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        test_file = os.path.join(OUTPUT_DIR, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception as e:
        errors.append(f"Output directory not writable: {OUTPUT_DIR} ({e})")

    return errors


async def _gather_context(
    config: AIStrategyConfig,
    on_progress: Callable[[str], None] | None = None
) -> tuple[list[str], list[str]]:
    """
    Gather context files for AI strategy generation.

    Returns:
        Tuple of (context_files, vendor_research_paths)
    """
    from primr.core.vendor_research import (
        generate_vendor_research,
        get_or_generate_vendor_research,
    )

    context_files = []
    vendor_paths = []

    # Add company research if provided
    if config.company_research_path and os.path.exists(config.company_research_path):
        context_files.append(config.company_research_path)

    # Get vendor-specific research
    if config.cloud_vendor != CloudVendor.AGNOSTIC:
        vendor_str = config.cloud_vendor.value

        if config.force_refresh_vendor:
            console.info(f"Force refreshing {vendor_str.upper()} vendor research...")
            generated = await generate_vendor_research(vendor_str, on_progress)
            if generated:
                vendor_paths = [generated]
        else:
            result = await get_or_generate_vendor_research(vendor_str, on_progress=on_progress)
            vendor_paths = [str(p) for p in result.paths]

        # Add vendor research to context
        for path in vendor_paths:
            if path and os.path.exists(path):
                context_files.append(path)

        if vendor_paths:
            console.info(f"Using {len(vendor_paths)} {vendor_str.upper()} research doc(s) as context")

    # Always include agnostic research as additional context
    agnostic_path = Path(PROJECT_ROOT) / "docs" / f"vendor-research-agnostic-{datetime.now().strftime('%Y-%m')}.txt"
    if agnostic_path.exists() and str(agnostic_path) not in context_files:
        context_files.append(str(agnostic_path))

    return context_files, vendor_paths


async def _execute_strategy_research(
    prompt: str,
    context_files: list[str],
    timeout: int,
    on_progress: Callable[[str], None] | None = None
) -> str | None:
    """Execute Deep Research for AI strategy."""
    from primr.ai.deep_research import ResearchStatus, get_deep_research_client

    client = get_deep_research_client()

    def progress_callback(progress):
        if progress.message:
            if on_progress:
                on_progress(progress.message)
            console.info(f"AI Strategy: {progress.message}")

    try:
        result = await client.research(
            query=prompt,
            output_format=None,
            on_progress=progress_callback,
            context_files=context_files if context_files else None,
            timeout=timeout
        )

        if result.status != ResearchStatus.COMPLETED or not result.content:
            console.error("AI Strategy research failed")
            return None

        return result.content

    except Exception as e:
        console.error(f"AI Strategy generation failed: {e}")
        logger.exception("AI Strategy error")
        return None


def _save_strategy_outputs(
    content: str,
    company_name: str,
    cloud_vendor: CloudVendor
) -> dict[str, str | None]:
    """Save AI strategy outputs in multiple formats."""
    from primr.output.markdown_converter import markdown_to_docx

    date_str = datetime.now().strftime("%m-%d-%Y")
    base_name = f"{company_name}_AI_Strategy_{date_str}"
    outputs: dict[str, str | None] = {"md": None, "txt": None, "docx": None}

    try:
        # Save markdown
        md_path = os.path.join(OUTPUT_DIR, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        outputs["md"] = md_path
        console.ok(f"AI Strategy MD: {base_name}.md", show_time=False)

        # Save plain text
        txt_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(content)
        outputs["txt"] = txt_path
        console.ok(f"AI Strategy TXT: {base_name}.txt", show_time=False)

        # Convert to DOCX
        docx_path = os.path.join(OUTPUT_DIR, f"{base_name}.docx")
        subtitle_parts = [datetime.now().strftime("%B %d, %Y")]
        subtitle_parts.append(f"Cloud Vendor: {cloud_vendor.value.upper()}")
        subtitle = " | ".join(subtitle_parts)

        try:
            markdown_to_docx(
                markdown_text=content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle
            )
            outputs["docx"] = docx_path
            console.ok(f"AI Strategy DOCX: {base_name}.docx", show_time=False)
        except PermissionError:
            # File locked - try with timestamp
            timestamp = datetime.now().strftime("%H%M%S")
            docx_path = os.path.join(OUTPUT_DIR, f"{base_name}_{timestamp}.docx")
            console.warn(f"Original file locked, saving as: {base_name}_{timestamp}.docx")
            markdown_to_docx(
                markdown_text=content,
                output_path=Path(docx_path),
                title=f"AI Strategy: {company_name}",
                subtitle=subtitle
            )
            outputs["docx"] = docx_path

    except Exception as e:
        console.warn(f"Output generation failed: {e}")
        logger.exception("AI Strategy output error")

    return outputs


def _track_usage(company_name: str, content: str, duration_seconds: float) -> None:
    """Track AI strategy usage for cost monitoring."""
    try:
        from primr.utils.usage_tracker import get_usage_tracker

        # Estimate tokens from content
        output_tokens = len(content) // 4
        input_tokens = 50_000  # Estimated prompt + context

        tracker = get_usage_tracker()
        tracker.record_usage(
            mode="ai-strategy",
            company=company_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_seconds=duration_seconds,
        )
    except Exception as e:
        logger.warning(f"Failed to track usage: {e}")


def _get_vendor_guidance(vendor: CloudVendor, current_date: str) -> str:
    """Get vendor-specific guidance for the prompt."""
    guidance = {
        CloudVendor.AZURE: """
KEY AZURE AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):

Productivity & Copilots:
- Microsoft 365 Copilot (Word, Excel, PowerPoint, Outlook, Teams)
- Copilot Studio (build custom copilots and agents)
- Work IQ (personalized AI based on work patterns)

Agentic AI & Automation:
- Agent 365 (AI agent control plane, governance, monitoring)
- Foundry (unified AI platform for building and deploying agents)
- Power Automate with AI Builder
- Semantic Kernel for agent orchestration

Data & Analytics:
- Microsoft Fabric (unified analytics platform)
- Fabric IQ (semantic layer for AI-ready data)
- Azure AI Search (vector search, RAG)
- Power BI with Copilot

AI Development:
- Azure OpenAI Service (GPT-4, GPT-4o, o1 models)
- Azure AI Foundry (model catalog, fine-tuning)
- GitHub Copilot for developers

Security & Governance:
- Entra Agent ID (identity for AI agents)
- Microsoft Purview (data governance, compliance)
- Microsoft Defender for Cloud (AI security)
- Responsible AI dashboard

Search for the latest announcements from Microsoft Ignite 2025 and recent Azure updates.
""",
        CloudVendor.AWS: """
KEY AWS AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):

Productivity & Assistants:
- Amazon Q (AI assistant for business and developers)
- Amazon Q in Connect (customer service AI)
- Amazon Q Business (enterprise knowledge assistant)

Agentic AI & Automation:
- Amazon Bedrock Agents (autonomous AI agents)
- AWS Step Functions for AI orchestration
- Amazon Bedrock Flows (visual agent builder)

Data & Analytics:
- Amazon SageMaker (ML platform)
- Amazon Bedrock Knowledge Bases (RAG)
- Amazon QuickSight Q (natural language BI)
- AWS Glue for data integration

AI Development:
- Amazon Bedrock (Claude, Llama, Titan, Mistral models)
- Amazon SageMaker JumpStart (model hub)
- Amazon CodeWhisperer for developers
- PartyRock (no-code AI app builder)

Security & Governance:
- Amazon Bedrock Guardrails (content filtering, PII protection)
- AWS IAM for AI access control
- Amazon Macie (data security)
- AWS CloudTrail for AI audit logging

Search for the latest announcements from AWS re:Invent 2024 and recent AWS updates.
""",
        CloudVendor.GCP: """
KEY GOOGLE CLOUD AI SERVICES TO RESEARCH AND RECOMMEND (search for latest as of {current_date}):

Productivity & Assistants:
- Gemini for Google Workspace (Docs, Sheets, Slides, Gmail, Meet)
- Gemini for Google Cloud (cloud console assistant)
- NotebookLM (AI research assistant)

Agentic AI & Automation:
- Vertex AI Agent Builder (build and deploy agents)
- Vertex AI Extensions (connect agents to APIs)
- Google Cloud Workflows for orchestration

Data & Analytics:
- BigQuery with Gemini (natural language SQL)
- Vertex AI Search (enterprise search)
- Looker with Gemini (conversational BI)
- Dataplex for data governance

AI Development:
- Vertex AI (Gemini Pro, Gemini Ultra, PaLM models)
- Vertex AI Model Garden (model catalog)
- Gemini Code Assist for developers
- Vertex AI Studio (prompt design, tuning)

Security & Governance:
- Vertex AI Model Monitoring
- Google Cloud IAM for AI
- Data Loss Prevention API
- Cloud Audit Logs

Search for the latest announcements from Google Cloud Next 2024 and recent GCP updates.
""",
        CloudVendor.AGNOSTIC: """
MULTI-CLOUD AI STRATEGY (search for latest as of {current_date}):

Compare and recommend the best services across Azure, AWS, and GCP for each use case.
Consider:
- Which vendor has the strongest offering for each domain?
- Interoperability and avoiding vendor lock-in
- Cost comparison across platforms
- Enterprise readiness and support

Key areas to compare:
- Foundation models: Azure OpenAI vs Amazon Bedrock vs Vertex AI
- Productivity AI: M365 Copilot vs Amazon Q vs Gemini for Workspace
- Agent platforms: Copilot Studio vs Bedrock Agents vs Agent Builder
- Data platforms: Fabric vs SageMaker/Bedrock vs BigQuery/Vertex
- Governance: Purview vs Bedrock Guardrails vs Vertex AI governance

Search for the latest announcements from all three vendors' recent conferences.
"""
    }
    return guidance.get(vendor, guidance[CloudVendor.AGNOSTIC]).format(current_date=current_date)


def _build_vendor_context(vendor: CloudVendor, current_date: str, vendor_guidance: str) -> str:
    """Build vendor context section for the prompt."""
    return f"""
CLOUD VENDOR FOCUS: {vendor.display_name}

CRITICAL RESEARCH REQUIREMENT:
You MUST actively search for and cite the LATEST AI services and capabilities from {vendor.display_name}
as of {current_date}. Do NOT rely on training data. AI technology changes monthly.

You have access to context files with the latest vendor announcements and capabilities.
USE THESE CONTEXT FILES as your primary source for current technology recommendations.

{vendor_guidance}

IMPORTANT: Search for additional information to verify current availability and pricing.
Cite specific announcement dates and sources for all technology recommendations.
"""



def _build_full_prompt(company_name: str, current_date: str, vendor_context: str) -> str:
    """Build the complete AI strategy prompt."""
    return f"""You are a senior AI strategy consultant. Generate a comprehensive AI roadmap for board-level decision making.

=============================================================================
OUTPUT FORMAT (Start the document with this exact header)
=============================================================================

# AI Strategy: {company_name}

**Prepared by:** Primr Research System  
**Date:** {current_date}

---

Then continue with the sections below.

=============================================================================
RESEARCH INSTRUCTIONS
=============================================================================

CRITICAL: This strategy must reflect the AI landscape as of {current_date}.
AI technology evolves rapidly. You MUST actively search for the latest announcements,
services, and capabilities. Do NOT rely on potentially outdated training data.
Every technology recommendation must be verified and cited per the Research Protocol below.

You have access to research about {company_name} in the context files. Use that foundation
to develop a comprehensive AI strategy that their CIO and board would actually use.

AUDIENCE CLARIFICATION:
This strategy is an internal planning artifact. Recommendations represent proposed directions to evaluate, not commitments or final decisions.

THE GOAL: Produce an AI roadmap that answers "What should we actually do with AI, and why?"
This is not a generic list of AI buzzwords. It's a strategic document that connects AI
capabilities to THIS company's specific business model, pain points, competitive pressures,
and organizational reality. The intent is to help leadership make confident, well-sequenced decisions, not to prescribe a single correct path.

=============================================================================
RESEARCH AND VALIDATION PROTOCOL
=============================================================================

For every vendor service, tool, or capability named in this document:

1. **Verify current name**: Confirm the service still exists and has not been renamed or deprecated
2. **Status**: Note if GA (Generally Available) or Preview/Beta
3. **Region availability**: Flag if limited to specific regions
4. **Compliance certifications**: Note relevant certifications (SOC2, HIPAA, FedRAMP) if applicable
5. **Citation**: Link to official product page or release note with date (e.g., "Announced Nov 2024")
6. **Pricing**: If pricing varies, cite pricing page and state assumptions (users, tokens, volume)
7. **Unconfirmed flag**: If anything cannot be verified through search, mark as "UNCONFIRMED" and offer an alternative

This protocol reduces confident but incorrect vendor claims.

=============================================================================
STRATEGIC CONTEXT
=============================================================================

THE AGENTIC TRANSFORMATION
We are in the "Agentic Era" where AI evolves from passive assistants to proactive agents
capable of planning, reasoning, and executing multi-step workflows autonomously. The key
distinction is between "AI-enabled" (AI bolted onto legacy processes) vs "AI-native"
(intelligence as the foundational operating substrate). The competitive advantage lies
not in "using AI" but in "becoming agentic." Not every function needs to become agentic
immediately. The strategy must distinguish where autonomy creates real economic leverage
versus where it adds unnecessary risk.

HEURISTICS AND RULES OF THUMB (internal planning guidance, not cited facts):
- The "10-20-70 Rule": Allocate roughly 10% effort to algorithms, 20% to technology
  infrastructure, and 70% to people, processes, and cultural transformation.
  In plain language: most AI projects fail due to change management, not technology.
- The "J-Curve": Expect productivity to dip during the learning phase before surging.
  Leadership must be prepared for a 2-4 month adjustment period.
- Default to RAG over fine-tuning for 90% of enterprise use cases. Fine-tune only when
  you need to change the model's style, format, or domain-specific reasoning.

The output should give them:
1. A clear strategic thesis: AI-enabled vs AI-native, and the path between
2. A framework for thinking about AI across ALL domains
3. 5 specific Quick Wins they can start in 90 days (with ROI models)
4. 5 specific Bigger Bets for transformational impact
5. 3 things they should explicitly NOT pursue (deprioritization)
6. ROI frameworks using the appropriate model (productivity, revenue, or risk)
7. An organizational model with governance "traffic light" system
8. A target AI architecture posture to prevent tool sprawl

CONFIDENCE LABELING RULE:
All recommendations must be labeled as one of:
- "Low-regret / proven pattern" - widely adopted, strong evidence base
- "Context-dependent bet" - success depends on company-specific factors
- "Exploratory / frontier" - emerging capability, higher uncertainty
Never present a recommendation without one of these labels. Confidence labels reflect uncertainty in outcomes, not confidence in the team's ability to execute.

{vendor_context}

FORMATTING RULES:
- Write in full paragraphs for strategic sections
- Use bullets only for specific recommendations or lists
- No em-dashes, use commas or periods
- Tone: Strategic and direct, like a CIO presenting to the board
- Avoid hype language. Prefer operational language over visionary claims.
- Cite sources per the Research and Validation Protocol above
- For each recommendation, include: Business Case, Technology, ROI Model, Timeline
- The final Board Summary must fit on ONE PAGE (approximately 500-600 words)

=============================================================================
DOCUMENT STRUCTURE
=============================================================================

## AI Strategic Thesis (Recommended Direction)

Based on our research into {company_name}'s business model, industry, and competitive landscape, we recommend the following strategic thesis. This is a PROPOSED direction to discuss with leadership, not an assessment of their current plans.

**Recommended Transformation Path**: Based on their industry and business model, should {company_name} pursue:
- "AI-enabled" (AI bolted onto existing processes for efficiency) - lower risk, faster wins
- "AI-native" (intelligence as the operating substrate) - higher investment, transformational potential

**Proposed Primary Value Lever**: Based on their competitive position and industry dynamics, where should AI investment focus?
- Cost reduction and operational efficiency?
- Revenue growth and customer experience?
- Risk reduction and compliance?
- Competitive differentiation?

**Recommended Priorities**: Based on their business, what should they focus on first?

**Suggested Deprioritizations**: What should they explicitly NOT pursue in the near term, and why?
- Include the condition under which they should revisit
- Include the signal that would indicate the condition has changed

**Change Management Reality**: Most AI projects fail due to change management, not technology. Recommend allocating 70% of AI budget to people, processes, and cultural transformation.

Be specific to {company_name}'s situation. Avoid generic statements like "AI will transform the business." Instead: "Based on {company_name}'s position in [industry], we recommend focusing AI investment on [specific area] because [specific reason]. This could target [estimated impact]. We suggest deferring [specific thing] until [specific condition]."

## Executive Summary

The "so what" for the board. 2-3 paragraphs covering:
- Why AI matters for THIS company specifically (competitive pressure, efficiency opportunity)
- The recommended investment level and expected ROI
- The 3 most important things to do in the next 12 months

## Likely Current State (Hypotheses to Validate)

IMPORTANT: We do NOT have visibility into {company_name}'s internal systems, data platforms, or organizational readiness. The following are HYPOTHESES based on:
- Their industry and company size
- Public signals (job postings, press releases, tech stack mentions)
- Typical patterns for companies in their sector

Frame each assessment as "Based on [evidence], we hypothesize..." and note what we'd want to validate in conversation.

### Data Platform Maturity (Hypothesis)
Based on their industry ({company_name}'s sector) and size, hypothesize their likely data situation:
- **Likely data sources**: What systems probably generate their core business data?
- **Probable challenges**: Based on industry patterns, what data debt might they face?
- **Signals we observed**: Any public mentions of data initiatives, cloud migrations, or analytics investments?

Frame as: "Companies of this size in this industry typically face [X]. We'd want to understand their specific situation."

### Technology Signals (What We Can Observe)
Based on public information (job postings, press releases, tech blog posts, conference talks):
- **Cloud posture**: Any signals about their cloud provider or migration status?
- **Tech stack hints**: What technologies appear in their job postings?
- **Digital maturity signals**: E-commerce sophistication, mobile apps, API mentions?

Note: This is inference from public signals, not confirmed knowledge.

### Organizational Readiness (Industry Baseline)
Based on typical patterns for their industry and size:
- **AI adoption curve**: Where do companies like this typically sit on AI maturity?
- **Change management capacity**: What's typical for organizations of this scale?
- **Likely constraints**: Budget cycles, regulatory requirements, talent availability?

Frame as hypotheses to explore, not assertions about their actual state.

### Common Anti-Patterns to Discuss
These are common failure modes we'd want to explore with leadership (not accusations):
- **Pilot proliferation**: Many companies have dozens of disconnected AI PoCs. Worth asking about their current AI initiatives.
- **Tool sprawl**: Without governance, teams often adopt conflicting AI tools. Worth understanding their current landscape.
- **Data foundation gaps**: AI projects often stall on data quality. Worth exploring their data readiness.

## Competitive AI Landscape

Be specific about the competitive context:
- **One competitor ahead on AI**: Who is doing AI better? What specifically are they doing? What is the gap?
- **One peer making common AI mistakes**: What mistakes should {company_name} avoid? (e.g., pilot proliferation, tool sprawl, no governance)
- **Value at stake over 24 months**: What value could be protected or created by acting on AI?

Framing Guidance: When discussing the cost of inaction, emphasize the value that could be protected or created by acting, not a presumption of failure if action is delayed. Express as a range of potential impacts, not a single deterministic outcome. Present best-case, likely-case, and worst-case scenarios rather than asserting a single inevitable future.

## Recommended AI Architecture Posture

Based on the target cloud vendor and industry best practices, here's what {company_name} SHOULD build toward. These are recommendations, not assessments of their current state.

### Knowledge Grounding Pattern (RAG as Default)
For most enterprise AI use cases, recommend:
- Retrieval-Augmented Generation (RAG) as the default pattern for knowledge grounding
- Specific vector database and embedding strategy for the target cloud vendor
- Fine-tuning reserved only for style/format changes or domain-specific reasoning
- Data sources to prioritize: internal documents, wikis, customer data, operational databases

### Identity, Access, and Audit (Recommended Framework)
What they should implement:
- User authentication to AI systems (SSO integration)
- Service principal / managed identity for AI agents calling backend systems
- Audit logging for all AI interactions (prompts, responses, actions taken)
- PII handling policies for prompts and responses

### Agent Boundaries and Kill Switches (Governance Model)
Recommended guardrails:
- Define where agents can act autonomously vs. require human approval
- Set dollar/impact thresholds for human-in-the-loop
- Implement runaway agent detection and automatic stopping
- Establish escalation paths for agent failures

### Reusable Platform Components (Build Once, Use Many)
To prevent tool sprawl, recommend building shared infrastructure:
- Common prompt templates and guardrails library
- Shared vector stores and knowledge bases
- Centralized model endpoints and API gateway
- Evaluation and monitoring infrastructure
- Cost allocation and chargeback mechanisms

=============================================================================
AI OPPORTUNITY DOMAINS
=============================================================================

For EACH domain below, provide specific recommendations tailored to {company_name}.
Do not give generic advice. Connect every recommendation to their actual business.

### Productivity AI by Persona
Different user groups need different AI tools. Identify 3-4 key personas and recommend specific productivity AI for each.

### Process Automation
Identify 3-5 high-value automation opportunities specific to {company_name}'s operations.

### Conversational AI
**Internal Conversational AI (Employee-Facing)** and **External Conversational AI (Customer-Facing)** recommendations.

### Agentic AI (Connected to Data, Apps, Services)
Identify 2-3 agentic AI opportunities for {company_name}.

### Generative BI and Analytics
Recommend how {company_name} should evolve their analytics.

### Traditional AI/ML
Identify opportunities for traditional ML (forecasting, churn prediction, etc.).

### Security, Governance, and Responsible AI
Recommend a framework for {company_name}.

=============================================================================
PRIORITIZATION FILTERS
=============================================================================

Before presenting recommendations, evaluate all candidate initiatives using these 5 filters:
- **Expected Business Impact**: Revenue, cost savings, risk reduction, or strategic value
- **Data Readiness**: Is the required data available, clean, and accessible?
- **Integration Complexity**: How many systems must connect? Are APIs available?
- **Adoption and Change Load**: How much workflow change and training is required?
- **Risk and Compliance Exposure**: Data sensitivity, regulatory requirements, autonomy level

=============================================================================
STRATEGIC RECOMMENDATIONS
=============================================================================

## ROI Model Selection

Use the appropriate ROI model for each recommendation type:

**Productivity ROI** (for labor savings and throughput)
**Revenue ROI** (for conversion, retention, pricing initiatives)
**Risk ROI** (for compliance, security, error reduction)

## Five Quick Wins (Start in 90 Days)

For each Quick Win, provide:
- **The Opportunity**: What is it?
- **Why It Matters for {company_name}**: Connect to their specific business pain point
- **Why It Won** (Prioritization): Reference prioritization filters
- **Technology**: Specific tools/services with citations
- **Implementation**: What does it take?
- **ROI Calculation**: Use the appropriate model with specific numbers
- **Success Metrics**: How do you verify "realized" vs "projected" savings?

## Five Bigger Bets (6-18 Month Horizon)

For each Bigger Bet, provide comprehensive details including technology architecture, ROI model, risk factors, and governance tier.

## Three Things NOT to Pursue (Explicit Deprioritization)

For each deprioritized item:
- **What it is**: The AI initiative being deprioritized
- **Why it is tempting**: Why might someone advocate for this?
- **Why NOT now**: What makes this wrong for {company_name} at this time?
- **Revisit trigger**: Under what conditions should this be reconsidered?
- **Signal to watch**: What observable signal would indicate the trigger condition has changed?

=============================================================================
ORGANIZATIONAL MODEL
=============================================================================

## AI Practice Group Structure

Recommend how {company_name} should organize for sustained AI innovation.

**Governance "Traffic Light" System for AI Approval**
- **Green (Low Risk)**: Internal, non-PII data. Auto-approved.
- **Yellow (Medium Risk)**: Customer data, proprietary IP. AI CoE Review required.
- **Red (High Risk)**: Health/Financial decisions, autonomous external agents. Board sign-off required.

## Operating Model for Experimentation and Failure

AI initiatives will fail. A mature organization plans for this.

## Investment Framework

Year 1 Investment Estimate, ROI Framework, Build vs. Buy vs. Partner guidance.

=============================================================================
RISK ANALYSIS
=============================================================================

## The Cost of Inaction
Quantify the cost of NOT acting.

## Technology Risks
Vendor lock-in, model obsolescence, integration complexity, data quality dependencies.

## Organizational Risks
Change resistance, skills gaps, competing priorities.

## AI-Specific Security Risks
Jailbreaks, hallucinations, model drift.

=============================================================================
BOARD SUMMARY (ONE PAGE)
=============================================================================

CRITICAL: This section must fit on ONE PAGE (approximately 500-600 words).

**Strategic Thesis** (1 paragraph)
**The 5 Most Important Decisions** (concise list with investment and ROI)
**Investment Summary** (Total Year 1 Investment Ask)
**Expected Year 1 Returns** (Hard savings, productivity gains, risk reduction)
**What We Are Choosing NOT to Do** (3 deprioritized items)
**Key Risks Acknowledged** (Top 3 risks and mitigation)

=============================================================================
NEXT STEPS (Next 30 Days)
=============================================================================

Specific, actionable next steps with owners and dates.

=============================================================================
CITATIONS
=============================================================================

All vendor services, capabilities, and benchmarks cited should be listed with source URLs and dates.

=============================================================================
DOWNSTREAM TRANSLATION NOTE
=============================================================================

This output is intended to inform internal thinking and deck creation. When reused externally, conclusions should be softened, hypotheses foregrounded, and language reframed for diplomacy.
"""
