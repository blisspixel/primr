"""Final-artifact validation and salvage helpers.

Extracted from `primr.core.research_agent` for isolated unit testing.

This module holds the single source of truth for forbidden internal markers
that must never reach a shipped artifact, plus the scanner / auto-strip /
DOCX text-extractor pair that the pipeline uses to fail closed when the
shipping prep stage leaves residue behind.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


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


def _validate_output_markdown(markdown_content: str) -> _ArtifactValidation:
    """Validate that a markdown artifact contains no forbidden internal markers."""
    try:
        issues = _scan_forbidden_output_patterns(markdown_content)
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
