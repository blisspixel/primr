"""Cached/volatile prompt-part assembly for strategy generation.

Roadmap #8 (prompt cache preparation) applied to the strategy stage,
mirroring `section_prompts.build_fast_section_prompt_parts`: the context
block shared by every strategy call in a run (company report +
working-folder artifacts) becomes a byte-stable cached prefix, and the
per-strategy material (vendor research docs, the strategy prompt itself)
stays in the volatile suffix. Concatenating the two parts reproduces the
exact prompt shape the stage always sent, so providers' implicit prefix
caching gets a shared key on multi-strategy runs without any behavioral
change. This module is also the single owner of the artifact-block read
logic the AI-vendor and YAML strategy loops previously duplicated.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from primr.utils.content_sanitizer import fence_untrusted
from primr.utils.logging_config import get_logger
from primr.utils.observability import log_structured

logger = get_logger(__name__)

__all__ = [
    "AI_STRATEGY_ARTIFACTS",
    "STRATEGY_REPORT_CHAR_LIMIT",
    "UNTRUSTED_ARTIFACTS",
    "YAML_STRATEGY_ARTIFACTS",
    "build_strategy_context_prefix",
    "build_strategy_prompt_parts",
    "read_artifact_blocks",
    "write_strategy_context_bundle",
]

# Working-folder artifacts enriching every strategy. Each entry is
# (relative path, char limit). AI Strategy needs the same recon and hiring
# evidence as the other strategy types so its stack and workforce conclusions
# do not depend only on the synthesized company report.
AI_STRATEGY_ARTIFACTS: tuple[tuple[str, int], ...] = (
    ("insights.txt", 20_000),
    ("gap_analysis.md", 15_000),
    ("analysis_workbook.md", 20_000),
    ("_recon_context.txt", 10_000),
    ("_hiring/hiring_signals.md", 15_000),
)

YAML_STRATEGY_ARTIFACTS = AI_STRATEGY_ARTIFACTS

# Trust boundary for the working-folder artifacts above. insights.txt fences
# its verbatim scraped-external block at assembly (insights_assembly), so
# re-fencing it here would corrupt the inner markers; gap_analysis.md and
# analysis_workbook.md are LLM-generated intermediates (the accepted
# "laundered injection" residual in docs/SECURITY.md). These two carry
# verbatim externally-derived text - scraped posting titles/URLs and
# DNS-derived recon lines - and enter prompts only as fenced data.
UNTRUSTED_ARTIFACTS: frozenset[str] = frozenset({"_hiring/hiring_signals.md", "_recon_context.txt"})

_CONTEXT_HEADER = "Use the following context documents to inform your analysis:\n\n"
# A typical Strategic Overview is roughly 20,000 words. The former 50,000
# character head slice silently removed later strategy, risk, and operating
# sections before AI Strategy synthesis. This bound retains a full normal
# report while keeping pathological inputs finite.
STRATEGY_REPORT_CHAR_LIMIT = 200_000


def read_artifact_blocks(folder_path: str, artifact_specs: Sequence[tuple[str, int]]) -> list[str]:
    """Read working-folder artifacts into ``--- name ---`` context blocks.

    Missing files, empty content, and read failures are skipped (failures
    logged), matching the tolerant behavior the strategy loops always had:
    a damaged artifact weakens context but never blocks strategy generation.
    """
    blocks: list[str] = []
    artifact_status: dict[str, str] = {}
    for artifact_name, artifact_limit in artifact_specs:
        artifact_path = os.path.join(folder_path, artifact_name)
        if not os.path.exists(artifact_path):
            artifact_status[artifact_name] = "missing"
            continue
        try:
            with open(artifact_path, encoding="utf-8") as fh:
                artifact_content = fh.read()[:artifact_limit]
        except Exception as e:
            artifact_status[artifact_name] = "unreadable"
            logger.warning("Failed to read artifact %s: %s", artifact_name, e)
            continue
        if not artifact_content.strip():
            artifact_status[artifact_name] = "blank"
            continue
        artifact_status[artifact_name] = "present"
        if artifact_name in UNTRUSTED_ARTIFACTS:
            artifact_content = fence_untrusted("ARTIFACT", artifact_content)
        blocks.append(f"--- {artifact_name} ---\n{artifact_content}")
    log_structured(
        "info",
        "Strategy artifact coverage",
        artifact_status=artifact_status,
        present=sum(status == "present" for status in artifact_status.values()),
        expected=len(artifact_specs),
    )
    return blocks


def build_strategy_context_prefix(report_content: str, shared_blocks: Sequence[str]) -> str:
    """Build the run-shared cached prefix: header + report + shared artifacts.

    Byte-identical across every strategy call of a run by construction -
    callers must build it once and reuse it, never rebuild it per call.
    """
    parts = [
        f"--- Company Report ---\n{report_content[:STRATEGY_REPORT_CHAR_LIMIT]}",
        *shared_blocks,
    ]
    return _CONTEXT_HEADER + "\n\n".join(parts)


def build_strategy_prompt_parts(
    cached_prefix: str,
    strategy_prompt: str,
    volatile_blocks: Sequence[str] = (),
) -> tuple[str, str]:
    """Return ``(cached_prefix, volatile_suffix)`` for one strategy call.

    ``cached_prefix + volatile_suffix`` reproduces the legacy combined
    prompt exactly: context blocks (shared, then per-call ones such as
    vendor research docs), a ``---`` divider, then the strategy prompt.
    """
    suffix = ""
    if volatile_blocks:
        suffix += "\n\n" + "\n\n".join(volatile_blocks)
    suffix += "\n\n---\n\n" + strategy_prompt
    return cached_prefix, suffix


def write_strategy_context_bundle(
    folder_path: str,
    company_report_path: str | None,
    artifact_specs: Sequence[tuple[str, int]] = AI_STRATEGY_ARTIFACTS,
) -> str | None:
    """Write one bounded, trust-labeled strategy context file for file-upload paths."""
    report_content = ""
    if company_report_path and os.path.exists(company_report_path):
        try:
            report_content = Path(company_report_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "Failed to read strategy report context %s: %s", company_report_path, exc
            )

    artifact_blocks = read_artifact_blocks(folder_path, artifact_specs)
    log_structured(
        "info",
        "Strategy context bundle",
        report_included=bool(report_content.strip()),
        artifacts_available=len(artifact_blocks),
        artifacts_expected=len(artifact_specs),
    )
    if not report_content.strip() and not artifact_blocks:
        return None

    bundle_path = Path(folder_path) / "_strategy_context.md"
    try:
        bundle_path.write_text(
            build_strategy_context_prefix(report_content, artifact_blocks),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to write strategy context bundle %s: %s", bundle_path, exc)
        return company_report_path if report_content.strip() else None
    return str(bundle_path)
