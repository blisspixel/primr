"""Weak-section regeneration helpers (extracted from ``research_agent``).

``_fast_regenerate_section`` (Phase 5 cross-validation) and
``_strategy_regenerate_section`` (Phase 6 strategy enrichment) re-write one
weak section with freshly gathered evidence. Both moved here verbatim when
``research_agent`` hit its architecture line ceiling; behavior is unchanged.
``research_agent`` re-exports both names so the lazy imports in the stage
modules and the existing test patch points keep working.

The ``new_evidence`` input is freshly scraped external page text - the T1
prompt-injection boundary - so both functions fence it as data before it
enters the prompt.
"""

from __future__ import annotations

from primr.qa.report_analyzer import SCAFFOLDING_PROHIBITION_GUIDANCE
from primr.utils.content_sanitizer import fence_untrusted
from primr.utils.observability import log_structured

__all__ = ["_fast_regenerate_section", "_strategy_regenerate_section"]


def _fast_regenerate_section(
    company_name: str,
    website: str | None,
    section_title: str,
    section_content: str,
    analysis_workbook: str,
    new_evidence: str,
    source_urls: list[str],
    model: str | None = None,
) -> str:
    """
    Phase 5 helper: Re-writes one weak section with additional evidence.

    Uses the same system prompt style as Phase 4 report writing.
    Returns the re-generated section content (starting with ## heading).
    """
    from primr.core.research_agent import _default_writing_model
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    # ``new_evidence`` is freshly scraped external page text - the T1
    # boundary: it must enter the prompt only as fenced data.
    new_evidence = fence_untrusted("NEW_EVIDENCE", new_evidence)

    source_list = "\n".join(f"- {url}" for url in source_urls[:50])

    prompt = f"""Re-write this section of a consulting brief for {company_name}, incorporating
the NEW EVIDENCE provided below. The goal is to make the section evidence-rich,
specific, and analytically strong.

SECTION TO REWRITE:
{section_content}

NEW EVIDENCE (incorporate this):
{new_evidence}

ANALYSIS CONTEXT (for background):
{analysis_workbook[:20_000]}

ALL AVAILABLE SOURCES:
{source_list}

RULES:
- Start with: ## {section_title}
- Full paragraphs with evidence and strategic interpretation, not bullet dumps
- Keep citations compact, usually at paragraph ends, and use [cite: N] references in the body
- Reserve the densest source inventory for the final Sources appendix
- Label claims: Confirmed, Reported, Estimated, Hypothesis
- Stress-test the company narrative - separate claims from evidence
- Keep roughly the same scope as the original section
- End with a single "What to validate:" line followed by a concrete check question
- Write that line as plain text - no bold, italics, or bullet prefix (it is prose, not a label)

{SCAFFOLDING_PROHIBITION_GUIDANCE}"""

    system_prompt = (
        "You are a senior strategic analyst rewriting a section of a consulting dossier. "
        "Your reader is a partner walking into a meeting. Incorporate the new evidence "
        "to make the section analytically stronger. Be conservative on financial inferences."
    )

    writing_model = model or _default_writing_model()
    try:
        result = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=5_000,
            temperature=0.7,
            system_prompt=system_prompt,
        )
    except Exception as e:
        log_structured(
            "warning", "Section regeneration failed", section=section_title, error=str(e)
        )
        return section_content  # Return original on failure

    if not result or not result.strip():
        return section_content

    # Ensure it starts with the correct heading
    result = result.strip()
    if not result.startswith(f"## {section_title}"):
        # Strip Grok's wrong heading if it starts with any ## heading
        if result.startswith("## "):
            # Remove the first line (wrong heading)
            first_newline = result.find("\n")
            if first_newline != -1:
                result = result[first_newline:].strip()
            else:
                result = ""
        result = f"## {section_title}\n\n{result}" if result else f"## {section_title}\n\n"

    return result


def _strategy_regenerate_section(
    company_name: str,
    vendor: str,
    section_title: str,
    section_content: str,
    new_evidence: str,
    analysis_workbook: str,
    model: str | None = None,
    label: str = "AI Strategy",
) -> str:
    """
    Phase 6 helper: Re-writes one weak strategy section with additional evidence.

    Returns the re-generated section content (starting with ## heading).
    """
    from primr.core.research_agent import _default_writing_model
    from primr.core.strategy_enrichment_contract import strategy_document_context
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    # T1 boundary: freshly scraped page text enters only as fenced data.
    new_evidence = fence_untrusted("NEW_EVIDENCE", new_evidence)
    document_label, emphasis = strategy_document_context(label, vendor)
    prompt = f"""Re-write this section of a {document_label} for {company_name},
incorporating the NEW EVIDENCE provided below. Make the section specific, actionable,
and tied to this company's actual situation.

{emphasis}

SECTION TO REWRITE:
{section_content}

NEW EVIDENCE (incorporate this):
{new_evidence}

ANALYSIS CONTEXT (for background):
{analysis_workbook[:20_000]}

RULES:
- Start with: ## {section_title}
- Connect capabilities to THIS company's specific business outcomes and constraints
- Name services, prices, availability, or lifecycle states only when the new evidence is current and official
- Otherwise state the capability requirement, evidence gap, and validation action
- Label claims: Confirmed, Reported, Estimated, Hypothesis
- Keep citations compact, usually at paragraph ends, and use [cite: N] references in the body
- Keep roughly the same scope as the original section
- Include concrete next steps or validation questions
- If you end with a "What to validate:" line, write it as plain text - no bold, italics, or bullet prefix
- Keep the densest supporting reference list in the final Sources appendix

{SCAFFOLDING_PROHIBITION_GUIDANCE}"""

    system_prompt = (
        f"You are a senior strategy consultant rewriting a section of a {document_label} "
        f"for {company_name}. {emphasis} "
        "Incorporate new evidence to make the section more specific and actionable. "
        "Be conservative on cost estimates."
    )

    writing_model = model or _default_writing_model()
    try:
        result = call_with_failover(
            LLMRole.WRITING,
            prompt,
            preferred_model=writing_model,
            max_tokens=8_000,
            temperature=0.6,
            system_prompt=system_prompt,
        )
    except Exception as e:
        log_structured(
            "warning", "Strategy section regeneration failed", section=section_title, error=str(e)
        )
        return section_content  # Return original on failure

    if not result or not result.strip():
        return section_content

    # Ensure it starts with the correct heading
    result = result.strip()
    if not result.startswith(f"## {section_title}"):
        if result.startswith("## "):
            first_newline = result.find("\n")
            if first_newline != -1:
                result = result[first_newline:].strip()
            else:
                result = ""
        result = f"## {section_title}\n\n{result}" if result else f"## {section_title}\n\n"

    return result
