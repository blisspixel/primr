"""Final-artifact validation and salvage helpers.

Extracted from `primr.core.research_agent` for isolated unit testing.

This module holds the single source of truth for forbidden internal markers
that must never reach a shipped artifact, plus the scanner / auto-strip /
DOCX text-extractor pair that the pipeline uses to fail closed when the
shipping prep stage leaves residue behind.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

# Configurable ceiling for leaked internal-scaffolding markers in a shipped
# report (bare [workbook] / [cross-ref ...] refs, bold-wrapped "What to
# validate:" lines, informal [cite: label] markers). Default 0 = zero
# tolerance: any leak that survived the upstream canonicalization seam blocks
# the polished DOCX (MD/TXT + a sidecar validation report are still written).
# Operators can relax it via PRIMR_MAX_SCAFFOLDING_LEAKS for a noisy corpus.
_SCAFFOLDING_LEAK_THRESHOLD_ENV = "PRIMR_MAX_SCAFFOLDING_LEAKS"


def _scaffolding_leak_threshold() -> int:
    """Resolve the max tolerated scaffolding-leak count from the environment.

    Defaults to 0 (zero tolerance). A malformed or negative value falls back to
    0 so the gate can never be silently disabled by a bad env value.
    """
    raw = os.environ.get(_SCAFFOLDING_LEAK_THRESHOLD_ENV)
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s=%r; falling back to zero-tolerance (0)",
            _SCAFFOLDING_LEAK_THRESHOLD_ENV,
            raw,
        )
        return 0


def _scan_scaffolding_leakage_issues(markdown_content: str, threshold: int) -> list[str]:
    """Return shipping-gate issue strings when scaffolding leaks exceed threshold.

    Empty list when the leak count is within the configured threshold. The
    detection logic lives in ``primr.qa.report_analyzer.scan_scaffolding_leakage``
    (single source of truth, shared with the QA scorecard).
    """
    from primr.qa.report_analyzer import scan_scaffolding_leakage

    leak = scan_scaffolding_leakage(markdown_content)
    if leak["total_leaked"] <= threshold:
        return []

    issues = [f"scaffolding_leak:total={leak['total_leaked']} (threshold {threshold})"]
    for key, label in (
        ("workbook_markers", "workbook_markers"),
        ("cross_ref_markers", "cross_ref_markers"),
        ("bare_bold_validate", "bold_validate_lines"),
        ("informal_cite_markers", "informal_cite_markers"),
    ):
        if leak[key]:
            issues.append(f"scaffolding_leak:{label}={leak[key]}")
    return issues


# Detection patterns are partial-match (no closing-bracket requirement) so the
# scanner catches truncated tokens the writer accidentally leaves behind.
_FORBIDDEN_OUTPUT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("raw_source_tag", r"\[Source:\s*(?:https?://)?[^\]\s]+"),
    ("section_cross_ref", r"\[\s*(?:see|cross-?ref|xref)\s+##\s+[^\]]+\]"),
    ("workbook_ref", r"\[Workbook:[^\]]*\]"),
    ("workbook_section_ref", r"\[workbook section[^\]]*\]"),
    ("workbook_section_symbol", r"\[Workbook §[^\]]*\]"),
    ("analysis_workbook_ref", r"\[Analysis Workbook[^\]]*\]"),
    ("analysis_ref", r"\[Analysis:[^\]]*\]"),
    ("external_sources_ref", r"\[External Sources\]"),
    ("citation_inventory", r"\[citation inventory[^\]]*\]"),
    ("vendor_research_file", r"vendor-research-[\w.-]+\.txt"),
    ("internal_roi_model", r"\bInternal ROI Model\b"),
    ("internal_analysis", r"\bInternal Analysis\b"),
)

# Cleaner patterns require the full closing-bracket form so substitution
# removes only the well-formed token (not arbitrary trailing text).
_FORBIDDEN_OUTPUT_CLEANERS: tuple[tuple[str, str], ...] = (
    ("raw_source_tag", r"\[Source:[^\]]*\]"),
    ("section_cross_ref", r"\[\s*(?:see|cross-?ref|xref)\s+##\s+[^\]]+\]"),
    ("workbook_ref", r"\[Workbook:[^\]]*\]"),
    ("workbook_section_ref", r"\[workbook section[^\]]*\]"),
    ("workbook_section_symbol", r"\[Workbook §[^\]]*\]"),
    ("analysis_workbook_ref", r"\[Analysis Workbook[^\]]*\]"),
    ("analysis_ref", r"\[Analysis:[^\]]*\]"),
    ("external_sources_ref", r"\[External Sources\]"),
    ("citation_inventory", r"\[citation inventory[^\]]*\]"),
    ("vendor_research_file", r"vendor-research-[\w.-]+\.txt"),
    ("internal_roi_model", r"\bInternal ROI Model\b"),
    ("internal_analysis", r"\bInternal Analysis\b"),
)

# Bare internal terms (no bracket form) that must never leak.
_FORBIDDEN_INTERNAL_TERMS: tuple[str, ...] = (
    "analysis context",
    "vendor-research",
)


class _ArtifactValidation(TypedDict):
    """Result of an artifact validation pass."""

    passed: bool
    issues: list[str]
    errors: list[str]


def _auto_strip_forbidden_patterns(text: str) -> str:
    """Last-resort defensive sweep: strip anything the artifact scanner would flag."""
    if not text.strip():
        return text

    for _label, pattern in _FORBIDDEN_OUTPUT_CLEANERS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    lower = text.lower()
    for term in _FORBIDDEN_INTERNAL_TERMS:
        if term in lower:
            text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)

    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


def _scan_forbidden_output_patterns(text: str) -> list[str]:
    """Return a list of human-readable issue strings, one per detected pattern."""
    issues: list[str] = []
    for label, pattern in _FORBIDDEN_OUTPUT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            issues.append(f"{label}: {match.group(0)[:120]}")

    lower = text.lower()
    for term in _FORBIDDEN_INTERNAL_TERMS:
        if term in lower:
            issues.append(f"internal_term: {term}")

    return issues


def _validate_output_markdown(
    markdown_content: str, *, scaffolding_threshold: int | None = None
) -> _ArtifactValidation:
    """Validate that a markdown artifact contains no forbidden internal markers.

    Two layered checks, both fail-closed:
    - zero-tolerance forbidden-marker scan (raw [Source:], [Workbook:], etc.);
    - a configurable scaffolding-leak gate (bare [workbook]/[cross-ref], bold
      "What to validate:" lines, informal [cite: label]) that blocks shipping
      once the leak count exceeds the threshold (default 0; override via
      ``PRIMR_MAX_SCAFFOLDING_LEAKS``).
    """
    if scaffolding_threshold is None:
        scaffolding_threshold = _scaffolding_leak_threshold()
    try:
        issues = _scan_forbidden_output_patterns(markdown_content)
        issues.extend(_scan_scaffolding_leakage_issues(markdown_content, scaffolding_threshold))
        return {"passed": len(issues) == 0, "issues": issues, "errors": []}
    except Exception as exc:
        # Fail closed: an exception inside the scanner means we could not
        # confirm the artifact is clean. Downstream code writes a sidecar
        # validation report and blocks DOCX shipping when this returns False.
        logger.warning("Markdown artifact validation failed: %s", exc)
        return {"passed": False, "issues": [], "errors": [str(exc)]}


def _extract_docx_text(document: Any) -> str:
    """Flatten a python-docx Document into a single text string."""
    parts: list[str] = []
    for para in document.paragraphs:
        if para.text:
            parts.append(para.text)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    parts.append(cell.text)
    return "\n".join(parts)


def _validate_output_docx(docx_path: Path) -> _ArtifactValidation:
    """Validate that a generated DOCX contains no markdown artifacts or forbidden tokens."""
    try:
        from docx import Document

        from primr.output.markdown_parser import ArtifactDetector

        document = Document(str(docx_path))
        detector = ArtifactDetector()
        artifacts = detector.scan_document(document)
        issues = [
            f"markdown_artifact:{artifact['type']}:{artifact['match']}"
            for artifact in artifacts[:10]
        ]
        issues.extend(_scan_forbidden_output_patterns(_extract_docx_text(document)))
        return {"passed": len(issues) == 0, "issues": issues, "errors": []}
    except Exception as exc:
        # Fail closed — see _validate_output_markdown for the rationale.
        logger.warning("DOCX artifact validation failed: %s", exc)
        return {"passed": False, "issues": [], "errors": [str(exc)]}


def _write_output_validation_report(
    base_path: Path,
    phase: str,
    issues: list[str],
    errors: list[str],
    diagnostics_dir: str | Path | None = None,
) -> Path | None:
    """Write a sidecar text report describing why an artifact failed validation."""
    if not issues and not errors:
        return None

    if diagnostics_dir is not None:
        diagnostics_path = Path(diagnostics_dir)
        diagnostics_path.mkdir(parents=True, exist_ok=True)
        report_path = diagnostics_path / f"{base_path.stem}_{phase}_validation.txt"
    else:
        report_path = base_path.with_name(f"{base_path.stem}_{phase}_validation.txt")
    lines = [f"Artifact validation report ({phase})", ""]
    if issues:
        lines.append("Issues:")
        lines.extend(f"- {item}" for item in issues)
        lines.append("")
    if errors:
        lines.append("Validator errors:")
        lines.extend(f"- {item}" for item in errors)
        lines.append("")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report_path
