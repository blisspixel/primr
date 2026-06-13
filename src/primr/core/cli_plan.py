"""The ``--plan`` checkpoint: preview framing + Day-1 hypothesis tree + outline
before committing budget (tradecraft Step 3).

A pre-run alignment step (the consulting "betting table" / Day-1 answer review):
from free and cheap signals (DNS recon + operator framing) it forms the Day-1
hypothesis tree, shows the proposed report outline, writes the plan artifacts to
the working folder, and exits BEFORE any expensive collection or writing.
Mirrors ``primr skills --plan-only``.

Kept out of ``cli.py`` (pinned by the file-size ratchet). External calls (recon
and the tree LLM) are best-effort and fail soft, so a plan preview never aborts
and never spends beyond the cheap tree pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from primr.utils.console import console
from primr.utils.logging_config import get_logger

if TYPE_CHECKING:
    from primr.core.cli import CLIConfig

logger = get_logger("core.cli_plan")


def _safe_recon(domain: str) -> str:
    """Best-effort DNS recon for the plan preview; returns "" on any failure.

    Recon is free and fast (~3s) but depends on the external recon-tool and the
    network, so it must never break the preview.
    """
    try:
        from recon_tool.resolver import resolve_tenant

        from primr.core.recon_context import format_recon_context
        from primr.utils.async_utils import run_sync

        info, _results = run_sync(resolve_tenant(domain))
        return format_recon_context(info)
    except Exception as e:  # recon is best-effort
        logger.info("Plan: recon unavailable (%s)", type(e).__name__)
        return ""


def _proposed_outline() -> list[str]:
    """The proposed report section outline (from the company-overview config)."""
    try:
        from primr.prompts.loader import load_prompt_config

        return [s.name for s in load_prompt_config("company_overview").sections]
    except Exception as e:  # pragma: no cover - config load is stable
        logger.warning("Plan: could not load section outline (%s)", e)
        return []


def run_plan(config: CLIConfig) -> int:
    """Render the pre-run plan (framing + hypothesis tree + outline) and exit."""
    if not config.company_name or not config.website:
        console.error("Both company name and website are required for --plan")
        console.info('Usage: primr "Company" https://company.com --plan')
        return 1

    from primr.core.hypothesis_tree import (
        generate_hypothesis_tree,
        save_hypothesis_tree,
    )
    from primr.core.research_agent import _extract_domain, create_working_folder
    from primr.core.research_framing import resolve_run_framing
    from primr.pipeline.llm_failover import LLMRole, call_with_failover

    framing, _notes, framing_error = resolve_run_framing(
        discovery_notes_path=config.discovery_notes_path,
        purpose=config.framing_purpose,
        audience=config.framing_audience,
        decision=config.framing_decision,
        core_question=config.framing_question,
    )
    if framing_error:
        console.error(framing_error)
        return 1

    console.banner("Plan preview (no spend beyond a cheap Day-1 pass)")

    domain = _extract_domain(config.website)
    recon_text = _safe_recon(domain) if (domain and not config.skip_recon) else ""

    with console.timed_operation("Forming Day-1 hypothesis tree"):
        tree = generate_hypothesis_tree(
            company=config.company_name,
            core_question=framing.core_question,
            recon_summary=recon_text,
            llm=lambda prompt: call_with_failover(LLMRole.WRITING, prompt, temperature=0.4),
        )

    outline = _proposed_outline()

    # --- Display ---
    framing_block = framing.to_prompt_block()
    if framing_block:
        console.blank()
        console.text(framing_block)
    console.blank()
    console.text(tree.to_markdown())
    if outline:
        console.header("Proposed report outline")
        for i, name in enumerate(outline, start=1):
            console.text(f"  {i}. {name}")
    console.blank()
    console.info("Preview only. Re-run without --plan to execute (API cost applies).")

    # --- Artifacts ---
    folder = create_working_folder(config.company_name, config.website)
    save_hypothesis_tree(tree, folder)
    _write_plan_markdown(folder, config, framing, tree, outline)
    console.ok(f"Plan written to {folder}")
    return 0


def _write_plan_markdown(folder, config, framing, tree, outline) -> None:
    """Write a human-readable plan.md summarizing framing + tree + outline."""
    from pathlib import Path

    lines = [f"# Research Plan: {config.company_name}", ""]
    if config.website:
        lines.append(f"**Website:** {config.website}")
        lines.append("")
    block = framing.to_prompt_block()
    if block:
        lines += ["## Framing", "", "```", block, "```", ""]
    lines += ["## Day-1 Hypothesis Tree", "", tree.to_markdown(), ""]
    if outline:
        lines.append("## Proposed Report Outline")
        lines.append("")
        lines += [f"{i}. {name}" for i, name in enumerate(outline, start=1)]
        lines.append("")
    try:
        (Path(folder) / "plan.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError as e:  # artifact write is best-effort
        logger.warning("Plan: could not write plan.md (%s)", e)
