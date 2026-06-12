"""QA iteration loop: refine weak report sections until the grade target.

``primr refine "Company"`` (roadmap Active Queue #10) takes an already-shipped
report, identifies its weakest sections with the deterministic QA scorer,
gathers fresh evidence for them, regenerates them section-by-section, and
repeats until the report grades >= the target (default 90) — or the loop hits
diminishing returns.

The loop follows the four-phase consolidation protocol:

1. **Orient** — read the full report, the analysis workbook, and the source
   appendix; score the report and rank the weakest sections.
2. **Gather** — targeted DDG searches for each weak section's gaps; scrape
   and validate the new sources.
3. **Consolidate** — regenerate the weak sections with the enriched context,
   preserving existing citations and confidence labels.
4. **Prune** — deterministic cleanup (citation normalization, scaffolding
   strip), re-score, and check the stop conditions.

Reading happens before writing (Orient/Gather vs Consolidate/Prune), which
prevents hallucinated improvements that contradict existing content.

All external effects (scoring, evidence gathering, regeneration) are
injectable seams so the loop is fully unit-testable without LLM or network
calls. Final output is written through the agentic write guard (roadmap #11):
the loop may only write the target artifact.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from primr.pipeline.diminishing_returns import (
    DiminishingReturnsDetector,
    SectionImprovement,
)
from primr.utils.logging_config import get_logger
from primr.utils.write_guard import ArtifactWriteGuard

logger = get_logger("core.refine")

DEFAULT_TARGET_GRADE = 90.0
DEFAULT_MAX_ITERATIONS = 3
DEFAULT_MAX_SECTIONS_PER_ITERATION = 3
# Sections below this word count are weak regardless of other signals.
WEAK_WORD_THRESHOLD = 150

# Appendix/meta sections that are never regeneration candidates.
_EXCLUDED_SECTIONS = {
    "sources",
    "references",
    "citations",
    "appendix",
    "table of contents",
}

_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_CITE_RE = re.compile(r"\[cite:\s*\d+\]")
_CONFIDENCE_RE = re.compile(r"\((?:Confirmed|Reported|Estimated|Hypothesis)\)", re.IGNORECASE)


@dataclass(frozen=True)
class WeakSection:
    """A section flagged for regeneration, with the reasons it was flagged."""

    title: str
    word_count: int
    citation_count: int
    confidence_labels: int
    reasons: tuple[str, ...]


@dataclass
class RefineResult:
    """Outcome of one ``refine_report`` invocation."""

    company: str
    report_path: str
    output_path: str | None
    initial_grade: float
    final_grade: float
    iterations: int
    sections_regenerated: list[str] = field(default_factory=list)
    stop_reason: str = ""
    # True when an iteration was reverted because the independent
    # label-traceability audit found degradation (anti-Goodhart guard).
    acceptance_rejected: bool = False

    @property
    def improved(self) -> bool:
        return self.final_grade > self.initial_grade


def split_sections(report_content: str) -> list[tuple[str, str]]:
    """Split a markdown report into (title, body) pairs of top-level sections."""
    sections: list[tuple[str, str]] = []
    matches = list(_SECTION_RE.finditer(report_content))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(report_content)
        sections.append((match.group(1).strip(), report_content[start:end]))
    return sections


def identify_weak_sections(
    report_content: str,
    max_sections: int = DEFAULT_MAX_SECTIONS_PER_ITERATION,
    skip_titles: set[str] | None = None,
) -> list[WeakSection]:
    """Rank the report's weakest sections by deterministic signals.

    A section is weak when it is short (< ``WEAK_WORD_THRESHOLD`` words),
    cites nothing, or carries no confidence labels. Sections are ranked by
    how many signals fire (then by ascending length) and capped at
    ``max_sections`` per iteration so each loop pass stays bounded.
    ``skip_titles`` excludes sections already regenerated in this run —
    re-regenerating the same section every iteration is how loops spin.
    """
    skip = {t.lower() for t in (skip_titles or set())}
    weak: list[WeakSection] = []

    for title, body in split_sections(report_content):
        if title.lower() in _EXCLUDED_SECTIONS or title.lower() in skip:
            continue

        words = len(body.split())
        citations = len(_CITE_RE.findall(body))
        labels = len(_CONFIDENCE_RE.findall(body))

        reasons: list[str] = []
        if words < WEAK_WORD_THRESHOLD:
            reasons.append(f"short ({words} words)")
        if citations == 0:
            reasons.append("no citations")
        if labels == 0:
            reasons.append("no confidence labels")

        if reasons:
            weak.append(
                WeakSection(
                    title=title,
                    word_count=words,
                    citation_count=citations,
                    confidence_labels=labels,
                    reasons=tuple(reasons),
                )
            )

    weak.sort(key=lambda s: (-len(s.reasons), s.word_count))
    return weak[:max_sections]


def extract_source_urls(report_content: str) -> list[str]:
    """Pull the source URLs from the report's Sources/References appendix."""
    appendix_match = re.search(
        r"^##\s+(?:Sources|References|Citations)\s*$", report_content, re.MULTILINE
    )
    haystack = report_content[appendix_match.end() :] if appendix_match else report_content
    urls = re.findall(r"https?://[^\s\)\]>\"']+", haystack)
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        cleaned = url.rstrip(".,;")
        if cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def score_report_content(content: str, filename_hint: str = "Strategic_Overview.md") -> float:
    """Deterministic 0-100 grade for in-memory report content.

    Wraps :meth:`ReportAnalyzer.compute_quality_score` (the same scorer the
    QA scorecard uses) via a temp file named to preserve report-type
    detection.
    """
    from primr.qa.report_analyzer import ReportAnalyzer

    with tempfile.TemporaryDirectory(prefix="primr_refine_") as tmpdir:
        tmp_path = Path(tmpdir) / filename_hint
        tmp_path.write_text(content, encoding="utf-8")
        score, _components = ReportAnalyzer(str(tmp_path)).compute_quality_score()
    return float(score)


