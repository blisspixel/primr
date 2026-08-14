"""Map orchestrator/fast-path progress text onto MCP research stages.

``PipelineRunner.on_progress`` used to heartbeat only, so jobs stayed on
``scraping`` through Deep Research and writing. Stage inference is best-effort
and monotonic: unknown messages leave the current stage unchanged.
"""

from __future__ import annotations

from primr.mcp_server.types import ResearchStage

_QA_MARKERS = (
    "running qa",
    "quality assessment",
    "quality analysis",
    "claim verification",
)
_WRITING_MARKERS = (
    "writing:",
    "writing report",
    "writing section",
    "phase 2: writing",
    "phase 3: assembl",
    "assembling final",
    "generating overview",
    "generating report",
)
_DEEP_MARKERS = (
    "deep research",
    "research dossier",
    "file search store",
    "starting deep",
    "gathering research",
)
_EXTRACT_MARKERS = (
    "extracting",
    "summarizing",
    "content summarized",
    "identifying industry",
    "insights",
)
_SCRAPE_MARKERS = (
    "scraping",
    "website scrape",
    "searching external",
    "validating external",
    "starting website",
)


def infer_research_stage(message: str) -> ResearchStage | None:
    """Return the stage implied by a progress line, or ``None`` if unknown."""
    text = (message or "").strip().lower()
    if not text:
        return None
    if _contains_any(text, _QA_MARKERS):
        return ResearchStage.QA
    if _contains_any(text, _WRITING_MARKERS):
        return ResearchStage.WRITING
    if _contains_any(text, _DEEP_MARKERS):
        return ResearchStage.DEEP_RESEARCH
    if _contains_any(text, _EXTRACT_MARKERS):
        return ResearchStage.EXTRACTING
    if _contains_any(text, _SCRAPE_MARKERS):
        return ResearchStage.SCRAPING
    return None


def apply_progress_stage(job: object, message: str) -> bool:
    """Advance ``job`` when the message names a later stage.

    Returns True when the stage changed. Terminal jobs and regressions are
    ignored by ``advance_stage``.
    """
    inferred = infer_research_stage(message)
    if inferred is None:
        return False
    advance = getattr(job, "advance_stage", None)
    if not callable(advance):
        return False
    return bool(advance(inferred))


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)
