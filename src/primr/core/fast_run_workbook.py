"""Fast-run analysis-workbook stage (roadmap #23, Batch C).

Extracted verbatim from stage 4 (Phase 3 banner) of ``perform_fast_research``
— no behavior change. Builds the structured analysis workbook via the
reasoning model, with the collected insights as the fallback on any failure
or empty output.

Tangle point handled here (refactor map #5): in continuous-reasoning mode
this stage CONSTRUCTS the shared ``ContinuousReasoningSession`` with the
workbook's system prompt, and Phase 5 cross-validation reuses it. The session
is therefore returned alongside the workbook and the orchestrator threads it
onward.

Side effects preserved from the original: phase banner/completion, fallback
warnings, structured log on fallback, and ``analysis_workbook.md`` written to
the working folder.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from primr.core.section_prompts import _build_fast_analysis_prompt
from primr.pipeline.llm_failover import LLMRole, call_with_failover
from primr.utils.console import console
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured

if TYPE_CHECKING:
    from primr.ai.grok_client import ContinuousReasoningSession
    from primr.core.research_framing import ResearchFraming

logger = get_logger("core.fast_run_workbook")

ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior strategic analyst conducting pre-engagement research "
    "for a consulting firm. Produce a structured analysis workbook — working "
    "notes with evidence, confidence levels, and hypotheses. Not polished prose. "
    "CRITICAL: Separate what the company CLAIMS from what external evidence "
    "SUPPORTS. Stress-test their narrative. Be conservative on financial inferences."
)


def _form_day1_hypothesis_tree(
    company_label: str,
    framing: ResearchFraming | None,
    raw_corpus: str,
    external_sources_raw: str,
    folder_path: str,
) -> str:
    """Form + save the Day-1 hypothesis tree; return a prompt block (or "").

    Only runs when the operator supplied framing (so default runs are unchanged
    in cost and behavior). Uses the cheap utility-tier writer chain and fails
    soft: any failure yields an empty tree and an empty block, never an abort.
    The homepage/hiring signals are approximated from the corpus and external
    sources available at this stage; truly pre-collection generation that steers
    scraping is Step 4.
    """
    if framing is None or not framing.is_specified:
        return ""

    from primr.core.hypothesis_tree import generate_hypothesis_tree, save_hypothesis_tree

    tree = generate_hypothesis_tree(
        company=company_label,
        core_question=framing.core_question,
        homepage_text=raw_corpus[:8000],
        hiring_summary=external_sources_raw[:8000],
        llm=lambda prompt: call_with_failover(LLMRole.WRITING, prompt, temperature=0.4),
    )
    save_hypothesis_tree(tree, folder_path)
    if tree.is_empty:
        return ""
    console.info("Day-1 hypothesis tree formed and saved (hypothesis_tree.md)")
    return "=== DAY-1 HYPOTHESIS TREE (formed before this analysis) ===\n" + tree.to_markdown()


def generate_analysis_workbook(
    *,
    company_label: str,
    website: str | None,
    raw_corpus: str,
    external_sources_raw: str,
    combined_insights: str,
    grok_reasoning: str,
    grok_reasoning_effort: str | None,
    continuous_reasoning: bool,
    reasoning_session: ContinuousReasoningSession | None,
    recovery_executor,
    folder_path: str,
    total_phases: int,
    framing_block: str = "",
    framing: ResearchFraming | None = None,
) -> tuple[str, ContinuousReasoningSession | None]:
    """Generate the analysis workbook; return (workbook, reasoning_session).

    ``framing_block`` carries operator intent (``ResearchFraming``) into the
    workbook prompt. ``framing`` is the object itself, used (when specified) to
    form the Day-1 hypothesis tree before the workbook. Both are no-ops when no
    framing was supplied.
    """
    console.phase_banner(
        3, total_phases, "Analysis (Grok)", "Building structured analysis workbook", "2-4 min"
    )

    analysis_system = ANALYSIS_SYSTEM_PROMPT

    # Day-1 hypothesis tree (tradecraft Step 2): when the run is framed, form a
    # MECE issue tree from the cheap signals, save it as an artifact, and prepend
    # it so the workbook analysis is hypothesis-driven. Unframed -> no-op.
    tree_block = _form_day1_hypothesis_tree(
        company_label, framing, raw_corpus, external_sources_raw, folder_path
    )

    analysis_prompt = _build_fast_analysis_prompt(
        company_label,
        website,
        raw_corpus,
        external_sources_raw,
        framing_block=framing_block,
    )
    if tree_block:
        analysis_prompt = f"{tree_block}\n\n{analysis_prompt}"

    try:
        from primr.pipeline.integration import analysis_with_recovery

        # In continuous mode, construct the session here with the workbook's
        # system prompt as a real role:system message. The session then
        # carries that role + the workbook reasoning forward into Phase 5
        # cross-validation as a follow-up user turn.
        if continuous_reasoning and reasoning_session is None:
            from primr.ai.grok_client import ContinuousReasoningSession as _Session

            reasoning_session = _Session(
                model=grok_reasoning,
                system_prompt=analysis_system,
                reasoning_effort=grok_reasoning_effort,
            )

        def _do_analysis():
            if reasoning_session is not None:
                return reasoning_session.send(
                    analysis_prompt,
                    max_tokens=18_000,
                    temperature=0.5,
                )
            return call_with_failover(
                LLMRole.REASONING,
                analysis_prompt,
                preferred_model=grok_reasoning,
                max_tokens=18_000,
                temperature=0.5,
                system_prompt=analysis_system,
                reasoning_effort=grok_reasoning_effort,
            )

        with console.timed_operation("Generating analysis workbook via Grok"):
            _analysis_result = analysis_with_recovery(recovery_executor, _do_analysis, folder_path)
            if _analysis_result.success:
                analysis_workbook = _analysis_result.output
            else:
                raise RuntimeError(_analysis_result.skip_reason or "Analysis recovery exhausted")
    except Exception as analysis_err:
        console.warn(f"Analysis workbook generation failed: {analysis_err}")
        console.info("Continuing with collected insights as fallback workbook")
        log_structured("warning", "Fast mode analysis fallback used", error=str(analysis_err))
        analysis_workbook = combined_insights

    if not analysis_workbook or not analysis_workbook.strip():
        console.warn("Analysis workbook empty — falling back to insights for report")
        analysis_workbook = combined_insights

    # Save workbook
    workbook_path = os.path.join(folder_path, "analysis_workbook.md")
    with open(workbook_path, "w", encoding="utf-8") as f:
        f.write(analysis_workbook)

    console.phase_complete("Analysis (Grok)")

    return analysis_workbook, reasoning_session