def _default_gather(
    company_name: str,
    website: str | None,
    section: WeakSection,
    working_folder: str | None,
) -> str:
    """Gather fresh evidence for one weak section (DDG search + validated scrape)."""
    from primr.data.scrape import scrape_external_sources_validated
    from primr.data.search_utils import search_web

    queries = [f"{company_name} {section.title}"]
    if "no citations" in section.reasons or "no confidence labels" in section.reasons:
        queries.append(f'"{company_name}" {section.title} news analysis')

    evidence_parts: list[str] = []
    for query in queries[:2]:
        try:
            results = search_web(query, company_name, website)
        except Exception as e:
            logger.warning("Refine evidence search failed for %r: %s", query, e)
            continue
        if not results:
            continue
        try:
            scraped = scrape_external_sources_validated(
                results[:3],
                company_name=company_name,
                website=website,
                max_sources=2,
                working_folder=working_folder,
            )
        except Exception as e:
            logger.warning("Refine evidence scrape failed for %r: %s", query, e)
            continue
        for url, content in scraped.items():
            evidence_parts.append(f"[Source: {url}]\n{content[:12_000]}")

    return "\n\n".join(evidence_parts)


def _default_regenerate(
    company_name: str,
    website: str | None,
    section_title: str,
    section_content: str,
    analysis_workbook: str,
    new_evidence: str,
    source_urls: list[str],
) -> str:
    from primr.core.research_agent import _fast_regenerate_section

    return _fast_regenerate_section(
        company_name,
        website,
        section_title,
        section_content,
        analysis_workbook,
        new_evidence,
        source_urls,
    )


def _default_prune(content: str) -> str:
    """Deterministic cleanup between iterations (Prune phase)."""
    from primr.core.research_agent import (
        _clean_fast_report_output,
        _normalize_fast_citations,
    )

    cleaned = _clean_fast_report_output(content)
    return _normalize_fast_citations(cleaned)


def _default_acceptance(
    before_content: str,
    after_content: str,
    regenerated_titles: list[str],
) -> bool:
    """Independent acceptance check: traceability must not degrade (anti-Goodhart).

    The loop's objective function is the artifact-discipline score, which
    counts exactly the tokens the regenerator can insert (citations,
    confidence labels). This check audits the regenerated sections with the
    label-calibration harness — an instrument the discipline score cannot
    see: per-label traceability precision on the rewritten sections must not
    drop below what those sections had before the rewrite. An iteration that
    raised the grade by inserting unsupported labels/citations is rejected
    and reverted.

    Fail-open on harness errors (acceptance must never brick refine), but a
    measured degradation is binding.
    """
    from primr.qa.label_calibration import (
        TRACEABLE_LABELS,
        calibrate_claims,
        extract_labeled_claims,
    )

    titles = set(regenerated_titles)
    try:
        claims_before = [c for c in extract_labeled_claims(before_content) if c.section in titles]
        claims_after = [c for c in extract_labeled_claims(after_content) if c.section in titles]
        if not any(c.label in TRACEABLE_LABELS for c in claims_after):
            # Nothing traceable-class was added — nothing for this audit to
            # judge; the discipline score governs the rest.
            return True

        report_before = calibrate_claims(claims_before)
        report_after = calibrate_claims(claims_after)
        for label in TRACEABLE_LABELS:
            precision_after = report_after.precision(label)
            precision_before = report_before.precision(label)
            if precision_after is None:
                continue
            baseline = precision_before if precision_before is not None else precision_after
            if precision_after < baseline:
                logger.warning(
                    "Refine acceptance rejected: %s traceability dropped %.2f -> %.2f "
                    "on regenerated sections",
                    label,
                    baseline,
                    precision_after,
                )
                return False
        return True
    except Exception as e:
        logger.warning("Refine acceptance check errored (fail-open): %s", e)
        return True


