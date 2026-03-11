"""
Master Architect for Recursive Hierarchical Research.

This module provides the MasterArchitect class that decomposes a comprehensive
strategic report into 8-10 substantive chapters, each with detailed research
instructions for parallel Deep Research execution.

The Master Architect uses Flash model for fast, cost-effective planning.
"""

import json
from dataclasses import dataclass, field
from typing import Any

try:
    from google import genai as _google_genai

    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as import_error:
    _GENAI_IMPORT_ERROR = import_error

    class _GenAIUnavailable:
        class Client:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("google.genai is unavailable")

    _google_genai = _GenAIUnavailable()  # type: ignore[assignment]
    _FALLBACK_CLIENT_CLASS = _GenAIUnavailable.Client
else:
    _FALLBACK_CLIENT_CLASS = None  # type: ignore[misc]

genai = _google_genai

from primr.config.models import PrimrModels
from primr.config.settings import get_settings
from primr.utils.logging_config import get_logger

logger = get_logger("ai.report_architect")


def _require_genai_dependency() -> None:
    if _GENAI_IMPORT_ERROR is None:
        return
    if (
        _FALLBACK_CLIENT_CLASS is not None
        and getattr(genai, "Client", None) is not _FALLBACK_CLIENT_CLASS
    ):
        return
    raise RuntimeError(
        "google.genai is not available. Install compatible dependencies "
        "(Python 3.11+ and project requirements)."
    ) from _GENAI_IMPORT_ERROR


@dataclass
class ChapterPlan:
    """A single chapter in the research plan."""

    chapter_number: int
    title: str
    research_prompt: str
    expected_pages: int = 5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chapter_number": self.chapter_number,
            "title": self.title,
            "research_prompt": self.research_prompt,
            "expected_pages": self.expected_pages,
        }


@dataclass
class ReportPlan:
    """Complete plan for a multi-chapter research report."""

    company_name: str
    chapters: list[ChapterPlan] = field(default_factory=list)
    total_expected_pages: int = 0

    def __post_init__(self) -> None:
        """Calculate total expected pages."""
        self.total_expected_pages = sum(ch.expected_pages for ch in self.chapters)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "company_name": self.company_name,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "total_expected_pages": self.total_expected_pages,
        }


# Default chapter structure when API fails or returns invalid response
DEFAULT_CHAPTERS = [
    {
        "title": "Executive Summary & Company Snapshot",
        "research_prompt": """Write a comprehensive executive summary for {company_name}.
Include: company overview, founding story, headquarters, employee count, revenue if available.
Synthesize the most critical findings a decision-maker needs in 60 seconds.
Use the File Search context for baseline company facts. Add market context from web search.""",
    },
    {
        "title": "Products, Services & Value Proposition",
        "research_prompt": """Analyze {company_name}'s complete product and service portfolio.
Include: detailed product lines, service offerings, pricing models, how they make money.
Explain their unique selling proposition and competitive differentiation.
Use File Search for official product info, web search for customer reviews and market perception.""",
    },
    {
        "title": "Leadership, Culture & Organization",
        "research_prompt": """Research {company_name}'s leadership team and organizational culture.
Include: key executives with backgrounds, board composition, leadership tenure and stability.
Analyze cultural signals from careers page, press releases, Glassdoor, and how they talk about their team.
Note any recent leadership changes or departures.""",
    },
    {
        "title": "Financial Position & Business Model",
        "research_prompt": """Analyze {company_name}'s financial position and business model.
Include: revenue, growth trajectory, profitability indicators, funding history if private.
Explain their business model, revenue streams, and key financial metrics.
Use estimates if needed and label confidence levels. If truly unavailable, state so.""",
    },
    {
        "title": "Target Markets & Customer Segments",
        "research_prompt": """Research {company_name}'s target markets and customer segments.
Include: who buys from them, customer segments, industries served, geographic focus.
Analyze typical buyer profile, customer success stories, and market penetration.
Include data tables comparing customer segments if available.""",
    },
    {
        "title": "Competitive Landscape & Market Position",
        "research_prompt": """Analyze {company_name}'s competitive landscape and market position.
Include: main competitors, market share estimates, competitive advantages and disadvantages.
Create comparison tables for key competitors on dimensions like pricing, features, market focus.
Analyze where they win deals vs. lose them, and emerging competitive threats.""",
    },
    {
        "title": "Industry Dynamics & External Forces",
        "research_prompt": """Research the industry dynamics affecting {company_name}.
Include: industry growth trends, disruption factors, regulatory pressures, technology shifts.
Analyze supply chain dynamics, talent market conditions, and macro-economic factors.
What external forces are shaping their world? What keeps leadership up at night?""",
    },
    {
        "title": "SWOT Analysis & Strategic Assessment",
        "research_prompt": """Conduct a comprehensive SWOT analysis for {company_name}.
Strengths: What appears difficult to replicate? Core competencies?
Weaknesses: What constraints, tradeoffs, or gaps exist?
Opportunities: What options are worth exploring? Market expansion?
Threats: What risks should be discussed? Competitive, regulatory, technological?
Frame as observations to validate, not conclusions.""",
    },
    {
        "title": "Risk Analysis & Mitigation Strategies",
        "research_prompt": """Analyze potential risks facing {company_name}.
Include: competitive risks, operational risks, market/macro risks, leadership/execution risks.
For each risk, assess likelihood, potential impact, and possible mitigation strategies.
Frame as areas worth discussing, not definitive threats. Note evidence quality.""",
    },
    {
        "title": "Strategic Recommendations & Discovery Questions",
        "research_prompt": """Synthesize strategic recommendations and discovery questions for {company_name}.
Include: quick wins (lower-effort options), strategic bets (transformational moves), defensive considerations.
Generate 5-7 thoughtful questions for the first client conversation.
Frame as hypotheses to explore, not conclusions. What do we most want to understand from them?""",
    },
]