def refine_report(
    company_name: str,
    report_path: str | Path,
    *,
    website: str | None = None,
    working_folder: str | None = None,
    analysis_workbook: str = "",
    target_grade: float = DEFAULT_TARGET_GRADE,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    max_sections_per_iteration: int = DEFAULT_MAX_SECTIONS_PER_ITERATION,
    in_place: bool = False,
    score_fn: Callable[[str], float] | None = None,
    gather_fn: Callable[[str, str | None, WeakSection, str | None], str] | None = None,
    regenerate_fn: Callable[..., str] | None = None,
    prune_fn: Callable[[str], str] | None = None,
    acceptance_fn: Callable[[str, str, list[str]], bool] | None = None,
) -> RefineResult:
    """Run the QA iteration loop on a report and write the refined artifact.

    Stop conditions, in priority order: grade >= ``target_grade``; no weak
    sections left to work on; an iteration rejected by the independent
    acceptance check (label-traceability must not degrade — anti-Goodhart;
    the iteration is reverted); diminishing returns (two consecutive
    iterations each improving the grade by < 5% relative); or
    ``max_iterations``.
    """
    path = Path(report_path)
    content = path.read_text(encoding="utf-8")

    score = score_fn or (lambda c: score_report_content(c, filename_hint=path.name))
    gather = gather_fn or _default_gather
    regenerate = regenerate_fn or _default_regenerate
    prune = prune_fn or _default_prune
    acceptance = acceptance_fn or _default_acceptance

    # --- Orient -----------------------------------------------------------
    initial_grade = score(content)
    grade = initial_grade
    source_urls = extract_source_urls(content)
    regenerated_titles: list[str] = []
    detector = DiminishingReturnsDetector(improvement_threshold=0.05, consecutive_limit=2)
    stop_reason = "max_iterations"
    iterations = 0
    acceptance_rejected = False

    if grade >= target_grade:
        stop_reason = "target_reached"

    while grade < target_grade and iterations < max_iterations:
        weak_sections = identify_weak_sections(
            content,
            max_sections=max_sections_per_iteration,
            skip_titles=set(regenerated_titles),
        )
        if not weak_sections:
            stop_reason = "no_weak_sections"
            break

        iterations += 1
        iteration_start_content = content
        iteration_titles: list[str] = []
        for section in weak_sections:
            # --- Gather ----------------------------------------------------
            evidence = gather(company_name, website, section, working_folder)

            # --- Consolidate -----------------------------------------------
            pattern = re.compile(rf"(## {re.escape(section.title)}\n.*?)(?=\n## |\Z)", re.DOTALL)
            match = pattern.search(content)
            if not match:
                logger.warning("Refine: section %r not found in report", section.title)
                continue
            original = match.group(1)
            regenerated = regenerate(
                company_name,
                website,
                section.title,
                original,
                analysis_workbook,
                evidence,
                source_urls,
            )
            if regenerated and regenerated != original:
                if not regenerated.endswith("\n"):
                    regenerated += "\n"
                content = content[: match.start()] + regenerated + content[match.end() :]
                iteration_titles.append(section.title)

        # --- Prune ----------------------------------------------------------
        content = prune(content)

        # --- Independent acceptance (anti-Goodhart) --------------------------
        # Judged by an instrument the discipline score can't see; a rejected
        # iteration is fully reverted so unsupported labels/citations never
        # ship just because they raised the grade.
        if iteration_titles and not acceptance(iteration_start_content, content, iteration_titles):
            content = iteration_start_content
            stop_reason = "acceptance_rejected"
            acceptance_rejected = True
            break
        regenerated_titles.extend(iteration_titles)

        new_grade = score(content)
        relative_gain = (new_grade - grade) / grade if grade > 0 else 1.0
        detector.record(
            SectionImprovement(
                section_title=f"iteration {iterations}",
                word_delta_ratio=relative_gain,
                new_citations=0,
                score=max(0.0, relative_gain),
            )
        )
        logger.info(
            "Refine iteration %d: grade %.0f -> %.0f (%d section(s) regenerated)",
            iterations,
            grade,
            new_grade,
            len(regenerated_titles),
        )
        grade = new_grade

        if grade >= target_grade:
            stop_reason = "target_reached"
            break
        if detector.should_stop():
            stop_reason = "diminishing_returns"
            break

    # Write the refined artifact through the agentic write guard (#11):
    # this stage may only touch the target artifact.
    output_path: str | None = None
    if regenerated_titles:
        guard = ArtifactWriteGuard(path)
        destination = path if in_place else path.with_name(f"{path.stem}_improved{path.suffix}")
        guard.write_text(destination, content)
        output_path = str(destination)

    return RefineResult(
        company=company_name,
        report_path=str(path),
        output_path=output_path,
        initial_grade=initial_grade,
        final_grade=grade,
        iterations=iterations,
        sections_regenerated=regenerated_titles,
        acceptance_rejected=acceptance_rejected,
        stop_reason=stop_reason,
    )