class MasterArchitect:
    """
    Decomposes strategic reports into chapters for parallel research.

    The Master Architect uses Flash model to analyze the company context
    and generate a customized chapter plan. Each chapter includes detailed
    research instructions for the Deep Research agent.

    Example:
        architect = MasterArchitect()
        plan = await architect.generate_chapter_plan(
            "Acme Corp",
            "Industrial products manufacturer founded in 2003..."
        )
        for chapter in plan.chapters:
            print(f"{chapter.chapter_number}. {chapter.title}")
    """

    # Model for planning (fast and cheap)
    PLANNING_MODEL = PrimrModels.FAST_MODEL

    def __init__(self, api_key: str | None = None):
        """
        Initialize the Master Architect.

        Args:
            api_key: Optional API key override. Uses settings if not provided.
        """
        _require_genai_dependency()
        settings = get_settings()
        self._api_key = api_key or settings.api.gemini_key
        self._client = genai.Client(api_key=self._api_key)
        logger.debug("Master Architect initialized")

    async def generate_chapter_plan(
        self,
        company_name: str,
        context_summary: str,
    ) -> ReportPlan:
        """
        Generate a chapter plan for comprehensive company research.

        Uses {PrimrModels.FAST_MODEL} to analyze the company context and create
        a customized 10-chapter research plan. Each chapter includes
        detailed instructions for the Deep Research agent.

        Args:
            company_name: Name of the company to research
            context_summary: Summary of scraped data and initial findings

        Returns:
            ReportPlan with 8-10 chapters

        Raises:
            AIError: If planning fails after retries
        """
        logger.info(f"Generating chapter plan for {company_name}")

        prompt = self._build_planning_prompt(company_name, context_summary)

        try:
            # Call fast model for planning
            response = self._client.models.generate_content(
                model=self.PLANNING_MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": 0.3,  # Lower temperature for consistent structure
                },
            )

            # Parse the JSON response
            response_text = response.text or ""
            chapters = self._parse_chapter_response(response_text, company_name)

            plan = ReportPlan(
                company_name=company_name,
                chapters=chapters,
            )

            logger.info(
                f"Generated plan with {len(chapters)} chapters, "
                f"~{plan.total_expected_pages} expected pages"
            )
            return plan

        except Exception as e:
            logger.warning(f"Chapter planning failed: {e}, using default structure", exc_info=True)
            return self._get_default_plan(company_name)

    def _build_planning_prompt(
        self,
        company_name: str,
        context_summary: str,
    ) -> str:
        """Build the prompt for chapter planning."""
        return f"""You are a Principal Strategic Architect. We are commissioning a comprehensive
strategic advisory report on {company_name}.

Context Summary (from initial research):
{context_summary[:4000]}  # Truncate to avoid token limits

Task: Deconstruct this topic into exactly 10 substantive chapters.
Each chapter must be distinct, exhaustive, and capable of standing alone
as a 5-6 page deep dive.

Output a JSON object with this exact structure:
{{
  "chapters": [
    {{
      "chapter_number": 1,
      "title": "Chapter Title",
      "research_prompt": "Detailed 200-word instruction set for a researcher agent. Explicitly ask for data tables, specific metrics, and analysis relevant to this chapter. Reference the company name '{company_name}' in the prompt.",
      "expected_pages": 5
    }}
  ]
}}

Required chapters (adapt titles and prompts based on the company context):
1. Executive Summary & Company Snapshot
2. Products, Services & Value Proposition
3. Leadership, Culture & Organization
4. Financial Position & Business Model
5. Target Markets & Customer Segments
6. Competitive Landscape & Market Position
7. Industry Dynamics & External Forces
8. SWOT Analysis & Strategic Assessment
9. Risk Analysis & Mitigation Strategies
10. Strategic Recommendations & Discovery Questions

For each chapter's research_prompt:
- Be specific to {company_name} and their industry
- Request data tables and metrics where appropriate
- Instruct the researcher to use File Search context for company facts
- Instruct the researcher to use web search for market/competitive context
- Ask for full paragraphs, not bullet lists
- Request citations for all claims

Output ONLY the JSON object, no other text."""

    def _parse_chapter_response(
        self,
        response_text: str,
        company_name: str,
    ) -> list[ChapterPlan]:
        """Parse the JSON response into ChapterPlan objects."""
        try:
            # Try to parse as JSON
            data = json.loads(response_text)

            chapters: list[ChapterPlan] = []
            for ch in data.get("chapters", []):
                chapter = ChapterPlan(
                    chapter_number=ch.get("chapter_number", len(chapters) + 1),
                    title=ch.get("title", f"Chapter {len(chapters) + 1}"),
                    research_prompt=ch.get("research_prompt", ""),
                    expected_pages=ch.get("expected_pages", 5),
                )
                chapters.append(chapter)

            # Validate we have enough chapters
            if len(chapters) < 8:
                logger.warning(f"Only {len(chapters)} chapters parsed, using defaults")
                return self._get_default_chapters(company_name)

            return chapters

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse chapter JSON: {e}")
            return self._get_default_chapters(company_name)

    def _get_default_chapters(self, company_name: str) -> list[ChapterPlan]:
        """Get default chapter structure when API fails."""
        chapters = []
        for i, ch in enumerate(DEFAULT_CHAPTERS, 1):
            # Replace {company_name} placeholder in prompts
            prompt = ch["research_prompt"].format(company_name=company_name)
            chapters.append(
                ChapterPlan(
                    chapter_number=i,
                    title=ch["title"],
                    research_prompt=prompt,
                    expected_pages=5,
                )
            )
        return chapters

    def _get_default_plan(self, company_name: str) -> ReportPlan:
        """Get default report plan when API fails."""
        return ReportPlan(
            company_name=company_name,
            chapters=self._get_default_chapters(company_name),
        )

    def get_chapter_titles(self) -> list[str]:
        """Get the list of default chapter titles."""
        return [ch["title"] for ch in DEFAULT_CHAPTERS]


# =============================================================================
# SINGLETON ACCESS (Thread-Safe)
# =============================================================================

import threading

_architect: MasterArchitect | None = None
_architect_lock = threading.Lock()


def get_master_architect() -> MasterArchitect:
    """
    Get the global Master Architect instance (thread-safe).
    """
    global _architect
    if _architect is None:
        with _architect_lock:
            if _architect is None:
                _architect = MasterArchitect()
    return _architect


def reset_master_architect() -> None:
    """Reset the global architect (useful for testing)."""
    global _architect
    with _architect_lock:
        _architect = None
